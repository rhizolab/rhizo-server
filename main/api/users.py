# standard python imports


# external imports
from flask import request, abort
from sqlalchemy.orm.exc import NoResultFound
from flask_login import current_user, login_required
from flask_restful import Resource as ApiResource


# internal imports
from main.users.models import User


class UserRecord(ApiResource):

    # get information about a user
    def get(self, user_id):

        # a special case for checking whether an account exists
        # fix(soon): carefully throttle this endpoint
        if request.values.get('check_exists', False):
            try:
                u = User.query.filter(User.email_address == user_id).one()
                return {'exists': 1}
            except NoResultFound:
                try:
                    u = User.query.filter(User.user_name == user_id).one()
                    return {'exists': 1}
                except NoResultFound:
                    return {'exists': 0}

        # normal user lookup
        elif current_user.is_authenticated:
            if current_user.id == user_id:
                return current_user.as_dict()
            elif current_user.role == current_user.SYSTEM_ADMIN:
                try:
                    u = User.query.filter(User.id == user_id).one()
                except NoResultFound:
                    abort(404)
                return u.as_dict()
            else:
                abort(403)

    # delete a user
    def delete(self, user_id):
        pass  # requires admin

    # update a user
    def put(self, user_id):
        pass  # requires admin


class UserList(ApiResource):

    # get a list of users
    @login_required
    def get(self):
        if current_user.role == current_user.SYSTEM_ADMIN:
            return {u.id: u.as_dict() for u in User.query.order_by('id')}
        else:
            abort(403)

    # create a new user
    def post(self):
        pass  # requires admin
