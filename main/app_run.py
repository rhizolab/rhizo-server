"""
this file can be used to provide an app object to gunicorn;
it includes the app object from the app module and makes sure all views/models are imported;
it provides an alternative to putting everything inside an __init__.py file;
it isn't used by the top-level run.py program
"""
from main.app import app

# import all views
import main.users.views
import main.api.views
import main.resources.views  # this should be last because it includes the catch-all resource viewer

# import all models
import main.users.models
import main.messages.models
import main.resources.models


def _make_use_of_imports():
    """Reference all the imported things so lint tools won't complain about them being unused."""
    if app is None or main.resources.models is None:
        pass
