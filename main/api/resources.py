import json
import base64
import hashlib  # fix(clean): remove?
import zipfile
import datetime
from io import BytesIO


# external imports
from flask import request, abort, make_response
from sqlalchemy import not_
from sqlalchemy.orm.exc import NoResultFound
from flask_restful import Resource as ApiResource
from flask_login import current_user


# internal imports
from main.app import db
from main.users.models import User
from main.users.permissions import access_level, ACCESS_LEVEL_READ, ACCESS_LEVEL_WRITE
from main.util import parse_json_datetime
from main.resources.models import Resource, ResourceRevision, ResourceView, ControllerStatus, Thumbnail
from main.resources.resource_util import find_resource, read_resource, add_resource_revision, _create_file, update_sequence_value, \
    resource_type_number, _create_folders, create_sequence
from main.resources.file_conversion import convert_csv_to_xls, convert_xls_to_csv, convert_new_lines, compute_thumbnail
from main.users.auth import find_key  # fix(clean): remove?


class ResourceRecord(ApiResource):

    # get the current value or meta data of a resource
    def get(self, resource_path):
        resource_path = '/' + resource_path  # we always want resource paths to start with leading slash
        args = request.values
        result = {}

        # handle case of controller requesting about self
        if resource_path == '/self':
            if request.authorization:
                key = find_key(request.authorization.password)
            else:
                key = None
            if key and key.access_as_controller_id:
                try:
                    r = Resource.query.filter(Resource.id == key.access_as_controller_id).one()
                    resource_path = r.path()
                except NoResultFound:
                    abort(404)
            else:
                abort(403)

        # look up the resource record
        else:
            r = find_resource(resource_path)
            if not r:
                abort(404)  # fix(later): revisit to avoid leaking file existance
            if access_level(r.query_permissions()) < ACCESS_LEVEL_READ:
                abort(403)

        # if request meta-data
        if request.values.get('meta', False):
            result = r.as_dict(extended=True)
            result['path'] = resource_path

        # if request data
        else:

            # if folder, return contents list or zip of collection of files
            if 10 <= r.type < 20:

                # multi-file download
                if 'ids' in args and args.get('download', False):
                    ids = args['ids'].split(',')
                    return batch_download(r, ids)

                # contents list
                else:
                    recursive = request.values.get('recursive', False)
                    type_name = request.values.get('type', None)
                    if type_name:
                        type_number = resource_type_number(type_name)
                    else:
                        type_number = None
                    name_filter = request.values.get('filter', None)
                    extended = request.values.get('extended', False)
                    result = resource_list(r.id, recursive, type_number, name_filter, extended)

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
                    except ValueError:
                        abort(400, 'Invalid date/time.')
                if end_timestamp:
                    try:
                        end_timestamp = parse_json_datetime(end_timestamp)
                    except ValueError:
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
                        # timezone = r.root().system_attributes['timezone']  # fix(soon): use this instead of UTC
                        lines = ['utc_timestamp,value\n']
                        for rr in resource_revisions:
                            lines.append('%s,%s\n' % (rr.timestamp.strftime('%Y-%m-%d %H:%M:%S.%f'), rr.data))
                        result = make_response(''.join(lines))
                        result.headers['Content-Type'] = 'application/octet-stream'
                        result.headers['Content-Disposition'] = 'attachment; filename=' + r.name + '.csv'
                        return result
                    else:
                        epoch = datetime.datetime.utcfromtimestamp(0)  # fix(clean): merge with similar code for sequence viewer
                        # fix(clean): use some sort of unzip function
                        timestamps = [(rr.timestamp.replace(tzinfo=None) - epoch).total_seconds() for rr in resource_revisions]
                        values = [rr.data.decode() for rr in resource_revisions]
                        units = json.loads(r.system_attributes).get('units', None)
                        return {'name': r.name, 'path': resource_path, 'units': units, 'timestamps': timestamps, 'values': values}

                # if no filter assume just want current value
                # fix(later): should instead provide all values and have a separate way to get more recent value?
                else:
                    rev = request.values.get('rev')
                    if rev:
                        rev = int(rev)  # fix(soon): save int conversion
                    result = make_response(read_resource(r, revision_id=rev))
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
        resource_path = '/' + resource_path  # we always want resource paths to start with leading slash

        # note: should check parent permissions, not org permissions, but no need to fix since we'll delete this code
        org_name = resource_path.split('/')[1]
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
        resource_path = '/' + resource_path  # we always want resource paths to start with leading slash
        r = find_resource(resource_path)
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
                    Resource.query.filter(Resource.parent_id == r.parent_id, Resource.name == new_name, not_(Resource.deleted)).one()
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
                Resource.query.filter(Resource.parent_id == parent_resource.id, Resource.name == r.name, not_(Resource.deleted)).one()
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
        if r.type == Resource.SEQUENCE:  # fix(soon): should use args['system_attributes'] instead of just args
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
            # fix(soon): should use args['system_attributes'] instead of just args
            update_system_attributes(r, args, ['remote_path', 'controller_id'])
        elif r.type == Resource.ORGANIZATION_FOLDER:
            update_system_attributes(r, args, ['full_name'])  # fix(soon): should use args['system_attributes'] instead of just args
        elif r.type == Resource.CONTROLLER_FOLDER:
            if 'status' in args:
                try:
                    controller_status = ControllerStatus.query.filter(ControllerStatus.id == r.id).one()
                    status = json.loads(controller_status.attributes)
                    # add/update status (don't provide way to remove status fields; maybe should overwrite instead)
                    status.update(json.loads(args['status']))
                    controller_status.attributes = json.dumps(status)
                except NoResultFound:
                    pass
            if 'system_attributes' in args:
                update_system_attributes(r, json.loads(args['system_attributes']), ['watchdog_recipients', 'watchdog_minutes'])
        else:  # fix(soon): remove this case
            if 'system_attributes' in args:
                # note that this will overwrite any existing system attributes; client must preserve any that aren't modified
                r.system_attributes = args['system_attributes']

        # update resource contents/value
        if 'contents' in args or 'data' in args:  # fix(later): remove contents option
            if 'contents' in args:
                data = args['contents']
            else:
                data = base64.b64decode(str(args['data']))  # convert unicode to regular string / fix(soon): revisit this
            timestamp = datetime.datetime.utcnow()
            if r.type == Resource.SEQUENCE:  # fix(later): collapse these two cases?
                resource_path = r.path()  # fix(faster): don't need to use this if were given path as arg
                update_sequence_value(r, resource_path, timestamp, data.decode())  # update sequence value expects string
            else:
                add_resource_revision(r, timestamp, data)  # this can be binary
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
        resource_type = int(args['type'])
        extended = int(args.get('extended', '0'))
        include_path = args.get('folder_info', args.get('folderInfo', False))  # fix(soon): change folderInfo to include_path?
        resources = Resource.query.filter(Resource.type == resource_type, not_(Resource.deleted))
        result = {}
        for r in resources:
            d = r.as_dict(extended=extended)
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
        if not path or not path.startswith('/'):
            abort(400)
        parent_resource = find_resource(path)  # expects leading slash
        if not parent_resource:
            try:  # fix(soon): need to traverse up tree to check permissions, not just check org permissions
                org_name = path.split('/')[1]
                org_resource = Resource.query.filter(Resource.name == org_name, Resource.parent_id.is_(None), not_(Resource.deleted)).one()
                if access_level(org_resource.query_permissions()) < ACCESS_LEVEL_WRITE:
                    abort(403)
            except NoResultFound:
                abort(403)
            _create_folders(path)
            parent_resource = find_resource(path)
            if not parent_resource:
                abort(400)

        # make sure we have write access to parent
        if access_level(parent_resource.query_permissions()) < ACCESS_LEVEL_WRITE:
            abort(403)

        # get main parameters
        file = request.files.get('file', None)
        name = file.filename if file else args['name']
        resource_type = int(args['type'])  # fix(soon): safe int conversion

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
            Resource.query.filter(Resource.parent_id == parent_resource.id, Resource.name == name, not_(Resource.deleted)).one()
            return {'message': 'Resource already exists.', 'status': 'error'}  # fix(soon): return 400 status code
        except NoResultFound:
            pass

        # create resource
        r = Resource()
        r.parent_id = parent_resource.id
        r.organization_id = parent_resource.organization_id
        r.name = name
        r.type = resource_type
        r.creation_timestamp = creation_timestamp
        r.modification_timestamp = modification_timestamp
        if resource_type == Resource.FILE:  # temporarily mark resource as deleted in case we fail to create resource revision record
            r.deleted = True
        else:
            r.deleted = False
        if 'user_attributes' in args:
            r.user_attributes = args['user_attributes']  # we assume that the attributes are already a JSON string

        # handle sub-types
        if resource_type == Resource.FILE:

            # get file contents (if any) from request
            if file:
                stream = BytesIO()
                file.save(stream)
                data = stream.getvalue()
            else:
                data = base64.b64decode(args.get('contents', args.get('data', '')))  # fix(clean): remove contents version

            # convert files to standard types/formgat
            # fix(soon): should give the user a warning or ask for confirmation
            if name.endswith('xls') or name.endswith('xlsx'):
                data = convert_xls_to_csv(data).encode()
                name = name.rsplit('.')[0] + '.csv'
                r.name = name
            if name.endswith('csv') or name.endswith('txt'):
                data = convert_new_lines(data.decode()).encode()

            # compute other file attributes
            system_attributes = {
                'hash': hashlib.sha1(data).hexdigest(),
                'size': len(data),
            }
            r.system_attributes = json.dumps(system_attributes)
        elif resource_type == Resource.SEQUENCE:
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
        elif resource_type == Resource.REMOTE_FOLDER:
            r.system_attributes = json.dumps({
                'remote_path': args['remote_path'],
            })

        # save resource record
        db.session.add(r)
        db.session.commit()

        # save file contents (after we have resource ID) and compute thumbnail if needed
        if resource_type == Resource.FILE:
            add_resource_revision(r, r.creation_timestamp, data)  # we assume data is already binary/encoded
            r.deleted = False  # now that have sucessfully created revision, we can make the resource live
            db.session.commit()

            # compute thumbnail
            # fix(soon): recompute thumbnail on resource update
            if name.endswith('.png') or name.endswith('.jpg'):  # fix(later): handle more types, capitalizations
                for width in [120]:  # fix(later): what will be our standard sizes?
                    # fix(later): if this returns something other than requested width, we'll keep missing the cache
                    (thumbnail_contents, thumbnail_width, thumbnail_height) = compute_thumbnail(data, width)
                    thumbnail = Thumbnail()
                    thumbnail.resource_id = r.id
                    thumbnail.width = thumbnail_width
                    thumbnail.height = thumbnail_height
                    thumbnail.format = 'jpg'
                    thumbnail.data = thumbnail_contents
                    db.session.add(thumbnail)

        # handle the case of creating a controller; requires creating some additional records
        elif resource_type == Resource.CONTROLLER_FOLDER:

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
            create_sequence(r, 'log', Resource.TEXT_SEQUENCE, max_history=10000)

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
            create_sequence(status_folder, 'free_disk_space', Resource.NUMERIC_SEQUENCE, max_history=10000, units='bytes')
            create_sequence(status_folder, 'processor_usage', Resource.NUMERIC_SEQUENCE, max_history=10000, units='percent')
            create_sequence(status_folder, 'messages_sent', Resource.NUMERIC_SEQUENCE, max_history=10000)
            create_sequence(status_folder, 'messages_received', Resource.NUMERIC_SEQUENCE, max_history=10000)
            create_sequence(status_folder, 'serial_errors', Resource.NUMERIC_SEQUENCE, max_history=10000)

        return {'status': 'ok', 'id': r.id}

    # update multiple resources at once
    # (currently only intended for updating multiple sequences at once)
    # values should be a dictionary mapping resource paths (starting with slash) to values
    # if timestamp is specified, it will be applied used for the updates
    def put(self):
        values = json.loads(request.values['values'])
        if 'timestamp' in request.values:
            timestamp = parse_json_datetime(request.values['timestamp'])

            # check for drift
            delta = datetime.datetime.utcnow() - timestamp
            drift = delta.total_seconds()
            # print 'drift', drift
            if abs(drift) > 30:

                # get current controller correction
                # fix(later): support user updates as well?
                auth = request.authorization
                key = find_key(auth.password)  # key is provided as HTTP basic auth password
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
                        # print 'storing new correction (%.2f)' % correction
                    else:
                        pass
                        # print 'applying previous correction (%.2f)' % correction
                    timestamp += datetime.timedelta(seconds=correction)
        else:
            timestamp = datetime.datetime.utcnow()

        # for now, assume all sequences in same folder
        items = list(values.items())
        if items:
            items = sorted(items)  # sort by keys so we can re-use folder lookup and permission check between items in same folder
            folder_resource = None
            folder_name = None
            for (full_name, value) in items:
                item_folder_name = full_name.rsplit('/', 1)[0]
                if item_folder_name != folder_name:  # if this folder doesn't match the folder resource record we have
                    folder_name = item_folder_name
                    folder_resource = find_resource(folder_name)
                    if folder_resource and access_level(folder_resource.query_permissions()) < ACCESS_LEVEL_WRITE:
                        folder_resource = None  # don't have write access
                if folder_resource:
                    seq_name = full_name.rsplit('/', 1)[1]
                    try:
                        resource = (
                            Resource.query
                            .filter(Resource.parent_id == folder_resource.id, Resource.name == seq_name, not_(Resource.deleted))
                            .one()
                        )
                        update_sequence_value(resource, full_name, timestamp, str(value), emit_message=True)  # fix(later): revisit emit_message
                    except NoResultFound:
                        pass
            db.session.commit()


# update resource record system attributes using a dictionary of new system attributes (send via REST API)
def update_system_attributes(resource, new_system_attribs, allowed_attribs):
    system_attributes = json.loads(resource.system_attributes) if resource.system_attributes else {}
    for attrib_name in allowed_attribs:
        if attrib_name in new_system_attribs and new_system_attribs[attrib_name]:
            system_attributes[attrib_name] = new_system_attribs[attrib_name]
    resource.system_attributes = json.dumps(system_attributes)


def resource_list(parent_id, recursive, resource_type, name_filter, extended):
    """Get a list of all resources contained with a folder (specified by parent_id)

    name_filter may contain "*" wildcards.
    """
    children = Resource.query.filter(Resource.parent_id == parent_id, not_(Resource.deleted)).order_by('name')
    if resource_type:
        children = children.filter(Resource.type == resource_type)
    if name_filter:
        name_filter = name_filter.replace('*', '%')
        children = children.filter(Resource.name.like(name_filter))
    file_infos = []
    for child in children:
        file_info = child.as_dict(extended=extended)
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
        child_folders = Resource.query.filter(Resource.parent_id == parent_id, Resource.type >= 10, Resource.type < 20, not_(Resource.deleted))
        for child_folder in child_folders:
            file_infos += resource_list(child_folder.id, recursive, resource_type, name_filter, extended)
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
    counts = [(count, lcp) for (lcp, count) in value_groups.values()]
    counts.sort(reverse=True)
    return [(lcp, count) for (count, lcp) in counts]


# add a file or folder (recursively) to the zip file; uncompressed_size is a single-element list to allow modification inside function
def add_to_zip(zip_file, resource, path_prefix, uncompressed_size):
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
        zip_file.writestr(name, data)

    # add folder contents
    elif resource.type == Resource.BASIC_FOLDER:
        resources = Resource.query.filter(Resource.parent_id == resource.id, not_(Resource.deleted))
        for r in resources:
            add_to_zip(zip_file, r, name, uncompressed_size)  # fix(soon): should we check permissions on each resource?


# download the a set of resources (from within a single folder) as a zip file
# fix(later): doesn't include empty folders
def batch_download(parent_folder, ids):

    # create zip file
    zip_buffer = BytesIO()
    zip_file = zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED, False)
    uncompressed_size = [0]

    # loop over IDs
    for resource_id in ids:

        # get resource
        try:
            r = Resource.query.filter(Resource.parent_id == parent_folder.id, Resource.id == resource_id, not_(Resource.deleted)).one()
        except NoResultFound:
            abort(404)

        # check permissions
        if access_level(r.query_permissions()) < ACCESS_LEVEL_READ:
            abort(403)

        # only process files and folders (for now)
        if r.type == Resource.FILE or r.type == Resource.BASIC_FOLDER:
            add_to_zip(zip_file, r, '', uncompressed_size)

    # make sure permissions are ok in Linux
    for zf in zip_file.filelist:
        zf.create_system = 0

    # return zip file contents
    zip_file.close()
    zip_buffer.seek(0)
    data = zip_buffer.read()
    result = make_response(data)
    result.headers['Content-Type'] = 'application/octet-stream'
    result.headers['Content-Disposition'] = 'attachment; filename=' + parent_folder.name + '_files.zip'
    return result
