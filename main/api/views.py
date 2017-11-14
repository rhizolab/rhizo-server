# standard python imports
import json
import base64
import datetime


# external imports
import gevent  # fix(clean): remove?
from flask import request, abort, session
from flask_login import current_user


# internal imports from outside API directory
from main.app import db, app, api_, sockets
from main.util import ssl_required
from main.users.permissions import generate_access_code
from main.messages.socket_receiver import manage_web_socket
from main.resources.models import Resource


# internal local (API) imports
from users import UserRecord, UserList
from keys import KeyRecord, KeyList
from organizations import OrganizationList, OrganizationUserRecord, OrganizationUserList
from messages import MessageList
from resources import ResourceRecord, ResourceList
from pins import PinRecord, PinList
from system import SystemStats


# API resources
api_.add_resource(UserList, '/api/v1/users')
api_.add_resource(UserRecord, '/api/v1/users/<string:id>')
api_.add_resource(KeyList, '/api/v1/keys')
api_.add_resource(KeyRecord, '/api/v1/keys/<int:key_id>')
api_.add_resource(OrganizationList, '/api/v1/organizations')
api_.add_resource(OrganizationUserList, '/api/v1/organizations/<int:org_id>/users')
api_.add_resource(OrganizationUserRecord, '/api/v1/organizations/<int:org_id>/users/<int:org_user_id>')
api_.add_resource(ResourceList, '/api/v1/resources')
api_.add_resource(ResourceRecord, '/api/v1/resources/<path:resource_path>')
api_.add_resource(PinList, '/api/v1/pins')
api_.add_resource(PinRecord, '/api/v1/pins/<int:pin>')
api_.add_resource(SystemStats, '/api/v1/system/stats')
api_.add_resource(MessageList, '/api/v1/messages')


# endpoint for creating a new websocket connect
@sockets.route('/api/v1/connectWebSocket')
#@ssl_required
def old_connect_web_socket(ws):
    manage_web_socket(ws)


# endpoint for creating a new websocket connect
@sockets.route('/api/v1/websocket')
#@ssl_required
def connect_web_socket(ws):
    manage_web_socket(ws)


# ======== CSRF PROTECTION ========
# based on http://flask.pocoo.org/snippets/3/


# check for CSRF token on every user POST
# (we only check CSRF token if user is authenticated; not needed for API calls using keys)
# the CSRF token provided with the request (in the form data) should match the CSRF token we put into the user's cookie
@app.before_request
def csrf_protect():
    if request.method != 'GET' and current_user.is_authenticated:
        token = session.get('csrf_token', None)
        if not token:
            print('CSRF token not found: %s' % request.url_rule)
            abort(403)
        if token != request.form.get('csrf_token'):
            print('CSRF invalid: %s' % request.url_rule)
            abort(403)


# generate a CSRF token for the current session
def generate_csrf_token():
    if 'csrf_token' not in session:
        session['csrf_token'] = generate_access_code(30)
    return session['csrf_token']


# add CSRF token function that can be used in templates
app.jinja_env.globals['csrf_token'] = generate_csrf_token
