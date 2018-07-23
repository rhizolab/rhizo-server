# standard python imports
import csv
import time  # fix(clean): remove
import json
import cStringIO
import datetime


# external imports
from flask import render_template, request, abort, Response, send_from_directory, current_app
from flask_login import login_required, current_user
from jinja2.exceptions import TemplateNotFound
from sqlalchemy import func
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound


# internal imports
from main.app import app, db, extensions
from main.util import ssl_required
from main.resources.models import Resource, ResourceRevision, ResourceView
from main.resources.models import Thumbnail
from main.resources.resource_util import read_resource, find_resource, mime_type_from_ext
from main.users.permissions import access_level, ACCESS_LEVEL_READ, ACCESS_LEVEL_WRITE
from main.resources.file_conversion import process_doc_page, compute_thumbnail


# view the server's home page
@app.route('/')
def view_home():
    resource = find_resource('/system/home.md')
    if not resource:
        resource = find_resource('/system/home')  # fix(soon): remove this
    return file_viewer(resource, is_home_page = True)


# provide a favicon
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(app.root_path + '/static', 'favicon.ico', mimetype='image/vnd.microsoft.icon')


# provide a robots.txt file
@app.route('/robots.txt')
def robots():
    return send_from_directory(app.root_path + '/static', 'robots.txt', mimetype='text/plain')


# provide extension static files
@app.route('/ext/<string:ext_name>/static/<path:path>')
def ext_static(ext_name, path):
    for extension in extensions:
        if extension.name == ext_name:
            file_path = extension.path + '/static/' + path
            dir_name, base_name = file_path.rsplit('/', 1)
            return send_from_directory(dir_name, base_name)


# view a resource
@app.route('/<path:item_path>')
@ssl_required
def view_item(item_path):
    full_path = '/' + item_path

    # display warning if trying receiving websocket request here
    if full_path == '/api/v1/connectWebSocket':
        print('warning: make sure running with websockets enabled')
        abort(403)

    # traverse path parts left-to-right
    # fix(clean): this whole process can probably be simplified
    parent_folder = None
    path_parts = item_path.split('/')
    for (index, path_part) in enumerate(path_parts):

        # check to see if the item is a folder
        folder = None
        if parent_folder:
            try:
                folder = Resource.query.filter(Resource.parent == parent_folder, Resource.name == path_part, Resource.deleted == False).one()
            except NoResultFound:
                pass
            except MultipleResultsFound:
                print('multiple results for %s at level %s' % (item_path, path_part))
                abort(404)
        else:
            try:
                folder = Resource.query.filter(Resource.parent == None, Resource.name == path_part, Resource.deleted == False).one()
            except NoResultFound:
                pass

        # if it is a folder
        if folder and folder.type < 20 and folder.type != Resource.REMOTE_FOLDER:

            # check permissions
            user_access_level = access_level(folder.query_permissions())
            if user_access_level < ACCESS_LEVEL_READ:
                abort(403)

            # if it's the end of the path, show the folder
            if index == len(path_parts) - 1:
                return folder_viewer(folder, full_path, user_access_level)

            # otherwise, store the folder and continue to the next path element
            else:
                parent_folder = folder

        # if it's not a folder, try to find an resource record and display it
        else:

            # if not folder and has no parent, we're requesting an invalid folder
            if not parent_folder:
                print('not a folder and no parent (%s)' % full_path)
                abort(403)

            # look up resource record
            # fix(faster): we just looked this up above
            try:
                resource = Resource.query.filter(Resource.parent_id == parent_folder.id, Resource.name == path_part, Resource.deleted == False).one()
            except NoResultFound:
                path_part = path_part.replace('_', ' ')  # fix(soon): how else should we handle spaces in resource names?
                try:
                    resource = Resource.query.filter(Resource.parent_id == parent_folder.id, Resource.name == path_part, Resource.deleted == False).one()
                except NoResultFound:
                    abort(404)

            # check permissions
            user_access_level = access_level(resource.query_permissions())
            if user_access_level < ACCESS_LEVEL_READ:
                abort(403)  # or 401 if no current user?

            # fix(soon): create a new resource type for custom views?
            if resource.type == Resource.APP or resource.type == Resource.REMOTE_FOLDER:
                for extension in extensions:
                    result = extension.view(resource, parent_folder)
                    if result:
                        return result

            # use a built-in resource viewer based on resource type
            if resource.type == Resource.APP and resource.path().startswith('/system/'):
                return system_app_viewer(resource, parent_folder)
            elif resource.type == Resource.SEQUENCE:
                return sequence_viewer(resource)
            elif resource.type == Resource.FILE:
                if request.args.get('width'):
                    return thumbnail_viewer(resource)
                else:
                    check_timing = request.args.get('check_timing')
                    if check_timing:
                        start_time = time.time()
                    response = file_viewer(resource, check_timing)
                    if check_timing:
                        print('total time: %.4f' % (time.time() - start_time))
                    return response

            # if nothing matched, return 404
            abort(404)
    abort(404)


# ======== RESOURCE VIEWERS ========


# view a folder resource (whether basic folder, organization folder, or controller folder)
def folder_viewer(folder, full_path, user_access_level):

    # handle tree view
    # fix(clean): reconsider how this relates to the folder.html path
    if request.args.get('tree', False):
        return folder_tree_viewer(folder)

    # resources
    resources = Resource.query.filter(Resource.parent == folder, Resource.deleted == False).order_by('name')
    resources = [r.as_dict(extended = True) for r in resources]

    # get view preferences if any
    if current_user.is_authenticated:
        try:
            resource_view = ResourceView.query.filter(ResourceView.resource_id == folder.id, ResourceView.user_id == current_user.id).one()
            view = resource_view.view
        except NoResultFound:
            view = '{}'
    else:
        view = '{}'

    # fix(clean): remove number of parameters passed to this template
    return render_template('resources/folder.html',
        folder_type = folder.type,
        folder_resource_json = json.dumps(folder.as_dict(extended = True)),
        full_path = full_path,
        view_json = view,
        user_access_level = user_access_level,
        is_admin = current_user.is_authenticated and current_user.role == current_user.SYSTEM_ADMIN,  # fix(clean): remove this
        resources_json = json.dumps(resources)
    )


# recursively gather information about a folder for a tree view
def folder_tree_info(prefix, folder):
    infos = []
    name = prefix + '/' + folder.name if prefix else folder.name
    file_count = db.session.query(func.count(Resource.id)).filter(Resource.parent_id == folder.id, Resource.deleted == False, Resource.type != Resource.BASIC_FOLDER).scalar()
    child_folders = Resource.query.filter(Resource.parent_id == folder.id, Resource.deleted == False, Resource.type == Resource.BASIC_FOLDER).order_by('name')
    for child in child_folders:
        infos += folder_tree_info(name, child)
    infos.append({'name': name, 'fileCount': file_count})
    return infos


# view a sub-folders in a tree form
def folder_tree_viewer(folder):
    print('folder tree')
    start_time = time.time()
    infos = folder_tree_info('', folder)
    print('time: %.2f' % (time.time() - start_time))
    return render_template('resources/folder-tree.html',
        folder_tree = json.dumps(infos),
    )


# view a system app
def system_app_viewer(resource, parent):
    template_name = 'system/%s.html' % resource.name.replace(' ', '_').lower()
    try:
        return render_template(template_name)
    except TemplateNotFound:
        abort(404)


# a viewer for sequences (time series)
def sequence_viewer(resource):

    # decide how many data points to show
    system_attributes = json.loads(resource.system_attributes)
    data_type = system_attributes['data_type']
    if data_type == Resource.NUMERIC_SEQUENCE:
        history_count = 5000
    elif data_type == Resource.TEXT_SEQUENCE:
        history_count = 500
    elif data_type == Resource.IMAGE_SEQUENCE:
        history_count = 200

    # get recent resource revisions (with ascending timestamps)
    resource_revisions = list(ResourceRevision.query.filter(ResourceRevision.resource_id == resource.id).order_by(ResourceRevision.timestamp.desc())[:history_count])
    epoch = datetime.datetime.utcfromtimestamp(0)
    timestamps = [(rr.timestamp.replace(tzinfo = None) - epoch).total_seconds() for rr in resource_revisions]  # fix(clean): use some sort of unzip function
    values = [rr.data for rr in resource_revisions]
    thumbnail_revs = []
    full_image_revs = []
    resource_path = resource.path()
    thumbnail_resource_path = ''

    # if image sequence get thumbnails and full image IDs
    if data_type == Resource.IMAGE_SEQUENCE:
        thumbnail_resources = Resource.query.filter(Resource.parent_id == resource.id, Resource.name.like('thumbnail%'), Resource.deleted == False)
        if thumbnail_resources.count():
            thumbnail_resource = thumbnail_resources[0]  # fix(later): deal with multiple thumbnail sizes?
            thumbnail_resource_path = resource_path + '/' + thumbnail_resource.name
            thumbnail_revisions = ResourceRevision.query.filter(ResourceRevision.resource_id == thumbnail_resource.id).order_by(ResourceRevision.timestamp.desc())[:history_count]
            thumb_map = {rr.timestamp: rr.id for rr in thumbnail_revisions}
            thumbnail_revs = [thumb_map.get(rr.timestamp) for rr in resource_revisions]  # get thumbnail rev for each sequence rev
        full_image_revs = [rr.id for rr in resource_revisions]

    # generate HTML response
    return render_template('resources/sequence.html',
        resource = json.dumps(resource.as_dict(extended = True)),
        resource_path = resource_path,
        thumbnail_resource_path = thumbnail_resource_path,
        timestamps = json.dumps(timestamps),
        values = json.dumps(values),
        thumbnail_revs = json.dumps(thumbnail_revs),
        full_image_revs = json.dumps(full_image_revs),
    )


# a viewer for a data file
def file_viewer(resource, check_timing = False, is_home_page = False):
    contents = read_resource(resource, check_timing=check_timing)
    if contents is None:
        print('file_viewer: storage not found (resource: %d, path: %s)' % (resource.id, resource.path()))
        abort(404)
    system_attributes = json.loads(resource.system_attributes) if resource.system_attributes else {}
    if system_attributes.get('file_type') == 'md' or resource.name.endswith('.md'):  # fix(soon): revisit this
        if 'edit' in request.args:
            return render_template('resources/text-editor.html',
                resource = resource,
                contents = contents,
                show_view_button = True,
            )
        else:
            file_html = process_doc_page(contents)
            allow_edit = access_level(resource.query_permissions()) >= ACCESS_LEVEL_WRITE
            title = current_app.config['SYSTEM_NAME'] if is_home_page else resource.name  # fix(later): allow specify title for doc page?
            return render_template('resources/doc-viewer.html', resource = resource, allow_edit = allow_edit, file_html = file_html, hide_loc_nav = is_home_page, title = title)
    else:
        file_ext = resource.name.rsplit('.', 1)[-1]
        edit = request.args.get('edit', False)
        if file_ext == 'csv' and edit == False:
            reader = csv.reader(cStringIO.StringIO(contents))
            data = list(reader)
            return render_template('resources/table-editor.html', resource = resource, data_json = json.dumps(data))
        elif file_ext == 'txt' or file_ext == 'csv':
            return render_template('resources/text-editor.html', resource = resource, contents = contents)
        return Response(response=contents, status=200, mimetype=mime_type_from_ext(resource.name))


# view an thumbnail image for a resource
def thumbnail_viewer(resource):
    width = int(request.args.get('width', 100))
    # fix(later): switch back to .one() query after fix issues with duplicates
    thumbnails = Thumbnail.query.filter(Thumbnail.resource_id == resource.id, Thumbnail.width == width)
    if thumbnails.count():
        thumbnail = thumbnails[0]
        thumbnail_contents = thumbnail.data
    else:
        contents = read_resource(resource)
        (thumbnail_contents, thumbnail_width, thumbnail_height) = compute_thumbnail(contents, width)  # fix(later): if this returns something other than requested width, we'll keep missing the cache
        thumbnail = Thumbnail()
        thumbnail.resource_id = resource.id
        thumbnail.width = thumbnail_width
        thumbnail.height = thumbnail_height
        thumbnail.format = 'jpg'
        thumbnail.data = thumbnail_contents
        db.session.add(thumbnail)
        db.session.commit()
    return Response(response=thumbnail_contents, status=200, mimetype='image/jpeg')
