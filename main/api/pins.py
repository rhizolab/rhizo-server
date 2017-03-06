import random
import datetime


# external imports
from flask import request, abort
from flask_login import current_user
from flask_restful import Resource as ApiResource
from sqlalchemy.orm.exc import NoResultFound


# internal imports
from main.app import db
from main.users.permissions import generate_access_code, access_level, ACCESS_LEVEL_WRITE
from main.users.auth import create_key
from main.resources.models import Resource, Pin
from main.resources.resource_util import find_resource


class PinRecord(ApiResource):

    # user by controller to check status of pin
    # fix(soon): carefully throttle use of this endpoint
    def get(self, pin):

        # get PIN record
        pin_code = request.values['pin_code']
        try:
            pin_record = Pin.query.filter(Pin.pin == pin, Pin.code == pin_code).one()
        except NoResultFound:
            abort(404)

        # make sure it hasn't expired
        if pin_record.creation_timestamp < datetime.datetime.utcnow() - datetime.timedelta(minutes = 30):
            return {'status': 'error', 'message': 'PIN has expired.'}

        # if we haven't yet created a key, create one now and return it
        if pin_record.enter_timestamp and not pin_record.key_created:
            try:
                controller = Resource.query.filter(Resource.id == pin_record.controller_id).one()
            except NoResultFound:
                return {'status': 'error', 'message': 'Controller not found.'}

            # create key
            (_, secret_key) = create_key(pin_record.user_id, controller.organization_id, None, controller.id)
            pin_record.key_created = True
            db.session.commit()
            return {'status': 'ok', 'controller_path': controller.path(), 'secret_key': secret_key}

        # otherwise no change since before
        else:
            return {'status': 'ok'}

    # used by user to enter a pin for a particular controller
    def put(self, pin):

        # we assume PIN entered by human user
        if current_user.is_anonymous:
            abort(403)

        # get controller
        controller_path = request.values['controller']
        controller = find_resource(controller_path)
        if not controller:
            abort(400)
        if access_level(controller.query_permissions()) < ACCESS_LEVEL_WRITE:
            abort(403)

        # get PIN record
        # fix(soon): how do we avoid abuse of this? (we do know user and org)
        try:
            pin_record = Pin.query.filter(Pin.pin == pin).one()
        except NoResultFound:
            abort(404)

        # make sure it hasn't expired
        if pin_record.creation_timestamp < datetime.datetime.utcnow() - datetime.timedelta(minutes = 30):
            return {'status': 'error', 'message': 'PIN has expired.'}

        # assocate pin with controller (and update other fields)
        pin_record.enter_timestamp = datetime.datetime.utcnow()
        pin_record.user_id = current_user.id
        pin_record.controller_id = controller.id
        db.session.commit()
        return {'status': 'ok'}


class PinList(ApiResource):

    # request creation of a new pin
    # fix(soon): carefully throttle use of this endpoint
    def post(self):
        pin_record = Pin()
        pin_record.pin = random.randint(1000, 9999)
        pin_record.code = generate_access_code(60)
        pin_record.creation_timestamp = datetime.datetime.utcnow()
        db.session.add(pin_record)
        db.session.commit()
        return {'status': 'ok', 'pin': pin_record.pin, 'pin_code': pin_record.code}
