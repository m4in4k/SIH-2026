import hashlib
import secrets
from datetime import timedelta
from fastapi import HTTPException, Request
from pwdlib import PasswordHash
from .db import database, now

passwords = PasswordHash.recommended()
DUMMY_HASH = passwords.hash(secrets.token_urlsafe(24))

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def current_user(request: Request):
    token = request.cookies.get('sentinel_session')
    if not token:
        raise HTTPException(401, 'Sign in to access your workspace.')
    session = database().sessions.find_one({'_id': digest(token), 'expires_at': {'$gt': now()}})
    user = database().users.find_one({'_id': session['user_id']}) if session else None
    if not user:
        raise HTTPException(401, 'Your session has expired. Please sign in again.')
    return user

def audit(user_id, case_id, action, detail):
    database().audit.insert_one({'_id': secrets.token_hex(12), 'user_id': user_id, 'case_id': case_id,
                                'action': action, 'detail': detail, 'created_at': now()})

def access(case_id, user, write=False, admin=False):
    case = database().cases.find_one({'_id': case_id})
    if not case:
        raise HTTPException(404, 'Case not found.')
    role = 'admin' if user['role'] == 'admin' else next((m['role'] for m in case['members'] if m['user_id'] == user['_id']), None)
    if not role:
        raise HTTPException(404, 'Case not found.')
    if (write and role == 'viewer') or (admin and role != 'admin'):
        raise HTTPException(403, 'Your role does not permit this action.')
    return case, role

def login_limited(email, ip):
    db = database()
    key = digest(email + '|' + ip)
    record = db.login_attempts.find_one({'_id': key})
    if record and record['expires_at'] > now() and record['count'] >= 8:
        raise HTTPException(429, 'Too many sign-in attempts. Try again in 15 minutes.')
    if record and record['expires_at'] <= now():
        db.login_attempts.delete_one({'_id': key})
    db.login_attempts.update_one({'_id': key}, {'$inc': {'count': 1}, '$setOnInsert': {'expires_at': now() + timedelta(minutes=15)}}, upsert=True)
    return key
