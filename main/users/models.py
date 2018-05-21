from main.app import db
from flask_login import UserMixin


# The User model stores information about a human user. A user is identified by a user name or email address.
class User(UserMixin, db.Model):
    __tablename__       = 'users'
    id                  = db.Column(db.Integer, primary_key = True)
    user_name           = db.Column(db.String(50), nullable = True)  # optional
    email_address       = db.Column(db.String(100), nullable = False, unique = True)
    password_hash       = db.Column(db.String(128), nullable = False)
    full_name           = db.Column(db.String(100), nullable = False)
    info_status         = db.Column(db.String, nullable = False)  # JSON string indicating which info messages have been displayed to user
    attributes          = db.Column(db.String, nullable = False)  # JSON string of additional information about user
    deleted             = db.Column(db.Boolean, nullable = False)
    creation_timestamp  = db.Column(db.DateTime, nullable = False)
    role                = db.Column(db.Integer, nullable = False)

    def __repr__(self):
        return '%d: %s' % (self.id, self.email_address)

    def as_dict(self):
        return {
            'id': self.id,
            'user_name': self.user_name,
            'email_address': self.email_address,
            'full_name': self.full_name,
            'role': self.role,
            'creation_timestamp': self.creation_timestamp.isoformat() + 'Z',
            'deleted': self.deleted,
        }

    # roles
    STANDARD_USER = 0
    SYSTEM_ADMIN = 2  # this is an admin role for the entire site; organization admins are specified in OrganizationUser model


# The Key model holds access keys (used for programmatic API access to the server).
class Key(db.Model):
    __tablename__           = 'keys'
    id                      = db.Column(db.Integer, primary_key = True)
    organization_id         = db.Column(db.ForeignKey('resources.id'), nullable = False)
    creation_user_id        = db.Column(db.ForeignKey('users.id'), nullable = False)
    revocation_user_id      = db.Column(db.ForeignKey('users.id'))         # null if not revoked
    creation_timestamp      = db.Column(db.DateTime, nullable = False)
    revocation_timestamp    = db.Column(db.DateTime)                       # null if not revoked
    access_as_user_id       = db.Column(db.ForeignKey('users.id'))         # null if access as controller
    access_as_controller_id = db.Column(db.ForeignKey('resources.id'))     # null if access as user
    key_part                = db.Column(db.String(8), nullable = False)
    key_hash                = db.Column(db.String(128), nullable = False)  # like a password hash, but for a key

    # fix(soon): remove these and just use key_hash
    key_storage             = db.Column(db.String(), nullable = True)
    key_storage_nonce       = db.Column(db.String(), nullable = True)

    def as_dict(self):
        return {
            'id': self.id,
            'organization_id': self.organization_id,
            'access_as_user_id': self.access_as_user_id,
            'access_as_controller_id': self.access_as_controller_id,
            'creation_timestamp': self.creation_timestamp.isoformat() + 'Z' if self.creation_timestamp else '',
            'revocation_timestamp': self.revocation_timestamp.isoformat() + 'Z' if self.revocation_timestamp else '',
            'key_part': self.key_part,
        }


# The AccountRequest model holds requests for new users and new organizations.
# Account request may require approval before they are turned into accounts.
class AccountRequest(db.Model):
    __tablename__       = 'account_requests'
    id                  = db.Column(db.Integer, primary_key = True)
    organization_name   = db.Column(db.String(100))                   # used for new organization
    organization_id     = db.Column(db.ForeignKey('resources.id'))    # used to join existing organization
    organization        = db.relationship('Resource')                 # used to join existing organization
    inviter_id          = db.Column(db.ForeignKey('users.id'))        # used to join existing organization
    creation_timestamp  = db.Column(db.DateTime, nullable = False)
    redeemed_timestamp  = db.Column(db.DateTime)
    access_code         = db.Column(db.String(40), nullable = False)
    email_address       = db.Column(db.String, nullable = False)
    email_sent          = db.Column(db.Boolean, nullable = False)     # True if sent successfully
    email_failed        = db.Column(db.Boolean, nullable = False)     # True if given up on sending
    attributes          = db.Column(db.String, nullable = False)      # JSON field containing extra attributes


# The OrganizationUser model represents membership of users in organizations.
# A single user can belong to multiple organizations. A user can be an adminstrator for an organization.
class OrganizationUser(db.Model):
    __tablename__   = 'organization_users'
    id              = db.Column(db.Integer, primary_key = True)
    organization_id = db.Column(db.ForeignKey('resources.id'), nullable = False)
    organization    = db.relationship('Resource')
    user_id         = db.Column(db.ForeignKey('users.id'), nullable = False)
    user            = db.relationship('User')
    is_admin        = db.Column(db.Boolean, default = False, nullable = False)

    def as_dict(self):
        return {
            'organization_id': self.organization_id,
            'user_id': self.user_id,
            'is_admin': self.is_admin,
        }
