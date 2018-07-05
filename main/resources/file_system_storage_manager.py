import os


class FileSystemStorageManager():

    def __init__(self, app_config):
        self.storage_path = app_config['FILE_SYSTEM_STORAGE_PATH']

    # write data to bulk storage
    def write(self, data_path, data):
        assert not data_path.startswith('/')
        path = self.storage_path + '/' + data_path
        dir_name = os.path.dirname(path)
        if not os.path.exists(dir_name):
            os.makedirs(dir_name)
        open(path, 'wb').write(data)

    # read data from bulk storage
    def read(self, data_path):
        assert not data_path.startswith('/')
        path = self.storage_path + '/' + data_path
        if os.path.exists(path):
            return open(path, 'rb').read()
        else:
            return None

    # returns true if object exists in bulk storage
    # fix(later): remove this?
    def exists(self, data_path):
        assert not data_path.startswith('/')
        return os.path.exists(self.storage_path + '/' + data_path)

    # delete a file in bulk storage
    def delete(self, data_path):
        assert not data_path.startswith('/')
        path = self.storage_path + '/' + data_path
        os.unlink(path)
