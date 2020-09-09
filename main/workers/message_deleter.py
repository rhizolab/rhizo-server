import time
import gevent
import datetime
from main.app import db
from main.workers.util import worker_log
from main.messages.models import Message


# this worker thread will delete old messages from the in-database message queue
def message_deleter():
    worker_log('message_deleter', 'starting')
    while True:
        delete_count = 0
        start_time = time.time()
        thresh = datetime.datetime.utcnow() - datetime.timedelta(hours = 1)
        messages = Message.query.filter(Message.timestamp < thresh)
        delete_count = messages.count()
        messages.delete()
        db.session.commit()
        db.session.expunge_all()
        db.session.close()
        delete_time = time.time() - start_time

        # display diagnostic
        worker_log('message_deleter', 'deleted %d messages in %.3f seconds' % (delete_count, delete_time))

        # sleep for 6 hours
        gevent.sleep(6 * 60 * 60)


# if run as top-level script
if __name__ == '__main__':
    message_deleter()
