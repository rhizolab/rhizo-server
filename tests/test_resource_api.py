import base64
import random
from typing import Union

import pytest


class TestResourceOperations:
    @pytest.fixture(autouse=True)
    def setup(self, client, api, folder_resource):
        self.client = client

    def _write_then_read(self, content: Union[bytes, str]):
        """Write a file and then read it again to make sure the content matches."""
        url_prefix = '/api/v1/resources'
        folder = '/folder'
        filename = 'test.txt'
        url = f'{url_prefix}{folder}/{filename}'

        if type(content) == str:
            content = content.encode()

        base64_content = base64.b64encode(content)

        file_info = {
            'data': base64_content,
            'path': folder,
            'file': filename
        }

        assert self.client.post(url, data=file_info).status_code == 200

        result = self.client.get(url)

        assert result.data == content

    def test_read_write_file(self):
        content = f'This is a test.\n{random.randint(1, 1000)}.\n'
        self._write_then_read(content)

    def test_read_write_large_text_file(self):
        content = f'This is test {random.randint(1, 1000)}' * 1000
        self._write_then_read(content)

    def test_read_write_large_binary_file(self):
        content = bytes(bytearray(list(range(256))) * 1000)
        self._write_then_read(content)

    def test_file_exists(self):
        assert self.client.get('/api/v1/resources/folder/nonexistentFile?meta=1').status_code == 404

    def test_create_multiple_folder_levels(self):
        resources_url = '/api/v1/resources'
        parent_folder = f'/folder/parent{random.randint(1, 999999)}'
        child_folder = f'child{random.randint(1, 999999)}'
        folder_resource_url = f'{resources_url}{parent_folder}/{child_folder}?meta=1'

        file_info = {'path': parent_folder, 'name': child_folder, 'type': 10}
        assert self.client.post(resources_url, data=file_info).status_code == 200

        assert self.client.get(folder_resource_url).status_code == 200

    def test_read_write_text_sequence(self):
        folder = '/folder'
        filename = 'test-sequence'
        resources_url = '/api/v1/resources'
        sequence_url = f'{resources_url}{folder}/{filename}'
        items = ['ok'.encode(), 'test'.encode()]

        assert self.client.post(resources_url,
                                data={'path': folder, 'name': filename,
                                      'type': 2}).status_code == 200

        for item in items:
            assert self.client.post(
                sequence_url,
                data={'data': base64.b64encode(item)}
            ).status_code == 200

            result = self.client.get(sequence_url)
            assert result.status_code == 200
            assert self.client.get(sequence_url).data == item


class TestSendMessage:
    @pytest.fixture(autouse=True)
    def setup(self, client, folder_resource, user_resource, controller_key_resource):
        auth = base64.b64encode(
            f'{user_resource.user_name}:{controller_key_resource.text}'.encode()).decode()
        self.headers = {'Authorization': f'Basic {auth}'}
        self.url = '/api/v1/messages'
        self.client = client

    def _send_message(self, folder_path):
        message_info = {
            'folder_path': folder_path,
            'type': 'testMessage',
            'parameters': '{"abc":"test","xyz":777}',
        }

        return self.client.post('/api/v1/messages', data=message_info, headers=self.headers)

    def test_valid_folder(self):
        assert self._send_message('/folder').status_code == 200

    def test_nonexistent_folder(self):
        assert self._send_message('/nonexistent').status_code == 404

    def test_unauthorized_folder(self):
        assert self._send_message('/system').status_code == 403
