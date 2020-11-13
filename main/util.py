import os  # fix(clean): remove?
import datetime
from functools import wraps
import flask  # fix(clean): remove?
from flask import request, redirect, current_app


# decorator require SSL for a view
# from http://flask.pocoo.org/snippets/93/
def ssl_required(fn):
    @wraps(fn)
    def decorated_view(*args, **kwargs):
        if current_app.config.get('SSL'):
            if request.headers.get('X-Forwarded-Proto', 'http') == 'https':  # request.is_secure:
                return fn(*args, **kwargs)
            else:
                return redirect(request.url.replace('http://', 'https://'))
        return fn(*args, **kwargs)
    return decorated_view


# parse an ISO formatted timestamp string, converting it to a python datetime object;
# note: this function is also defined in client code
def parse_json_datetime(json_timestamp):
    assert json_timestamp.endswith('Z')
    format = ''
    if '.' in json_timestamp:
        format = '%Y-%m-%dT%H:%M:%S.%f'
    else:
        format = '%Y-%m-%dT%H:%M:%S'
    if json_timestamp.endswith(' Z'):
        format += ' Z'
    else:
        format += 'Z'
    return datetime.datetime.strptime(json_timestamp, format)


# get the current server configuration module (for use when current_app isn't available)
# fix(soon): try to remove this; can probably use current_app.config in most places
def load_server_config():
    server_config = flask.Config('.')
    if 'PROD' in os.environ:
        server_config.from_object('prod_config')
    else:
        server_config.from_object('settings.config')
    return server_config
