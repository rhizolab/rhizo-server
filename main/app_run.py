# this file can be used to provide an app object to gunicorn;
# it includes the app object from the app module and makes sure all views/models are imported;
# it provides an alternative to putting everything inside an __init__.py file;
# it isn't used by the top-level run.py program
from app import *


# import all views
from main.users import views
from main.api import views
from main.resources import views  # this should be last because it includes the catch-all resource viewer


# import all models
from main.users import models
from main.messages import models
from main.resources import models
