import gevent
from main.workers.util import worker_log


# this worker monitors MQTT messages for ones that need to be acted upon by the server
def message_monitor():
    verbose = True
    worker_log('message_monitor', 'starting')
    while True:
        gevent.sleep(60)

# if run as top-level script
if __name__ == '__main__':
    message_monitor()
