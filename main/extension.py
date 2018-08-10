from flask import render_template_string
from collections import defaultdict, OrderedDict

# a super-class to be sub-classes by server extension packages
class Extension(object):

    # create a new extension object
    def __init__(self, extension_interface=None):
        self.name = None  # set in app.py
        self.path = None  # set in app.py
        self.extension_interface = extension_interface

    # render a template from the extension's templates folder
    def render_template(self, name, **kwargs):
        template_file_name = self.path + '/templates/' + name
        template = open(template_file_name).read()
        return render_template_string(template, **kwargs)

class ExtensionInterface():

    def __init__(self):
        self._listeners = defaultdict(OrderedDict)

    def on(self, eventName, listener):
        self._listeners[eventName][listener] = listener

    def off(self, eventName, listener):
        self._listeners[eventName].pop(listener)

    def emit(self, eventName, *args, **kwargs):
        for listener in list(self._listeners[eventName].values()):
            listener(*args, **kwargs)


