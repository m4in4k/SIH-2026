"""Mongo-backed queue. A worker claims one dataset at a time; interrupted jobs fail visibly."""
import logging
import secrets
import time
from datetime import timedelta
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from .db import database, indexes, now
from .analysis import parse, analyze, MODEL_VERSION

logger=logging.getLogger(__name__)

def process(dataset_id):
    db=database(); d=db.datasets.find_one({'_id':dataset_id}); scope={'case_id':d['case_id'],'dataset_id':dataset_id}
    def record_stage(stage,status,detail,stamp):
        db.datasets.update_one({'_id':dataset_id},{'$push':{'stage_events':{'id':secrets.token_hex(12),'stage':stage,'status':status,'at':stamp,'detail':detail}},'$set':{'current_stage':stage,'heartbeat':stamp}})
    try:
        record_stage('validation','started',{},now())
        payload=db.uploads.find_one({'_id':dataset_id})
        rows,observations,warnings=parse(bytes(payload['content']),d['name'])
        record_stage('validation','completed',{'valid_records':len(rows),'warnings':len(warnings)},now())
        db.datasets.update_one({'_id':dataset_id},{'$set':{'progress':25,'heartbeat':now()}})
        # Retry cleanup applies only to records belonging to this dataset.
        for collection in ['transactions','alerts','features','observations']:
            db[collection].delete_many(scope)
        accepted=[]; skipped=0
        for t in rows:
            try:
                db.transactions.insert_one({'_id':secrets.token_hex(12),**scope,**t})
                accepted.append(t)
            except DuplicateKeyError:
                skipped+=1
        if not accepted:
            raise ValueError('All transaction IDs already exist in this case; no new records were imported.')
        if skipped:
            warnings.append(f'{skipped} TXIDs already in this case were skipped; original provenance retained.')
        imported_ids={t['txid'] for t in accepted}
        references={i['prev_txid'] for t in accepted for i in t['inputs']}
        known=set(imported_ids)
        missing=list(references-known)
        for start in range(0,len(missing),1000):
            known.update(t['txid'] for t in db.transactions.find({'case_id':d['case_id'],'txid':{'$in':missing[start:start+1000]}},{'txid':1}))
        unresolved=sum(1 for t in accepted for i in t['inputs'] if i['prev_txid'] not in known)
        if unresolved:
            warnings.append(f'{unresolved} input references are outside the available case records. Missing relationships are not inferred.')
        db.datasets.update_one({'_id':dataset_id},{'$set':{'progress':60,'heartbeat':now()}})
        alerts,features=analyze(accepted,on_stage=record_stage)
        for a in alerts:
            db.alerts.insert_one({'_id':secrets.token_hex(12),**scope,**a})
        for f in features:
            db.features.insert_one({'_id':secrets.token_hex(12),**scope,**f})
        for o in observations:
            db.observations.insert_one({'_id':secrets.token_hex(12),**scope,**o,'relationship':'observed relay; origin and ownership unknown'})
        if len(accepted)<40:
            warnings.append('Fewer than 40 records: rule detection only. ML scores are unavailable (shown as zero).')
        db.datasets.update_one({'_id':dataset_id},{'$set':{'status':'completed','progress':100,'count':len(accepted),'warnings':warnings,'completed_at':now(),'model_version':MODEL_VERSION if len(accepted)>=40 else 'rules-only-v2','parameters':{'n_estimators':100,'random_state':42,'score':'in-dataset mid-rank percentile; not a crime probability'}}})
        db.audit.insert_one({'_id':secrets.token_hex(12),'case_id':d['case_id'],'user_id':d['uploaded_by'],'action':'analysis_completed','detail':{'dataset_id':dataset_id,'records':len(accepted),'alerts':len(alerts)},'created_at':now()})
    except Exception as exc:
        logger.exception('Dataset analysis failed: %s', dataset_id)
        failed_stage=db.datasets.find_one({'_id':dataset_id}).get('current_stage','validation')
        record_stage(failed_stage,'failed',{'reason':'Processing failed; see dataset error.'},now())
        for collection in ['transactions','alerts','features','observations']:
            db[collection].delete_many(scope)
        safe=str(exc)[:300] if isinstance(exc,(ValueError,UnicodeError,KeyError)) else 'Analysis failed. Check worker logs and dataset format.'
        db.datasets.update_one({'_id':dataset_id},{'$set':{'status':'failed','error':safe,'progress':0}})

def tick():
    db=database()
    # Do not retry automatically: preserve a visible failure instead of silently racing an active worker.
    db.datasets.update_many({'status':'running','heartbeat':{'$lt':now()-timedelta(hours=1)}},{'$set':{'status':'failed','error':'Worker interrupted or timed out. Administrator review required before retry.'}})
    job=db.datasets.find_one_and_update({'status':'queued'},{'$set':{'status':'running','progress':5,'heartbeat':now()}},sort=[('created_at',1)],return_document=ReturnDocument.AFTER)
    if job:
        process(job['_id']);return True
    return False

def run(stop=None):
    while not (stop and stop.is_set()):
        try:
            if tick():
                continue
        except Exception:
            logger.exception('Worker connection error')
        if stop:
            stop.wait(2)
        else:
            time.sleep(2)

if __name__=='__main__':
    logging.basicConfig(level=logging.INFO)
    indexes(database())
    run()
