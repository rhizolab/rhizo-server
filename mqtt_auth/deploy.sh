#!/bin/bash
# this script assists with testing the plugin
sudo mv mqtt_auth_rhizo.so /etc/mosquitto/
sudo systemctl restart mosquitto
journalctl -u mosquitto -n 40
