rhizo-server
============

## Installation

1.  Clone this repo and change to the `rhizo-server` directory in a terminal window.
2.  Run `sudo pip install -r requirements.txt`
3.  If you are using postgres, run `sudo pip install psycopg2`
4.  Run `python prep_config.py`
5.  Edit `settings/config.py` and add this line:
    `DISCLAIMER = 'This is pre-release code; the API and database structure will probably change.'`
6.  Run this command to initialize your database: `python run.py --init-db`
7.  Create your system admin user: `python run.py --create-admin [email_address]:[password]`

## Running the Server

For development purposes you can run the server with automatic code reloading: `python run.py`

You can also run it with websocket support (but no auto-reloading): `python run.py -s`

Note: this websocket server (`-s` option) don't seem to work with gevent 1.2 (at least on Windows); 
you may need to downgrade to gevent 1.1.2.

## System Design

### Users

A user can be identified by a user name or email address. A user has a password that is stored in hashed form.
A user can be a system admin or normal user.

### Organizations

Users can be associated with organizations. An organization provides the primary unit of access control;
typically all users within an organization have access to all data owned by the organization. (A more detailed
discussion of this is provided in the Permissions section below.)

A user can be an admin within a particular organization, which gives her/him the ability to add/remove users
and change other organization-level settings. (An organization admin is different from a system admin.)

### Controllers

Controllers are computers or virtual machines that access the server as a client. A controller could be a
Raspberry Pi, an EC2 instance, or any other machine with a CPU and network connection.

### Resources

Resources are data files and folders containing data files hosted on the server.
The resources files and folders are accessed by URLs in the same way that file system
objects are accessed using paths. The top-level folder is always an organization.
Each resource has a type:

*   basic folder: a folder that can contain other resources
*   organization folder: the top-level folder corresponding to an organization
*   controller folder: a folder corresponding to a controller
*   file: a text or binary file (image, CSV, markdown, etc.)
*   sequence: a time series of values (numeric, string, or images)

Non-folder resources (files and sequences) are represented as a sequence of
resource revisions. In a sequence, these revisions are timestamped values of the time series.
A log file can be represented as a sequence of text values. In the case of files and apps,
the revisions provide a history of previous versions of the file data or app specification.

Large resource revision can be placed in bulk storage (e.g. S3). Small resource revisions are
placed directly in the server database.

### Messages

Messages have types and parameters. The longest allowed value for a type is 40 characters.
Parameters are represented as a dictionary.

All messages are addressed to a folder. A client (whether browser or controller) can subscribe to 
messages on a per-folder basis. A controller does not need to specify the target folder; its messages will be 
addressed to a folder that is created for each controller.

Many messages pass through the server from one client to another (between browser and controller or between
controller and controller). Some messages are handled specifically by the server. These include:

*   connect: informs the server of a new connection from a client
*   subscribe: subscribes to messages from one or more folders (optionally of a specific message type)
*   update_sequence: updates a sequence to have a new value
*   send_email: sends an email message from the server
*   send_text_message: sends a text message from the server

### WebSocket connections

A WebSocket connection is opened by via `/api/v1/websocket`. Authentication is similar to the REST 
authentication described below.

Websocket messages are sent as JSON strings with the following minimum format: 
`{ “type”: <type>, “parameters”: { <parameters> }`. 
Here `<parameters>` is a dictionary of parameter names and values.

## Permissions

Permissions specify which users can access which resources. We're currently reworking the permission 
system and will provide more documentation on that down the road.

## Keys

Each organization can have a set of API keys. An API key can be associated with a controller or a user, providing 
access equivalent to that controller or user, as determined by the permissions system. 

Currently keys can be created and revoked only by human users. Creating/revoking a key for a controller requires 
write access to the controller. Creating/revoking a key for a user requires organization admin access or access as 
that user. The revocation user and timestamp (along with creation user and timestamp) are stored.

Data on the server can be accessed via three kinds of authentication:

1.  user login/password on website; subsequent requests are validated using a session cookie
2.  API access using a user-associated key
3.  API access using a controller-associated key

In the first two cases, user-based permissions apply. In the third case, controller-based permissions apply.

## Other notes

### Code structure

You can customize the server behavior with settings and extensions. We use the following structure:

*   misc top-level files: stored in `rhizo-server` repo
*   main: stored in `rhizo-server` repo
*   settings: separate repo (.gitignored)
*   extensions (.gitignored)
    *   foo: separate repo
    *   bar: separate repo

### Coding style

Coding style guidelines:

*   Python code should be mostly PEP8 compliant. We currently ignore some PEP8 errors:
    E124, E128, E221, E251, E266, E402, E501, E712, E713
*   Aim to use single quotes around strings.
*   Template variables should have spaces just inside brackes: `{{ template_var }}`
*   Use underscores for database fields, API parameters, message types, and message parameters.
*   JavaScript code should use camel case.
*   JavaScript code should have two blank lines between top-level code blocks (to match Python code).
*   JavaScript and HTML files should use dashes as word separators in their file names.

## Running in Production

These are preliminary notes on running the server in a production environment with nginx and uwsgi.
When running the server in this way, you will no longer execute 'run.py' from the command line.
Instead the server will be run as a set of systemd services.

We have previously deployed the server on EC2 instances running Ubuntu.
We assume that you have followed the setup instructions above and have placed
the rhizo-server repository at `/home/ubuntu/rhizo-server` (if you want to use a 
different path, update the settings and service files accordingly).

Copy `nginx.conf`, `uwsgi.ini`, and `ws-config.py` from `sample_settings` to `settings`. 
Set your domain name within the file `nginx.conf`.

Install dependencies:

    sudo apt install nginx
    sudo apt install libpq-dev
    sudo pip install uwsgi
    sudo apt install letsencrypt

Configure nginx:

    cd /etc/nginx/sites-enabled
    sudo rm default
    sudo ln -s /home/ubuntu/rhizo-server/settings/nginx.conf rhizo-server

Get SSL certificates:

    sudo systemctl stop nginx
    sudo letsencrypt certonly --standalone -d [domain name here]
    sudo systemctl start nginx

Configure systemd services:

    sudo cp /home/ubuntu/rhizo-zerver/sample_settings/*.service /etc/systemd/system
    sudo systemctl enable nginx
    sudo systemctl enable rs
    sudo systemctl enable rs-ws
    sudo systemctl enable rs-worker
    sudo systemctl start rs
    sudo systemctl start rs-ws
    sudo systemctl start rs-worker
