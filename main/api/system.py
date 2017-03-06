# standard python imports


# external imports
from sqlalchemy import func
from flask import abort
from flask_restful import Resource as ApiResource
from flask_login import current_user, login_required


# internal imports
from main.app import db
from main.users.models import User
from main.messages.models import Message
from main.resources.models import Resource, ResourceRevision, Thumbnail


class SystemStats(ApiResource):

    # get information about the current state of the server system
    @login_required
    def get(self):
        if current_user.role != current_user.SYSTEM_ADMIN:
            abort(403)
        s = db.session
        return {
            'user_count': s.query(func.count(User.id)).scalar(),
            'resource_count': s.query(func.count(Resource.id)).scalar(),
            'thumbnail_count': s.query(func.count(Thumbnail.id)).scalar(),
            'resource_revision_count': s.query(func.count(ResourceRevision.id)).scalar(),
            'message_count': s.query(func.count(Message.id)).scalar(),
        }
