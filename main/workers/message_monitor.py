# standard library imports
import json
import datetime


# external imports
import gevent
import paho.mqtt.client as mqtt


# internal imports
from main.app import db
from main.workers.util import worker_log
from main.util import load_server_config, parse_json_datetime
from main.users.auth import message_auth_token
from main.messages.outgoing_messages import handle_send_email, handle_send_text_message
from main.resources.models import Resource, ControllerStatus
from main.resources.resource_util import find_resource, update_sequence_value


# this worker monitors MQTT messages for ones that need to be acted upon by the server
def message_monitor():
    server_config = load_server_config()
    if 'MQTT_HOST' not in server_config:
        worker_log('message_monitor', 'MQTT host not configured')
        return
    worker_log('message_monitor', 'starting')
    mqtt_host = server_config['MQTT_HOST']
    mqtt_port = server_config.get('MQTT_PORT', 443)
    mqtt_tls = server_config.get('MQTT_TLS', True)

    # run this on connect/reconnect
    def on_connect(client, userdata, flags, rc):
        # pylint: disable=unused-argument
        if rc:
            worker_log('message_monitor', 'unable to connect to MQTT broker/server at %s:%d' % (mqtt_host, mqtt_port))
        else:
            worker_log('message_monitor', 'connected to MQTT broker/server at %s:%d' % (mqtt_host, mqtt_port))
        client.subscribe('#')  # subscribe to all messages

    # run this on message
    def on_message(client, userdata, msg):
        # pylint: disable=unused-argument
        payload = msg.payload.decode()

        # handle full (JSON) messages
        if payload.startswith('{'):
            message_struct = json.loads(payload)
            for message_type, parameters in message_struct.items():

                # update sequence values; doesn't support image sequence; should use REST API for image sequences
                if message_type == 'update':
                    folder = find_resource('/' + msg.topic)  # for now we assume these messages are published on controller channels
                    if folder and folder.type in (Resource.BASIC_FOLDER, Resource.ORGANIZATION_FOLDER, Resource.CONTROLLER_FOLDER):
                        timestamp = parameters.get('$t', '')
                        if timestamp:
                            timestamp = parse_json_datetime(timestamp)  # fix(soon): handle conversion errors
                        else:
                            timestamp = datetime.datetime.utcnow()
                        for name, value in parameters.items():
                            if name != '$t':
                                seq_name = '/' + msg.topic + '/' + name
                                resource = find_resource(seq_name)
                                if resource:
                                    # don't emit new message since UI will receive this message
                                    update_sequence_value(resource, seq_name, timestamp, value, emit_message=False)
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
                        handle_send_email(controller.id, parameters)

                # send SMS messages
                elif message_type == 'send_sms' or message_type == 'send_text_message':
                    controller = find_resource('/' + msg.topic)  # for now we assume these messages are published on controller channels
                    if controller and controller.type == Resource.CONTROLLER_FOLDER:
                        handle_send_text_message(controller.id, parameters)

        # handle short (non-JSON) messages
        else:
            # print('MQTT: %s %s' % (msg.topic, payload))
            if payload.startswith('s,'):  # type 's' is "store and display new sequence value"
                parts = payload.split(',', 3)
                if len(parts) == 4:
                    seq_name = '/' + msg.topic + '/' + parts[1]
                    timestamp = parse_json_datetime(parts[2])  # fix(soon): handle conversion errors
                    value = parts[3]
                    resource = find_resource(seq_name)
                    if resource and resource.type == Resource.SEQUENCE:
                        # don't emit new message since UI will receive this message
                        update_sequence_value(resource, seq_name, timestamp, value, emit_message=False)
                        db.session.commit()

    # connect and run
    mqtt_client = mqtt.Client(transport='websockets')
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    mqtt_client.username_pw_set('token', message_auth_token(0))  # user_id 0 indicates that this is an internal connection from the server
    if mqtt_tls:
        mqtt_client.tls_set()  # enable SSL
    mqtt_client.connect(mqtt_host, mqtt_port)
    mqtt_client.loop_start()
    while True:
        gevent.sleep(60)


# if run as top-level script
if __name__ == '__main__':
    message_monitor()
