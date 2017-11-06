# standard python imports
import json
import datetime


# external imports
from flask import abort, request, current_app
from sqlalchemy.orm.exc import NoResultFound
from flask_restful import Resource as ApiResource
from flask_login import current_user, login_required


# internal imports
from main.app import db
from main.users.auth import make_code
from main.resources.models import Resource
from main.users.models import OrganizationUser, AccountRequest
from main.messages.outgoing_messages import send_email
from main.resources.resource_util import create_organization


class OrganizationList(ApiResource):

    # fix(soon): remove this?
    @login_required
    def get(self):
        if current_user.role == current_user.SYSTEM_ADMIN:
            organizations = Resource.query.filter(Resource.type == Resource.ORGANIZATION_FOLDER)
            return {org.id: org.as_dict(extended = True) for org in organizations}
        else:  # fix(soon): rework this
            org_users = OrganizationUser.query.filter(OrganizationUser.user_id == current_user.id)
            org_resources = [org_user.organization for org_user in org_users]
            return {org.id: org.as_dict() for org in org_resources}  # fix(soon): just provide name and ID?

    # fix(soon): remove this?
    @login_required
    def post(self):
        if current_user.role == current_user.SYSTEM_ADMIN:
            args = request.values
            org_id = create_organization(args['full_name'], args['folder_name'])
            return {'status': 'ok', 'organization_id': org_id}
        else:  # for now we require non-system-admins to create organizations through sign-up process
            abort(403)


class OrganizationUserRecord(ApiResource):

    # get a user/organization association
    # fix(clean): remove this
    @login_required
    def get(self, org_id, org_user_id):
        if current_user.role == current_user.SYSTEM_ADMIN:
            try:
                org_user = OrganizationUser.query.filter(OrganizationUser.organization_id == org_id, OrganizationUser.id == org_user_id).one()
            except NoResultFound:
                abort(404)
            return org_user.as_dict()
        else:
            abort(403)

    # remove a user from an organization
    def delete(self, org_id, org_user_id):
        if current_user.role == current_user.SYSTEM_ADMIN:
            try:
                org_users = OrganizationUser.query.filter(OrganizationUser.organization_id == org_id, OrganizationUser.user_id == org_user_id)
                org_users.delete()
                db.session.commit()
            except NoResultFound:
                abort(404)
        else:
            abort(403)

    # update a user/organization association
    def put(self, org_id, org_user_id):
        pass


class OrganizationUserList(ApiResource):

    # get a list of users who are members of a particular organization
    # fix(clean): remove this
    @login_required
    def get(self, org_id):
        if current_user.role == current_user.SYSTEM_ADMIN:
            org_users = OrganizationUser.query.filter(OrganizationUser.organization_id == org_id)
            return {org_user.id: org_user.as_dict() for org_user in org_users}
        else:
            abort(403)

    # assign a new user to an organization
    @login_required
    def post(self, org_id):
        args = request.values

        # check that user is an org admin or system admin
        if current_user.role != current_user.SYSTEM_ADMIN:
            try:
                current_org_user = OrganizationUser.query.filter(OrganizationUser.organization_id == org_id, OrganizationUser.user_id == current_user.id).one()
                if not current_org_user.is_admin:
                    abort(403)
                current_org_user = None
            except NoResultFound:
                abort(403)

        # case 1: inviting a new user by email
        if 'email_address' in args:
            email_address = args['email_address']
            if not ('.' in email_address and '@' in email_address):  # fix(later): better validation
                abort(405)
            ar = AccountRequest()
            ar.organization_id = org_id
            ar.inviter_id = current_user.id
            ar.creation_timestamp = datetime.datetime.utcnow()
            ar.email_address = email_address
            ar.email_sent = True
            ar.email_failed = False
            ar.access_code = make_code(30)
            ar.attributes = '{}'
            db.session.add(ar)
            db.session.commit()

            # send an email to the user
            # fix(later): add error handling/retry
            sys_name = current_app.config['SYSTEM_NAME']
            org_full_name = json.loads(ar.organization.system_attributes)['full_name']
            subject = '%s invitation from %s' % (sys_name, org_full_name)
            message_body = '''You have been invited to join %s on %s.

Follow this link to create an account:
%screate-account/%s
''' % (org_full_name, sys_name, request.url_root, ar.access_code)
            try:
                send_email(email_address, subject, message_body, current_app.config)
            except:
                return {'status': 'error'}
            return {'status': 'ok'}

        # case 2: assigning an existing user to be a member of this organization
        else:
            org_user = OrganizationUser()  # fix(later): prevent duplicates
            org_user.organization_id = org_id
            org_user.user_id = args['user_id']
            org_user.is_admin = bool(int(args['is_admin']))  # fix(later): make conversion safe
            db.session.add(org_user)
            db.session.commit()
            return {'status': 'ok'}
