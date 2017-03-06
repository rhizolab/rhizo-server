from flask_login import current_user
from sqlalchemy.orm.exc import NoResultFound
from main.app import db
from main.users.permissions import access_level, ACCESS_LEVEL_NONE
from main.users.models import User
from main.resources.models import Resource, ControllerStatus


# The WebSocketConnection class represents a connection to a client controller or browser.
# It is a wrapper for a flask_socket websocket object.
class WebSocketConnection(object):

    # create connection with a new/live flask_socket websocket object
    def __init__(self, ws):
        self.ws = ws
        self.subscriptions = []
        self.user_id = None
        self.controller_id = None
        self.auth_method = None
        self.connected = True

    # returns level of permissions client (user or controller) has for this folder
    def access_level(self, folder_id):
        client_access_level = ACCESS_LEVEL_NONE
        try:
            folder = Resource.query.filter(Resource.id == folder_id, Resource.deleted == False).one()

            # if this is a browser websocket, controller_id will be None and access_level will use current_user
            client_access_level = access_level(folder.query_permissions(), controller_id = self.controller_id)
        except NoResultFound:
            pass
        return client_access_level

    # call this when we detect the the connection has been terminated
    def set_disconnected(self):
        self.connected = False
        if self.controller_id:
            print('disconnect controller: %d' % self.controller_id)
            try:
                controller_status = ControllerStatus.query.filter(ControllerStatus.id == self.controller_id).one()
                controller_status.web_socket_connected = False
                db.session.commit()
            except:
                print('unable to find controller')
        elif self.user_id:
            print('disconnect user: %d' % self.user_id)
        else:
            print('disconnect without controller_id or user_id')
