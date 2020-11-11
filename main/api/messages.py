# standard python imports
import json


# external imports
from flask import request, abort
from flask_restful import Resource as ApiResource


# internal imports
from main.app import message_queue
from main.resources.resource_util import find_resource
from main.users.permissions import access_level, ACCESS_LEVEL_WRITE
from main.users.auth import find_key


class MessageList(ApiResource):

    # get a list of messages
    def get(self):
        pass

    # create/send a new message
    def post(self):
        folder_path = request.values.get('folderPath', request.values.get('folder_path', ''))
        if not folder_path:
            abort(400)
        if not folder_path.startswith('/'):
            abort(400)
        folder = find_resource(folder_path)
        if not folder:
            abort(404)
        if access_level(folder.query_permissions()) < ACCESS_LEVEL_WRITE:
            abort(403)
        if not request.authorization:
            abort(403)
        key = find_key(request.authorization.password)
        if not key:
            abort(403)
        type = request.values['type']
        parameters = json.loads(request.values['parameters'])
        sender_controller_id = key.access_as_controller_id  # None if access as user
        sender_user_id = key.access_as_user_id  # None if access as controller
        message_queue.add(folder.id, None, type, parameters, sender_controller_id = sender_controller_id, sender_user_id = sender_user_id)
        return {'status': 'ok'}
