"""Mongo-backed queue. A worker claims one dataset at a time; interrupted jobs fail visibly."""
import logging
import secrets
import time
from datetime import timedelta
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from .db import database, indexes, now
from .analysis import parse, analyze, MODEL_VERSION
from .geoip import enrich_observations
from .clustering import cluster_wallets, cluster_ips

logger = logging.getLogger(__name__)


def process(dataset_id):
    db = database()
    d = db.datasets.find_one({'_id': dataset_id})
    if not d:
        return False
    scope = {'case_id': d['case_id'], 'dataset_id': dataset_id}

    def record_stage(stage, status, detail, stamp):
        db.datasets.update_one(
            {'_id': dataset_id},
            {'$push': {'stage_events': {'id': secrets.token_hex(12), 'stage': stage,
                                         'status': status, 'at': stamp, 'detail': detail}},
             '$set': {'current_stage': stage, 'heartbeat': stamp}},
        )

    try:
<<<<<<< HEAD
<<<<<<< HEAD
=======
        record_stage('validation', 'started', {}, now())
        payload = db.uploads.find_one({'_id': dataset_id})
        rows, observations, warnings = parse(bytes(payload['content']), d['name'])
        record_stage('validation', 'completed', {'valid_records': len(rows), 'warnings': len(warnings)}, now())
        db.datasets.update_one({'_id': dataset_id}, {'$set': {'progress': 20, 'heartbeat': now()}})

        # Retry cleanup: remove only records from this dataset
        for collection in ['transactions', 'alerts', 'features', 'observations', 'clusters']:
=======
>>>>>>> 20a0cb789f0b780745cb32d39b36cd06620b3b24
        record_stage('validation','started',{},now())
        payload=db.uploads.find_one({'_id':dataset_id})
        if not payload:
            raise ValueError('Uploaded dataset payload is missing; the dataset cannot be processed.')
        rows,observations,warnings=parse(bytes(payload['content']),d['name'])
        record_stage('validation','completed',{'valid_records':len(rows),'warnings':len(warnings)},now())
        db.datasets.update_one({'_id':dataset_id},{'$set':{'progress':25,'heartbeat':now()}})
        # Retry cleanup applies only to records belonging to this dataset.
        for collection in ['transactions','alerts','features','observations']:
<<<<<<< HEAD
=======
        record_stage('validation', 'started', {}, now())
        payload = db.uploads.find_one({'_id': dataset_id})
        rows, observations, warnings = parse(bytes(payload['content']), d['name'])
        record_stage('validation', 'completed', {'valid_records': len(rows), 'warnings': len(warnings)}, now())
        db.datasets.update_one({'_id': dataset_id}, {'$set': {'progress': 20, 'heartbeat': now()}})

        # Retry cleanup: remove only records from this dataset
        for collection in ['transactions', 'alerts', 'features', 'observations', 'clusters']:
>>>>>>> a2af0ae (feat: implement backend database schema, analytical processing pipeline, and frontend dashboard for transaction monitoring and ML anomaly detection)
=======
>>>>>>> 8bd8a2169d83afd7ad90d8125606ba357648d268
>>>>>>> 20a0cb789f0b780745cb32d39b36cd06620b3b24
            db[collection].delete_many(scope)

        # --- GeoIP enrichment ---
        record_stage('geoip_enrichment', 'started', {'observation_count': len(observations)}, now())
        enriched_obs = enrich_observations(observations)
        record_stage('geoip_enrichment', 'completed',
                     {'enriched': sum(1 for o in enriched_obs if o.get('country') != 'Unknown')}, now())
        db.datasets.update_one({'_id': dataset_id}, {'$set': {'progress': 35, 'heartbeat': now()}})

        # --- Insert transactions ---
        accepted = []
        skipped = 0
        for t in rows:
            try:
                db.transactions.insert_one({'_id': secrets.token_hex(12), **scope, **t})
                accepted.append(t)
            except DuplicateKeyError:
                skipped += 1

        if not accepted:
            raise ValueError('All transaction IDs already exist in this case; no new records were imported.')
        if skipped:
            warnings.append(f'{skipped} TXIDs already in this case were skipped; original provenance retained.')

        # Cross-dataset reference resolution
        imported_ids = {t['txid'] for t in accepted}
        references = {i['prev_txid'] for t in accepted for i in t['inputs']}
        known = set(imported_ids)
        missing = list(references - known)
        for start in range(0, len(missing), 1000):
            known.update(t['txid'] for t in db.transactions.find(
                {'case_id': d['case_id'], 'txid': {'$in': missing[start:start + 1000]}}, {'txid': 1}))
        unresolved = sum(1 for t in accepted for i in t['inputs'] if i['prev_txid'] not in known)
        if unresolved:
            warnings.append(f'{unresolved} input references are outside the available case records.')

        db.datasets.update_one({'_id': dataset_id}, {'$set': {'progress': 55, 'heartbeat': now()}})

        # --- AI/ML analysis (with network observation context) ---
        alerts, features = analyze(accepted, observations=enriched_obs, on_stage=record_stage)

        for a in alerts:
            db.alerts.insert_one({'_id': secrets.token_hex(12), **scope, **a})
        for f in features:
            db.features.insert_one({'_id': secrets.token_hex(12), **scope, **f})

        # --- Insert enriched observations ---
        for o in enriched_obs:
            db.observations.insert_one({
                '_id': secrets.token_hex(12), **scope, **o,
                'relationship': 'observed relay; origin and ownership unknown',
            })

        db.datasets.update_one({'_id': dataset_id}, {'$set': {'progress': 80, 'heartbeat': now()}})

        # --- Entity clustering ---
        record_stage('entity_clustering', 'started',
                     {'transactions': len(accepted), 'observations': len(enriched_obs)}, now())
        wallet_clusters = cluster_wallets(accepted, alerts)
        ip_clusters = cluster_ips(enriched_obs, alerts)
        for c in wallet_clusters + ip_clusters:
            db.clusters.insert_one({**scope, **c})
        record_stage('entity_clustering', 'completed',
                     {'wallet_clusters': len(wallet_clusters), 'ip_clusters': len(ip_clusters)}, now())

        db.datasets.update_one({'_id': dataset_id}, {'$set': {'progress': 95, 'heartbeat': now()}})

        if len(accepted) < 40:
            warnings.append('Fewer than 40 records: rule detection only. ML scores are zero.')

        db.datasets.update_one({'_id': dataset_id}, {'$set': {
            'status': 'completed', 'progress': 100, 'count': len(accepted),
            'warnings': warnings, 'completed_at': now(),
            'model_version': MODEL_VERSION if len(accepted) >= 40 else 'rules-only-v3',
            'parameters': {
                'n_estimators': 200, 'random_state': 42,
                'score': 'in-dataset mid-rank percentile; not a crime probability',
                'features': 14, 'clustering': 'common_input_ownership+ip_cooccurrence',
            },
        }})
        db.audit.insert_one({
            '_id': secrets.token_hex(12), 'case_id': d['case_id'], 'user_id': d['uploaded_by'],
            'action': 'analysis_completed',
            'detail': {'dataset_id': dataset_id, 'records': len(accepted), 'alerts': len(alerts),
                       'wallet_clusters': len(wallet_clusters), 'ip_clusters': len(ip_clusters)},
            'created_at': now(),
        })

    except Exception as exc:
        logger.exception('Dataset analysis failed: %s', dataset_id)
        failed_stage = (db.datasets.find_one({'_id': dataset_id}) or {}).get('current_stage', 'validation')
        record_stage(failed_stage, 'failed', {'reason': 'Processing failed; see dataset error.'}, now())
        for collection in ['transactions', 'alerts', 'features', 'observations', 'clusters']:
            db[collection].delete_many(scope)
        safe = str(exc)[:300] if isinstance(exc, (ValueError, UnicodeError, KeyError)) else \
            'Analysis failed. Check worker logs and dataset format.'
        db.datasets.update_one({'_id': dataset_id}, {'$set': {'status': 'failed', 'error': safe, 'progress': 0}})
    return True


def claim_and_process(dataset_id):
    job = database().datasets.find_one_and_update(
        {'_id': dataset_id, 'status': 'queued'},
        {'$set': {'status': 'running', 'progress': 5, 'heartbeat': now()}},
        return_document=ReturnDocument.AFTER,
    )
    return process(dataset_id) if job else False


def tick():
    db = database()
    db.datasets.update_many(
        {'status': 'running', 'heartbeat': {'$lt': now() - timedelta(hours=1)}},
        {'$set': {'status': 'failed', 'error': 'Worker interrupted or timed out. Administrator review required before retry.'}},
    )
    job = db.datasets.find_one_and_update(
        {'status': 'queued'},
        {'$set': {'status': 'running', 'progress': 5, 'heartbeat': now()}},
        sort=[('created_at', 1)],
        return_document=ReturnDocument.AFTER,
    )
    if job:
        process(job['_id'])
        return True
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


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    indexes(database())
    run()
