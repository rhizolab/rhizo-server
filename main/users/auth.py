# standard python imports
import time  # fix(clean): remove
import random
import string
import base64
import hashlib
import datetime


# external imports
import bcrypt
from flask import current_app
from sqlalchemy import not_
from sqlalchemy.orm.exc import NoResultFound


# internal imports
from main.app import db
from main.app import login_manager
from main.users.models import User, Key, OrganizationUser
from main.util import load_server_config  # fix(clean): remove?


# return a user model for the given user ID
@login_manager.user_loader
def load_user(user_id):
    try:
        user = User.query.filter(User.id == int(user_id), not_(User.deleted)).one()
    except NoResultFound:
        user = None
    return user


# return a user model for the given password and user name / email address;
# returns None if user not found or password doesn't match
def login_validate(user_name_or_email, password):
    if not user_name_or_email or not password:
        return None
    try:  # fix(faster): combine into a single query
        user = User.query.filter(User.email_address == user_name_or_email, not_(User.deleted)).one()
    except NoResultFound:
        try:
            user = User.query.filter(User.user_name == user_name_or_email, not_(User.deleted)).one()
        except NoResultFound:
            user = None
    if user and not bcrypt.checkpw(inner_password_hash(password).encode(), user.password_hash.encode()):
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
    return base64.standard_b64encode(hashlib.sha512((password + salt).encode('utf-8')).digest()).decode()


# compute a full hash of the password
def hash_password(password):
    return bcrypt.hashpw(inner_password_hash(password).encode(), bcrypt.gensalt(12)).decode('utf-8')


# create a new access key associated with a user or controller
def create_key(creation_user_id, organization_id, access_as_user_id, access_as_controller_id, key_text=None):

    # compute the key text
    if not key_text:
        key_text = current_app.config['KEY_PREFIX'] + generate_access_code(50)

    # create a key record
    key = Key()
    key.organization_id = organization_id
    key.creation_user_id = creation_user_id
    key.creation_timestamp = datetime.datetime.utcnow()
    key.access_as_user_id = access_as_user_id
    key.access_as_controller_id = access_as_controller_id
    key.key_part = key_text[:3] + key_text[-3:]
    key.key_hash = hash_password(key_text)
    key.key_storage = ''  # not used; should remove
    key.key_storage_nonce = ''  # not used; should remove
    db.session.add(key)
    db.session.commit()
    return (key, key_text)


# find a key record from the database given the raw key string
def find_key(key_text):
    key_part = key_text[:3] + key_text[-3:]
    iph = inner_password_hash(key_text)
    for key in Key.query.filter(Key.key_part == key_part, Key.revocation_timestamp.is_(None)):
        if key.key_hash.startswith('$2b$'):  # handle bcrypt hash
            if bcrypt.checkpw(iph.encode(), key.key_hash.encode()):
                key.key_hash = iph
                db.session.commit()
                return key
        elif iph == key.key_hash:  # handle sha512 hash
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


# generate a random alphanumeric code
# fix(clean): merge with other similar functions
def generate_access_code(length):
    letter_choices = string.ascii_uppercase + string.digits
    letters = [random.SystemRandom().choice(letter_choices) for x in range(length)]
    return ''.join(letters)


# temp function to migrate password hashing algorithms
def migrate_passwords():
    users = User.query.order_by('id')
    for user in users:
        old_hash = user.password_hash.encode()
        new_hash = bcrypt.hashpw(old_hash, bcrypt.gensalt(12))
        print('%d, %s' % (user.id, new_hash[:10]))
        user.password_hash = new_hash
        db.session.commit()


# create a token used to authenticate with the MQTT broker/server
def message_auth_token(user_id):
    try:
        salt = current_app.config['MESSAGE_TOKEN_SALT']
    except RuntimeError:  # handle case that we're running outside app (e.g. in a worker process)
        config = load_server_config()
        salt = config['MESSAGE_TOKEN_SALT']

    # find/create a key for this user
    if user_id:
        keys = Key.query.filter(Key.access_as_user_id == user_id, Key.revocation_timestamp.is_(None))
        if keys.count():
            key_hash = keys[0].key_hash
            key_id = keys[0].id
        else:
            org_users = OrganizationUser.query.filter(OrganizationUser.user_id == user_id)
            if org_users.count():
                organization_id = org_users[0].organization_id  # for now we'll just create a key for one organization; revisit this
                (key, _) = create_key(user_id, organization_id, user_id, None)
                key_hash = key.key_hash
                key_id = key.id
            else:
                return ''
    else:  # this case is used for inter-server access; we could create special keys for inter-server access (access from another server, not a user)
        key_hash = ''
        key_id = 0

    # generate the token
    nonce = generate_access_code(10)
    timestamp = int(time.time())
    hash_message = '%d,%d,%s,%s,%s' % (timestamp, key_id, nonce, salt, key_hash)
    b64hash = base64.standard_b64encode(hashlib.sha512(hash_message.encode()).digest()).decode()
    return '0,%d,%d,%s,%s' % (timestamp, key_id, nonce, b64hash)
