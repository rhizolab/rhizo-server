# standard python imports
import time
import datetime
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


# external imports
try:
    from twilio.rest import Client
except ModuleNotFoundError:
    pass
from sqlalchemy.orm.exc import NoResultFound


# internal imports
from main.app import db
from main.util import load_server_config
from main.messages.models import ActionThrottle, OutgoingMessage


# handle a message from a controller requesting to send an email
def handle_send_email(controller_id, parameters):

    # get parameters
    if 'emailAddresses' in parameters:
        email_addresses = parameters['emailAddresses']
    else:
        email_addresses = parameters['email_addresses']
    subject = parameters['subject']
    body = parameters['body']

    # check to make sure not sending too many messages
    if check_and_update_throttle(controller_id, 'send_email'):

        # record message (for use investigating abuse)
        outgoing_message = OutgoingMessage()
        outgoing_message.timestamp = datetime.datetime.utcnow()
        outgoing_message.controller_id = controller_id
        outgoing_message.recipients = email_addresses
        outgoing_message.message = subject
        outgoing_message.attributes = '{}'
        db.session.add(outgoing_message)
        db.session.commit()

        # send the message
        # fix(soon): handle multiple recipients (up to 5)
        send_email(email_addresses, subject, body, load_server_config())

    else:
        pass  # fix(later): provide an error?


# handle a message from a controller requesting to send a text message
def handle_send_text_message(controller_id, parameters):

    # get parameters
    if 'phoneNumbers' in parameters:
        phone_numbers = parameters['phoneNumbers']
    else:
        phone_numbers = parameters['phone_numbers']
    message = parameters['message']

    # check to make sure not sending too many messages
    if check_and_update_throttle(controller_id, 'send_text_message'):

        # record message (for use investigating abuse)
        outgoing_message = OutgoingMessage()
        outgoing_message.timestamp = datetime.datetime.utcnow()
        outgoing_message.controller_id = controller_id
        outgoing_message.recipients = phone_numbers
        outgoing_message.message = message
        outgoing_message.attributes = '{}'
        db.session.add(outgoing_message)
        db.session.commit()

        # send the message
        send_text_message(phone_numbers, message, load_server_config())

    else:
        pass  # fix(later): provide an error?


# check the rate limiting on an action such as sending an email or text
def check_and_update_throttle(controller_id, type):

    # get timestamp
    dt = datetime.datetime.utcnow()
    timestamp = int(time.mktime(dt.timetuple()))  # we don't care about fractions of seconds for throttling
    threshold = timestamp - 60 * 60  # one hour ago

    # if existing record, check recent usage
    try:
        action_throttle = ActionThrottle.query.filter(ActionThrottle.controller_id == controller_id, ActionThrottle.type == type).one()
        recent_usage = [int(ts) for ts in action_throttle.recent_usage.split(',')]
        recent_usage = [ts for ts in recent_usage if ts > threshold]
        recent_usage.append(timestamp)
        action_throttle.recent_usage = ','.join([str(ts) for ts in recent_usage])
        db.session.commit()
        if len(recent_usage) > 10:
            return False

    # if not, create new record
    except NoResultFound:
        action_throttle = ActionThrottle()
        action_throttle.controller_id = controller_id
        action_throttle.type = type
        action_throttle.recent_usage = str(timestamp)
        db.session.add(action_throttle)
        db.session.commit()

    return True


# send an email (blocks until sent)
def send_email(to_email_address, subject, body, server_config):

    # get settings
    from_email_address = server_config['OUTGOING_EMAIL_ADDRESS']
    smtp_user_name = server_config['OUTGOING_EMAIL_USER_NAME']
    password = server_config['OUTGOING_EMAIL_PASSWORD']
    server = server_config['OUTGOING_EMAIL_SERVER']
    port = server_config['OUTGOING_EMAIL_PORT']

    # build message object
    message = MIMEMultipart()
    message['Subject'] = subject
    message['From'] = from_email_address
    message['To'] = to_email_address
    message.preamble = body
    message.attach(MIMEText(body))

    # send email message
    result = 'ok'
    try:
        smtp_server = smtplib.SMTP(server, port)
        smtp_server.starttls()
        smtp_server.login(smtp_user_name, password)
        smtp_server.sendmail(from_email_address, to_email_address, message.as_string())
        smtp_server.quit()
    except smtplib.SMTPRecipientsRefused:
        result = 'recipient refused: %s' % to_email_address
    return result


# send a text message
# fix(soon): handle multiple recipients (up to 5)
def send_text_message(phone_numbers, message, server_config):
    account_sid = server_config['TWILIO_ACCOUNT_SID']
    auth_token = server_config['TWILIO_AUTH_TOKEN']
    from_number = server_config['TEXT_FROM_PHONE_NUMBER']
    client = Client(account_sid, auth_token)
    message = client.messages.create(to=phone_numbers, from_=from_number, body=message)
