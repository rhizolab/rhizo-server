import paho.mqtt.client as mqtt


# maintains a connection to the MQTT server; used for sending outgoing MQTT messages from web endpoints
class MessageSender(object):

    def __init__(self, config):
        self.mqtt_host = config['MQTT_HOST']
        self.mqtt_port = config['MQTT_PORT']
        self.mqtt_tls = config['MQTT_TLS']
        self.mqtt_client = None
        print('starting message sender with host %s:%d' % (self.mqtt_host, self.mqtt_port))

    def connect(self):
        from main.users.auth import message_auth_token

        def on_connect(client, userdata, flags, rc):
            # pylint: disable=unused-argument
            if rc:
                print('unable to connect to MQTT broker/server at %s:%d' % (self.mqtt_host, self.mqtt_port))
            else:
                print('connected to MQTT broker/server at %s:%d' % (self.mqtt_host, self.mqtt_port))
        self.mqtt_client = mqtt.Client(transport='websockets')
        self.mqtt_client.on_connect = on_connect
        self.mqtt_client.username_pw_set('token', message_auth_token(0))  # user_id 0 indicates that this is an internal connection from the server
        if self.mqtt_tls:
            self.mqtt_client.tls_set()  # enable SSL
        self.mqtt_client.connect(self.mqtt_host, self.mqtt_port)
        self.mqtt_client.loop_start()

    def send_message(self, path, message_body):
        if not self.mqtt_client:
            self.connect()
        topic = path.lstrip('/')  # rhizo-server paths start with slash (to distinguish absolute vs relative paths) while MQTT topics don't
        self.mqtt_client.publish(topic, message_body)
