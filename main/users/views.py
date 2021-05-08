# standard python imports
import datetime
import json
from smtplib import SMTPException


# external imports
from flask import render_template, request, redirect, g, abort, Response, current_app
from sqlalchemy.orm.exc import NoResultFound
from flask_login import login_required, login_user, logout_user, current_user


# internal imports
from main.app import app, db
from main.users.models import User, AccountRequest, OrganizationUser
from main.resources.models import Resource
from main.users.auth import login_validate, create_user, change_user_password, make_code
from main.util import ssl_required
from main.messages.outgoing_messages import send_email
from main.resources.resource_util import create_organization


# this is run before every request to set up some variables used by the base template
# fix(clean): move to main/app.py?
# fix(faster): would it be better to define these as custom template functions (similar to csrf_token)?
@app.before_request
def before_request():
    if request.endpoint != 'static' and not request.path.startswith('/api/'):
        g.system_name = current_app.config['SYSTEM_NAME']
        g.extra_nav_items = current_app.config.get('EXTRA_NAV_ITEMS', '')
        g.use_system_css = current_app.config.get('USE_SYSTEM_CSS', False)  # allows customizing CSS
        g.user = current_user
        g.organization_names = []
        if hasattr(g.user, 'id'):
            org_users = OrganizationUser.query.filter(OrganizationUser.user_id == g.user.id)
            for org_user in org_users:
                org_resource = org_user.organization
                g.organization_names.append({
                    'full_name': json.loads(org_resource.system_attributes)['full_name'] if org_resource.system_attributes else org_resource.name,
                    'folder_name': org_resource.name,
                })


# display a sign-in form or handle the form being posted
# fix(soon): add more client-side validation and a friendlier message if invalid password
@app.route('/sign-in', methods=['GET', 'POST'])
@ssl_required
def sign_in():
    if request.method == 'POST':
        email_address = request.form['email_address']
        password = request.form['password']
        remember_me = bool(int(request.form.get('remember_me', '0')))  # fix(soon): safe convert
        user = login_validate(email_address, password)
        if not user:
            message = 'Invalid email address or user name or password.'
            return render_template('users/sign-in.html', message=message, hide_loc_nav=True)  # display login form again
        login_user(user, remember=remember_me)
        return redirect('/')
        # return redirect(request.args.get("next") or "/") # need to use next_is_valid(next) - https://flask-login.readthedocs.org/en/latest/
    return render_template('users/sign-in.html', hide_loc_nav=True)


# sign out the current user
@app.route('/sign-out')
def sign_out():
    logout_user()
    return redirect('/')


# view current user's settings
@app.route('/settings')
@ssl_required
@login_required
def settings():
    org_users = OrganizationUser.query.filter(OrganizationUser.user_id == current_user.id)
    org_user_dicts = []
    for org_user in org_users:
        org_user_dict = org_user.as_dict()
        org_user_dict['organization_full_name'] = json.loads(org_user.organization.system_attributes)['full_name']
        org_user_dict['organization_name'] = org_user.organization.name
        org_user_dicts.append(org_user_dict)
    return render_template('users/settings.html', user_json=json.dumps(current_user.as_dict()), org_users=org_user_dicts)


# page for changing current user's password
@app.route('/settings/change-password', methods=["GET", "POST"])
@ssl_required
@login_required
def change_password():
    if request.method == 'POST':
        old_password = request.form['oldPassword']
        new_password1 = request.form['newPassword1']
        new_password2 = request.form['newPassword2']
        if not login_validate(current_user.email_address, old_password):
            return Response('Original password invalid.')
        if new_password1 != new_password2:
            return Response('New passwords do not match.')
        if len(new_password1) < 8:
            return Response('Password is too short.')
        change_user_password(current_user.email_address, old_password, new_password1)
        return redirect('/')
    return render_template('users/change-password.html')


# page for applying for a new account
@app.route('/sign-up', methods=['GET', 'POST'])
def sign_up():
    if current_user.role != current_user.SYSTEM_ADMIN:
        abort(403)
    if request.method == 'GET':
        return render_template('users/sign-up.html', hide_loc_nav=True)
    else:
        ar = AccountRequest()
        ar.organization_name = request.form['orgName']
        ar.email_address = request.form['email_address']
        ar.creation_timestamp = datetime.datetime.utcnow()
        ar.email_sent = True
        ar.email_failed = False
        ar.access_code = make_code(30)
        ar.attributes = '{}'
        sys_name = current_app.config['SYSTEM_NAME']
        subject = '%s account request' % sys_name
        message_body = '''Follow this link to create an account on %s:
%screate-account/%s

(If you did not request an account, you can ignore this email.)
''' % (sys_name, request.url_root, ar.access_code)
        try:
            send_email(ar.email_address, subject, message_body, current_app.config)
        except SMTPException:
            return Response('Error sending email.')
        db.session.add(ar)
        db.session.commit()
        return render_template('users/account-request-complete.html', hide_loc_nav=True)


# page to create a new account given an approved request
@app.route('/create-account/<string:access_code>', methods=['GET', 'POST'])
def create_account(access_code):
    try:
        ar = AccountRequest.query.filter(AccountRequest.access_code == access_code).one()
    except NoResultFound:
        return Response('Sign-up code not found.')
    if ar.redeemed_timestamp:
        return Response('Sign-up code already redeemed.')
    if datetime.datetime.utcnow() - ar.creation_timestamp > datetime.timedelta(days=7):
        return Response('Sign-up code has expired (must be used within one week).')

    # handle form post case
    if request.method == 'POST':

        # get parameters
        email_address = request.form['email_address']
        password = request.form['pw1']
        user_name = request.form.get('user_name', None)
        full_name = request.form.get('full_name', None)

        # verify user doesn't already exist with this email address
        try:
            User.query.filter(User.email_address == email_address).one()
            return Response('An account with that email address already exists.')
        except NoResultFound:
            pass

        # verify user doesn't already exist with this user name
        if user_name:
            try:
                User.query.filter(User.user_name == user_name).one()
                return Response('User name already in use.')
            except NoResultFound:
                pass

        # create user
        user_id = create_user(email_address, user_name, password, full_name, User.STANDARD_USER)
        ar.redeemed_timestamp = datetime.datetime.utcnow()

        # create organization (unless invitation to join existing)
        org_id = ar.organization_id
        new_org = not org_id
        if new_org:
            org_id = create_organization(request.form['orgName'], request.form['orgFolderName'])

        # assign user to organization
        org_user = OrganizationUser()
        org_user.user_id = user_id
        org_user.organization_id = org_id
        org_user.is_admin = new_org
        db.session.add(org_user)
        db.session.commit()
        return render_template('users/account-creation-complete.html', hide_loc_nav=True)

    # handle GET case
    else:
        if ar.organization_id:
            return render_template(
                'users/user-invitation.html',
                organization_full_name=json.loads(ar.organization.system_attributes)['full_name'],
                email_address=ar.email_address,
                access_code=access_code,
                hide_loc_nav=True,
            )
        else:
            return render_template(
                'users/account-creation.html',
                organization_name=ar.organization_name,
                email_address=ar.email_address,
                access_code=access_code,
                hide_loc_nav=True,
            )


# page for viewing/editing settings for an organization
@app.route('/settings/<string:org_folder_name>')
@login_required
def organization_settings(org_folder_name):

    # get organization record
    try:
        resource = Resource.query.filter(Resource.name == org_folder_name, Resource.parent_id.is_(None)).one()
    except NoResultFound:
        abort(404)

    # check that current user has admin access to this organization
    if current_user.role != User.SYSTEM_ADMIN:
        try:
            org_user = (
                OrganizationUser.query
                .filter(OrganizationUser.organization_id == resource.id, OrganizationUser.user_id == current_user.id)
                .one()
            )
        except NoResultFound:
            abort(403)
        if not org_user.is_admin:
            abort(403)

    # prepare data
    org_users = OrganizationUser.query.filter(OrganizationUser.organization_id == resource.id).order_by('id')  # fix(later): other ordering?
    org_user_dicts = []
    for org_user in org_users:
        org_user_dict = org_user.as_dict()
        org_user_dict['email_address'] = org_user.user.email_address
        org_user_dict['full_name'] = org_user.user.full_name
        org_user_dicts.append(org_user_dict)
    if current_user.role == User.SYSTEM_ADMIN:
        users = User.query.order_by('id')
        users = [{'id': u.id, 'name': u.email_address} for u in users]
    else:
        users = []

    # display the page
    return render_template(
            'users/organization-settings.html',
            org_resource=resource,
            org_full_name=json.loads(resource.system_attributes)['full_name'],
            org_users=json.dumps(org_user_dicts),
            users=json.dumps(users),
            is_system_admin=(current_user.role == User.SYSTEM_ADMIN)
        )
