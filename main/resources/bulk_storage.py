import datetime
import boto
from sqlalchemy.orm.exc import NoResultFound
from main.app import app, db, storage_manager


# cache s3 connection and information in the storage manager object
def update_connection():
    if not 'connection' in storage_manager:
        from main.util import load_server_config  # fix(clean): remove?
        config = load_server_config()
        storage_manager['connection'] = boto.connect_s3(config['S3_ACCESS_KEY'], config['S3_SECRET_KEY'])
        storage_manager['bucket_name'] = config['S3_STORAGE_BUCKET']
        storage_manager['write_allowed'] = config['PRODUCTION'] or config['S3_STORAGE_BUCKET'].endswith('testing')
        storage_manager['bucket'] = storage_manager['connection'].get_bucket(storage_manager['bucket_name'])


# write data to bulk storage
def write_storage(key_path, data):
    update_connection()
    if not storage_manager['write_allowed']:
        print('write to production bucket not allowed')
        return  # make sure we aren't writing to prod from a test system; should make something more bulletproof than this
    bucket = storage_manager['connection'].get_bucket(storage_manager['bucket_name'])
    key = boto.s3.key.Key(bucket)
    key.key = key_path
    key.set_contents_from_string(data)


# read data from bulk storage
def read_storage(key_path):
    update_connection()
    bucket = storage_manager['connection'].get_bucket(storage_manager['bucket_name'])
    key = bucket.get_key(key_path)
    return key.get_contents_as_string() if key else None


# returns true if object exists in bulk storage
def storage_exists(key_path):
    update_connection()
    key = storage_manager['bucket'].get_key(key_path)
    return not key is None


# the path of resource contents in bulk storage
def storage_path(resource, revision_id):
    org_id = resource.organization_id
    if not org_id:  # fix(clean): remove this
        org_id = resource.root().id
    id_str = '%09d' % resource.id
    return '%d/%s/%s/%s/%d_%d' % (org_id, id_str[-9:-6], id_str[-6:-3], id_str[-3:], resource.id, revision_id)
