# standard python imports
import json


# external imports
import gevent


# internal imports
from main.app import message_queue
from main.workers.util import worker_log
from main.workers.controller_watchdog import controller_watchdog
from main.workers.sequence_truncator import sequence_truncator
from main.workers.message_deleter import message_deleter
from main.workers.message_monitor import message_monitor


# import all models
from main.users import models
from main.messages import models
from main.resources import models


# the worker process
def worker():

    # log that the worker process is starting
    worker_log('system', 'starting worker process')

    # start various worker threads
    gevent.spawn(controller_watchdog)
    gevent.spawn(sequence_truncator)
    gevent.spawn(message_deleter)
    gevent.spawn(message_monitor)

    # loop forever
    while True:

        # sleep for one second each loop
        gevent.sleep(1)

        # check for messages
        if False:
            messages = message_queue.receive()
            for message in messages:
                if message.type == 'start_worker_task':
                    print('#### %s' % message.parameters)
                    params = json.loads(message.parameters)
                    if params['name'] == 'add_resource_revisions':
                        print('#### starting add_resource_revisions')
                        gevent.spawn(add_resource_revisions)


# if run as top-level script
if __name__ == '__main__':
    worker()
