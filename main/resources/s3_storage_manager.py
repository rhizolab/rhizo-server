import io

import boto3
from botocore.errorfactory import ClientError


class S3StorageManager():

    def __init__(self, app_config):
        if 'S3_ACCESS_KEY' in app_config:
            self.s3 = boto3.resource(
                's3',
                aws_access_key_id=app_config['S3_ACCESS_KEY'],
                aws_secret_access_key=app_config['S3_SECRET_KEY']
            )
        else:
            self.s3 = boto3.resource('s3')
        self.bucket_name = app_config['S3_STORAGE_BUCKET']
        self.write_allowed = app_config['PRODUCTION'] or app_config['S3_STORAGE_BUCKET'].endswith('testing')
        self.bucket = self.s3.Bucket(self.bucket_name)
        self.verbose = False

    # write data to bulk storage
    def write(self, data_path, data):
        if not self.write_allowed:
            print('write to production bucket not allowed')
            return  # make sure we aren't writing to prod from a test system; should make something more bulletproof than this
        if self.verbose:
            print('writing to bucket: %s, key: %s, data len: %d' % (self.bucket_name, data_path, len(data)))
        self.bucket.put_object(Body=data, Key=data_path)

    # read data from bulk storage
    def read(self, data_path):
        if self.verbose:
            print('reading from bucket: %s, key: %s' % (self.bucket_name, data_path))
        obj = self.bucket.Object(data_path).get()
        try:
            return obj['Body'].read()
        except ClientError as e:
            if e.response['ResponseMetadata']['HTTPStatusCode'] == 404:
                return None
            else:
                raise e

    # returns true if object exists in bulk storage
    # fix(later): remove or improve this
    def exists(self, data_path):
        response = self.s3.list_objects_v2(Bucket=self.bucket_name, Prefix=data_path)
        for obj in response.get('Contents', []):
            if obj['Key'] == data_path:
                return True
        return False

    # fix(soon): implement and use this
    def delete(self, data_path):
        pass
