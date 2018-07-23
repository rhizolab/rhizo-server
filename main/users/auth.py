# standard python imports
import os
import time  # fix(clean): remove
import random
import base64
import hashlib
import datetime


# external imports
import bcrypt
from flask import current_app
from sqlalchemy.orm.exc import NoResultFound


# internal imports
from main.app import db
from main.app import login_manager
from main.users.models import User, Key
from main.util import load_server_config  # fix(clean): remove?


# return a user model for the given user ID
@login_manager.user_loader
def load_user(user_id):
    try:
        user = User.query.filter(User.id == user_id, User.deleted == False).one()
    except NoResultFound:
        user = None
    return user


# return a user model for the given password and user name / email address;
# returns None if user not found or password doesn't match
def login_validate(user_name_or_email, password):
    if not user_name_or_email or not password:
        return None
    try:  # fix(faster): combine into a single query
        user = User.query.filter(User.email_address == user_name_or_email, User.deleted == False).one()
    except NoResultFound:
        try:
            user = User.query.filter(User.user_name == user_name_or_email, User.deleted == False).one()
        except NoResultFound:
            user = None
    if user and not bcrypt.checkpw(inner_password_hash(password), user.password_hash.encode()):
        user = None
    return user


# create a user account
def create_user(email_address, user_name, password, full_name, role):
    user = User()
    user.email_address = email_address
    user.user_name = user_name if user_name else None  # use NULL instead of empty string
    user.password_hash = hash_password(password)
    user.full_name = full_name
    user.info_status = '{}'
    user.attributes = '{}'
    user.deleted = False
    user.creation_timestamp = datetime.datetime.utcnow()
    user.role = role
    db.session.add(user)
    db.session.commit()
    return user.id


# change a user's password
def change_user_password(user_name_or_email_address, old_password, new_password):
    user = login_validate(user_name_or_email_address, old_password)
    if user:
        user.password_hash = hash_password(new_password)
        db.session.commit()


# reset a user's password
# fix(clean): merge with above?
def reset_user_password(user_name_or_email_address, new_password):
    try:
        user = User.query.filter(User.email_address == user_name_or_email_address).one()
    except NoResultFound:
        try:
            user = User.query.filter(User.user_name == user_name_or_email_address).one()
        except NoResultFound:
            user = None
    if user:
        user.password_hash = hash_password(new_password)
        db.session.commit()


# compute the inner hash of a password using system's salt
def inner_password_hash(password):
    try:
        salt = current_app.config['SALT']
    except RuntimeError:  # handle case that we're running outside app (e.g. creating admin from command line)
        config = load_server_config()
        salt = config['SALT']
    return base64.standard_b64encode(hashlib.sha512(password + salt).digest())


# compute a full hash of the password
def hash_password(password):
    return bcrypt.hashpw(inner_password_hash(password), bcrypt.gensalt(12))


# create a new access key associated with a user or controller
def create_key(creation_user_id, organization_id, access_as_user_id, access_as_controller_id, key_text = None):

    # compute the key text
    if not key_text:
        from main.users.permissions import generate_access_code  # import here to avoid import loop
        key_text = current_app.config['KEY_PREFIX'] + generate_access_code(50)

    # encrypt the key
    # fix(soon): remove this once no longer in use
    if current_app.config.get('KEY_STORAGE_KEY'):  # not needed on new systems
        from main.users.encrypt import AESCipher
        nonce = base64.b64encode(os.urandom(32))
        aes = AESCipher(current_app.config['KEY_STORAGE_KEY'])
        key_enc = aes.encrypt(nonce + ';' + key_text)
    else:
        nonce = ''
        key_enc = ''

    # create a key record
    key = Key()
    key.organization_id = organization_id
    key.creation_user_id = creation_user_id
    key.creation_timestamp = datetime.datetime.utcnow()
    key.access_as_user_id = access_as_user_id
    key.access_as_controller_id = access_as_controller_id
    key.key_part = key_text[:3] + key_text[-3:]
    key.key_hash = hash_password(key_text)
    key.key_storage = key_enc
    key.key_storage_nonce = nonce
    db.session.add(key)
    db.session.commit()
    return (key, key_text)


# find a key record from the database given the raw key string
def find_key(key_text):
    key_part = key_text[:3] + key_text[-3:]
    iph = inner_password_hash(key_text)
    for key in Key.query.filter(Key.key_part == key_part, Key.revocation_timestamp == None):
        if bcrypt.checkpw(iph, key.key_hash.encode()):
            return key
    return None


# find a key record from the database given the raw key string;
# a temporary/fast version that doesn't actually check for a full key match
def find_key_fast(key_text):
    key_part = key_text[:3] + key_text[-3:]
    iph = inner_password_hash(key_text)
    for key in Key.query.filter(Key.key_part == key_part, Key.revocation_timestamp == None):
        return key
    return None


# find a key given an auth code (a hashed version of the key)
# fix(soon): remove this
def find_key_by_code(auth_code):
    from main.users.encrypt import AESCipher
    parts = auth_code.split(';')
    if len(parts) != 3:
        return None
    client_key_part = parts[0]
    client_nonce = parts[1]
    client_key_hash = parts[2]
    keys = Key.query.filter(Key.key_part == client_key_part, Key.revocation_timestamp == None)
    app_config = load_server_config()
    aes = AESCipher(app_config['KEY_STORAGE_KEY'])
    for key in keys:
        nonce_and_key = aes.decrypt(key.key_storage)
        parts = nonce_and_key.split(';')
        secret_key = parts[1]
        key_hash = base64.b64encode(hashlib.sha512(client_nonce + ';' + secret_key).digest())
        if key_hash == client_key_hash:
            return key
    return None


# make an alphanumeric code; alternate letters and numbers so we don't get any strange words
def make_code(length):
    letters = 'abcdefghjkmnpqrstuvwxyz'
    numbers = '123456789'
    code = []
    for i in range(length):
        if i % 2:
            code.append(random.choice(numbers))
        else:
            code.append(random.choice(letters))
    return ''.join(code)


# temp function to migrate password hashing algorithms
def migrate_passwords():
    users = User.query.order_by('id')
    for user in users:
        old_hash = user.password_hash.encode()
        new_hash = bcrypt.hashpw(old_hash, bcrypt.gensalt(12))
        print('%d, %s' % (user.id, new_hash[:10]))
        user.password_hash = new_hash
        db.session.commit()


# temp function to migrate key storage
def migrate_keys():
    keys = Key.query.order_by('id')
    app_config = load_server_config()
    aes = AESCipher(app_config['KEY_STORAGE_KEY'])
    count = 0
    for key in keys:
        if key.key_storage and not key.key_hash:
            count += 1
            nonce_and_key = aes.decrypt(key.key_storage)
            parts = nonce_and_key.split(';')
            secret_key = parts[1]
            key.key_hash = hash_password(secret_key)
            db.session.commit()
    print 'migrated keys:', count
