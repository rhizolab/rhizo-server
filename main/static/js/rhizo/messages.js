// This code manages a websocket connection for passing messages to/from the server.
// It maintains a list of message subscriptions and a set of message handlers.
// It manages pinging the server and reconnecting when disconnected.


// global instance of WebSocketHolder; creating the holder does not connect; use connectWebSocket when ready to connect
var g_wsh = createWebSocketHolder();



// ======== public API functions ========


// open a websocket connection to the server;
// afterOpen (optional) will called after the websocket is opened (will be re-called if reconnect);
// does not reconnect if already connected
function connectWebSocket(afterOpen) {
	g_wsh.afterOpen = afterOpen;
	if (g_wsh.connectStarted) // fix(later): move inside connect? need to be sure that reconnects still work
		return;
	g_wsh.connect();
}


// subscript to messages from a folder;
// if includeSelf is specified, messages sent from self will be reflected back
// fix(clean): move contents of this function into webSocketHolder (so this is just a simple wrapper)?
function subscribeToFolder(folderPath, includeSelf) {
	console.log('subscribe: ' + folderPath);
	for (var i = 0; i < g_wsh.subscriptions.length; i++) {
		if (g_wsh.subscriptions[i].folder == folderPath)
			return;
	}
	var subscription = {'folder': folderPath};
	if (includeSelf)
		subscription['include_self'] = 1;
	g_wsh.subscriptions.push(subscription);
	if (g_wsh.targetFolderPath === null) {
		g_wsh.targetFolderPath = folderPath;  // fix(soon): require explicitly setting this on connect or using setTargetFolder?
	}
}


// add a handler for a particular type of message;
// when a message of this type is received the server, the function will be called;
// the function will be passed three arguments: timestamp, message type, and message parameters (dictionary)
function addMessageHandler(type, func) {
	g_wsh.addOldHandler(type, func);
}


// top-level function for sending messages;
// defaults to using g_wsh.targetFolderPath as the target/recipient folder
function sendMessage(messageType, params, targetFolderPath) {
	if (!params)
		params = {};
	g_wsh.sendMessage(messageType, params, targetFolderPath);
}


// set the default destination for messages
// fix(clean): make this part of connect?
function setTargetFolder(targetFolderPath) {
	g_wsh.targetFolderPath = targetFolderPath;
}


// ======== a class for managing a websocket connection with message l/subscriptions/etc. ========


// create a websocket object with a few additional/custom methods
function createWebSocketHolder() {

	// prepare the object
	var wsh = {};
	wsh.webSocket = null;
	wsh.connected = false;
	wsh.connectStarted = false;
	wsh.handlers = [];
	wsh.sequenceHandlers = [];
	wsh.oldHandlers = {};  // old type-specific handlers
	wsh.genericHandlers = [];  // old generic handlers
	wsh.subscriptions = [];
	wsh.errorModal = null;
	wsh.pingStarted = false;
	wsh.targetFolderPath = null;  // default target for messages
	wsh.afterOpen = null;  // called after the websocket is opened (will be re-called if reconnect)
	wsh.client = null;  // MQTT client
	wsh.clientConnected = false;  // true if connected to MQTT server

	// connect to the server; this creates a websocket object
	wsh.connect = function() {
		wsh.connectStarted = true; // fix(soon): could have race condition
		console.log('connecting');

		// if old websocket-based messaging is enabled
		if (g_mqttInfo && g_mqttInfo.enableOld) {

			// compute url
			var protocol = 'ws://';
			if (window.location.protocol.slice(0, 5) == 'https')
				protocol = 'wss://';
			var url = protocol + window.location.host + '/api/v1/websocket';

			// open the connection
			if ('WebSocket' in window) {
				this.webSocket = new WebSocket(url);
			} else {
				alert('This app requires a browser with WebSocket support.');
			}

			// handle message from websocket
			this.webSocket.onmessage = function(evt) {
				var message = JSON.parse(evt.data);
				var type = message['type'];
				if (type) {
					var func = wsh.oldHandlers[type];
					if (func) {
						func(moment(message['timestamp']), message['parameters']);
					}
					for (var i = 0; i < wsh.genericHandlers.length; i++) {
						var func = wsh.genericHandlers[i];
						func(moment(message['timestamp']), type, message['parameters']);
					}
				}
			};

			// run this code after connection is opened
			this.webSocket.onopen = function() {
				wsh.connected = true;

				// send a connect message (can be used to provide client version info)
				// fix(later): remove this if we're not sending any info?
				wsh.sendMessage('connect');

				// send list of folders for which we want messages
				console.log('subscriptions: ' + g_wsh.subscriptions.length);
				wsh.sendMessage('subscribe', {'subscriptions': g_wsh.subscriptions});

				// call user-provided function (if any) to run after websocket is open
				if (wsh.afterOpen)
					wsh.afterOpen();

				// hide reconnect modal if any
				setTimeout(function() {
					if (wsh.errorModal && wsh.connected) {
						console.log('hide');
						$('#wsError').modal('hide');
						$('#wsError').remove();
						$('body').removeClass('modal-open'); // fix(later): these two lines shouldn't be necessary, but otherwise window stays dark
						$('.modal-backdrop').remove(); // fix(later): these two lines shouldn't be necessary, but otherwise window stays dark
						wsh.errorModal = null;
					}
				}, 1000);

				// start pinging if not already started
				if (wsh.pingStarted === false) {
					wsh.pingStarted = true;
					setTimeout(pingServer, 20000);
				}
			};

			// run this code when connection is closed
			this.webSocket.onclose = function() {
				console.log('connection closed by server');
				wsh.connected = false;
				setTimeout(reconnect, 10000);

				// show modal to display connection status
				// fix(later): if this gets displayed repeatedly, each time the background gets darker
				if (!wsh.errorModal) {
					console.log('show');
					wsh.errorModal = createBasicModal('wsError', 'Reconnecting to server...', {infoOnly: true});
					wsh.errorModal.appendTo($('body'));
					$('#wsError-body').html('Will attempt to reconnect shortly.');
					$('#wsError').modal('show');
				}
			};
		}

		// ======== MQTT code ========

		// called when connected successfully to MQTT server/broker
		function onConnect() {
			wsh.clientConnected = true;
			console.log('connected to MQTT server/broker');
			for (var i = 0; i < wsh.subscriptions.length; i++) {
				var subscription = wsh.subscriptions[i];
				var topic = subscription.folder;
				if (topic[0] === '/') {
					topic = topic.slice(1);  // our folder paths have leading slashes, but not MQTT topics
				}
				wsh.client.subscribe(topic);
			}
		}

		// called when fails to connect to MQTT server/broker
		function onConnectFailure() {
			wsh.clientConnected = false;
			console.log('failed to connect to MQTT server/broker');
		}

		// called when MQTT connection is lost
		function onConnectionLost(responseObject) {
			wsh.clientConnected = false;
			if (responseObject.errorCode) {
				console.log('onConnectionLost:' + responseObject.errorMessage);
			}
		}

		// called when an MQTT message arrives
		function onMessageArrived(message) {
			var payload = message.payloadString;
			if (payload[0] == '{') {  // JSON message
				var path = '/' + message.topic;  // paths in our system use leading slashs; MQTT topics do not
				var messageStruct = JSON.parse(payload);
				for (var type in messageStruct) {
					if (messageStruct.hasOwnProperty(type)) {
						var params = messageStruct[type];
						for (var i = 0; i < wsh.handlers.length; i++) {
							wsh.handlers[i](path, type, params);
						}

						// handle sequence updates
						if (type == 'update') {
							var timestamp = moment(params['$t']);
							for (var name in params) {
								if (params.hasOwnProperty(name)) {
									var value = params[name];
									var seq_path = path + '/' + name;
									for (var i = 0; i < wsh.handlers.length; i++) {
										wsh.sequenceHandlers[i](seq_path, timestamp, value);
									}
								}
							}
						}
					}
				}
			} else {  // simple message
				var path = '/' + message.topic;  // paths in our system use leading slashs; MQTT topics do not
				var commaPos = payload.indexOf(',');  // comma separates message type from parameters
				var type = payload.slice(0, commaPos);
				var params = payload.slice(commaPos + 1);
				for (var i = 0; i < wsh.handlers.length; i++) {
					wsh.handlers[i](path, type, params);  // params in this case is a string
				}

				// handle sequence updates
				if (type == 's' || type == 'd') {
					var params = params.split(',', 3);
					var seq_path = path + '/' + params[0];
					var timestamp = moment(params[1]);
					var value = params[2];
					for (var i = 0; i < wsh.sequenceHandlers.length; i++) {
						wsh.sequenceHandlers[i](seq_path, timestamp, value);
					}
				}
			}
		}

		if (g_mqttInfo && g_mqttInfo.host) {
			console.log('opening MQTT connection');
			var useSSL = g_mqttInfo.ssl;
			var clientId = g_mqttInfo.clientId;
			var userName = 'token';
			var password = g_mqttInfo.token;
			wsh.client = new Paho.Client(g_mqttInfo.host, Number(g_mqttInfo.port), clientId);

			// set callback handlers
			wsh.client.onConnectionLost = onConnectionLost;
			wsh.client.onMessageArrived = onMessageArrived;

			// connect the client
			wsh.client.connect({onSuccess:onConnect, onFailure:onConnectFailure, useSSL:useSSL, userName:userName, password:password});

		} else {
			wsh.client = null;
		}
	};

	// send a message to the server;
	// messages should be addressed to a particular folder
	wsh.sendMessage = function(type, parameters, folderPath) {

		// send message using old websocket method
		if (this.connected) {
			if (!parameters)
				parameters = {};
			var message = {
				'type': type,
				'parameters': parameters,
				'folder': folderPath || this.targetFolderPath,
			};
			var messageStr = JSON.stringify(message);
			try {
				this.webSocket.send(messageStr);
			} catch (e) {
				console.log('error sending ' + type + '; try to reconnect in 10 seconds');
				this.connected = true; // fix(soon): should this be false?
				setTimeout(reconnect, 10000);
			}
		}

		// send MQTT message
		if (this.client && this.clientConnected) {
			var messageStruct = {};
			messageStruct[type] = parameters;
			var messageStr = JSON.stringify(messageStruct);
			var m = new Paho.Message(messageStr);
			var topic = folderPath || this.targetFolderPath;
			if (topic[0] === '/') {
				topic = topic.slice(1);  // our folder paths have leading slashes, but not MQTT topics
			}
			m.destinationName = topic;
			this.client.send(m);
		}
	};

	// add a handler for a particular type of message;
	// when a message of this type is received the server, the function will be called;
	// the function will be passed three arguments: timestamp, message type, and message parameters (dictionary)
	wsh.addOldHandler = function(type, func) {
		wsh.oldHandlers[type] = func;
	};

	// fix(clean): remove this; instead append '*' handler (make handlers for each type be a list)
	wsh.addGenericHandler = function(func) {
		wsh.genericHandlers.push(func);
	};

	// add a handler for incoming MQTT messages; function will receive message path, type, params
	wsh.addHandler = function(func) {
		wsh.handlers.push(func);
	};

	// add a handler for incoming MQTT sequence update messages; function will receive seq_path, timestamp (moment.js object), value
	wsh.addSequenceHandler = function(func) {
		wsh.sequenceHandlers.push(func);
	};

	return wsh;
}


// ======== other internal functions ========


// periodically send a message so that the connection doesn't timeout on heroku
// fix(later): should we disable this when disconnected?
function pingServer() {
	g_wsh.sendMessage('ping', {});
	setTimeout(pingServer, 20000);
}


// attempt to reconnect to the server
function reconnect() {
	console.log('attempting to reconnect');
	g_wsh.connect();
}


// ======== MQTT testing ========


function testMQTT(hostname) {
	var clientId = 'test';
	var userName = 'browser';
	var password = 'test';
	var client = new Paho.Client(hostname, Number(443), clientId);

	// set callback handlers
	client.onConnectionLost = onConnectionLost;
	client.onMessageArrived = onMessageArrived;

	// connect the client
	client.connect({onSuccess:onConnect, useSSL:true, userName:userName, password:password});

	// called when the client connects
	function onConnect() {
		console.log("onConnect");
		client.subscribe("/test");
		message = new Paho.Message("hi");
		message.destinationName = "/test";
		client.send(message);
	}

	// called when the client loses its connection
	function onConnectionLost(responseObject) {
		if (responseObject.errorCode !== 0) {
			console.log("onConnectionLost:" + responseObject.errorMessage);
		}
	}

	// called when a message arrives
	function onMessageArrived(message) {
		console.log("onMessageArrived:" + message.payloadString);
	}
}
