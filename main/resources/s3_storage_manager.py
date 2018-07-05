import boto


class S3StorageManager():

    def __init__(self, app_config):
        self.connection = boto.connect_s3(app_config['S3_ACCESS_KEY'], app_config['S3_SECRET_KEY'])
        self.bucket_name = app_config['S3_STORAGE_BUCKET']
        self.write_allowed = app_config['PRODUCTION'] or app_config['S3_STORAGE_BUCKET'].endswith('testing')
        self.bucket = self.connection.get_bucket(self.bucket_name)  # fix(soon): should we use this in read/write? currently just using it in exists()
        self.verbose = False

    # write data to bulk storage
    def write(self, data_path, data):
        if not self.write_allowed:
            print('write to production bucket not allowed')
            return  # make sure we aren't writing to prod from a test system; should make something more bulletproof than this
        if self.verbose:
            print('writing to bucket: %s, key: %s, data len: %d' % (self.bucket_name, data_path, len(data)))
        bucket = self.connection.get_bucket(self.bucket_name)
        key = boto.s3.key.Key(bucket)
        key.key = data_path
        key.set_contents_from_string(data)

    # read data from bulk storage
    def read(self, data_path):
        bucket = self.connection.get_bucket(self.bucket_name)
        key = bucket.get_key(data_path)
        if self.verbose:
            print('reading from bucket: %s, key: %s' % (self.bucket_name, data_path))
        return key.get_contents_as_string() if key else None

    # returns true if object exists in bulk storage
    # fix(later): remove or improve this
    def exists(self, data_path):
        key = self.bucket.get_key(data_path)
        return not key is None

    # fix(soon): implement and use this
    def delete(self, data_path):
        pass
