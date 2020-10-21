# The MessageQueue class provides an interface to be implemented by classes that store messages.
class MessageQueue(object):

    # add a single message to the queue
    def add(self, folder_id, folder_path, type, parameters = None, sender_controller_id = None, sender_user_id = None, timestamp = None):
        pass

    # returns a list of message objects once some are ready
    def receive(self):
        pass
