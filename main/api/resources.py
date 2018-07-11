import json
import time  # fix(clean): remove?
import base64
import hashlib  # fix(clean): remove?
import zipfile
import datetime
import cStringIO


# external imports
from flask import request, abort, make_response
from sqlalchemy.orm.exc import NoResultFound
from flask_restful import Resource as ApiResource
from flask_login import current_user


# internal imports
from main.app import db
from main.users.models import User
from main.users.permissions import access_level, ACCESS_LEVEL_READ, ACCESS_LEVEL_WRITE
from main.util import parse_json_datetime
from main.resources.models import Resource, ResourceRevision, ResourceView, ControllerStatus, Thumbnail
from main.resources.resource_util import find_resource, read_resource, add_resource_revision, _create_file, update_sequence_value, resource_type_number, _create_folders, create_sequence
from main.resources.file_conversion import convert_csv_to_xls, convert_xls_to_csv, convert_new_lines, compute_thumbnail
from main.users.auth import find_key, find_key_fast, find_key_by_code  # fix(clean): remove?


class ResourceRecord(ApiResource):

    # get the current value or meta data of a resource
    def get(self, resource_path):
        args = request.values
        result = {}

        # handle case of controller requesting about self
        if resource_path == 'self':
            if 'authCode' in request.values:
                auth_code = request.values.get('authCode', '')  # fix(soon): remove auth codes
                key = find_key_by_code(auth_code)
            elif request.authorization:
                key = find_key(request.authorization.password)
            else:
                key = None
            if key and key.access_as_controller_id:
                try:
                    r = Resource.query.filter(Resource.id == key.access_as_controller_id).one()
                except NoResultFound:
                    abort(404)
            else:
                abort(403)

        # look up the resource record
        else:
            r = find_resource('/' + resource_path)
            if not r:
                abort(404)  # fix(later): revisit to avoid leaking file existance
            if access_level(r.query_permissions()) < ACCESS_LEVEL_READ:
                abort(403)

        # if request meta-data
        if request.values.get('meta', False):
            result = r.as_dict(extended = True)
            if request.values.get('include_path', False):
                result['path'] = r.path()

        # if request data
        else:

            # if folder, return contents list or zip of collection of files
            if r.type >= 10 and r.type < 20:

                # multi-file download
                if 'ids' in args and args.get('download', False):
                    ids = args['ids'].split(',')
                    return batch_download(r, ids)

                # contents list
                else:
                    recursive = request.values.get('recursive', False)
                    type_name = request.values.get('type', None)
                    if type_name:
                        type = resource_type_number(type_name)
                    else:
                        type = None
                    filter = request.values.get('filter', None)
                    extended = request.values.get('extended', False)
                    result = resource_list(r.id, recursive, type, filter, extended)

            # if sequence, return value(s)
            # fix(later): merge with file case?
            elif r.type == Resource.SEQUENCE:

                # get parameters
                text = request.values.get('text', '')
                download = request.values.get('download', False)
                count = int(request.values.get('count', 1))
                start_timestamp = request.values.get('start_timestamp', '')
                end_timestamp = request.values.get('end_timestamp', '')
                if start_timestamp:
                    try:
                        start_timestamp = parse_json_datetime(start_timestamp)
                    except:
                        abort(400, 'Invalid date/time.')
                if end_timestamp:
                    try:
                        end_timestamp = parse_json_datetime(end_timestamp)
                    except:
                        abort(400, 'Invalid date/time.')

                # if filters specified, assume we want a sequence of values
                if text or start_timestamp or end_timestamp or count > 1:

                    # get summary of values
                    if int(request.values.get('summary', False)):
                        return sequence_value_summary(r.id)

                    # get preliminary set of values
                    resource_revisions = ResourceRevision.query.filter(ResourceRevision.resource_id == r.id)

                    # apply filters (if any)
                    if text:
                        resource_revisions = resource_revisions.filter(text in ResourceRevision.data)
                    if start_timestamp:
                        resource_revisions = resource_revisions.filter(ResourceRevision.timestamp >= start_timestamp)
                    if end_timestamp:
                        resource_revisions = resource_revisions.filter(ResourceRevision.timestamp <= end_timestamp)
                    resource_revisions = resource_revisions.order_by('timestamp')
                    if resource_revisions.count() > count:
                        resource_revisions = resource_revisions[-count:]  # fix(later): is there a better/faster way to do this?

                    # return data
                    if download:
                        #timezone = r.root().system_attributes['timezone']  # fix(soon): use this instead of UTC
                        lines = ['utc_timestamp,value\n']
                        for rr in resource_revisions:
                            lines.append('%s,%s\n' % (rr.timestamp.strftime('%Y-%m-%d %H:%M:%S.%f'), rr.data))
                        result = make_response(''.join(lines))
                        result.headers['Content-Type'] = 'application/octet-stream'
                        result.headers['Content-Disposition'] = 'attachment; filename=' + r.name + '.csv'
                        return result
                    else:
                        epoch = datetime.datetime.utcfromtimestamp(0)  # fix(clean): merge with similar code for sequence viewer
                        timestamps = [(rr.timestamp.replace(tzinfo = None) - epoch).total_seconds() for rr in resource_revisions]  # fix(clean): use some sort of unzip function
                        values = [rr.data for rr in resource_revisions]
                        return {'name': r.name, 'timestamps': timestamps, 'values': values}

                # if no filter assume just want current value
                # fix(later): should instead provide all values and have a separate way to get more recent value?
                else:
                    rev = request.values.get('rev')
                    if rev:
                        rev = int(rev)  # fix(soon): save int conversion
                    result = make_response(read_resource(r, revision_id = rev))
                    data_type = json.loads(r.system_attributes)['data_type']
                    if data_type == Resource.IMAGE_SEQUENCE:
                        result.headers['Content-Type'] = 'image/jpeg'
                    else:
                        result.headers['Content-Type'] = 'text/plain'

            # if file, return file data/contents
            else:
                data = read_resource(r)
                if not data:
                    abort(404)
                name = r.name
                if request.values.get('convert_to', request.values.get('convertTo', '')) == 'xls' and r.name.endswith('csv'):
                    data = convert_csv_to_xls(data)
                    name = name.replace('csv', 'xls')
                result = make_response(data)
                result.headers['Content-Type'] = 'application/octet-stream'
                if request.values.get('download', False):
                    result.headers['Content-Disposition'] = 'attachment; filename=' + name
        return result

    # delete a resource
    def delete(self, resource_path):
        r = find_resource('/' + resource_path)
        if not r:
            abort(404)  # fix(later): revisit to avoid leaking file existance
        if access_level(r.query_permissions()) < ACCESS_LEVEL_WRITE:
            abort(403)
        if request.values.get('data_only', False):
            ResourceRevision.query.filter(ResourceRevision.resource_id == r.id).delete()
            # fix(later): support delete_min_timestamp and delete_max_timestamp to delete subsets
        else:
            r.deleted = True
        db.session.commit()
        return {'status': 'ok', 'id': r.id}

    # create new resource
    # fix(soon): remove this after update client installations; should use ResourceList POST not this endpoint
    def post(self, resource_path):

        # note: should check parent permissions, not org permissions, but no need to fix since we'll delete this code
        org_name = resource_path.split('/')[0]
        org_resource = find_resource('/' + org_name)
        if not org_resource:
            abort(403)
        if access_level(org_resource.query_permissions()) < ACCESS_LEVEL_WRITE:
            abort(403)

        # get attributes of new file
        args = request.values
        if 'contents' in args:
            data = base64.b64decode(args['contents'])  # fix(clean): remove this case
        else:
            data = base64.b64decode(args.get('data', ''))
        if 'creation_timestamp' in args:
            creation_timestamp = parse_json_datetime(args['creation_timestamp'])
        else:
            creation_timestamp = datetime.datetime.utcnow()
        if 'modification_timestamp' in args:
            modification_timestamp = parse_json_datetime(args['modification_timestamp'])
        else:
            modification_timestamp = creation_timestamp

        # create the file or folder
        r = _create_file(resource_path, creation_timestamp, modification_timestamp, data)
        return {'status': 'ok', 'id': r.id}

    # update existing resource
    def put(self, resource_path):
        r = find_resource('/' + resource_path)
        if not r:
            abort(404)  # fix(later): revisit to avoid leaking file existance
        if access_level(r.query_permissions()) < ACCESS_LEVEL_WRITE:
            abort(403)
        args = request.values

        # update resource name/location
        if 'name' in args:
            new_name = args['name']
            if new_name != r.name:
                try:
                    Resource.query.filter(Resource.parent_id == r.parent_id, Resource.name == new_name, Resource.deleted == False).one()
                    abort(400)  # a resource already exists with this name
                except NoResultFound:
                    pass
                r.name = new_name
        if 'parent' in args:
            parent_resource = find_resource(args['parent'])  # expects leading slash
            if not parent_resource:
                abort(400)
            if access_level(parent_resource.query_permissions()) < ACCESS_LEVEL_WRITE:
                abort(403)
            try:
                Resource.query.filter(Resource.parent_id == parent_resource.id, Resource.name == r.name, Resource.deleted == False).one()
                abort(400)  # a resource already exists with this name
            except NoResultFound:
                pass
            r.parent_id = parent_resource.id

        # update view
        if 'view' in args and current_user.is_authenticated:
            try:
                resource_view = ResourceView.query.filter(ResourceView.resource_id == r.id, ResourceView.user_id == current_user.id).one()
                resource_view.view = args['view']
            except NoResultFound:
                resource_view = ResourceView()
                resource_view.resource_id = r.id
                resource_view.user_id = current_user.id
                resource_view.view = args['view']
                db.session.add(resource_view)

        # update other resource metadata
        if 'user_attributes' in args:
            r.user_attributes = args['user_attributes']
        if r.type == Resource.SEQUENCE:
            if 'data_type' in args or 'decimal_places' in args or 'max_history' in args or 'min_storage_interval' in args or 'units' in args:
                system_attributes = json.loads(r.system_attributes)
                if 'data_type' in args:
                    system_attributes['data_type'] = args['data_type']
                if args.get('decimal_places', '') != '':
                    system_attributes['decimal_places'] = int(args['decimal_places'])  # fix(later): safe convert
                if args.get('max_history', '') != '':
                    system_attributes['max_history'] = int(args['max_history'])  # fix(later): safe convert
                if args.get('units', '') != '':
                    system_attributes['units'] = args['units']
                if args.get('min_storage_interval', '') != '':
                    system_attributes['min_storage_interval'] = int(args['min_storage_interval'])  # fix(later): safe convert
                r.system_attributes = json.dumps(system_attributes)
        elif r.type == Resource.REMOTE_FOLDER:
            system_attributes = json.loads(r.system_attributes) if r.system_attributes else {}
            if 'remote_path' in args:
                system_attributes['remote_path'] = args['remote_path']
            if 'controller_id' in args:
                system_attributes['controller_id'] = args['controller_id']
            r.system_attributes = json.dumps(system_attributes)
        elif r.type == Resource.ORGANIZATION_FOLDER:
            system_attributes = json.loads(r.system_attributes) if r.system_attributes else {}
            if 'full_name' in args and args['full_name']:
                system_attributes['full_name'] = args['full_name']
            r.system_attributes = json.dumps(system_attributes)
        elif r.type == Resource.CONTROLLER_FOLDER:
            if 'status' in args:
                try:
                    controller_status = ControllerStatus.query.filter(ControllerStatus.id == r.id).one()
                    status = json.loads(controller_status.attributes)
                    status.update(json.loads(args['status']))  # add/update status (don't provide way to remove status fields; maybe should overwrite instead)
                    controller_status.attributes = json.dumps(status)
                except NoResultFound:
                    pass
        else:  # fix(soon): remove this case
            if 'system_attributes' in args:
                r.system_attributes = args['system_attributes']  # note that this will overwrite any existing system attributes; client must preserve any that aren't modified

        # update resource contents/value
        if 'contents' in args or 'data' in args:  # fix(later): remove contents option
            if 'contents' in args:
                data = args['contents']
            else:
                data = str(args['data'])  # convert unicode to regular string / fix(soon): revisit this
            timestamp = datetime.datetime.utcnow()
            if r.type == Resource.SEQUENCE:  # fix(later): collapse these two cases?
                resource_path = resource.path()  # fix(faster): don't need to use this if were given path as arg
                update_sequence_value(resource, resource_path, timestamp, data)
            else:
                add_resource_revision(r, timestamp, data)
                r.modification_timestamp = timestamp
        db.session.commit()
        return {'status': 'ok', 'id': r.id}


class ResourceList(ApiResource):

    # get a list of resources of a particular type
    # (use the individual resource GET method to get a list of resources contained with a folder)
    # fix(later): decide what this should do; current just using for system controller list
    def get(self):
        args = request.values
        if current_user.is_anonymous or current_user.role != User.SYSTEM_ADMIN:
            abort(403)
        type = int(args['type'])
        extended = int(args.get('extended', '0'))
        include_path = args.get('folder_info', args.get('folderInfo', False))  # fix(soon): change folderInfo to include_path?
        resources = Resource.query.filter(Resource.type == type, Resource.deleted == False)
        result = {}
        for r in resources:
            d = r.as_dict(extended = extended)
            if r.type == Resource.CONTROLLER_FOLDER:
                try:
                    controller_status = ControllerStatus.query.filter(ControllerStatus.id == r.id).one()
                    d.update(controller_status.as_dict())
                except NoResultFound:
                    pass
            if include_path:
                d['path'] = r.path()
            result[r.id] = d
        return result

    # create a new resource
    def post(self):
        args = request.values

        # get parent
        path = args.get('path', args.get('parent'))  # fix(soon): decide whether to use path or parent
        if not path:
            abort(400)
        parent_resource = find_resource(path)  # expects leading slash
        if not parent_resource:
            try:  # fix(soon): need to traverse up tree to check permissions, not just check org permissions
                org_name = path.split('/')[1]
                org_resource = Resource.query.filter(Resource.name == org_name, Resource.parent_id == None, Resource.deleted == False).one()
                if access_level(org_resource.query_permissions()) < ACCESS_LEVEL_WRITE:
                    abort(403)
            except NoResultFound:
                abort(403)
            _create_folders(path.strip('/'))
            parent_resource = find_resource(path)
            if not parent_resource:
                abort(400)

        # make sure we have write access to parent
        if access_level(parent_resource.query_permissions()) < ACCESS_LEVEL_WRITE:
            abort(403)

        # get main parameters
        file = request.files.get('file', None)
        name = file.filename if file else args['name']
        type = int(args['type'])  # fix(soon): safe int conversion

        # get timestamps
        if 'creation_timestamp' in args:
            creation_timestamp = parse_json_datetime(args['creation_timestamp'])
        elif 'creationTimestamp' in args:
            creation_timestamp = parse_json_datetime(args['creationTimestamp'])
        else:
            creation_timestamp = datetime.datetime.utcnow()
        if 'modification_timestamp' in args:
            modification_timestamp = parse_json_datetime(args['modification_timestamp'])
        elif 'modificationTimestamp' in args:
            modification_timestamp = parse_json_datetime(args['modificationTimestamp'])
        else:
            modification_timestamp = creation_timestamp

        # check for existing resource
        try:
            resource = Resource.query.filter(Resource.parent_id == parent_resource.id, Resource.name == name, Resource.deleted == False).one()
            return {'message': 'Resource already exists.', 'status': 'error'}  # fix(soon): return 400 status code
        except NoResultFound:
            pass

        # create resource
        r = Resource()
        r.parent_id = parent_resource.id
        r.organization_id = parent_resource.organization_id
        r.name = name
        r.type = type
        r.creation_timestamp = creation_timestamp
        r.modification_timestamp = modification_timestamp
        if type == Resource.FILE:  # temporarily mark resource as deleted in case we fail to create resource revision record
            r.deleted = True
        else:
            r.deleted = False
        if 'user_attributes' in args:
            r.user_attributes = args['user_attributes']  # we assume that the attributes are already a JSON string

        # handle sub-types
        if type == Resource.FILE:

            # get file contents (if any) from request
            if file:
                stream = cStringIO.StringIO()
                file.save(stream)
                data = stream.getvalue()
            else:
                data = base64.b64decode(args.get('contents', args.get('data', '')))  # fix(clean): remove contents version

            # convert files to standard types/formgat
            # fix(soon): should give the user a warning or ask for confirmation
            if name.endswith('xls') or name.endswith('xlsx'):
                data = convert_xls_to_csv(data)
                name = name.rsplit('.')[0] + '.csv'
                r.name = name
            if name.endswith('csv') or name.endswith('txt'):
                data = convert_new_lines(data)

            # compute other file attributes
            system_attributes = {
                'hash': hashlib.sha1(data).hexdigest(),
                'size': len(data),
            }
            if 'file_type' in args:  # fix(soon): can we remove this? current just using for markdown files
                system_attributes['file_type'] = args['file_type']
            r.system_attributes = json.dumps(system_attributes)
        elif type == Resource.SEQUENCE:
            data_type = int(args['data_type'])  # fix(soon): safe convert to int
            system_attributes = {
                'max_history': 10000,
                'data_type': data_type,
            }
            if args.get('decimal_places', '') != '':
                system_attributes['decimal_places'] = int(args['decimal_places'])  # fix(soon): safe convert to int
            if args.get('min_storage_interval', '') != '':
                min_storage_interval = int(args['min_storage_interval'])  # fix(soon): safe convert to int
            else:
                if data_type == Resource.TEXT_SEQUENCE:
                    min_storage_interval = 0  # default to 0 seconds for text sequences (want to record all log entries)
                else:
                    min_storage_interval = 50  # default to 50 seconds for numeric and image sequences
            if args.get('units'):
                system_attributes['units'] = args['units']
            system_attributes['min_storage_interval'] = min_storage_interval
            r.system_attributes = json.dumps(system_attributes)
        elif type == Resource.REMOTE_FOLDER:
            r.system_attributes = json.dumps({
                'remote_path': args['remote_path'],
            })

        # save resource record
        db.session.add(r)
        db.session.commit()

        # save file contents (after we have resource ID) and compute thumbnail if needed
        if type == Resource.FILE:
            add_resource_revision(r, r.creation_timestamp, data)
            r.deleted = False  # now that have sucessfully created revision, we can make the resource live
            db.session.commit()

            # compute thumbnail
            # fix(soon): recompute thumbnail on resource update
            if name.endswith('.png') or name.endswith('.jpg'):  # fix(later): handle more types, capitalizations
                for width in [120]:  # fix(later): what will be our standard sizes?
                    (thumbnail_contents, thumbnail_width, thumbnail_height) = compute_thumbnail(data, width)  # fix(later): if this returns something other than requested width, we'll keep missing the cache
                    thumbnail = Thumbnail()
                    thumbnail.resource_id = r.id
                    thumbnail.width = thumbnail_width
                    thumbnail.height = thumbnail_height
                    thumbnail.format = 'jpg'
                    thumbnail.data = thumbnail_contents
                    db.session.add(thumbnail)

        # handle the case of creating a controller; requires creating some additional records
        elif type == Resource.CONTROLLER_FOLDER:

            # create controller status record
            controller_status = ControllerStatus()
            controller_status.id = r.id
            controller_status.client_version = ''
            controller_status.web_socket_connected = False
            controller_status.watchdog_notification_sent = False
            controller_status.attributes = '{}'
            db.session.add(controller_status)
            db.session.commit()

            # create log sequence
            create_sequence(r, 'log', Resource.TEXT_SEQUENCE, max_history = 10000)

            # create a folder for status sequences
            status_folder = Resource()
            status_folder.parent_id = r.id
            status_folder.organization_id = r.organization_id
            status_folder.name = 'status'
            status_folder.type = Resource.BASIC_FOLDER
            status_folder.creation_timestamp = datetime.datetime.utcnow()
            status_folder.modification_timestamp = status_folder.creation_timestamp
            db.session.add(status_folder)
            db.session.commit()

            # create status sequences
            create_sequence(status_folder, 'free_disk_space', Resource.NUMERIC_SEQUENCE, max_history = 10000, units = 'bytes')
            create_sequence(status_folder, 'processor_usage', Resource.NUMERIC_SEQUENCE, max_history = 10000, units = 'percent')
            create_sequence(status_folder, 'messages_sent', Resource.NUMERIC_SEQUENCE, max_history = 10000)
            create_sequence(status_folder, 'messages_received', Resource.NUMERIC_SEQUENCE, max_history = 10000)
            create_sequence(status_folder, 'serial_errors', Resource.NUMERIC_SEQUENCE, max_history = 10000)

        return {'status': 'ok', 'id': r.id}

    # update multiple resources at once
    # (currently only intended for updating multiple sequences at once)
    # values should be a dictionary mapping resource paths (starting with slash) to values
    # if timestamp is specified, it will be applied used for the updates
    def put(self):
        start_time = time.time()
        values = json.loads(request.values['values'])
        if 'timestamp' in request.values:
            timestamp = parse_json_datetime(request.values['timestamp'])

            # check for drift
            delta = datetime.datetime.utcnow() - timestamp
            drift = delta.total_seconds()
            #print 'drift', drift
            if abs(drift) > 30:

                # get current controller correction
                # fix(later): support user updates as well?
                auth = request.authorization
                start_key_time = time.time()
                key = find_key_fast(auth.password)  # key is provided as HTTP basic auth password
                end_key_time = time.time()
                #print '---- key: %.2f' % (end_key_time - start_key_time)
                if key and key.access_as_controller_id:
                    controller_id = key.access_as_controller_id
                    controller_status = ControllerStatus.query.filter(ControllerStatus.id == controller_id).one()
                    attributes = json.loads(controller_status.attributes)
                    correction = attributes.get('timestamp_correction', 0)

                    # if stored correction is reasonable, use it; otherwise store new correction
                    if abs(correction - drift) > 100:
                        correction = drift
                        attributes['timestamp_correction'] = drift
                        controller_status.attributes = json.dumps(attributes)
                        db.session.commit()
                        #print 'storing new correction (%.2f)' % correction
                    else:
                        pass
                        #print 'applying previous correction (%.2f)' % correction
                    timestamp += datetime.timedelta(seconds=correction)
        else:
            timestamp = datetime.datetime.utcnow()

        # for now, assume all sequences in same folder
        first_name = values.iterkeys().next()
        folder_name = first_name.rsplit('/', 1)[0]
        folder_resource = find_resource(folder_name)
        if folder_resource: # and access_level(folder_resource.query_permissions()) >= ACCESS_LEVEL_WRITE:
            for (full_name, value) in values.iteritems():
                seq_name = full_name.rsplit('/', 1)[1]
                try:
                    resource = Resource.query.filter(Resource.parent_id == folder_resource.id, Resource.name == seq_name, Resource.deleted == False).one()
                    update_sequence_value(resource, full_name, timestamp, str(value), emit_message=False)  # fix(later): revisit emit_message
                except NoResultFound:
                    pass
        db.session.commit()
        end_time = time.time()
        #print '==== %.2f' % (end_time - start_time)


# get a list of all resources contained with a folder (specified by parent_id)
def resource_list(parent_id, recursive, type, filter, extended):
    children = Resource.query.filter(Resource.parent_id == parent_id, Resource.deleted == False).order_by('name')
    if type:
        children = children.filter(Resource.type == type)
    if filter:
        filter = filter.replace('*', '%')
        children = children.filter(Resource.name.like(filter))
    file_infos = []
    for child in children:
        file_info = child.as_dict(extended = extended)
        if extended and child.type == Resource.CONTROLLER_FOLDER:
            try:
                controller_status = ControllerStatus.query.filter(ControllerStatus.id == child.id).one()
                file_info.update(controller_status.as_dict(extended=True))
            except NoResultFound:
                pass
        if recursive:
            file_info['path'] = child.path()
            file_info['fullPath'] = child.path()  # fix(soon): remove this
        file_infos.append(file_info)
    if recursive:
        child_folders = Resource.query.filter(Resource.parent_id == parent_id, Resource.type >= 10, Resource.type < 20, Resource.deleted == False)
        for child_folder in child_folders:
            file_infos += resource_list(child_folder.id, recursive, type, filter, extended)
    return file_infos


# compute a summary of the previous values of a sequence
def sequence_value_summary(resource_id):
    history_count = int(request.values['count'])
    prefix_length = int(request.values['prefix_length'])
    seq_values = ResourceRevision.query.filter(ResourceRevision.resource_id == resource_id).order_by(ResourceRevision.id.desc())[:history_count]

    # for each prefix, compute count and longest-common-prefix
    value_groups = {}
    for sv in seq_values:
        value = sv.data
        prefix = value[:prefix_length]
        if prefix in value_groups:
            (lcp, count) = value_groups[prefix]
            if not value.startswith(lcp):
                start = len(prefix)
                length = min(len(lcp), len(value))
                for i in range(start, length):
                    if lcp[i] != value[i]:
                        length = i
                        break
                lcp = lcp[:length]
            count += 1
        else:
            lcp = value
            count = 1
        value_groups[prefix] = (lcp, count)

    # sort by counts
    counts = [(count, lcp) for (lcp, count) in value_groups.itervalues()]
    counts.sort(reverse = True)
    return [(lcp, count) for (count, lcp) in counts]


# add a file or folder (recursively) to the zip file; uncompressed_size is a single-element list to allow modification inside function
def add_to_zip(zip, resource, path_prefix, uncompressed_size):
    name = (path_prefix + '/' + resource.name) if path_prefix else resource.name

    # add file contents
    if resource.type == Resource.FILE:

        # read data
        data = read_resource(resource)
        if not data:
            abort(404)
        uncompressed_size[0] += len(data)
        if uncompressed_size[0] >= 500 * 1024 * 1024:
            abort(400, 'Batch download only supported if total file size is less than 500MB.')  # fix(later): friendlier error handling

        # add to zip file
        zip.writestr(name, data)

    # add folder contents
    elif resource.type == Resource.BASIC_FOLDER:
        resources = Resource.query.filter(Resource.parent_id == resource.id, Resource.deleted == False)
        for r in resources:
            add_to_zip(zip, r, name, uncompressed_size)  # fix(soon): should we check permissions on each resource?


# download the a set of resources (from within a single folder) as a zip file
# fix(later): doesn't include empty folders
def batch_download(parent_folder, ids):

    # create zip file
    zip_file = cStringIO.StringIO()
    zip = zipfile.ZipFile(zip_file, 'w', zipfile.ZIP_DEFLATED, False)
    uncompressed_size = [0]

    # loop over IDs
    for id in ids:

        # get resource
        try:
            r = Resource.query.filter(Resource.parent_id == parent_folder.id, Resource.id == id, Resource.deleted == False).one()
        except NoResultFound:
            abort(404)

        # check permissions
        if access_level(r.query_permissions()) < ACCESS_LEVEL_READ:
            abort(403)

        # only process files and folders (for now)
        if r.type == Resource.FILE or r.type == Resource.BASIC_FOLDER:
            add_to_zip(zip, r, '', uncompressed_size)

    # make sure permissions are ok in Linux
    for zf in zip.filelist:
        zf.create_system = 0

    # return zip file contents
    zip.close()
    zip_file.seek(0)
    data = zip_file.read()
    result = make_response(data)
    result.headers['Content-Type'] = 'application/octet-stream'
    result.headers['Content-Disposition'] = 'attachment; filename=' + parent_folder.name + '_files.zip'
    return result
