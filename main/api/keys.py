# standard python imports
import datetime


# external imports
from flask import request, abort
from sqlalchemy.orm.exc import NoResultFound
from flask_restful import Resource as ApiResource
from flask_login import current_user  # fix(later): remove


# internal imports
from main.app import db
from main.users.models import Key, User
from main.users.permissions import access_level, ACCESS_LEVEL_WRITE
from main.users.auth import create_key, find_key
from main.resources.models import Resource


class KeyRecord(ApiResource):

    # get a key
    def get(self, key_id):
        pass

    # revoke or remove a key
    def delete(self, key_id):

        # get the key
        try:
            key = Key.query.filter(Key.id == key_id).one()
        except NoResultFound:
            abort(400)

        # get the resource for the key
        # fix(soon): handle user keys
        try:
            r = Resource.query.filter(Resource.id == key.access_as_controller_id, Resource.deleted == False).one()
        except NoResultFound:
            abort(400)

        # check permissions; require write access to the controller to delete its key
        if access_level(r.query_permissions()) < ACCESS_LEVEL_WRITE:
            abort(403)

        # admin can revoke or delete; user can only revoke
        delete_key = False
        if current_user.role == current_user.SYSTEM_ADMIN:
            delete_key = bool(int(request.values.get('delete', 0)))
        if delete_key:
            Key.query.filter(Key.id == key_id).delete()
        else:
            key.revocation_user_id = current_user.id
            key.revocation_timestamp = datetime.datetime.utcnow()
        db.session.commit()

    # update a key
    def put(self, key_id):
        pass


class KeyList(ApiResource):

    # get a list of keys
    def get(self):
        if 'access_as_controller_id' in request.values:
            access_as_controller_id = request.values['access_as_controller_id']
            try:
                r = Resource.query.filter(Resource.id == access_as_controller_id, Resource.deleted == False).one()
            except NoResultFound:
                abort(400)

            # require that we have *write* access to the controller to read its keys
            if access_level(r.query_permissions()) >= ACCESS_LEVEL_WRITE:
                keys = Key.query.filter(Key.access_as_controller_id == access_as_controller_id).order_by('id')
            else:
                abort(403)
        else:
            if current_user.is_anonymous or current_user.role != current_user.SYSTEM_ADMIN:
                abort(403)
            keys = Key.query.order_by('id')
        return {k.id: k.as_dict() for k in keys}

    # create a new key
    def post(self):

        # create a key for a controller
        if 'access_as_controller_id' in request.values:
            access_as_controller_id = request.values['access_as_controller_id']
            try:
                r = Resource.query.filter(Resource.id == access_as_controller_id, Resource.deleted == False).one()
            except NoResultFound:
                abort(400)
            if access_level(r.query_permissions()) < ACCESS_LEVEL_WRITE:  # require write access to the controller to create a key for it
                abort(403)
            organization_id = r.root().id
            if current_user.is_anonymous:  # handle special case of creating a key using a user-associated key (controllers aren't allowed to create keys)
                key = find_key(request.authorization.password)
                if key.access_as_user_id:
                    creation_user_id = key.access_as_user_id
                else:
                    abort(403)
            else:
                creation_user_id = current_user.id
            (k, key_text) = create_key(current_user.id, organization_id, None, access_as_controller_id, key_text = request.values.get('key'))
            return {'status': 'ok', 'id': k.id, 'secret_key': key_text}

        # create a key for a users
        # fix(later): handle case of creating a user-associated key using a user-associated key (see code above)
        elif 'access_as_user_id' in request.values:
            access_as_user_id = request.values['access_as_user_id']
            try:
                u = User.query.filter(User.id == access_as_user_id, User.deleted == False).one()
            except NoResultFound:
                abort(400)
            organization_id = request.values['organization_id']
            if current_user.is_anonymous or current_user.role != current_user.SYSTEM_ADMIN:  # fix(soon): instead check that (1) access_as_user_id is a member of org and (2) current user has admin access to org; current check is too strict
                abort(403)
            (k, key_text) = create_key(current_user.id, organization_id, access_as_user_id, None)
            return {'status': 'ok', 'id': k.id, 'secret_key': key_text}
