import json
import logging
import paho.mqtt.client as mqtt


# maintains a connection to the MQTT server; used for sending outgoing MQTT messages from web endpoints
class MessageSender(object):

    def __init__(self, config):
        self.server_name = config['MQTT_HOST']
        self.mqtt_client = None
        print('starting message sender with host %s' % self.server_name)

    def connect(self):
        from main.users.auth import message_auth_token
        def on_connect(client, userdata, flags, rc):
            if rc:
                print('unable to connect to MQTT broker/server at %s' % self.server_name)
            else:
                print('connected to MQTT broker/server at %s' % self.server_name)
        self.mqtt_client = mqtt.Client(transport='websockets')
        self.mqtt_client.on_connect = on_connect
        self.mqtt_client.username_pw_set('token', message_auth_token(0))
        self.mqtt_client.tls_set()  # enable SSL
        self.mqtt_client.connect(self.server_name, 8088)  # using port 8088 for testing
        self.mqtt_client.loop_start()

    def send_message(self, path, type, parameters, timestamp=None):
        if not self.mqtt_client:
            self.connect()
        message_struct = {
            'type': type,
            'parameters': parameters
        }
        if timestamp:
            message_struct['timestamp'] = timestamp.isoformat() + 'Z'
        path = path.lstrip('/')  # rhizo-server paths start with slash (to distinguish absolute vs relative paths) while MQTT topics don't
        self.mqtt_client.publish(path, json.dumps(message_struct))
