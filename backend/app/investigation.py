"""Case-scoped search, transaction evidence, and chronological investigation events."""
import re
from datetime import datetime, timezone
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator, model_validator
from .db import database, public
from .security import access, current_user

router=APIRouter(prefix='/api/cases')
STAGES={'validation','feature_engineering','rule_detection','model_scoring','alert_generation'}

def scope(case_id):
    ids=[d['_id'] for d in database().datasets.find({'case_id':case_id,'status':'completed'},{'_id':1})]
    return {'case_id':case_id,'dataset_id':{'$in':ids}}

class Filters(BaseModel):
    q:str=Field(default='',max_length=200)
    dataset_id:str=Field(default='',max_length=100)
    date_from:datetime|None=None
    date_to:datetime|None=None
    time_basis:Literal['observed_at','block_time']='observed_at'
    min_sats:int|None=Field(default=None,ge=0,le=2100000000000000)
    max_sats:int|None=Field(default=None,ge=0,le=2100000000000000)
    min_fee_rate:float|None=Field(default=None,ge=0,allow_inf_nan=False)
    max_fee_rate:float|None=Field(default=None,ge=0,allow_inf_nan=False)
    min_inputs:int|None=Field(default=None,ge=0,le=2147483647)
    max_inputs:int|None=Field(default=None,ge=0,le=2147483647)
    min_outputs:int|None=Field(default=None,ge=0,le=2147483647)
    max_outputs:int|None=Field(default=None,ge=0,le=2147483647)
    confirmation:Literal['all','confirmed','unconfirmed','unknown']='all'
    script_type:str=Field(default='',max_length=80)
    alert_state:Literal['all','flagged','unflagged']='all'
    sort:Literal['txid','value_desc','fee_desc','time_desc']='txid'
    offset:int=Field(default=0,ge=0,le=1000000000)
    limit:int=Field(default=25,ge=1,le=100)
    @field_validator('date_from','date_to')
    @classmethod
    def aware(cls,v):
        if v is not None and v.tzinfo is None:raise ValueError('Date filters require a timezone.')
        return v
    @model_validator(mode='after')
    def ordered(self):
        for low,high in [('date_from','date_to'),('min_sats','max_sats'),('min_fee_rate','max_fee_rate'),('min_inputs','max_inputs'),('min_outputs','max_outputs')]:
            a,b=getattr(self,low),getattr(self,high)
            if a is not None and b is not None and a>b:raise ValueError(f'{low} must not exceed {high}.')
        return self

class AlertFilters(Filters):
    severity:Literal['all','high','medium']='all'
    status:Literal['all','open','reviewed']='all'
    stage:Literal['all','rule_detection','model_scoring','unknown']='all'
    min_score:float|None=Field(default=None,ge=0,le=100,allow_inf_nan=False)

DERIVED={'output_total_sats':{'$sum':'$outputs.value_sats'},'input_count':{'$size':'$inputs'},'output_count':{'$size':'$outputs'},
         'fee_rate_sat_vb':{'$cond':[{'$and':[{'$gte':[{'$ifNull':['$fee_sats',-1]},0]},{'$gt':[{'$ifNull':['$vsize',0]},0]}]},{'$divide':['$fee_sats','$vsize']},None]}}

def tx_pipeline(case_id,f):
    match={}
    if f.q:
        pattern=re.escape(f.q);match['$or']=[{'txid':{'$regex':pattern,'$options':'i'}},{'outputs.address':{'$regex':pattern,'$options':'i'}}]
    if f.dataset_id:match['dataset_id']=f.dataset_id
    for name,lo,hi in [(f.time_basis,f.date_from,f.date_to),('output_total_sats',f.min_sats,f.max_sats),('fee_rate_sat_vb',f.min_fee_rate,f.max_fee_rate),('input_count',f.min_inputs,f.max_inputs),('output_count',f.min_outputs,f.max_outputs)]:
        if lo is not None or hi is not None:
            match[name]={'$ne':None}
            if lo is not None:match[name]['$gte']=lo
            if hi is not None:match[name]['$lte']=hi
    if f.confirmation!='all':match['confirmed']={'confirmed':True,'unconfirmed':False,'unknown':None}[f.confirmation]
    if f.script_type:match['outputs.script_type']=f.script_type
    if f.alert_state!='all':
        ids=database().alerts.distinct('txid',scope(case_id))
        match['txid']={'$in' if f.alert_state=='flagged' else '$nin':ids}
    return [{'$match':scope(case_id)},{'$addFields':DERIVED},{'$match':match}]

@router.get('/{case_id}/transaction-search')
def search_transactions(case_id:str,f:Annotated[Filters,Query()],user=Depends(current_user)):
    access(case_id,user)
    order={'txid':{'txid':1},'value_desc':{'output_total_sats':-1,'txid':1},'fee_desc':{'fee_rate_sat_vb':-1,'txid':1},'time_desc':{f.time_basis:-1,'txid':1}}[f.sort]
    pipeline=tx_pipeline(case_id,f)+[{'$sort':order},{'$facet':{'items':[{'$skip':f.offset},{'$limit':f.limit}],'count':[{'$count':'total'}]}}]
    result=list(database().transactions.aggregate(pipeline))[0]
    return {'items':[public(t) for t in result['items']],'total':result['count'][0]['total'] if result['count'] else 0}

@router.get('/{case_id}/alert-search')
def search_alerts(case_id:str,f:Annotated[AlertFilters,Query()],user=Depends(current_user)):
    access(case_id,user)
    txfilters=Filters.model_validate({**f.model_dump(),'q':''})
    ids=[t['txid'] for t in database().transactions.aggregate(tx_pipeline(case_id,txfilters)+[{'$project':{'txid':1}}])]
    query={**scope(case_id),'txid':{'$in':ids}}
    if f.q:
        pattern=re.escape(f.q);query['$or']=[{k:{'$regex':pattern,'$options':'i'}} for k in ['title','txid','reasons']]
    if f.severity!='all':query['severity']=f.severity
    if f.status!='all':query['status']=f.status
    if f.stage=='unknown':query['first_detected_stage']={'$exists':False}
    elif f.stage!='all':query['detection_stages']=f.stage
    if f.min_score is not None:
        query['score']={'$gte':f.min_score};query['model_version']={'$not':{'$regex':'^rules-only'}}
    col=database().alerts
    return {'items':[public(a) for a in col.find(query).sort([('severity',1),('score',-1),('_id',1)]).skip(f.offset).limit(f.limit)],'total':col.count_documents(query)}

@router.get('/{case_id}/transaction-details/{txid}')
def transaction_details(case_id:str,txid:str,user=Depends(current_user)):
    access(case_id,user);db=database();base=scope(case_id)
    t=db.transactions.find_one({**base,'txid':txid})
    if not t:raise HTTPException(404,'Transaction not found in completed datasets for this case.')
    previous={x['txid']:x for x in db.transactions.find({**base,'txid':{'$in':list({i['prev_txid'] for i in t['inputs']})}})}
    inputs=[]
    for i in t['inputs']:
        parent=previous.get(i['prev_txid'])
        output=next((o for o in parent['outputs'] if o['index']==i['prev_vout']),None) if parent else None
        inputs.append({**i,'previous_output':output,'resolved':output is not None})
    spenders=list(db.transactions.find({**base,'inputs.prev_txid':txid},{'txid':1,'inputs':1}).limit(1001))
    outputs=[{**o,'spending_txids':[s['txid'] for s in spenders[:1000] if any(i['prev_txid']==txid and i['prev_vout']==o['index'] for i in s['inputs'])]} for o in t['outputs']]
    known=bool(inputs) and all(i['resolved'] for i in inputs)
    return {'transaction':public(t),'inputs':inputs,'outputs':outputs,
        'dataset':public(db.datasets.find_one({'_id':t['dataset_id'],'case_id':case_id})),
        'alerts':[public(a) for a in db.alerts.find({**base,'txid':txid})],
        'features':[public(a) for a in db.features.find({**base,'txid':txid})],
        'observations':[public(a) for a in db.observations.find({**base,'txid':txid}).limit(100)],
        'metrics':{'output_total_sats':sum(o['value_sats'] for o in outputs),
            'resolved_input_count':sum(i['resolved'] for i in inputs),
            'input_total_sats':sum(i['previous_output']['value_sats'] for i in inputs) if known else None,
            'fee_rate_sat_vb':t['fee_sats']/t['vsize'] if t.get('fee_sats') is not None and t.get('vsize') else None},
        'spenders_truncated':len(spenders)>1000}

class TimelineFilters(BaseModel):
    q:str=Field(default='',max_length=200)
    dataset_id:str=Field(default='',max_length=100)
    event_type:Literal['all','observation','block','network','pipeline','detection','audit']='all'
    stage:Literal['all','validation','feature_engineering','rule_detection','model_scoring','alert_generation']='all'
    date_from:datetime|None=None
    date_to:datetime|None=None
    offset:int=Field(default=0,ge=0,le=1000000000)
    limit:int=Field(default=50,ge=1,le=100)
    @model_validator(mode='after')
    def valid_dates(self):
        for v in [self.date_from,self.date_to]:
            if v and v.tzinfo is None:raise ValueError('Timeline dates require a timezone.')
        if self.date_from and self.date_to and self.date_from>self.date_to:raise ValueError('Start date must precede end date.')
        return self

@router.get('/{case_id}/timeline')
def timeline(case_id:str,f:Annotated[TimelineFilters,Query()],user=Depends(current_user)):
    access(case_id,user);db=database();base=scope(case_id);events=[];limited=False
    def add(e):
        at=e.get('at')
        if not at:return
        if f.event_type!='all' and e['type']!=f.event_type:return
        if f.stage!='all' and e.get('stage')!=f.stage:return
        if f.dataset_id and e.get('dataset_id')!=f.dataset_id:return
        if f.date_from and at<f.date_from:return
        if f.date_to and at>f.date_to:return
        if f.q and f.q.lower() not in ((e.get('title') or '')+' '+(e.get('txid') or '')+' '+str(e.get('detail',''))).lower():return
        events.append(e)
    def bounded(cursor):
        nonlocal limited
        for n,record in enumerate(cursor.limit(20001)):
            if n==20000:limited=True;break
            yield record
    if f.event_type in {'all','observation','block'}:
        for t in bounded(db.transactions.find(base,{'txid':1,'observed_at':1,'block_time':1,'dataset_id':1,'source_record':1}).sort('txid',1)):
            for field,kind,title in [('observed_at','observation','Transaction observed'),('block_time','block','Reported block time')]:
                add({'id':f'{t["_id"]}:{kind}','type':kind,'title':title,'at':t.get(field),'txid':t['txid'],'dataset_id':t['dataset_id'],'detail':{'source_record':t.get('source_record'),'time_basis':field}})
    if f.event_type in {'all','network'}:
        for o in bounded(db.observations.find(base).sort('observed_at',-1)):
            add({'id':o['_id'],'type':'network','title':'Peer relay observed — origin unknown','at':o['observed_at'],'txid':o['txid'],'dataset_id':o['dataset_id'],'detail':{'sensor':o['sensor'],'peer_ip':o['peer_ip'],'peer_port':o['peer_port']}})
    if f.event_type in {'all','pipeline'}:
        for d in bounded(db.datasets.find({'case_id':case_id}).sort('created_at',-1)):
            add({'id':d['_id']+':queued','type':'pipeline','title':'Dataset queued','at':d['created_at'],'dataset_id':d['_id'],'detail':{'filename':d['name']}})
            for e in d.get('stage_events',[]):
                add({'id':e['id'],'type':'pipeline','title':e['stage'].replace('_',' ').title()+' · '+e['status'],'stage':e['stage'],'at':e['at'],'dataset_id':d['_id'],'detail':{**e['detail'],'status':e['status'],'filename':d['name']}})
    if f.event_type in {'all','detection'}:
        for a in bounded(db.alerts.find(base).sort('created_at',-1)):
            # Legacy alerts did not capture detection time. Do not substitute transaction time.
            for index,d in enumerate(a.get('detections',[])):
                add({'id':f'{a["_id"]}:{index}','type':'detection','title':d['title'],'at':d.get('detected_at'),'stage':d['stage'],'txid':a['txid'],'alert_id':a['_id'],'dataset_id':a['dataset_id'],'detail':{'reason':d['reason'],'observed':d['observed'],'threshold':d['threshold'],'detector':d['detector']}})
    if f.event_type in {'all','audit'}:
        actors={u['_id']:u['name'] for u in db.users.find({},{'name':1})}
        for a in bounded(db.audit.find({'case_id':case_id}).sort('created_at',-1)):
            detail=a.get('detail',{});did=detail.get('dataset_id');txid=None
            if detail.get('alert_id'):
                alert=db.alerts.find_one({**base,'_id':detail['alert_id']})
                if alert:did=alert['dataset_id'];txid=alert['txid']
            add({'id':a['_id'],'type':'audit','title':a['action'].replace('_',' ').title(),'at':a['created_at'],'dataset_id':did,'txid':txid,'detail':{**detail,'actor':actors.get(a['user_id'],'System')}})
    events.sort(key=lambda e:(e['at'],e['id']),reverse=True)
    return {'items':events[f.offset:f.offset+f.limit],'total':len(events),'source_limit_reached':limited,
            'legacy_alerts_without_detection_time':db.alerts.count_documents({**base,'detected_at':{'$exists':False}})}

@router.get('/{case_id}/alert-details/{alert_id}')
def alert_details(case_id:str,alert_id:str,user=Depends(current_user)):
    access(case_id,user)
    alert=database().alerts.find_one({**scope(case_id),'_id':alert_id})
    if not alert:raise HTTPException(404,'Alert not found in this case.')
    return public(alert)
