# standard library imports
import json
import base64
import datetime


# external imports
import gevent
import paho.mqtt.client as mqtt


# internal imports
from main.app import db
from main.workers.util import worker_log
from main.util import load_server_config
from main.users.auth import message_auth_token
from main.messages.outgoing_messages import handle_send_email, handle_send_text_message
from main.resources.models import Resource, ControllerStatus
from main.resources.resource_util import find_resource, update_sequence_value


# this worker monitors MQTT messages for ones that need to be acted upon by the server
def message_monitor():
    server_config = load_server_config()
    if not 'MQTT_HOST' in server_config:
        worker_log('message_monitor', 'MQTT host not configured')
        return
    worker_log('message_monitor', 'starting')
    mqtt_host = server_config['MQTT_HOST']
    mqtt_port = server_config.get('MQTT_PORT', 443)

    # run this on connect/reconnect
    def on_connect(client, userdata, flags, rc):
        if rc:
            worker_log('message_monitor', 'unable to connect to MQTT broker/server at %s:%d' % (mqtt_host, mqtt_port))
        else:
            worker_log('message_monitor', 'connected to MQTT broker/server at %s:%d' % (mqtt_host, mqtt_port))
        client.subscribe('#')  # subscribe to all messages

    # run this on message
    def on_message(client, userdata, msg):
        # print('MQTT: %s %s' % (msg.topic, msg.payload.decode()))
        message_struct = json.loads(msg.payload.decode())
        message_type = message_struct['type']
        if message_type == 'update_sequence':
            controller = find_resource('/' + msg.topic)  # for now we assume these messages are published on controller channels
            if controller and controller.type == Resource.CONTROLLER_FOLDER:
                parameters = message_struct['parameters']
                seq_name = parameters['sequence']
                if not seq_name.startswith('/'):  # handle relative sequence names
                    resource = Resource.query.filter(Resource.id == controller.id).one()
                    seq_name = resource.path() + '/' + seq_name  # this is ok for now since .. doesn't have special meaning in resource path (no way to escape controller folder)
                timestamp = parameters.get('timestamp', '')  # fix(soon): need to convert to datetime
                if not timestamp:
                    timestamp = datetime.datetime.utcnow()
                value = parameters['value']
                if 'encoded' in parameters:
                    value = base64.b64decode(value)

                # remove this; require clients to use REST POST for images
                resource = find_resource(seq_name)
                if not resource:
                    return
                system_attributes = json.loads(resource.system_attributes) if resource.system_attributes else None
                if system_attributes and system_attributes['data_type'] == Resource.IMAGE_SEQUENCE:
                    value = base64.b64decode(value)
                else:
                    value = str(value)

                update_sequence_value(resource, seq_name, timestamp, value, emit_message=False)  # don't emit message since the message is already in the system
                db.session.commit()

        # update controller watchdog status
        elif message_type == 'watchdog':
            controller = find_resource('/' + msg.topic)  # for now we assume these messages are published on controller channels
            if controller and controller.type == Resource.CONTROLLER_FOLDER:
                controller_status = ControllerStatus.query.filter(ControllerStatus.id == controller.id).one()
                controller_status.last_watchdog_timestamp = datetime.datetime.utcnow()
                db.session.commit()

        # send emails
        elif message_type == 'send_email':
            controller = find_resource('/' + msg.topic)  # for now we assume these messages are published on controller channels
            if controller and controller.type == Resource.CONTROLLER_FOLDER:
                print('sending email')
                handle_send_email(controller.id, message_struct['parameters'])

        # send SMS messages
        elif message_type == 'send_sms' or message_type == 'send_text_message':
            controller = find_resource('/' + msg.topic)  # for now we assume these messages are published on controller channels
            if controller and controller.type == Resource.CONTROLLER_FOLDER:
                handle_send_text_message(controller.id, message_struct['parameters'])

    # connect and run
    mqtt_client = mqtt.Client(transport='websockets')
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    mqtt_client.username_pw_set('token', message_auth_token(0))  # user_id 0 indicates that this is an internal connection from the server
    mqtt_client.tls_set()  # enable SSL
    mqtt_client.connect(mqtt_host, mqtt_port)
    mqtt_client.loop_start()
    while True:
        gevent.sleep(60)


# if run as top-level script
if __name__ == '__main__':
    message_monitor()
