# standard python imports
import os
import time
import json
import hashlib
import datetime
import logging


# external imports
from sqlalchemy import not_
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound


# internal imports
from main.app import db, message_queue, storage_manager
from main.resources.models import Resource, ResourceRevision, Thumbnail, ControllerStatus, ResourceView
from main.resources.file_conversion import compute_thumbnail
from main.users.permissions import ACCESS_LEVEL_WRITE, ACCESS_TYPE_ORG_USERS, ACCESS_TYPE_ORG_CONTROLLERS


# get the number corresponding to a resource type (given by a string name)
def resource_type_number(type_name):
    if type_name == 'basic_folder' or type_name == 'basicFolder':
        return Resource.BASIC_FOLDER
    elif type_name == 'organization_folder' or type_name == 'organizationFolder':
        return Resource.ORGANIZATION_FOLDER
    elif type_name == 'controller_folder' or type_name == 'controllerFolder':
        return Resource.CONTROLLER_FOLDER
    elif type_name == 'remote_folder' or type_name == 'remoteFolder':
        return Resource.REMOTE_FOLDER
    elif type_name == 'file':
        return Resource.FILE
    elif type_name == 'sequence':
        return Resource.SEQUENCE
    elif type_name == 'app':
        return Resource.APP


# fix(soon): remove this
def _create_folders(path):
    parts = path.strip('/').split('/')
    parent = None
    for part in parts:
        try:
            if parent:
                resource = Resource.query.filter(Resource.parent_id == parent.id, Resource.name == part, not_(Resource.deleted)).one()
            else:
                resource = Resource.query.filter(Resource.parent_id.is_(None), Resource.name == part, not_(Resource.deleted)).one()
        except NoResultFound:
            resource = Resource()
            resource.parent_id = parent.id
            resource.organization_id = parent.organization_id
            resource.name = part
            resource.type = Resource.BASIC_FOLDER
            resource.creation_timestamp = datetime.datetime.utcnow()
            resource.modification_timestamp = resource.creation_timestamp
            db.session.add(resource)
            db.session.commit()
        except MultipleResultsFound:
            print('create_folders: duplicate folder at %s in %s' % (part, path))
        parent = resource
    return parent


# create a file-type resource with the given file data and other attributes; file data should be binary
# file name should include leading slash
# returns the newly created resource record object (or existing resource if already exists)
# fix(soon): remove this
def _create_file(file_name, creation_timestamp, modification_timestamp, file_data):
    last_slash = file_name.rfind('/')
    path = file_name[:last_slash]
    short_file_name = file_name[last_slash+1:]
    folder = _create_folders(path)

    # check for existing resource with same name
    try:
        resource = Resource.query.filter(Resource.parent_id == folder.id, Resource.name == short_file_name, not_(Resource.deleted)).one()
        new_resource = False
    except NoResultFound:

        # create new resource record
        resource = Resource()
        resource.parent_id = folder.id
        resource.organization_id = folder.organization_id
        resource.name = short_file_name
        resource.creation_timestamp = creation_timestamp
        resource.type = Resource.FILE
        new_resource = True

    # update or init resource record
    resource.deleted = False
    resource.modification_timestamp = modification_timestamp
    if resource.type != Resource.SEQUENCE:
        if resource.system_attributes:
            system_attributes = json.loads(resource.system_attributes)
        else:
            system_attributes = {}
        system_attributes['hash'] = hashlib.sha1(file_data).hexdigest()
        system_attributes['size'] = len(file_data)
        resource.system_attributes = json.dumps(system_attributes)
    if new_resource:
        db.session.add(resource)
        db.session.commit()

    # write file contents to a resource revision (possibly bulk storage)
    add_resource_revision(resource, modification_timestamp, file_data)
    db.session.commit()

    # compute thumbnail for images
    if file_name.endswith('.png') or file_name.endswith('.jpg'):  # fix(soon): handle more types, capitalizations
        for width in [120]:  # fix(soon): what will be our standard sizes?
            # fix(later): if this returns something other than requested width, we'll keep missing the cache
            (thumbnail_contents, thumbnail_width, thumbnail_height) = compute_thumbnail(file_data, width)
            thumbnail = Thumbnail()
            thumbnail.resource_id = resource.id
            thumbnail.width = thumbnail_width
            thumbnail.height = thumbnail_height
            thumbnail.format = 'jpg'
            thumbnail.data = thumbnail_contents
            db.session.add(thumbnail)
        db.session.commit()
    return resource


# fix(soon): make leading slash required
# find a resource given it's full name with path
def find_resource(file_name):
    if not file_name.startswith('/'):
        logging.warning('find_resource called with %s; should be called with a path starting with a slash', file_name)
        assert False
    file_name = file_name.strip('/')  # at some point can just strip off first character (since we'll assume there's exactly one leading slash)
    parts = file_name.split('/')
    parent = None
    for part in parts:
        try:
            if parent:
                resource = Resource.query.filter(Resource.parent_id == parent.id, Resource.name == part, not_(Resource.deleted)).one()
            else:
                resource = Resource.query.filter(Resource.parent_id.is_(None), Resource.name == part, not_(Resource.deleted)).one()
        except NoResultFound:
            return None
        except MultipleResultsFound:
            print('find_resource/MultipleResultsFound: %s' % file_name)
            return None
        parent = resource
    return parent


# split a camel case string into a space-separated string
def split_camel_case(name):
    result = ''
    for c in name:
        if c.isupper():
            result += ' '
        result += c
    return result


# determine (guess) the mimetype of a file based on its file name extension
def mime_type_from_ext(file_name):
    file_ext = file_name.rsplit('.', 1)[-1]
    mime_type = ''
    if file_ext == 'jpg':
        mime_type = 'image/jpeg'
    elif file_ext == 'png':
        mime_type = 'image/png'
    elif file_ext == 'txt':
        mime_type = 'text/plain'
    elif file_ext == 'csv':
        mime_type = 'text/csv'
    return mime_type


# this is a high-level function for setting the value of a sequence;
# it (1) creates a sequence value record and (2) sends out a sequence_update message;
# note that we don't commit resource here; outside code must commit
# value should be a plain string (not unicode string), possibly containing binary data or encoded unicode data
def update_sequence_value(resource, resource_path, timestamp, value, emit_message=True):
    system_attr = json.loads(resource.system_attributes)
    if 'data_type' not in system_attr:
        logging.warning('attempt to update sequence (%s) without data_type', resource_path)
        return
    data_type = system_attr['data_type']

    # determine min interval between updates
    system_attributes = json.loads(resource.system_attributes) if resource.system_attributes else {}
    min_storage_interval = system_attributes.get('min_storage_interval')
    if min_storage_interval is None:
        if data_type == Resource.TEXT_SEQUENCE:
            min_storage_interval = 0
        else:
            min_storage_interval = 50

    # prep sequence update message data
    if emit_message:
        message_params = {
            'id': resource.id,
            'name': resource_path,  # full/absolute path of the sequence
            'timestamp': timestamp.isoformat() + 'Z',
        }
        if data_type != Resource.IMAGE_SEQUENCE:  # for images we'll send revision IDs
            message_params['value'] = value  # fix(soon): json.dumps crashes if this included binary data

    # if too soon since last update, don't store a new value (but do still send out an update message)
    if min_storage_interval == 0 or timestamp >= resource.modification_timestamp + datetime.timedelta(seconds=min_storage_interval):
        resource_revision = add_resource_revision(resource, timestamp, value.encode())
        resource.modification_timestamp = timestamp

        # create thumbnails for image sequences
        if data_type == Resource.IMAGE_SEQUENCE:
            max_width = 240
            name = 'thumbnail-%d-x' % max_width
            thumbnail_contents = compute_thumbnail(value, max_width)[0]
            try:
                thumbnail_resource = Resource.query.filter(Resource.parent_id == resource.id, Resource.name == name, not_(Resource.deleted)).one()
            except NoResultFound:
                thumbnail_resource = create_sequence(resource, name, Resource.IMAGE_SEQUENCE)
            thumbnail_revision = add_resource_revision(thumbnail_resource, timestamp, thumbnail_contents)
            if emit_message:
                message_params['revision_id'] = resource_revision.id
                message_params['thumbnail_revision_id'] = thumbnail_revision.id

    # create a short lived update message for subscribers to the folder containing this sequence
    if emit_message:
        folder_path = resource_path.rsplit('/', 1)[0]
        message_queue.add(
            folder_id=resource.parent_id, folder_path=folder_path, message_type='sequence_update', parameters=message_params, timestamp=timestamp)
        from main.app import message_sender
        if message_sender:
            message = 'd,%s,%s Z,%s' % (resource.name, timestamp.isoformat(), value)  # emit a display message, not a store-and-display message
            message_sender.send_message(folder_path, message)


# creates a resource revision record; places the data in the record (if it is small) or bulk storage (if it is large);
# note that we don't commit resource here (just resource revision); outside code must commit resource
# data should be binary data (strings should be encoded first)
def add_resource_revision(resource, timestamp, data):
    resource_revision = ResourceRevision()
    resource_revision.resource_id = resource.id
    resource_revision.timestamp = timestamp
    if len(data) < 1000 or not storage_manager:
        resource_revision.data = data
        bulk_storage = False
    else:
        bulk_storage = True
    db.session.add(resource_revision)
    db.session.commit()
    if bulk_storage:
        storage_manager.write(resource.storage_path(resource_revision.id), data)
    resource.last_revision_id = resource_revision.id  # note that we don't commit here; outside code must commit
    return resource_revision


# reads the most recent revision/value of a resource;
# if check_timing is True, will display some timing diagnostics
def read_resource(resource, revision_id=None, check_timing=False):
    data = None
    if not revision_id:
        revision_id = resource.last_revision_id  # if no last revision, this is a new resource with new data
    if revision_id:
        try:
            if check_timing:
                start_time = time.time()
            resource_revision = ResourceRevision.query.filter(ResourceRevision.id == revision_id).one()
            if check_timing:
                print('query time: %.4f' % (time.time() - start_time))
            data = resource_revision.data
        except NoResultFound:
            pass
        # fix(later): move this inside try statement; we should always have a resource revision if we have data in storage
        if data is None and storage_manager:
            if check_timing:
                start_time = time.time()
            data = storage_manager.read(resource.storage_path(revision_id))
            if check_timing:
                print('storage time: %.4f' % (time.time() - start_time))
    return data


# create a new sequence resource; commits it to database and returns resource record
def create_sequence(parent_resource, name, data_type, max_history=10000, units=None):
    r = Resource()
    r.parent_id = parent_resource.id
    r.organization_id = parent_resource.organization_id
    r.name = name
    r.type = Resource.SEQUENCE
    r.creation_timestamp = datetime.datetime.utcnow()
    r.modification_timestamp = r.creation_timestamp
    system_attributes = {
        'data_type': data_type,
        'max_history': max_history
    }
    if units:
        system_attributes['units'] = units
    r.system_attributes = json.dumps(system_attributes)
    db.session.add(r)
    db.session.commit()
    return r


# create a new organization record
def create_organization(full_name, folder_name):
    r = Resource()
    r.name = folder_name
    r.type = Resource.ORGANIZATION_FOLDER
    r.creation_timestamp = datetime.datetime.utcnow()
    r.modification_timestamp = r.creation_timestamp
    r.system_attributes = json.dumps({
        'full_name': full_name,
        'timezone': 'US/Pacific',
    })
    db.session.add(r)
    db.session.commit()
    r.permissions = json.dumps([[ACCESS_TYPE_ORG_USERS, r.id, ACCESS_LEVEL_WRITE], [ACCESS_TYPE_ORG_CONTROLLERS, r.id, ACCESS_LEVEL_WRITE]])
    r.organization_id = r.id  # the organization record has its own id as its organization
    db.session.commit()
    return r.id


# create/update system resources
def create_system_resources():
    print('creating/updating system resources in database')

    # make sure system folder exists
    system_folder = find_resource('/system')
    if not system_folder:
        create_organization('System', 'system')
        system_folder = find_resource('/system')
        print('created system folder')

    # make sure home page exists
    home_page = find_resource('/system/home.md')
    if not home_page:
        resource = Resource()
        resource.parent_id = system_folder.id
        resource.type = Resource.FILE
        resource.name = 'home.md'
        db.session.add(resource)
        db.session.commit()
        home_contents = '''### Welcome

If you are logged in as a system admin, you can [edit this page](/system/home.md?edit=1).
'''
        resource_revision = add_resource_revision(resource, datetime.datetime.utcnow(), home_contents.encode())
        db.session.commit()
        print('created home page (resource: %d, revision: %d)' % (resource.id, resource_revision.id))

    # fix(soon): create workers folder, system log sequence, doc org?, workers/log

    # add apps for system app templates
    file_names = os.listdir('main/templates/system')
    app_create_count = 0
    for file_name in file_names:
        if file_name.endswith('.html'):
            app_name = file_name.rsplit('.', 1)[0]
            app_title = split_camel_case(app_name).title().replace('_', ' ')
            try:
                resource = Resource.query.filter(Resource.parent_id == system_folder.id, Resource.name == app_title, not_(Resource.deleted)).one()
            except NoResultFound:
                print('creating: %s, %s' % (app_name, app_title))
                resource = Resource()
                resource.parent_id = system_folder.id
                resource.type = Resource.APP
                resource.name = app_title
                db.session.add(resource)
                db.session.commit()
                app_create_count += 1
    print('created %d apps' % app_create_count)


# deletes the given resource and all of its children;
# this actually deletes the records, rather than just marking them as deleted;
# also deletes all revisions and thumbnails for this resource
def delete_resource(resource, verbose=False):
    if verbose:
        print('deleting %s' % resource.name)
    children = Resource.query.filter(Resource.parent_id == resource.id)
    if verbose:
        child_count = children.count()
        if child_count:
            print('deleting %d children' % child_count)
    for r in children:
        delete_resource(r, verbose)
    ResourceRevision.query.filter(ResourceRevision.resource_id == resource.id).delete()
    Thumbnail.query.filter(Thumbnail.resource_id == resource.id).delete()
    ResourceView.query.filter(ResourceView.resource_id == resource.id).delete()
    ControllerStatus.query.filter(ControllerStatus.id == resource.id).delete()
    db.session.delete(resource)
    db.session.commit()


def remove_duplicate_resources(parent=None, delete=False):

    # find duplicate resources
    if parent:
        resources = Resource.query.filter(Resource.parent_id == parent.id)
    else:
        resources = Resource.query.filter(Resource.parent_id.is_(None))
    resources_by_name = {}
    for r in resources:
        if r.name in resources_by_name:
            resources_by_name[r.name].append(r)
        else:
            resources_by_name[r.name] = [r]

    # handle duplicate resources
    for name, rlist in resources_by_name.items():
        if len(rlist) > 1:
            rlist.sort(key=lambda r: r.id)  # seems to be much faster to sort here rather than in query above
            print('    duplicates of %s/%s' % (parent.path(), name))
            for r in rlist:
                print('        id: %d, del: %d' % (r.id, r.deleted))
            for r in rlist[:-1]:
                if delete:  # permanently delete the resource and all its children
                    delete_resource(r)
                    print('        id %d deleted' % r.id)
                else:  # just rename it so it's no longer a duplicate
                    r.name = '%s~%d' % (r.name, r.id)
                    db.session.commit()
                    print('        id %d renamed' % r.id)

    # recurse
    for r in resources:
        if not parent:
            print('checking %s...' % r.name)
        if r.name != 'notable':
            remove_duplicate_resources(r)
