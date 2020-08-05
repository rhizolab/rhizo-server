from flask import render_template_string

# a super-class to be sub-classes by server extension packages
class Extension(object):

    # create a new extension object
    def __init__(self):
        self.name = None  # set in app.py
        self.path = None  # set in app.py

    # render a template from the extension's templates folder
    def render_template(self, name, **kwargs):
        template_file_name = self.path + '/templates/' + name
        template = open(template_file_name).read()
        return render_template_string(template, **kwargs)
