import json
from main.app import db


# The Resource model provides a hierarchy of folders and files.
# It is the primary table for organization data stored on the server.
class Resource(db.Model):
    __tablename__       = 'resources'
    id                  = db.Column(db.Integer, primary_key = True)
    last_revision_id    = db.Column(db.Integer)                     # can be null for folder resources or empty files/sequences
    organization_id     = db.Column(db.ForeignKey('resources.id'))  # would like this to be non-null, but how else do we create first organization?
    creation_timestamp  = db.Column(db.DateTime)
    modification_timestamp = db.Column(db.DateTime)                 # fix(later): remove this and use revision timestamp? what about folders? should we track modification timestamps for this?

    # meta-data that could eventually have change tracking (probably best to move into a separate table e.g. resource_meta_revisions)
    parent_id           = db.Column(db.ForeignKey('resources.id'), index = True)
    parent              = db.relationship('Resource', remote_side = [id], foreign_keys = [parent_id])
    name                = db.Column(db.String, nullable = False)
    type                = db.Column(db.Integer, nullable = False)                 # fix(later): add index for this?
    permissions         = db.Column(db.String)                                    # JSON; NULL -> inherit from parent
    system_attributes   = db.Column(db.String, nullable = False, default = '{}')  # JSON dictionary; additional attributes of the resource (system-defined)
    user_attributes     = db.Column(db.String)                                    # JSON dictionary; additional attributes of the resource (user-defined)
    deleted             = db.Column(db.Boolean, nullable = False, default = False)

    # fix(soon): remove after migrate
    file_type           = db.Column(db.String(20))
    hash                = db.Column(db.String(50))
    size                = db.Column(db.BigInteger)

    # resource types
    BASIC_FOLDER = 10
    ORGANIZATION_FOLDER = 11
    CONTROLLER_FOLDER = 12
    REMOTE_FOLDER = 13
    FILE = 20
    SEQUENCE = 21
    APP = 22

    # sequence data types
    NUMERIC_SEQUENCE = 1
    TEXT_SEQUENCE = 2
    IMAGE_SEQUENCE = 3

    # ======== methods ========

    # get information about the resource in a json-ready dictionary
    def as_dict(self, extended = False):
        d = {
            'id': self.id,
            'name': self.name,
            'type': self.type,
        }
        if extended:
            d['parent_id'] = self.parent_id
            if self.creation_timestamp:  # fix(clean): remove this after make sure everything has timestamp
                d['creationTimestamp'] = self.creation_timestamp.isoformat() + 'Z'  # fix(soon): remove
                d['creation_timestamp'] = self.creation_timestamp.isoformat() + 'Z'
            if self.modification_timestamp:  # fix(clean): remove this after make sure everything has timestamp
                d['modificationTimestamp'] = self.modification_timestamp.isoformat() + 'Z'  # fix(soon): remove
                d['modification_timestamp'] = self.modification_timestamp.isoformat() + 'Z'
            d['permissions'] = json.loads(self.permissions) if self.permissions else []
            d['settings'] = json.loads(self.system_attributes) if self.system_attributes else {}  # fix(soon): remove
            d['system_attributes'] = json.loads(self.system_attributes) if self.system_attributes else {}
            d['user_attributes'] = json.loads(self.user_attributes) if self.user_attributes else {}
            d['lastRevisionId'] = self.last_revision_id  # fix(soon): remove
            d['last_revision_id'] = self.last_revision_id
            if self.last_revision_id:
                d['storage_path'] = self.storage_path(self.last_revision_id)
            if self.type == self.FILE:  # fix(later): remove this case after migrate DB and update client sync code (and browser display code) to use direct system_attributes
                d['hash'] = d['system_attributes'].get('hash') or self.hash
                d['size'] = d['system_attributes'].get('size') or self.size
        return d

    # get the path of the resource (including it's own name)
    # includes leading slash
    def path(self):
        if self.parent:
            path = self.parent.path() + '/' + self.name
        else:
            path = '/' + self.name
        return path

    # returns True if this resource is a child/grandchild/etc. of the specified resource
    def is_descendent_of(self, resource_id):
        if not self.parent_id:
            return False
        elif self.parent_id == resource_id:
            return True
        else:
            return self.parent.is_descendent_of(resource_id)

    # get a list of folders contained within this folder (recursively)
    # fix(clean): maybe this is too specialized; move elsewhere?
    def descendent_folder_ids(self):
        ids = []
        children = Resource.query.filter(Resource.parent_id == self.id, Resource.deleted == False)
        for child in children:
            if child.type >= 10 and child.type < 20:
                ids.append(child.id)
                ids += child.descendent_folder_ids()
        return ids

    # the root of a hierachy of resources; this will generally be an organization (or system folder such as 'doc' or 'system')
    def root(self):
        if self.parent:
            return self.parent.root()
        else:
            return self

    # get a list of permission applied to this resource (including inherited from parents)
    def query_permissions(self):
        permissions = json.loads(self.permissions) if self.permissions else None
        if self.parent:
            parent_permissions = self.parent.query_permissions()

            # if we have permissions at this level, we need to merge in the parent permissions
            if self.permissions:
                permission_dict = {(type, id): level for (type, id, level) in self.permissions}
                for permission_record in parent_permissions:
                    (type, id, level) = permission_record
                    if not (type, id) in permission_dict:
                        permissions.append((type, id, level))

            # otherwise, just use the parent permissions (the common case)
            else:
                permissions = parent_permissions
        return permissions

    # get the path of the resource in the bulk storage system
    def storage_path(self, revision_id):
        org_id = self.organization_id
        if not org_id:  # fix(clean): remove this
            org_id = self.root().id
        id_str = '%09d' % self.id
        return '%d/%s/%s/%s/%d_%d' % (org_id, id_str[-9:-6], id_str[-6:-3], id_str[-3:], self.id, revision_id)


# The ResourceRevision model holds a revision history or time series history of a resource.
class ResourceRevision(db.Model):
    __tablename__       = 'resource_revisions'
    id                  = db.Column(db.Integer, primary_key = True)  # upgrade to 64-bit at some point?
    resource_id         = db.Column(db.ForeignKey('resources.id'), nullable = False, index = True)
    timestamp           = db.Column(db.DateTime, nullable = False, index = True)
    data                = db.Column(db.LargeBinary, nullable = True)


# The ResourceView model holds per-used preferences for viewing a resource (e.g. folder sorting).
class ResourceView(db.Model):
    __tablename__       = 'resource_views'
    id                  = db.Column(db.Integer, primary_key = True)
    resource_id         = db.Column(db.ForeignKey('resources.id'), nullable = False, index = True)
    user_id             = db.Column(db.ForeignKey('users.id'), nullable = False, index = True)
    view                = db.Column(db.String, nullable = False)  # JSON string


# ======== other resource-related tables ========


# The Pin model is used for provisioning new controllers. The controller requests a PIN, displays it,
# and the user enters it. This associates the controller hardware with a controller resource on the server.
class Pin(db.Model):
    __tablename__       = 'pins'
    id                  = db.Column(db.Integer, primary_key = True)
    pin                 = db.Column(db.Integer, nullable = False)
    code                = db.Column(db.String(80), nullable = False)  # a key used to make sure only the original controller can check this PIN
    creation_timestamp  = db.Column(db.DateTime, nullable = False)
    enter_timestamp     = db.Column(db.DateTime)
    user_id             = db.Column(db.ForeignKey('users.id'))        # null if not yet entered
    controller_id       = db.Column(db.ForeignKey('resources.id'))    # null if not yet entered
    key_created         = db.Column(db.Boolean)
    attributes          = db.Column(db.String, nullable = False)      # JSON field containing extra attributes


# The Usage model stores data and message usage by organization
class Usage(db.Model):
    __tablename__       = 'usage'
    id                  = db.Column(db.Integer, primary_key = True)
    organization_id     = db.Column(db.ForeignKey('resources.id'), nullable = False)
    period              = db.Column(db.String(10), nullable = False)
    message_count       = db.Column(db.BigInteger, nullable = False)
    data_bytes          = db.Column(db.BigInteger, nullable = False)
    attributes          = db.Column(db.String, nullable = False)      # JSON field containing extra attributes


# The ControllerStatus model stores real-time status information about a controller
# (external hardware that sends messages using to the server).
class ControllerStatus(db.Model):
    __tablename__               = 'controller_status'
    id                          = db.Column(db.ForeignKey('resources.id'), primary_key = True)
    client_version              = db.Column(db.String(80), nullable = False)
    web_socket_connected        = db.Column(db.Boolean, nullable = False)  # not used currently (may be too brittle); remove?
    last_connect_timestamp      = db.Column(db.DateTime)                   # last time the controler connected
    last_watchdog_timestamp     = db.Column(db.DateTime)                   # last time the controller sent good watchdog message
    watchdog_notification_sent  = db.Column(db.Boolean, nullable = False)
    attributes                  = db.Column(db.String, nullable = False)   # JSON field containing extra controller status information

    def as_dict(self, extended=False):
        d = {
            'client_version': self.client_version,
            'web_socket_connected': self.web_socket_connected,
            'last_connect_timestamp': self.last_connect_timestamp.isoformat() + ' Z' if self.last_connect_timestamp else '',
            'last_watchdog_timestamp': self.last_watchdog_timestamp.isoformat() + ' Z' if self.last_watchdog_timestamp else '',
        }
        if extended:
            d['status'] = json.loads(self.attributes)
        return d


# the Thumbnail model stores versions of image resources at multiple scales
class Thumbnail(db.Model):
    __tablename__       = 'thumbnails'
    id                  = db.Column(db.Integer, primary_key = True)
    resource_id         = db.Column(db.ForeignKey('resources.id'), nullable = False, index = True)
    width               = db.Column(db.Integer, nullable = False)
    height              = db.Column(db.Integer, nullable = False)
    format              = db.Column(db.String(4), nullable = False)
    data                = db.Column(db.LargeBinary, nullable = False)


# unit (for use in sequence attributes)
# fix(later): could move into a separate table (with nullable organization_id so orgs can define own units)
UNITS = {
    'bytes': '',
    'degrees C': 'C',
    'percent': '%',
}
