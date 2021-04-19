# standard python imports
import json
import base64
import logging
import datetime


# external imports
import gevent
from flask import request
from flask_login import current_user
from sqlalchemy import not_
from sqlalchemy.orm.exc import NoResultFound


# internal imports
from main.app import db, socket_sender, message_queue
from main.users.auth import find_key
from main.users.permissions import ACCESS_LEVEL_READ, ACCESS_LEVEL_WRITE
from main.messages.outgoing_messages import handle_send_email, handle_send_text_message
from main.messages.web_socket_connection import WebSocketConnection
from main.resources.models import Resource, ControllerStatus
from main.resources.resource_util import find_resource, update_sequence_value

VERBOSE = False


# The MessageSubscription class represents a client subscription to messages associated with a set of folders.
class MessageSubscription(object):

    # create a message subscription
    def __init__(self, folder_id, message_type, include_children=False):
        self.folder_ids = [folder_id]  # fix(later): change back to single ID
        self.message_type = message_type  # None means match any
        self.include_children = include_children
        if self.include_children:  # fix(later): limit this to a certain number and return warning if too many
            resource = Resource.query.filter(Resource.id == folder_id, not_(Resource.deleted)).one()
            self.folder_ids += resource.descendent_folder_ids()
            if VERBOSE:  # check verbosity level
                print('subscribe folder IDs: %s' % self.folder_ids)

    # returns true if a given message record matches this subscription
    def matches(self, message):
        folder_matches = message.folder_id in self.folder_ids
        type_matches = (self.message_type is None or self.message_type == message.type)
        if VERBOSE:  # check verbosity level
            print('        folderMatches: %d, typeMatches: %d' % (folder_matches, type_matches))
        return folder_matches and type_matches

    # return the subscription as a JSON-ready dictionary
    def as_dict(self):
        return {
            'folder_id': self.folder_ids[0],  # fix(later): return all
            'message_type': self.message_type,
        }


# set up a new websocket; handle incoming messages on the socket
def manage_web_socket(ws):
    ws_conn = WebSocketConnection(ws)

    # handle key-based authentication
    if request.authorization:
        logging.debug('ws connect with auth')
        auth = request.authorization
        key = find_key(auth.password)  # key is provided as HTTP basic auth password
        if not key:
            logging.debug('key not found')
            return  # would be nice to abort(403), but doesn't look like you can do that inside a websocket handler
        ws_conn.controller_id = key.access_as_controller_id
        ws_conn.user_id = key.access_as_user_id
        ws_conn.auth_method = 'key'
        if ws_conn.controller_id:
            try:
                controller_status = ControllerStatus.query.filter(ControllerStatus.id == ws_conn.controller_id).one()
                controller_status.last_connect_timestamp = datetime.datetime.utcnow()
                controller_status.client_version = auth.username  # client should pass version in HTTP basic auth user name
                db.session.commit()
            except NoResultFound:
                logging.debug('warning: unable to find controller status record')

    # handle regular user authentication
    elif current_user.is_authenticated:
        logging.debug('ws connect with web browser session')
        ws_conn.user_id = current_user.id
        ws_conn.auth_method = 'user'

    # register this socket to receive outgoing messages
    socket_sender.register(ws_conn)

    # process incoming messages
    while not ws_conn.ws.closed:
        message = ws_conn.ws.receive()
        if message:
            try:
                message_struct = json.loads(message)
            except json.JSONDecodeError:
                break  # if client sends bad message; close this connection
            process_web_socket_message(message_struct, ws_conn)
        gevent.sleep(0.05)  # sleep to let other stuff run

    # websocket has been closed
    ws_conn.log_disconnect()
    socket_sender.unregister(ws_conn)
    db.session.close()


# handle a message received from a websocket
# fix(later): add more comprehensive approach to authentication on websocket messages; currently just check for a couple types
def process_web_socket_message(message_struct, ws_conn):
    message_type = message_struct['type']
    message_debug = False

    # handle new connection; no longer used; websocket should be authenticated using HTTP basic auth
    if message_type == 'connect':
        pass

    # handle watchdog message (updates controller status record)
    elif message_type == 'watchdog':
        if ws_conn.controller_id:
            controller_status = ControllerStatus.query.filter(ControllerStatus.id == ws_conn.controller_id).one()
            controller_status.last_watchdog_timestamp = datetime.datetime.utcnow()
            db.session.commit()

    # handle ping (does nothing; used to keep connection active)
    elif message_type == 'ping':
        pass

    # handle subscription (used to subscribe to messages from one or more folders)
    elif message_type == 'subscribe':

        # process the subscription
        parameters = message_struct['parameters']
        subscriptions = parameters.get('subscriptions', [])
        for subscription in subscriptions:
            # fix(clean): remove support for folder IDs and old message args
            folder_path = subscription.get('folder', subscription.get('folderId', None))
            message_type = subscription.get('message_type', subscription.get('messageType', None))
            include_children = subscription.get('include_children', subscription.get('includeChildren', False))

            # fix(clean): remove "[self]" option
            if folder_path == 'self' or folder_path == '[self]':
                folder_id = ws_conn.controller_id
            elif hasattr(folder_path, 'strip'):
                resource = find_resource(folder_path)
                if not resource:
                    print('unable to find subscription folder: %s' % folder_path)
                    return
                folder_id = resource.id
            else:
                folder_id = folder_path

            # if subscription is allowed, store it
            # fix(later): send a message back if not allowed
            if ws_conn.access_level(folder_id) >= ACCESS_LEVEL_READ:
                if message_debug:
                    print('subscribe folder: %s (%d), message type: %s' % (folder_path, folder_id, message_type))
                ws_conn.subscriptions.append(MessageSubscription(folder_id, message_type, include_children=include_children))

    # fix(soon): remove this case after clients are updated
    elif message_type == 'setNode' or message_type == 'updateSequence' or message_type == 'update_sequence':
        if ws_conn.controller_id:
            parameters = message_struct['parameters']
            if message_type == 'setNode':  # fix(soon): remove this case
                seq_name = parameters['node']
            else:
                seq_name = parameters['sequence']
            if not seq_name.startswith('/'):  # handle relative sequence names
                resource = Resource.query.filter(Resource.id == ws_conn.controller_id).one()
                # this is ok for now since .. doesn't have special meaning in resource path (no way to escape controller folder)
                seq_name = resource.path() + '/' + seq_name
            timestamp = parameters.get('timestamp', '')  # fix(soon): need to convert to datetime
            if not timestamp:
                timestamp = datetime.datetime.utcnow()
            value = parameters['value']
            if 'encoded' in parameters:
                value = base64.b64decode(value)

            # remove this; require clients to use REST POST for images
            resource = find_resource(seq_name)
            if not resource:
                return
            system_attributes = json.loads(resource.system_attributes) if resource.system_attributes else None
            if system_attributes and system_attributes['data_type'] == Resource.IMAGE_SEQUENCE:
                value = base64.b64decode(value)
            else:
                value = str(value)

            update_sequence_value(resource, seq_name, timestamp, value)
            db.session.commit()

    # update a resource
    elif message_type == 'write_resource':
        parameters = message_struct['parameters']
        if 'path' and 'data' in parameters:
            path = parameters['path']
            if not path.startswith('/'):  # fix(soon): remove this after clients updated
                path = '/' + path
            data = parameters['data']
            resource = find_resource(path)
            if resource:
                if ws_conn.access_level(resource.id) >= ACCESS_LEVEL_WRITE:
                    timestamp = datetime.datetime.utcnow()
                    update_sequence_value(resource, path, timestamp, data)
                    db.session.commit()
                else:
                    socket_sender.send_error(ws_conn, 'permission error: %s' % path)
            else:
                socket_sender.send_error(ws_conn, 'resource not found: %s' % path)
        else:
            socket_sender.send_error(ws_conn, 'expected data and path parameters for write_resource message')

    # handle request for detailed message logging
    elif message_type == 'debug_messaging':
        parameters = message_struct['parameters']
        enable = bool(parameters['enable'])
        level = logging.DEBUG if enable else logging.INFO
        logging.getLogger().setLevel(level)

    # handle other action messages
    elif message_type in ('sendEmail', 'sendTextMessage', 'send_email', 'send_text_message'):
        if ws_conn.controller_id:  # only support these messages from controllers, not browsers
            if message_type == 'sendEmail' or message_type == 'send_email':
                handle_send_email(ws_conn.controller_id, message_struct['parameters'])
            elif message_type == 'sendTextMessage' or message_type == 'send_text_message':
                handle_send_text_message(ws_conn.controller_id, message_struct['parameters'])

    # for other types, assume that we want to create a message record
    else:

        # figure out target folder
        if 'folder' in message_struct:
            folder_name = message_struct['folder']
            if message_debug:
                print('message to folder: %s' % folder_name)
            if hasattr(folder_name, 'startswith') and folder_name.startswith('/'):
                if message_debug:
                    print('message to folder name: %s' % folder_name)
                folder = find_resource(folder_name)  # assumes leading slash
                if folder:
                    folder_id = folder.id
                    if message_debug:
                        print('message to folder id: %d' % folder_id)
                else:
                    print('message to unknown folder (%s)' % folder_name)
                    return
            else:
                folder_id = folder_name  # fix(soon): remove this case
        elif ws_conn.controller_id:
            folder_id = ws_conn.controller_id
        else:
            print('message (%s) without folder or controller; discarding' % message_type)
            return

        # if allowed, create a message for the folder
        if ws_conn.access_level(folder_id) >= ACCESS_LEVEL_WRITE:
            parameters = message_struct['parameters']
            # fix(soon): can we move this spawn above access level check (might require request context)
            gevent.spawn(
                message_queue.add, folder_id, None, message_type, parameters, sender_controller_id=ws_conn.controller_id,
                sender_user_id=ws_conn.user_id)
