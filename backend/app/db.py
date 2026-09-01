import os
from datetime import datetime, timezone
from pymongo import MongoClient

_client = None
_test_db = None

def now():
    return datetime.now(timezone.utc)

def database():
    global _client
    if _test_db is not None:
        return _test_db
    if _client is None:
        _client = MongoClient(os.getenv('MONGO_URI', 'mongodb://127.0.0.1:27017'), serverSelectionTimeoutMS=3000, tz_aware=True)
    return _client[os.getenv('MONGO_DB', 'bitcoin_sentinel')]

def indexes(db):
    db.users.create_index('email', unique=True)
    db.sessions.create_index('expires_at', expireAfterSeconds=0)
    db.login_attempts.create_index('expires_at', expireAfterSeconds=0)
    db.cases.create_index('members.user_id')
    db.transactions.create_index([('case_id', 1), ('txid', 1)], unique=True)
    db.transactions.create_index([('case_id', 1), ('inputs.prev_txid', 1)])
    db.transactions.create_index([('case_id', 1), ('dataset_id', 1)])
    db.transactions.create_index([('case_id', 1), ('outputs.address', 1)])
    db.datasets.create_index([('case_id', 1), ('sha256', 1)], unique=True)
    db.datasets.create_index([('status', 1), ('created_at', 1)])
    db.alerts.create_index([('case_id', 1), ('score', -1)])
    db.features.create_index([('case_id', 1), ('txid', 1), ('dataset_id', 1)], unique=True)
    db.transactions.create_index([('case_id',1),('observed_at',-1)])
    db.transactions.create_index([('case_id',1),('block_time',-1)])
    db.alerts.create_index([('case_id',1),('detection_stages',1),('detected_at',-1)])
    db.audit.create_index([('case_id', 1), ('created_at', -1)])
    db.observations.create_index([('case_id', 1), ('txid', 1)])

def public(doc):
    if not doc:
        return None
    return {('id' if k == '_id' else k): v for k, v in doc.items() if k not in {'password_hash', 'content', 'members'}}
