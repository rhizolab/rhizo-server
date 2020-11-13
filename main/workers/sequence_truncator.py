import json
import gevent
from sqlalchemy import func
from main.app import db
from main.resources.models import Resource, ResourceRevision
from main.workers.util import worker_log


# this worker thread will delete old entries for each sequence resource (keeping at least max_history entries)
def sequence_truncator():
    verbose = True
    worker_log('sequence_truncator', 'starting')
    while True:
        truncate_count = 0

        # loop over all sequences
        resources = Resource.query.filter(Resource.type == Resource.SEQUENCE)
        for resource in resources:

            # get number of revisions for this sequence
            rev_count = db.session.query(func.count(ResourceRevision.id)).filter(ResourceRevision.resource_id == resource.id).scalar()

            # get max history
            system_attributes = json.loads(resource.system_attributes) if resource.system_attributes else {}
            max_history = system_attributes.get('max_history', 1)

            # if too many revisions (with 1000 item buffer), delete old ones
            # fix(later): revisit buffer for image sequences and others with large objects
            if rev_count > max_history + 1000:

                # determine timestamp of revision max_history records ago;
                # this could be made faster if we assumed that revisions are created sequentially
                revisions = (
                    ResourceRevision.query
                    .with_entities(ResourceRevision.timestamp)
                    .filter(ResourceRevision.resource_id == resource.id)
                    .order_by('timestamp')
                )
                boundary_timestamp = revisions[-max_history].timestamp

                # diagnostics
                if verbose:
                    message = 'id: %s, path: %s, max hist: %d, revs: %d, first: %s, thresh: %s, last: %s' % (
                        resource.id, resource.path(), max_history, rev_count,
                        revisions[0].timestamp.strftime('%Y-%m-%d'),
                        boundary_timestamp.strftime('%Y-%m-%d'),
                        revisions[-1].timestamp.strftime('%Y-%m-%d')
                    )
                    worker_log('sequence_truncator', message)

                # delete the old records
                # it is critical that we filter by resource ID and timestamp
                ResourceRevision.query.filter(ResourceRevision.resource_id == resource.id, ResourceRevision.timestamp < boundary_timestamp).delete()
                db.session.commit()
                truncate_count += 1

        # display diagnostic
        if truncate_count:
            worker_log('sequence_truncator', 'done with truncation pass; truncated %d sequences' % truncate_count)

        # sleep for an hour
        gevent.sleep(60 * 60)


# if run as top-level script
if __name__ == '__main__':
    sequence_truncator()
