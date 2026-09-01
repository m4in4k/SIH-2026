"""Exploratory in-dataset anomaly ranking. No attribution or crime probabilities."""
import csv
import io
import json
import math
import statistics
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from defusedxml import ElementTree
from pydantic import ValidationError
from sklearn.ensemble import IsolationForest
from .models import Transaction, Observation

MODEL_VERSION = 'sentinel-iforest-v2'
MAX_RECORDS = 10000

def parse(content: bytes, filename: str):
    text = content.decode('utf-8-sig')
    observations = []
    if filename.lower().endswith('.json'):
        raw = json.loads(text)
        rows = raw if isinstance(raw, list) else raw.get('transactions', [])
        if isinstance(raw, dict):
            observations = raw.get('observations', [])
    elif filename.lower().endswith('.csv'):
        rows = list(csv.DictReader(io.StringIO(text)))
        for row in rows:
            for key in ['inputs', 'outputs']:
                row[key] = json.loads(row.get(key) or '[]')
            for key in ['fee_sats', 'vsize', 'confirmations', 'block_height', 'size_bytes', 'weight', 'version', 'locktime']:
                row[key] = int(row[key]) if row.get(key) else None
            for key in ['observed_at', 'block_time']:
                row[key] = row.get(key) or None
    elif filename.lower().endswith('.xml'):
        root = ElementTree.fromstring(text)
        rows = []
        for node in root.findall('transaction'):
            row = {child.tag: child.text for child in node if child.tag not in {'inputs', 'outputs'}}
            row['inputs'] = [dict(i.attrib) for i in node.findall('inputs/input')]
            row['outputs'] = [dict(o.attrib) for o in node.findall('outputs/output')]
            for entry in row['inputs']:
                entry['prev_vout'] = int(entry['prev_vout'])
                if entry.get('sequence') is not None: entry['sequence']=int(entry['sequence'])
            for entry in row['outputs']:
                entry['index'] = int(entry['index']); entry['value_sats'] = int(entry['value_sats'])
            for key in ['fee_sats', 'vsize', 'confirmations', 'block_height', 'size_bytes', 'weight', 'version', 'locktime']:
                row[key] = int(row[key]) if row.get(key) else None
            rows.append(row)
    else:
        raise ValueError('Use .json, .csv, or .xml files.')
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_RECORDS:
        raise ValueError(f'Import between 1 and {MAX_RECORDS:,} transactions per file.')
    if not isinstance(observations, list) or len(observations) > MAX_RECORDS:
        raise ValueError('Import at most 10,000 network observations.')
    # CSV/XML scalars arrive as text; accept only explicit boolean spellings.
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get('confirmed'), str):
            flag=row['confirmed'].strip().lower()
            if flag not in {'true','false',''}:
                raise ValueError('confirmed must be true, false, or empty.')
            row['confirmed']={'true':True,'false':False,'':None}[flag]
        if isinstance(row, dict) and row.get('block_hash')=='':
            row['block_hash']=None
    seen = set(); result = []; duplicate = 0
    for n, row in enumerate(rows, 1):
        try:
            tx = Transaction.model_validate(row).model_dump()
        except ValidationError as exc:
            err = exc.errors()[0]
            raise ValueError(f'Record {n}: {".".join(map(str, err["loc"]))}: {err["msg"]}') from exc
        if tx['txid'] in seen:
            duplicate += 1
            continue
        seen.add(tx['txid']); tx['source_record'] = n; result.append(tx)
    obs = [Observation.model_validate(o).model_dump() for o in observations]
    warnings = []
    if duplicate:
        warnings.append(f'{duplicate} duplicate TXIDs within this file were skipped.')
    if any(t['fee_sats'] is None for t in result):
        warnings.append('Missing fees are not inferred; the model includes a missing-fee indicator.')
    if any(t['observed_at'] is None for t in result):
        warnings.append('Some observation timestamps are missing. Block time is displayed separately where available.')
    return result, obs, warnings

def analyze(rows, on_stage=None):
    """Record actual stage completion times; blockchain times never stand in for detection time."""
    from bisect import bisect_left, bisect_right
    def stage(name,status,**detail):
        stamp=datetime.now(timezone.utc)
        if on_stage: on_stage(name,status,detail,stamp)
        return stamp
    stage('feature_engineering','started',records=len(rows))
    vectors=[]
    for t in rows:
        vals=[o['value_sats'] for o in t['outputs']];total=sum(vals)
        rate=t['fee_sats']/t['vsize'] if t['fee_sats'] is not None and t['vsize'] else None
        vectors.append([len(t['inputs']),len(vals),math.log1p(total),max(vals)/total if total else 0,math.log1p(rate or 0),int(rate is None)])
    stage('feature_engineering','completed',records=len(rows),features=6)
    median_out=statistics.median(len(t['outputs']) for t in rows)
    median_in=statistics.median(len(t['inputs']) for t in rows)
    stage('rule_detection','started',records=len(rows))
    detections=[[] for _ in rows]
    rule_time=datetime.now(timezone.utc)
    for t,signals in zip(rows,detections):
        for field,code,title,baseline in [('outputs','fan_out','Unusual output fan-out',median_out),('inputs','fan_in','High input consolidation',median_in)]:
            value=len(t[field])
            if value>=10:
                signals.append({'code':code,'stage':'rule_detection','detector':'Count threshold rule',
                    'title':title,'feature':f'{field[:-1]}_count','observed':value,'operator':'>=','threshold':10,
                    'baseline':baseline,'unit':'count','detected_at':rule_time,
                    'reason':f'{value} {field} meet the configured threshold of 10; dataset median is {baseline:g}.'})
    stage('rule_detection','completed',matched_transactions=sum(bool(x) for x in detections))
    stage('model_scoring','started',records=len(rows))
    if len(rows)>=40:
        model=IsolationForest(n_estimators=100,contamination='auto',random_state=42,n_jobs=1)
        raw=-model.fit(vectors).score_samples(vectors);ordered=sorted(raw)
        scores=[round(100*(bisect_left(ordered,v)+.5*(bisect_right(ordered,v)-bisect_left(ordered,v)))/len(raw),1) for v in raw]
        model_time=datetime.now(timezone.utc)
        for signals,score in zip(detections,scores):
            if score>=97:
                signals.append({'code':'isolation_forest','stage':'model_scoring','detector':'Isolation Forest',
                    'title':'Multivariate transaction anomaly','feature':'anomaly_percentile','observed':score,
                    'operator':'>=','threshold':97,'baseline':None,'unit':'percentile','detected_at':model_time,
                    'reason':f'In-dataset anomaly percentile {score:g} meets the 97th-percentile review threshold. This is not a crime probability.'})
        stage('model_scoring','completed',records=len(rows),model_version=MODEL_VERSION)
    else:
        scores=[0.0]*len(rows)
        stage('model_scoring','skipped',reason='At least 40 records are required; rules remain active.')
    stage('alert_generation','started')
    alerts=[];features=[]
    for t,vector,score,signals in zip(rows,vectors,scores,detections):
        version=MODEL_VERSION if len(rows)>=40 else 'rules-only-v2'
        if signals:
            reasons=[signal['reason'] for signal in signals]
            reasons.append(f'Feature evidence: {len(t["inputs"])} inputs, {len(t["outputs"])} outputs, total {sum(o["value_sats"] for o in t["outputs"])} satoshis. Descriptive evidence, not exact model attribution.')
            alerts.append({'txid':t['txid'],'title':signals[0]['title'],
                'severity':'high' if signals[0]['stage']=='rule_detection' else 'medium',
                'score':score,'reasons':reasons,'status':'open','detections':signals,
                'first_detected_stage':signals[0]['stage'],'detection_stages':list(dict.fromkeys(x['stage'] for x in signals)),
                'detected_at':signals[0]['detected_at'],'transaction_observed_at':t.get('observed_at'),
                'transaction_block_time':t.get('block_time'),'created_at':datetime.now(timezone.utc),
                'alternative':'Payment batching, wallet consolidation, or other ordinary activity may explain this pattern. Ownership and intent remain unknown.',
                'model_version':version})
        features.append({'txid':t['txid'],'values':vector,'score':score,'model_version':version,
            'feature_names':['input_count','output_count','log_output_total','largest_output_share','log_fee_rate','fee_rate_missing']})
    stage('alert_generation','completed',alerts=len(alerts))
    return sorted(alerts,key=lambda a:(a['severity']=='high',a['score']),reverse=True),features

def training_data():
    """Synthetic UTXO-consistent branching trace, not real blockchain transactions."""
    rows=[]; available=[]; base=datetime(2026,8,31,tzinfo=timezone.utc)
    for i in range(180):
        txid=sha256(f'sentinel-training-v1-{i}'.encode()).hexdigest()
        if available:
            prev=available.pop(0)
            ins=[{'prev_txid':prev['txid'],'prev_vout':prev['index']}]
            budget=prev['value_sats']
        else:
            ins=[];budget=50_000_000_000
        fee=min(500,budget//100)
        count=16 if i in {20,60,100,140} else 2
        if budget-fee<count:
            count=1
        each=(budget-fee)//count
        outputs=[{'index':j,'value_sats':each+(budget-fee-each*count if j==0 else 0),'address':f'synthetic-address-{i}-{j}','script_type':'p2wpkh'} for j in range(count)]
        available.extend({'txid':txid,**o} for o in outputs if o['value_sats']>10000)
        rows.append({'txid':txid,'observed_at':(base+timedelta(minutes=8*i)).isoformat(),'inputs':ins,'outputs':outputs,'fee_sats':fee,'vsize':140+count*31,'size_bytes':200+count*31,'weight':(140+count*31)*4,'version':2,'locktime':0,'confirmed':i<160,'confirmations':3 if i<160 else 0,'block_height':900000+i//20 if i<160 else None,'block_time':(base+timedelta(minutes=8*i+10)).isoformat() if i<160 else None})
    return json.dumps({'synthetic':True,'transactions':rows}).encode()
