import datetime
from main.resources.resource_util import update_sequence_value, find_resource


# add a message to the worker log
def worker_log(worker_name, message):
    print(worker_name + ': ' + message)
    name = '/system/worker/log'
    update_sequence_value(find_resource(name), name, datetime.datetime.utcnow(), str(worker_name + ': ' + message))  # convert unicode to plain string
