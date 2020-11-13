import json
import datetime
import gevent
from .message_queue import MessageQueue


# A basic message queue using a message table in the primary database.
class MessageQueueBasic(MessageQueue):

    def __init__(self):
        self._last_message_id = None
        self._start_timestamp = datetime.datetime.utcnow()

    # add a single message to the queue
    def add(self, folder_id, folder_path, type, parameters=None, sender_controller_id=None, sender_user_id=None, timestamp=None):
        # fix(soon): add warning if type is too long
        from main.messages.models import Message  # would like to do at top, but creates import loop in __init__
        from main.app import db  # would like to do at top, but creates import loop in __init__
        if not timestamp:
            timestamp = datetime.datetime.utcnow()
        message_record = Message()
        message_record.timestamp = timestamp
        message_record.sender_controller_id = sender_controller_id  # the ID of the controller that created the message (if it was not created by a human/browser)
        message_record.sender_user_id = sender_user_id
        message_record.folder_id = folder_id
        message_record.type = type
        message_record.parameters = json.dumps(parameters) if parameters else '{}'
        db.session.add(message_record)
        db.session.commit()
        if folder_path:
            from main.app import message_sender
            if message_sender:
                message_sender.send_message(folder_path, type, parameters, timestamp)

    # returns a list of message objects once some are ready
    def receive(self):
        from main.messages.models import Message  # would like to do at top, but creates import loop in __init__
        while True:

            # sleep for a bit; don't want to overload the database
            gevent.sleep(0.5)

            # fix(soon): is there a good way to avoid losing messages while server is restarting? could go back 5 minutes, but then we'd get duplicates
            # it would be nice if each web/worker process could remember where it was across restarts
            if self._last_message_id:
                messages = Message.query.filter(Message.id > self._last_message_id).order_by('id')
            else:
                messages = Message.query.filter(Message.timestamp > self._start_timestamp).order_by('id')
            if messages.count():
                try:
                    self._last_message_id = messages[-1].id  # fix(soon): check that this works
                except:
                    pass
                return messages
