from main.app import db


# The Message model holds messages temporarily in the database.
# (It is used by the MessageQueueBasic class; other message queue implementations may use other message storages.)
class Message(db.Model):
    __tablename__   = 'messages'
    id                      = db.Column(db.BigInteger().with_variant(db.Integer, "sqlite"), primary_key=True)
    timestamp               = db.Column(db.DateTime, nullable=False)
    sender_controller_id    = db.Column(db.ForeignKey('resources.id'))  # nullable (null if sent by user or server system)
    sender_user_id          = db.Column(db.ForeignKey('users.id'))      # nullable (null if sent by controller or server system)
    folder_id               = db.Column(db.ForeignKey('resources.id'), nullable=False)  # not nullable; all messages must belong to a folder
    type                    = db.Column(db.String(40), nullable=False)
    parameters              = db.Column(db.String, nullable=False)    # JSON dictionary
    attributes              = db.Column(db.String)                      # JSON field containing extra message attributes
    def __repr__(self):
        return '%d: %s, %s' % (self.id, self.timestamp, self.type)


# The ActionThrottle model is used to rate-limit certain client-requested activities like sending emails/texts.
class ActionThrottle(db.Model):
    __tablename__       = 'action_throttles'
    id                  = db.Column(db.Integer, primary_key=True)
    controller_id       = db.Column(db.ForeignKey('resources.id'))      # the controller being throttled (null if user)
    user_id             = db.Column(db.ForeignKey('users.id'))          # the user being throttled (null if controller)
    type                = db.Column(db.String(50), nullable=False)    # type of action being throttled
    recent_usage        = db.Column(db.String, nullable=False)        # list of timestamp numbers


# The OutgoingMessage model holds email/text messages being sent by the system.
class OutgoingMessage(db.Model):
    __tablename__       = 'outgoing_messages'
    id                  = db.Column(db.Integer, primary_key=True)
    controller_id       = db.Column(db.ForeignKey('resources.id'))  # the originating controller (null if user)
    user_id             = db.Column(db.ForeignKey('users.id'))      # the originating user (null if controller)
    timestamp           = db.Column(db.DateTime, nullable=False)
    recipients          = db.Column(db.String, nullable=False)    # e.g. email addresses or phone numbers
    message             = db.Column(db.String, nullable=False)    # e.g. message content or subject
    attributes          = db.Column(db.String, nullable=False)    # JSON field containing extra message attributes
