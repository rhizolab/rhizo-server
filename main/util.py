import logging
import os  # fix(clean): remove?
import datetime
from functools import wraps
from typing import Dict

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
    format_str = ''
    if '.' in json_timestamp:
        format_str = '%Y-%m-%dT%H:%M:%S.%f'
    else:
        format_str = '%Y-%m-%dT%H:%M:%S'
    if json_timestamp.endswith(' Z'):
        format_str += ' Z'
    else:
        format_str += 'Z'
    return datetime.datetime.strptime(json_timestamp, format_str)


# get the current server configuration module (for use when current_app isn't available)
# fix(soon): try to remove this; can probably use current_app.config in most places
def load_server_config():
    server_config = flask.Config('.')
    if 'PROD' in os.environ:
        server_config.from_object('prod_config')
    else:
        server_config.from_object('settings.config')
    return server_config


def prep_logging(app_config: Dict[str, str]):
    """Initialize logging based on the application config.

    The log level is set to DEBUG if the DEBUG_MESSAGING config option is truthy, else INFO.

    If the MESSAGING_LOG_PATH config option is set, logs are written to a file in that
    directory in addition to the console.
    """
    root = logging.getLogger()
    if root.hasHandlers():
        # Logging was already initialized.
        return

    formatter = logging.Formatter('%(asctime)s: %(levelname)s: %(message)s')

    level = logging.DEBUG if app_config['DEBUG_MESSAGING'] else logging.INFO

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    root.addHandler(console_handler)
    root.setLevel(level)

    log_path = app_config['MESSAGING_LOG_PATH']
    if log_path:
        time_str = datetime.datetime.now().strftime('%Y-%m-%d-%H%M%S')
        file_handler = logging.FileHandler('%s/%d-%s.txt' % (log_path, os.getpid(), time_str))
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
