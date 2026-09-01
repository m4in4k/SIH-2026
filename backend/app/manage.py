"""Local administrator provisioning; never expose bootstrap as a public API."""
import argparse
import getpass
import secrets
from .db import database,indexes,now
from .security import passwords
from .models import Credentials

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['create-admin','reset-password'])
    parser.add_argument('--email',required=True)
    parser.add_argument('--name',default='Workspace administrator')
    args=parser.parse_args()
    password=getpass.getpass('Password (at least 12 characters): ')
    if len(password)<12 or password!=getpass.getpass('Confirm password: '):
        raise SystemExit('Password must be at least 12 characters and confirmations must match.')
    email=Credentials(email=args.email,password=password).email
    db=database();indexes(db)
    if args.action=='reset-password':
        user=db.users.find_one({'email':email})
        if not user:raise SystemExit('User not found.')
        db.users.update_one({'_id':user['_id']},{'$set':{'password_hash':passwords.hash(password)}})
        db.sessions.delete_many({'user_id':user['_id']})
        print('Password updated; existing sessions revoked.')
        return
    if db.users.find_one({'email':email}):raise SystemExit('A user with this email already exists.')
    db.users.insert_one({'_id':secrets.token_hex(12),'email':email,'name':args.name,'role':'admin','password_hash':passwords.hash(password),'created_at':now()})
    print('Administrator created. Sign in to create your first case.')

if __name__=='__main__':main()
