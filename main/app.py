import os
import pathlib
import importlib
from flask import Flask, render_template, redirect, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_restful import Api
from . import config
from .messages.socket_sender import SocketSender
from .messages.message_queue_basic import MessageQueueBasic
from .messages.message_sender import MessageSender

# Create and configure the application. Default config values may be overridden by a config file,
# and then overridden by environment variables.
app = Flask(__name__)
app.config.update(config.defaults())
app.config.from_pyfile(
    os.environ.get(
        'RHIZO_SERVER_SETTINGS',
        str(pathlib.Path(__file__).parent.parent) + '/settings/config.py'),
    silent=True)
app.config.update(config.environment())


# check disclaimer
assert app.config['DISCLAIMER'] == 'This is pre-release code; the API and database structure will probably change.'

# create database wrapper
db = SQLAlchemy(app)

# create REST API object
api_ = Api(app)

# create login manager
login_manager = LoginManager(app)

# create a storage manager;
# this is responsible for bulk data storage of large files/objects
# fix(later): make this into class?
if app.config.get('S3_STORAGE_BUCKET'):
    from .resources.s3_storage_manager import S3StorageManager
    print('using S3 storage manager')
    storage_manager = S3StorageManager(app.config)
elif app.config.get('FILE_SYSTEM_STORAGE_PATH'):
    from .resources.file_system_storage_manager import FileSystemStorageManager
    print('using file system storage manager')
    storage_manager = FileSystemStorageManager(app.config)
else:
    storage_manager = None

# create a static file manager
static_manager = {}

# create a message queue that will be used to handle messages to/from clients
message_queue = MessageQueueBasic()

# prepare MQTT message sender
if 'MQTT_HOST' in app.config:
    message_sender = MessageSender(app.config)
else:
    message_sender = None

# create error pages


@app.errorhandler(403)
def forbidden(error):  # pylint: disable=unused-argument
    return render_template('403.html'), 403


@app.errorhandler(404)
def not_found(error):  # pylint: disable=unused-argument
    return render_template('404.html'), 404

# require SSL for all pages; based on code from http://stackoverflow.com/questions/32237379/python-flask-redirect-to-https-from-http
# fix(clean): remove elsewhere?


@app.before_request
def force_secure():
    # fix(later): use request.startswith('https') for non-heroku installations
    if app.config.get('FORCE_SSL', False) and request.headers.get('X-Forwarded-Proto', 'http') != 'https':
        url = request.url.replace('http://', 'https://', 1)
        return redirect(url, code=301)


# start the socket sender
socket_sender = SocketSender()
socket_sender.start()

# clear existing websocket connections in database
# fix(later): revisit this
# clear_web_sockets()

# load server extensions
extensions = []
auto_load_config = app.config.get('AUTOLOAD_EXTENSIONS', False)
for extension_name in app.config.get('EXTENSIONS', []):
    print('loading extension: %s' % extension_name)
    extension_module = importlib.import_module('extensions.' + extension_name + '.ext')
    extension = extension_module.create()
    extension.name = extension_name
    extension.path = os.path.dirname(extension_module.__file__)
    if not os.path.isabs(extension.path):
        extension.path = os.getcwd() + '/' + extension.path
    extensions.append(extension)
    if auto_load_config:
        app.config.from_pyfile(extension.path + '/autoload-config.py', True)

# a static file function for templates that uses content-based hashes to avoid cache problems


def static_file(path):
    if path not in static_manager:
        static_manager[path] = file_hash(os.getcwd() + '/main/static/' + path)
    return '/static/' + path + '?rev=' + static_manager[path]


# a version of static_file that works on files for extensions
def ext_static_file(ext_name, path):
    file_id = ext_name + ':' + path
    if file_id not in static_manager:
        local_file_name = os.getcwd() + '/extensions/' + ext_name + '/static/' + path
        static_manager[file_id] = file_hash(local_file_name)
    return '/ext/' + ext_name + '/static/' + path + '?rev=' + static_manager[file_id]


# returns a quick/simple string-valued hash of a local file
def file_hash(local_file_name):
    if os.path.exists(local_file_name):
        return str(hash(open(local_file_name).read()))
    return '0'


# add static file function for templates
app.add_template_global(name='static_file', f=static_file)
app.add_template_global(name='ext_static_file', f=ext_static_file)
