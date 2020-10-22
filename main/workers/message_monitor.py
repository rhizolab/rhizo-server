import json
import gevent
import paho.mqtt.client as mqtt
from main.app import db
from main.workers.util import worker_log
from main.util import load_server_config
from main.users.auth import message_auth_token


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
        print('MQTT: %s %s' % (msg.topic, msg.payload.decode()))

    # connect and run
    mqtt_client = mqtt.Client(transport='websockets')
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    mqtt_client.username_pw_set('token', message_auth_token(0))
    mqtt_client.tls_set()  # enable SSL
    mqtt_client.connect(mqtt_host, mqtt_port)
    mqtt_client.loop_start()
    while True:
        gevent.sleep(60)


# if run as top-level script
if __name__ == '__main__':
    message_monitor()
