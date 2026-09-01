import hashlib
import os
import re
import secrets
from collections import Counter
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, Request, Response, UploadFile, File, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pymongo.errors import DuplicateKeyError, PyMongoError
import networkx as nx
from .db import database, indexes, now, public
from .security import passwords, DUMMY_HASH, current_user, digest, access, audit, login_limited
from .models import Credentials, UserCreate, CaseCreate, MemberAdd, Review
from .analysis import training_data

MAX_UPLOAD=10*1024*1024
DISCLAIMER='Unusual behavior is a lead for human review, not proof of wrongdoing. Scores are relative to the imported dataset, not calibrated probabilities. Observed network peers do not establish transaction origin or wallet ownership.'

def case_public(c,user):
    role='admin' if user['role']=='admin' else next((m['role'] for m in c['members'] if m['user_id']==user['_id']),None)
    return {**public(c),'member_role':role}

def completed_scope(case_id):
    ids=[d['_id'] for d in database().datasets.find({'case_id':case_id,'status':'completed'},{'_id':1})]
    return {'case_id':case_id,'dataset_id':{'$in':ids}}

@asynccontextmanager
async def lifespan(app):
    indexes(database())
    yield

app=FastAPI(title='Bitcoin Sentinel AI',version='0.1.0',lifespan=lifespan,docs_url='/api/docs',openapi_url='/api/openapi.json')

@app.middleware('http')
async def safety_headers(request:Request,call_next):
    if request.method in {'POST','PATCH','PUT','DELETE'} and request.url.path.startswith('/api/'):
        if request.headers.get('X-Sentinel-Request')!='1':
            return JSONResponse({'detail':'Missing request verification header.'},403)
        origin=request.headers.get('origin')
        allowed=os.getenv('ALLOWED_ORIGINS','http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000,http://localhost:8080,http://127.0.0.1:8080').split(',')
        if origin and origin not in allowed:
            return JSONResponse({'detail':'Origin not permitted.'},403)
        length=request.headers.get('content-length')
        if length is None:
            return JSONResponse({'detail':'Content-Length is required for uploads and mutations.'},411)
        try:
            if int(length)>MAX_UPLOAD+256*1024:
                return JSONResponse({'detail':'Request exceeds the 10 MB upload limit.'},413)
        except ValueError:
            return JSONResponse({'detail':'Invalid Content-Length.'},400)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='same-origin'
    response.headers['X-Frame-Options']='DENY'
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control']='no-store'
    return response

@app.exception_handler(PyMongoError)
async def db_error(request,exc):
    return JSONResponse({'detail':'Database unavailable. Check the MongoDB connection and retry.'},503)

@app.get('/api/health')
def health():
    database().command('ping')
    return {'status':'ok','database':'mongodb'}

@app.post('/api/auth/login')
def login(body:Credentials,request:Request,response:Response):
    db=database();key=login_limited(body.email,request.client.host if request.client else 'unknown')
    user=db.users.find_one({'email':body.email})
    valid=passwords.verify(body.password,user['password_hash'] if user else DUMMY_HASH)
    if not user or not valid:
        raise HTTPException(401,'Email or password is incorrect.')
    db.login_attempts.delete_one({'_id':key})
    token=secrets.token_urlsafe(32)
    db.sessions.insert_one({'_id':digest(token),'user_id':user['_id'],'expires_at':now()+timedelta(hours=8)})
    response.set_cookie('sentinel_session',token,httponly=True,secure=os.getenv('COOKIE_SECURE','false').lower()=='true',samesite='strict',max_age=8*3600,path='/api')
    audit(user['_id'],None,'sign_in',{})
    return public(user)

@app.get('/api/auth/me')
def me(user=Depends(current_user)):
    return public(user)

@app.post('/api/auth/logout',status_code=204)
def logout(request:Request,response:Response):
    token=request.cookies.get('sentinel_session')
    if token:
        database().sessions.delete_one({'_id':digest(token)})
    response.delete_cookie('sentinel_session',path='/api')

@app.post('/api/users',status_code=201)
def create_user(body:UserCreate,user=Depends(current_user)):
    if user['role']!='admin':
        raise HTTPException(403,'Administrator access required.')
    record={'_id':secrets.token_hex(12),'email':body.email,'name':body.name,'role':body.role,'password_hash':passwords.hash(body.password),'created_at':now()}
    try:
        database().users.insert_one(record)
    except DuplicateKeyError:
        raise HTTPException(409,'A user with this email already exists.')
    audit(user['_id'],None,'user_created',{'user_id':record['_id'],'role':body.role})
    return public(record)

@app.get('/api/cases')
def cases(user=Depends(current_user)):
    query={} if user['role']=='admin' else {'members.user_id':user['_id']}
    return [case_public(c,user) for c in database().cases.find(query).sort('created_at',-1)]

@app.post('/api/cases',status_code=201)
def new_case(body:CaseCreate,user=Depends(current_user)):
    if user['role']=='viewer':
        raise HTTPException(403,'Viewers cannot create cases.')
    c={'_id':secrets.token_hex(12),'name':body.name.strip(),'description':body.description.strip(),'created_at':now(),'members':[{'user_id':user['_id'],'role':'admin'}]}
    if len(c['name'])<3:
        raise HTTPException(422,'Case name must contain at least three non-space characters.')
    database().cases.insert_one(c)
    audit(user['_id'],c['_id'],'case_created',{'name':c['name']})
    return case_public(c,user)

@app.get('/api/cases/{case_id}/members')
def members(case_id:str,user=Depends(current_user)):
    c,_=access(case_id,user)
    result=[]
    for m in c['members']:
        member=database().users.find_one({'_id':m['user_id']})
        if member:
            result.append({**public(member),'case_role':m['role']})
    return result

@app.post('/api/cases/{case_id}/members')
def add_member(case_id:str,body:MemberAdd,user=Depends(current_user)):
    c,_=access(case_id,user,admin=True)
    member=database().users.find_one({'email':body.email.strip().lower()})
    if not member:
        raise HTTPException(404,'Create this workspace user before granting case access.')
    existing=next((m for m in c['members'] if m['user_id']==member['_id']),None)
    if existing and existing['role']=='admin':
        raise HTTPException(400,'Cannot change the case owner through this action.')
    if member['role']=='viewer' and body.role!='viewer':
        raise HTTPException(400,'Workspace viewers can only receive viewer access.')
    if existing:
        database().cases.update_one({'_id':case_id,'members.user_id':member['_id']},{'$set':{'members.$.role':body.role}})
    else:
        database().cases.update_one({'_id':case_id},{'$addToSet':{'members':{'user_id':member['_id'],'role':body.role}}})
    audit(user['_id'],case_id,'membership_updated',{'member_id':member['_id'],'role':body.role})
    return {'ok':True}

def enqueue(case_id,user,filename,content,synthetic=False):
    db=database();sha=hashlib.sha256(content).hexdigest();did=secrets.token_hex(12)
    d={'_id':did,'case_id':case_id,'name':Path(filename).name[:160],'sha256':sha,'status':'queued','count':0,'progress':0,'created_at':now(),'uploaded_by':user['_id'],'synthetic':synthetic,'warnings':[]}
    # Save the payload before publishing the queue entry, so workers cannot claim an incomplete upload.
    db.uploads.insert_one({'_id':did,'case_id':case_id,'content':content})
    try:
        db.datasets.insert_one(d)
    except DuplicateKeyError:
        db.uploads.delete_one({'_id':did})
        raise HTTPException(409,'This file has already been imported into this case.')
    except Exception:
        db.uploads.delete_one({'_id':did})
        raise
    audit(user['_id'],case_id,'dataset_queued',{'dataset_id':did,'sha256':sha})
    return public(d)

@app.post('/api/cases/{case_id}/datasets',status_code=202)
async def upload(case_id:str,file:UploadFile=File(...),user=Depends(current_user)):
    access(case_id,user,write=True)
    filename=file.filename or ''
    if not filename.lower().endswith(('.json','.csv','.xml')):
        raise HTTPException(400,'Choose a CSV, JSON, or XML file.')
    content=await file.read(MAX_UPLOAD+1)
    await file.close()
    if not content or len(content)>MAX_UPLOAD:
        raise HTTPException(413,'Upload a non-empty file no larger than 10 MB.')
    # Disk/network DB calls belong on the thread pool, not the async event loop.
    from starlette.concurrency import run_in_threadpool
    return await run_in_threadpool(enqueue,case_id,user,filename,content)

@app.post('/api/cases/{case_id}/demo',status_code=202)
def seed(case_id:str,user=Depends(current_user)):
    access(case_id,user,write=True)
    return enqueue(case_id,user,'synthetic-training.json',training_data(),True)

@app.get('/api/cases/{case_id}/datasets')
def datasets(case_id:str,user=Depends(current_user)):
    access(case_id,user)
    return [public(d) for d in database().datasets.find({'case_id':case_id}).sort('created_at',-1)]

@app.get('/api/cases/{case_id}/transactions')
def transactions(case_id:str,q:str=Query('',max_length=200),offset:int=Query(0,ge=0),user=Depends(current_user)):
    access(case_id,user);query=completed_scope(case_id)
    if q:
        pattern=re.escape(q)
        query['$or']=[{'txid':{'$regex':pattern}},{'outputs.address':{'$regex':pattern}}]
    db=database()
    return {'items':[public(t) for t in db.transactions.find(query).sort('txid',1).skip(offset).limit(25)],'total':db.transactions.count_documents(query)}

@app.get('/api/cases/{case_id}/alerts')
def alerts(case_id:str,user=Depends(current_user)):
    access(case_id,user)
    return [public(a) for a in database().alerts.find(completed_scope(case_id)).sort([('severity',1),('score',-1)]).limit(1000)]

@app.patch('/api/cases/{case_id}/alerts/{alert_id}')
def update_alert(case_id:str,alert_id:str,body:Review,user=Depends(current_user)):
    access(case_id,user,write=True)
    query={**completed_scope(case_id),'_id':alert_id}
    result=database().alerts.update_one(query,{'$set':{'status':body.status,'reviewed_by':user['_id'],'reviewed_at':now()}})
    if not result.matched_count:
        raise HTTPException(404,'Alert not found.')
    audit(user['_id'],case_id,'alert_reviewed',{'alert_id':alert_id,'status':body.status})
    return public(database().alerts.find_one(query))

@app.get('/api/cases/{case_id}/summary')
def summary(case_id:str,user=Depends(current_user)):
    access(case_id,user);db=database();query=completed_scope(case_id)
    count=db.transactions.count_documents(query)
    # Bounded MVP: at most 100k records per summary scan, report the limitation explicitly.
    if count>100000:
        raise HTTPException(422,'This MVP supports summary analysis of up to 100,000 transactions per case.')
    total=0;times=[]
    for t in db.transactions.find(query,{'outputs.value_sats':1,'observed_at':1,'block_time':1}):
        total+=sum(o['value_sats'] for o in t['outputs'])
        timestamp=t.get('observed_at') or t.get('block_time')
        if timestamp:
            times.append(timestamp)
    if times:
        hourly=(max(times)-min(times))<=timedelta(hours=24)
        counter=Counter(t.strftime('%H:00' if hourly else '%Y-%m-%d') for t in times)
        chart=[{'label':k,'count':v} for k,v in sorted(counter.items())]
    else:
        chart=[]
    return {'transactions':count,'total_output_sats':total,'alerts_count':db.alerts.count_documents(query),
            'high_priority':db.alerts.count_documents({**query,'severity':'high'}),'chart':chart,
            'alerts':alerts(case_id,user),'datasets':datasets(case_id,user)}

@app.get('/api/cases/{case_id}/graph/{txid}')
def graph(case_id:str,txid:str,user=Depends(current_user)):
    access(case_id,user);db=database();query=completed_scope(case_id)
    if not re.fullmatch('[0-9a-f]{64}',txid):
        raise HTTPException(422,'Enter a 64-character hexadecimal transaction ID.')
    root=db.transactions.find_one({**query,'txid':txid})
    if not root:
        raise HTTPException(404,'Transaction not found in completed datasets for this case.')
    chosen={txid:root};frontier=[root];truncated=False
    for depth in range(2):
        nxt=[]
        for t in frontier:
            refs=[i['prev_txid'] for i in t['inputs']]
            candidates=db.transactions.find({**query,'$or':[{'txid':{'$in':refs}},{'inputs.prev_txid':t['txid']}]}).limit(26)
            for candidate in candidates:
                if candidate['txid'] in chosen:
                    continue
                if len(chosen)>=25:
                    truncated=True;break
                chosen[candidate['txid']]=candidate;nxt.append(candidate)
        frontier=nxt
    graph=nx.DiGraph()
    for t in chosen.values():
        graph.add_node(t['txid'],kind='transaction',label=t['txid'][:7]+'…',focus=t['txid']==txid)
    # Keep connecting outputs even when visual output limits hide unrelated outputs.
    required={(i['prev_txid'],i['prev_vout']) for t in chosen.values() for i in t['inputs']}
    for t in chosen.values():
        shown=[o for o in t['outputs'] if (t['txid'],o['index']) in required]
        shown.extend(o for o in t['outputs'][:8] if o not in shown)
        if len(shown)<len(t['outputs']):truncated=True
        for o in shown:
            oid=f'{t["txid"]}:{o["index"]}'
            graph.add_node(oid,kind='output',label=f'{o["value_sats"]/1e8:.5g} BTC',focus=False)
            graph.add_edge(t['txid'],oid,label='creates')
    for t in chosen.values():
        for i in t['inputs']:
            oid=f'{i["prev_txid"]}:{i["prev_vout"]}'
            if oid in graph:
                graph.add_edge(oid,t['txid'],label='spent by')
    return {'nodes':[{'data':{'id':n,**attrs}} for n,attrs in graph.nodes(data=True)],
            'edges':[{'data':{'id':f'{a}>{b}','source':a,'target':b,**attrs}} for a,b,attrs in graph.edges(data=True)],
            'truncated':truncated,'network_observations':[public(o) for o in db.observations.find({**query,'txid':txid}).limit(50)],
            'disclaimer':DISCLAIMER}

@app.get('/api/cases/{case_id}/report')
def report(case_id:str,user=Depends(current_user)):
    c,_=access(case_id,user);query=completed_scope(case_id);db=database()
    audit(user['_id'],case_id,'report_exported',{})
    signal_records=list(db.alerts.find(query).sort('score',-1).limit(1000))
    ids=list({a['txid'] for a in signal_records})
    evidence=[public(t) for t in db.transactions.find({**query,'txid':{'$in':ids}})]
    return {'schema_version':'1.1','exported_at':now(),'case':public(c),'disclaimer':DISCLAIMER,
            'datasets':datasets(case_id,user),'alerts':[public(a) for a in signal_records],
            'transactions':evidence,'features':[public(f) for f in db.features.find({**query,'txid':{'$in':ids}})],
            'network_observations':[public(o) for o in db.observations.find({**query,'txid':{'$in':ids}}).limit(1000)],
            'audit':[public(a) for a in db.audit.find({'case_id':case_id}).sort('created_at',-1).limit(200)],
            'limits':{'max_alerts':1000,'max_audit_entries':200,'max_observations':1000,'alerts_truncated':db.alerts.count_documents(query)>1000}}

from .investigation import router as investigation_router
app.include_router(investigation_router)

static=Path(os.getenv('FRONTEND_DIST',str(Path(__file__).resolve().parents[2]/'frontend'/'dist')))
if static.exists():
    app.mount('/',StaticFiles(directory=str(static),html=True),name='frontend')
