import random
import string
import json
from flask import request
from flask_login import current_user
from sqlalchemy.orm.exc import NoResultFound
from main.users.models import OrganizationUser
from main.users.auth import find_key
from main.resources.models import Resource


# access level defintions
ACCESS_LEVEL_NONE = 0
ACCESS_LEVEL_READ = 10
ACCESS_LEVEL_WRITE = 20


# access type definitions
ACCESS_TYPE_PUBLIC = 100
ACCESS_TYPE_ORG_USERS = 110
ACCESS_TYPE_ORG_CONTROLLERS = 120
ACCESS_TYPE_USER = 130
ACCESS_TYPE_CONTROLLER = 140


# provides the maximum access level of the current (or given) user to an object with the given permission string;
# returns one of [ACCESS_LEVEL_NONE, ACCESS_LEVEL_READ, ACCESS_LEVEL_WRITE]
# (currently admin access is handled by separate org user records)
def access_level(permissions, controller_id = None):

    # determine current user (if any)
    # fix(soon): handle API auth with key as user if not handled elsewhere
    user_id = current_user.id if current_user.is_authenticated else None

    # handle system admin
    # fix(soon): require that system admins explicitly add themselves to orgs
    if user_id and current_user.role == current_user.SYSTEM_ADMIN:
        return ACCESS_LEVEL_WRITE

    # determine current API client (if any)
    if not controller_id:
        key = None
        if request.authorization:
            key = find_key(request.authorization.password)  # key is provided as HTTP basic auth password
        if key:
            if key.access_as_controller_id:
                controller_id = key.access_as_controller_id
            elif key.access_as_user_id:
                user_id = key.access_as_user_id

    # start with no access
    client_access_level = ACCESS_LEVEL_NONE

    # take max level of all applicable permissions
    for permission_record in permissions:
        (type, id, level) = permission_record

        # applies to everyone
        if type == ACCESS_TYPE_PUBLIC:
            client_access_level = max(client_access_level, level)

        # applies if current user is contained within the organization given by the permission ID
        elif type == ACCESS_TYPE_ORG_USERS:
            if user_id:
                try:
                    org_user = OrganizationUser.query.filter(OrganizationUser.user_id == user_id, OrganizationUser.organization_id == id).one()
                    client_access_level = max(client_access_level, level)
                    break
                except NoResultFound:
                    pass

        # applies if current controller is contained within the organization given by the permission ID
        elif type == ACCESS_TYPE_ORG_CONTROLLERS:
            if controller_id:
                try:
                    controller = Resource.query.filter(Resource.id == controller_id, Resource.deleted == False).one()
                    controller_org_id = controller.organization_id if controller.organization_id else controller.root().id  # fix(soon): remove this after all resources have org ids
                    if controller_org_id == id:
                        client_access_level = max(client_access_level, level)
                    break
                except NoResultFound:
                    pass

        # applies if permission ID is the same as current user ID
        elif type == ACCESS_TYPE_USER:
            if user_id and user_id == id:
                client_access_level = max(client_access_level, level)

        # applies if permission ID is the same as current controller ID
        elif type == ACCESS_TYPE_CONTROLLER:
            if controller_id and controller_id == id:
                client_access_level = max(client_access_level, level)

    return client_access_level


# generate a random alphanumeric code
# fix(clean): merge with other similar functions
def generate_access_code(length):
    letter_choices = string.ascii_uppercase + string.digits
    letters = [random.SystemRandom().choice(letter_choices) for x in range(length)]
    return ''.join(letters)
