import json
import secrets
import mongomock
import pytest
from fastapi.testclient import TestClient
from app import db, geoip
from app.main import app
from app.worker import tick

@pytest.fixture
def client():
    db._test_db = mongomock.MongoClient(tz_aware=True).sentinel_test_audit
    with TestClient(app) as c:
        c.headers['X-Sentinel-Request'] = '1'
        yield c
    db._test_db = None

def test_full_e2e_login_audit_and_sih_pipeline(client, monkeypatch):
    # 1. Test wrong credentials error and retry ability (no 15-minute wait)
    wrong_res = client.post('/api/auth/login', json={'email': 'nobody@example.org', 'password': 'WrongPassword123!'})
    assert wrong_res.status_code == 401
    assert 'Email or password is incorrect' in wrong_res.json()['detail']
    assert '15 minutes' not in wrong_res.json()['detail']
    
    # Retry immediately with another attempt
    wrong_res2 = client.post('/api/auth/login', json={'email': 'nobody@example.org', 'password': 'AnotherWrongPassword123!'})
    assert wrong_res2.status_code == 401
    assert '15 minutes' not in wrong_res2.json()['detail']

    # 2. Mock GeoLite2 readers for offline enrichment verification
    class CountryResult:
        country = type('Country', (), {'iso_code': 'IN', 'name': 'India'})()
    class ASNResult:
        autonomous_system_number = 13335
        autonomous_system_organization = 'Cloudflare Inc'
    class MockCountryReader:
        def country(self, ip):
            return CountryResult()
    class MockASNReader:
        def asn(self, ip):
            return ASNResult()

    monkeypatch.setattr(geoip, '_readers', lambda: (MockCountryReader(), MockASNReader()))

    # 3. Test 12-character password requirement
    # Shorter than 12 chars must fail
    res_short = client.post('/api/auth/signup', json={'name': 'Short', 'email': 'short@sih2026.gov.in', 'password': '12345678901'})
    assert res_short.status_code == 422

    # Exactly 12 chars must succeed
    res_12char = client.post('/api/auth/signup', json={'name': 'Twelve Char', 'email': 'twelve@sih2026.gov.in', 'password': '123456789012'})
    assert res_12char.status_code == 201
    assert res_12char.json()['email'] == 'twelve@sih2026.gov.in'

    # 12-char alpha password must also succeed
    res_alpha = client.post('/api/auth/signup', json={'name': 'Alpha User', 'email': 'alpha@sih2026.gov.in', 'password': 'abcdefghijkl'})
    assert res_alpha.status_code == 201

    # Login with 12-char password
    client.post('/api/auth/logout')
    login_12char = client.post('/api/auth/login', json={'email': 'twelve@sih2026.gov.in', 'password': '123456789012'})
    assert login_12char.status_code == 200
    assert client.get('/api/auth/me').json()['email'] == 'twelve@sih2026.gov.in'

    # Create investigator account for dataset workflow test
    signup_payload = {
        'name': 'SIH Investigator',
        'email': 'investigator@sih2026.gov.in',
        'password': 'SIHsecure1234'
    }
    signup_res = client.post('/api/auth/signup', json=signup_payload)
    assert signup_res.status_code == 201
    user = signup_res.json()
    assert user['email'] == 'investigator@sih2026.gov.in'
    assert user['role'] == 'analyst'

    # 4. Verify new account starts completely clean and empty (0 datasets, 0 cases, 0 alerts)
    cases_res = client.get('/api/cases')
    assert cases_res.status_code == 200
    assert cases_res.json() == []

    # 5. Create a new case
    case_res = client.post('/api/cases', json={'name': 'Operation SIH Sentinel', 'description': 'AI monitoring of Bitcoin traffic'})
    assert case_res.status_code == 201
    case_id = case_res.json()['id']

    # Summary for the empty case must be all zeros
    summary_empty = client.get(f'/api/cases/{case_id}/summary').json()
    assert summary_empty['transactions'] == 0
    assert summary_empty['alerts_count'] == 0
    assert summary_empty['high_priority'] == 0
    assert summary_empty['chart'] == []

    # 6. Import SIH dataset with all SIH problem statement fields
    # Generate 45 transactions so Isolation Forest ML runs
    sih_csv_lines = [
        'txid,timestamp,src_ip,dst_ip,src_port,dst_port,input_addresses,output_addresses,input_amounts,output_amounts,geo_country,asn'
    ]
    for i in range(45):
        txid = f'{i+1:064x}'
        src_ip = f'8.8.8.{(i % 50) + 1}'
        dst_ip = f'1.1.1.{(i % 50) + 1}'
        timestamp = f'2026-09-01T{i%24:02d}:00:00+00:00'
        # Transactions 5 and 15 have fan-out of 12 outputs (trigger rule & ML)
        out_count = 12 if i in {5, 15} else 2
        in_addrs = [f'1in_{i}_{j}' for j in range(1)]
        in_amts = ['10.0']
        out_addrs = [f'1out_{i}_{j}' for j in range(out_count)]
        out_amts = [f'{9.99/out_count:.6f}' for _ in range(out_count)]
        
        line = f'{txid},{timestamp},{src_ip},{dst_ip},18333,8333,"{json.dumps(in_addrs).replace('"', '""')}","{json.dumps(out_addrs).replace('"', '""')}","{json.dumps(in_amts).replace('"', '""')}","{json.dumps(out_amts).replace('"', '""')}",IN,AS13335'
        sih_csv_lines.append(line)

    sih_csv_content = '\n'.join(sih_csv_lines)
    upload_res = client.post(
        f'/api/cases/{case_id}/datasets',
        files={'file': ('sih_dataset.csv', sih_csv_content.encode('utf-8'), 'text/csv')}
    )
    assert upload_res.status_code == 202
    dataset_id = upload_res.json()['id']
    assert upload_res.json()['status'] == 'queued'

    # 7. Worker processes dataset
    processed = tick()
    assert processed is True

    # 8. Verify dataset status is completed
    datasets = client.get(f'/api/cases/{case_id}/datasets').json()
    assert len(datasets) == 1
    ds = datasets[0]
    assert ds['status'] == 'completed'
    assert ds['count'] == 45
    assert ds['model_version'] == 'sentinel-iforest-shap-v3'

    # 9. Verify Summary & Analytics
    summary = client.get(f'/api/cases/{case_id}/summary').json()
    assert summary['transactions'] == 45
    assert summary['alerts_count'] >= 2
    assert summary['high_priority'] >= 2
    assert len(summary['chart']) > 0

    # 10. Verify Alerts, Priority, ML & Rule detection
    alerts = client.get(f'/api/cases/{case_id}/alerts').json()
    assert len(alerts) >= 2
    top_alert = alerts[0]
    assert top_alert['priority'] in {'critical', 'high', 'medium', 'low'}
    assert top_alert['detection_method'] in {'rule', 'ml', 'combined'}
    assert 'feature_evidence' in top_alert
    assert len(top_alert['reasons']) >= 1
    assert top_alert['risk_score'] > 0

    # 11. Verify Transaction Search & Details with correlation & GeoIP
    tx_search = client.get(f'/api/cases/{case_id}/transaction-search', params={'limit': 10}).json()
    assert tx_search['total'] == 45
    first_txid = alerts[0]['txid']
    tx_detail = client.get(f'/api/cases/{case_id}/transaction-details/{first_txid}').json()
    assert tx_detail['transaction']['txid'] == first_txid
    assert len(tx_detail['outputs']) >= 2
    assert len(tx_detail['observations']) >= 1
    obs = tx_detail['observations'][0]
    assert obs['src_country'] == 'IN'
    assert obs['src_asn'] == 'AS13335'
    assert obs['src_asn_org'] == 'Cloudflare Inc'

    # 12. Verify Graph Explorer
    graph = client.get(f'/api/cases/{case_id}/graph/{first_txid}').json()
    assert len(graph['nodes']) > 0
    assert len(graph['edges']) > 0
    node_ids = {n['data']['id'] for n in graph['nodes']}
    assert first_txid in node_ids
    assert any(n['data'].get('kind') == 'ip' for n in graph['nodes'])
    assert any(n['data'].get('kind') == 'wallet' for n in graph['nodes'])

    # 13. Verify Timeline
    timeline = client.get(f'/api/cases/{case_id}/timeline').json()
    assert timeline['total'] > 0
    types = {e['type'] for e in timeline['items']}
    assert 'pipeline' in types or 'observation' in types

    # 14. Review Alert & Verify Audit
    review_res = client.patch(f'/api/cases/{case_id}/alerts/{top_alert["id"]}', json={'status': 'reviewed'})
    assert review_res.status_code == 200
    assert review_res.json()['status'] == 'reviewed'

    # 15. Export Investigation Report
    report = client.get(f'/api/cases/{case_id}/report').json()
    assert report['schema_version'] == '1.2'
    assert len(report['datasets']) == 1
    assert len(report['alerts']) >= 2
    assert len(report['transactions']) >= 1
    assert len(report['features']) >= 1
    assert len(report['network_observations']) >= 1
    assert len(report['audit']) >= 1

    # 16. Logout
    logout_res = client.post('/api/auth/logout')
    assert logout_res.status_code == 204
    assert client.get('/api/auth/me').status_code == 401

    # 17. Sign in again with correct credentials
    login_res = client.post('/api/auth/login', json={'email': 'investigator@sih2026.gov.in', 'password': 'SIHsecure1234'})
    assert login_res.status_code == 200
    assert login_res.json()['email'] == 'investigator@sih2026.gov.in'
    assert client.get('/api/auth/me').status_code == 200
