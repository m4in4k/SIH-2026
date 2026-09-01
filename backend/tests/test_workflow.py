import json
import os
import secrets
from datetime import timedelta
import mongomock
import pytest
from fastapi.testclient import TestClient
from app import db
from app.main import app
from app.security import passwords,digest
from app.worker import tick
from app.analysis import parse,analyze,training_data

@pytest.fixture
def client():
    real_uri=os.getenv('SENTINEL_TEST_MONGO_URI')
    real_client=None
    if real_uri:
        from pymongo import MongoClient
        real_client=MongoClient(real_uri,tz_aware=True)
        db._test_db=real_client['sentinel_test_'+secrets.token_hex(8)]
    else:
        db._test_db=mongomock.MongoClient(tz_aware=True).sentinel_test
    with TestClient(app) as c:
        c.headers['X-Sentinel-Request']='1'
        yield c
    if real_client is not None:
        real_client.drop_database(db._test_db.name)
        real_client.close()
    db._test_db=None

def account(client,email='admin@example.org',role='admin',login=True):
    uid=secrets.token_hex(12)
    db.database().users.insert_one({'_id':uid,'email':email,'name':email.split('@')[0],'role':role,'password_hash':passwords.hash('Strong-test-password-123'),'created_at':db.now()})
    if login:
        r=client.post('/api/auth/login',json={'email':email,'password':'Strong-test-password-123'})
        assert r.status_code==200,r.text
    return uid

def case(client,name='Training investigation'):
    r=client.post('/api/cases',json={'name':name,'description':'Test case'})
    assert r.status_code==201,r.text
    return r.json()['id']

def test_complete_import_analysis_review_export(client):
    account(client);cid=case(client)
    r=client.post(f'/api/cases/{cid}/demo');assert r.status_code==202,r.text
    assert client.get(f'/api/cases/{cid}/summary').json()['transactions']==0
    assert tick()
    dataset=client.get(f'/api/cases/{cid}/datasets').json()[0]
    assert dataset['status']=='completed',dataset
    assert dataset['count']==180
    summary=client.get(f'/api/cases/{cid}/summary').json()
    assert summary['transactions']==180 and summary['high_priority']>=4
    alerts=client.get(f'/api/cases/{cid}/alerts').json();assert alerts
    alert=alerts[0]
    graph=client.get(f'/api/cases/{cid}/graph/{alert["txid"]}').json()
    ids={n['data']['id'] for n in graph['nodes']}
    assert alert['txid'] in ids
    assert all(e['data']['source'] in ids and e['data']['target'] in ids for e in graph['edges'])
    review=client.patch(f'/api/cases/{cid}/alerts/{alert["id"]}',json={'status':'reviewed'})
    assert review.status_code==200 and review.json()['status']=='reviewed'
    report=client.get(f'/api/cases/{cid}/report').json()
    assert report['transactions'] and report['features'] and report['datasets'][0]['sha256']
    assert any(e['action']=='alert_reviewed' for e in report['audit'])
    assert client.post(f'/api/cases/{cid}/demo').status_code==409
    assert db.database().uploads.count_documents({})==1

def test_auth_case_isolation_and_viewer_permissions(client):
    account(client);cid=case(client)
    viewer=account(client,'viewer@example.org','viewer',False)
    outsider=account(client,'other@example.org','analyst',False)
    assert client.post(f'/api/cases/{cid}/members',json={'email':'viewer@example.org','role':'viewer'}).status_code==200
    client.post('/api/auth/logout')
    assert client.get(f'/api/cases/{cid}/summary').status_code==401
    client.post('/api/auth/login',json={'email':'other@example.org','password':'Strong-test-password-123'})
    assert client.get('/api/cases').json()==[]
    for path in ['summary','datasets','alerts','transactions','members','report']:
        assert client.get(f'/api/cases/{cid}/{path}').status_code==404
    assert client.post(f'/api/cases/{cid}/demo').status_code==404
    client.post('/api/auth/login',json={'email':'viewer@example.org','password':'Strong-test-password-123'})
    assert client.get(f'/api/cases/{cid}/summary').status_code==200
    assert client.post(f'/api/cases/{cid}/demo').status_code==403
    assert client.post('/api/cases',json={'name':'Forbidden case'}).status_code==403
    assert client.patch(f'/api/cases/{cid}/alerts/anything',json={'status':'reviewed'}).status_code==403
    assert client.post('/api/users',json={'email':'new@example.org','password':'another-long-password','name':'Other'}).status_code==403

def test_malformed_upload_fails_without_visible_partial_data(client):
    account(client);cid=case(client)
    payload=json.loads(training_data());payload['transactions'][3]['outputs'][0]['value_sats']=0.1
    r=client.post(f'/api/cases/{cid}/datasets',files={'file':('invalid.json',json.dumps(payload),'application/json')})
    assert r.status_code==202
    tick()
    d=client.get(f'/api/cases/{cid}/datasets').json()[0]
    assert d['status']=='failed' and 'Record 4' in d['error']
    assert client.get(f'/api/cases/{cid}/summary').json()['transactions']==0
    assert client.post(f'/api/cases/{cid}/datasets',files={'file':('bad.exe',b'abc')}).status_code==400
    assert client.post(f'/api/cases/{cid}/datasets',files={'file':('empty.json',b'')}).status_code==413

def test_expired_sessions_csrf_and_logout(client):
    account(client)
    assert client.post('/api/cases',json={'name':'Bad origin'},headers={'Origin':'https://evil.example'}).status_code==403
    assert client.post('/api/cases',json={'name':'Bad header'},headers={'X-Sentinel-Request':'0'}).status_code==403
    db.database().sessions.update_many({}, {'$set':{'expires_at':db.now()-timedelta(seconds=1)}})
    assert client.get('/api/auth/me').status_code==401
    client.post('/api/auth/login',json={'email':'admin@example.org','password':'Strong-test-password-123'})
    r=client.post('/api/auth/logout');assert r.status_code==204
    assert client.get('/api/auth/me').status_code==401

def test_login_throttling(client):
    account(client,login=False)
    for _ in range(8):
        assert client.post('/api/auth/login',json={'email':'admin@example.org','password':'wrong'}).status_code==401
    assert client.post('/api/auth/login',json={'email':'admin@example.org','password':'wrong'}).status_code==429

def test_duplicate_record_provenance(client):
    account(client);cid=case(client)
    tx=json.loads(training_data())['transactions'][0]
    r=client.post(f'/api/cases/{cid}/datasets',files={'file':('dupes.json',json.dumps([tx,tx]),'application/json')})
    assert r.status_code==202;tick()
    data=client.get(f'/api/cases/{cid}/datasets').json()[0]
    assert data['count']==1 and 'duplicate' in data['warnings'][0]
    record=client.get(f'/api/cases/{cid}/transactions').json()['items'][0]
    assert record['source_record']==1

def test_uniform_data_is_not_all_anomalous():
    rows,_,_=parse(training_data(),'test.json')
    uniform=[{**rows[0],'txid':f'{i:064x}'} for i in range(50)]
    alerts,features=analyze(uniform)
    assert not alerts
    assert all(f['score']==50 for f in features)

def test_csv_xml_and_xml_entity_rejection():
    import csv,io
    row=json.loads(training_data())['transactions'][0]
    out=io.StringIO();w=csv.DictWriter(out,fieldnames=row.keys());w.writeheader();w.writerow({**row,'inputs':json.dumps(row['inputs']),'outputs':json.dumps(row['outputs'])})
    parsed,_,_=parse(out.getvalue().encode(),'sample.csv');assert parsed[0]['txid']==row['txid']
    xml=f'<transactions><transaction><txid>{row["txid"]}</txid><outputs><output index="0" value_sats="100"/></outputs></transaction></transactions>'
    parsed,_,_=parse(xml.encode(),'sample.xml');assert parsed[0]['outputs'][0]['value_sats']==100
    with pytest.raises(Exception):
        parse(b'<!DOCTYPE x [<!ENTITY secret SYSTEM "file:///etc/passwd">]><transactions>&secret;</transactions>','evil.xml')

def test_rich_transaction_detail_and_combined_filters(client):
    account(client);cid=case(client)
    client.post(f'/api/cases/{cid}/demo');tick()
    r=client.get(f'/api/cases/{cid}/transaction-search',params={'min_outputs':10,'confirmation':'confirmed','script_type':'p2wpkh','min_sats':1,'sort':'value_desc'})
    assert r.status_code==200,r.text
    results=r.json();assert results['total']==4
    values=[t['output_total_sats'] for t in results['items']]
    assert values==sorted(values,reverse=True)
    tx=results['items'][0]
    detail=client.get(f'/api/cases/{cid}/transaction-details/{tx["txid"]}').json()
    assert detail['transaction']['confirmed'] is True
    assert detail['transaction']['confirmations']==3
    assert detail['transaction']['version']==2
    assert detail['metrics']['resolved_input_count']==1
    assert detail['inputs'][0]['previous_output']
    assert detail['dataset']['sha256']
    assert detail['alerts'][0]['detections'][0]['threshold']==10
    assert len(detail['dataset']['stage_events'])==10
    assert client.get(f'/api/cases/{cid}/transaction-search',params={'min_sats':100,'max_sats':1}).status_code==422
    assert client.get(f'/api/cases/{cid}/transaction-search',params={'min_fee_rate':'NaN'}).status_code==422
    assert client.get(f'/api/cases/{cid}/transaction-search',params={'date_from':'2026-08-31T00:00:00'}).status_code==422


def test_filter_dates_missing_fields_and_pagination(client):
    account(client);cid=case(client)
    rows=json.loads(training_data())['transactions'][:50]
    rows[0].update(observed_at=None,block_time=None,confirmed=None,fee_sats=None)
    client.post(f'/api/cases/{cid}/datasets',files={'file':('metadata.json',json.dumps(rows),'application/json')});tick()
    base=f'/api/cases/{cid}/transaction-search'
    assert client.get(base,params={'confirmation':'unknown'}).json()['total']==1
    assert client.get(base,params={'min_fee_rate':0}).json()['total']==49
    q={'date_from':rows[1]['observed_at'],'date_to':rows[2]['observed_at'],'time_basis':'observed_at'}
    assert client.get(base,params=q).json()['total']==2
    first=client.get(base,params={'limit':10}).json();second=client.get(base,params={'limit':10,'offset':10}).json()
    assert first['total']==50 and len(first['items'])==10
    assert not ({t['txid'] for t in first['items']}&{t['txid'] for t in second['items']})
    flagged=client.get(base,params={'alert_state':'flagged'}).json()['total']
    unflagged=client.get(base,params={'alert_state':'unflagged'}).json()['total']
    assert flagged+unflagged==50
    assert client.get(base,params={'q':'.*'}).json()['total']==0


def test_detection_stage_timestamps_timeline_and_export(client):
    account(client);cid=case(client)
    started=db.now()
    client.post(f'/api/cases/{cid}/demo');tick()
    r=client.get(f'/api/cases/{cid}/alert-search',params={'stage':'rule_detection','severity':'high'})
    assert r.status_code==200,r.text
    alerts=r.json()['items'];assert len(alerts)==4
    a=alerts[0]
    from datetime import datetime
    detected=datetime.fromisoformat(a['detected_at'].replace('Z','+00:00'))
    assert detected>=started
    assert a['transaction_observed_at']!=a['detected_at']
    assert a['first_detected_stage']=='rule_detection'
    assert all(d['observed']>=d['threshold'] for d in a['detections'])
    response=client.get(f'/api/cases/{cid}/timeline',params={'event_type':'detection','stage':'rule_detection'})
    assert response.status_code==200,response.text
    timeline=response.json()
    assert timeline['total']==4
    assert all(e['stage']=='rule_detection' and e['detail']['reason'] for e in timeline['items'])
    assert [e['at'] for e in timeline['items']]==sorted([e['at'] for e in timeline['items']],reverse=True)
    client.patch(f'/api/cases/{cid}/alerts/{a["id"]}',json={'status':'reviewed'})
    audit_events=client.get(f'/api/cases/{cid}/timeline',params={'event_type':'audit','q':'reviewed'}).json()
    assert audit_events['total']==1 and audit_events['items'][0]['txid']==a['txid']
    report=client.get(f'/api/cases/{cid}/report').json()
    assert report['schema_version']=='1.1'
    assert report['datasets'][0]['stage_events'] and report['alerts'][0]['detections']


def test_legacy_detection_times_are_not_invented(client):
    account(client);cid=case(client)
    client.post(f'/api/cases/{cid}/demo');tick()
    db.database().alerts.update_many({}, {'$unset':{'detections':'','detected_at':'','first_detected_stage':'','detection_stages':''}})
    result=client.get(f'/api/cases/{cid}/timeline',params={'event_type':'detection'}).json()
    assert result['total']==0 and result['legacy_alerts_without_detection_time']>0
    assert client.get(f'/api/cases/{cid}/alert-search',params={'stage':'unknown'}).json()['total']>0


def test_new_investigation_endpoints_enforce_case_access(client):
    account(client);cid=case(client);client.post(f'/api/cases/{cid}/demo');tick()
    a=client.get(f'/api/cases/{cid}/alerts').json()[0]
    account(client,'outsider@example.org','analyst')
    for endpoint in ['timeline','transaction-search','alert-search',f'transaction-details/{a["txid"]}',f'alert-details/{a["id"]}']:
        assert client.get(f'/api/cases/{cid}/{endpoint}').status_code==404


def test_small_dataset_records_skipped_model_and_validation_failure(client):
    account(client);cid=case(client)
    rows=json.loads(training_data())['transactions'][:25]
    r=client.post(f'/api/cases/{cid}/datasets',files={'file':('small.json',json.dumps(rows),'application/json')});tick()
    d=client.get(f'/api/cases/{cid}/datasets').json()[0]
    assert any(e['stage']=='model_scoring' and e['status']=='skipped' for e in d['stage_events'])
    alerts=client.get(f'/api/cases/{cid}/alerts').json()
    assert alerts and all(a['first_detected_stage']=='rule_detection' for a in alerts)
    bad=json.loads(training_data())['transactions'][:1];bad[0]['confirmed']=False;bad[0]['confirmations']=3
    client.post(f'/api/cases/{cid}/datasets',files={'file':('bad-confirmation.json',json.dumps(bad),'application/json')});tick()
    failed=next(x for x in client.get(f'/api/cases/{cid}/datasets').json() if x['status']=='failed')
    assert failed['stage_events'][-1]['stage']=='validation' and failed['stage_events'][-1]['status']=='failed'


def test_dual_rule_and_model_detection_preserves_first_stage():
    rows,_,_=parse(training_data(),'example.json')
    ordinary=[{**rows[0],'txid':f'{i:064x}'} for i in range(60)]
    ordinary[-1]={**rows[20],'txid':f'{999:064x}'}
    history=[]
    alerts,_=analyze(ordinary,lambda stage,status,detail,at:history.append((stage,status,at)))
    a=next(a for a in alerts if a['txid']==f'{999:064x}')
    assert a['first_detected_stage']=='rule_detection'
    assert a['detection_stages']==['rule_detection','model_scoring']
    assert a['detections'][0]['detected_at']<=a['detections'][1]['detected_at']<=a['created_at']
    assert [x[0] for x in history if x[1]=='completed']==['feature_engineering','rule_detection','model_scoring','alert_generation']
