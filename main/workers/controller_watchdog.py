# standard python imports
import json
import time
import datetime


# external imports
import gevent
from sqlalchemy import not_
from sqlalchemy.orm.exc import NoResultFound


# internal imports
from main.workers.util import worker_log
from main.app import db
from main.util import load_server_config
from main.resources.models import Resource, ControllerStatus
from main.messages.outgoing_messages import send_email, send_text_message


# check controllers for watchdog timeouts; send notifications if timed out
def controller_watchdog():
    server_config = load_server_config()
    worker_log('controller_watchdog', 'starting')
    last_log_time = None
    while True:
        watchdog_check_count = 0
        watchdog_expire_count = 0
        try:

            # get list of controllers
            controllers = Resource.query.filter(Resource.type == Resource.CONTROLLER_FOLDER, not_(Resource.deleted))
            for controller in controllers:
                system_attributes = json.loads(controller.system_attributes) if controller.system_attributes else {}

                # if watchdog notifications are enabled
                if system_attributes.get('watchdog_minutes', 0) > 0  and 'watchdog_recipients' in system_attributes:
                    watchdog_check_count += 1
                    try:

                        # check controller status; if stale watchdog timestamp, send message (if not done already);
                        # if no watchdog timestamp, don't send message (assume user is just setting on the controller for the first time)
                        controller_status = ControllerStatus.query.filter(ControllerStatus.id == controller.id).one()
                        # fix(soon): safe int convert
                        time_thresh = datetime.datetime.utcnow() - datetime.timedelta(minutes=system_attributes['watchdog_minutes'])
                        if controller_status.last_watchdog_timestamp and controller_status.last_watchdog_timestamp < time_thresh:
                            watchdog_expire_count += 1
                            if controller_status.watchdog_notification_sent is False:

                                # send notifications
                                recipients = system_attributes['watchdog_recipients']
                                worker_log('controller_watchdog', 'sending notification for %s to %s' % (controller.path(), recipients))
                                recipients = recipients.split(',')
                                message = '%s is offline' % controller.path()
                                if server_config['PRODUCTION']:  # only send message in production; this is very important
                                    for recipient in recipients:
                                        if '@' in recipient:
                                            send_email(recipient, message, message, server_config)
                                        else:
                                            send_text_message(recipient, message, server_config)
                                controller_status.watchdog_notification_sent = True
                                db.session.commit()
                        else:
                            if controller_status.watchdog_notification_sent:
                                controller_status.watchdog_notification_sent = False
                                db.session.commit()
                        db.session.expire(controller_status)
                    except NoResultFound:
                        worker_log('controller_watchdog', 'controller status not found (%d)' % controller.id)

        # handle all exceptions because we don't want an error in this code (e.g. sending email or bad status/controller data) stopping all
        # notifications
        except Exception as e:
            print('controller_watchdog error: %s' % str(e))
            worker_log('controller_watchdog', str(e))

        # once an hour, log current status
        if (last_log_time is None) or time.time() - last_log_time > 60 * 60:
            worker_log('controller_watchdog', 'checked %d controllers; %d are currently expired' % (watchdog_check_count, watchdog_expire_count))
            last_log_time = time.time()

        # wait one minute
        gevent.sleep(60)
