from sqlalchemy import func
from main.app import db
from main.resources.models import Resource
from main.workers.util import worker_log


def check_resource_migration():
    worker_log('migrate_db', 'resources without org id: %d' % db.session.query(func.count(Resource.id)).filter(Resource.organization_id == None).scalar())
    worker_log('migrate_db', 'file resources without last rev: %d' % db.session.query(func.count(Resource.id)).filter(Resource.type == Resource.FILE, Resource.last_revision_id == None).scalar())


if __name__ == '__main__':
    pass
