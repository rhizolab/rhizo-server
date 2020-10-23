import datetime
import json
import os

from flask_restful import Api
import pytest

from main.api.messages import MessageList
from main.api.resources import ResourceList, ResourceRecord
import main.app
import main.messages.models
from main.resources.models import ControllerStatus, Resource
from main.resources.resource_util import create_system_resources
from main.users.auth import create_key
from main.users.models import User
from main.users.permissions import ACCESS_TYPE_PUBLIC, ACCESS_LEVEL_WRITE


# noinspection PyUnresolvedReferences
@pytest.fixture(scope='session')
def _db(app):
    """A clean database initialized with system resources.

    This is used internally by the flask-sqlalchemy plugin; if you want a SQLAlchemy session,
    add a "db_session" parameter to your test function rather than using this.
    """
    # Override the initialization of main.app.db that happens when main.app is imported
    main.app.db.init_app(app)

    with main.app.app.app_context():
        main.app.db.create_all()
        create_system_resources()

    return main.app.db


@pytest.fixture(scope='session')
def app(request):
    """An instance of the Flask app that points at a test database.

    If the TEST_DATABASE environment variable is set to "postgres", launch a temporary PostgreSQL
    server that gets torn down at the end of the test run.
    """
    database = os.environ.get('TEST_DATABASE', 'sqlite')
    if database == 'postgres':
        try:
            psql = request.getfixturevalue('postgresql_proc')
            uri = f'postgresql+psycopg2://{psql.user}:@{psql.host}:{psql.port}/'
        except pytest.FixtureLookupError:
            raise Exception('TEST_POSTGRESQL was set but pytest-postgresql was not installed')
    else:
        uri = 'sqlite://'

    config = main.app.app.config
    config.from_object('settings.config')
    config['SQLALCHEMY_DATABASE_URI'] = uri
    return main.app.app


@pytest.fixture(scope='session')
def api(app):
    """Initialize the Flask app with endpoints.

    You typically won't use this fixture directly, just declare it to make the endpoints available.
    """
    api = Api(app)

    api.add_resource(MessageList, '/api/v1/messages')
    api.add_resource(ResourceList, '/api/v1/resources')
    api.add_resource(ResourceRecord, '/api/v1/resources/<path:resource_path>')

    return api


@pytest.fixture(scope='function')
def folder_resource(db_session):
    """A basic folder Resource called '/folder'."""

    folder_resource = Resource(name='folder', type=Resource.BASIC_FOLDER)
    db_session.add(folder_resource)
    db_session.flush()
    folder_resource.permissions = json.dumps(
        [[ACCESS_TYPE_PUBLIC, folder_resource.id, ACCESS_LEVEL_WRITE]])

    return folder_resource


@pytest.fixture(scope='function')
def controller_resource(db_session, folder_resource):
    """A controller folder Resource called '/folder/controller'."""
    controller_resource = Resource(name='controller',
                                   type=Resource.CONTROLLER_FOLDER,
                                   parent_id=folder_resource.id)
    db_session.add(controller_resource)
    db_session.flush()

    controller_status = ControllerStatus(id=controller_resource.id, client_version='?',
                                         web_socket_connected=False,
                                         watchdog_notification_sent=False, attributes='{}')
    db_session.add(controller_status)

    return controller_resource


@pytest.fixture(scope='function')
def organization_resource(db_session):
    """An organization folder Resource called '/organization'."""
    resource = Resource(name='organization', type=Resource.ORGANIZATION_FOLDER)
    db_session.add(resource)
    db_session.flush()

    return resource


@pytest.fixture(scope='function')
def user_resource(db_session):
    """A User called 'test'."""
    resource = User(user_name='test', email_address='test@terraformation.com',
                    password_hash='x', full_name='Dummy User', info_status='[]',
                    attributes='{}', deleted=False, creation_timestamp=datetime.datetime.utcnow(),
                    role=User.STANDARD_USER)
    db_session.add(resource)

    return resource


@pytest.fixture(scope='function')
def controller_key_resource(db_session, user_resource, organization_resource, controller_resource):
    """A Key that accesses data as a controller. This can be used to make authenticated requests.

    This generates a random secret key. The secret key in plaintext form is added to the object
    in a property called "text" (that property is not part of the Key model).
    """
    key, key_text = create_key(user_resource.id, organization_resource.id, None,
                               controller_resource.id)

    # Stash the key text on the object so the caller can use it for authentication
    key.text = key_text

    return key
