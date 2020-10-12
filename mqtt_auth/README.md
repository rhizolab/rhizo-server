We use a mosquitto plugin to allow authenticate and check access permissions 
for rhizo clients (controllers and browsers).

The plugin is a C library the checks controller access keys and user access tokens
using the postgres database that stores controller and user information.

The instructions below assume that the plugin has already been configured in `mosquitto-rhizo.conf`
according to the instructions in the main rhizo-server readme.

# Compiling and installing the plugin

*   run: `sudo apt install libssl-dev`
*   download and uncompress the mosquitto source
*   from the mosquitto source directory, run `make` and `sudo make install`
*   from your home directory (or another suitable location) run `git clone https://github.com/rg3/libbcrypt`
*   edit `libbcrypt/crypt_blowfish/Makefile` to add `-fPIC` to `CFLAGS`
*   from the `libbcrypt` directory run `make`
*   from the `rhizo-server/mqtt_auth` directory:
    *   edit the `BCRYPT` path in `Makefile` as needed
    *   run `make`
    *   run `sudo mv mqtt_auth_rhizo.so /etc/mosquitto`
