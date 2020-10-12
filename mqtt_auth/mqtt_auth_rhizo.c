#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <libpq-fe.h>
#include <mosquitto.h>
#include <mosquitto_plugin.h>
#include "rhizo_access.h"


typedef struct AuthData {
	PGconn *db;
	char *salt;
} AuthData;


// ======== mosquitto plugin callbacks ========


int mosquitto_auth_plugin_version(void) {
	return MOSQ_AUTH_PLUGIN_VERSION;
}

int mosquitto_auth_plugin_init(void **user_data, struct mosquitto_opt *opts, int opt_count) {
	fprintf(stderr, "mqtt_auth_rhizo: plugin init\n");

	// read options
	const char *db_name = NULL;
	const char *db_host = NULL;
	const char *db_username = NULL;
	const char *db_password = NULL;
	const char *salt = NULL;
	for (int i = 0; i < opt_count; i++) {
		struct mosquitto_opt *opt = opts + i;
		if (strcmp(opt->key, "db_name") == 0) {
			db_name = opt->value;
		} else if (strcmp(opt->key, "db_host") == 0) {
			db_host = opt->value;
		} else if (strcmp(opt->key, "db_username") == 0) {
			db_username = opt->value;
		} else if (strcmp(opt->key, "db_password") == 0) {
			db_password = opt->value;
		} else if (strcmp(opt->key, "salt") == 0) {
			salt = opt->value;
		}
	}

	// check options
	if (db_name == NULL || db_host == NULL || db_username == NULL || db_password == NULL || salt == NULL) {
		fprintf(stderr, "mqtt_auth_rhizo: missing option(s)\n");
		return MOSQ_ERR_UNKNOWN;
	}

	// connect to database
	char conn_info[400];
	snprintf(conn_info, 400, "dbname=%s host=%s user=%s password=%s", db_name, db_host, db_username, db_password);
	PGconn *db = PQconnectdb(conn_info);
	if (PQstatus(db) == CONNECTION_BAD) {
		fprintf(stderr, "mqtt_auth_rhizo: unable to connect to the database %s\n", db_name);
		return MOSQ_ERR_AUTH;
	}
	fprintf(stderr, "mqtt_auth_rhizo: connected to the database %s\n", db_name);

	// store data for future use
	AuthData *auth_data = (AuthData *) malloc(sizeof(AuthData));
	auth_data->db = db;
	auth_data->salt = (char *) malloc(strlen(salt) + 1);
	strcpy(auth_data->salt, salt);
	*user_data = auth_data;
	return MOSQ_ERR_SUCCESS;
}

int mosquitto_auth_plugin_cleanup(void *user_data, struct mosquitto_opt *opts, int opt_count) {
	AuthData *auth_data = (AuthData *) user_data;

	// disconnect from database
	PQfinish(auth_data->db);
	fprintf(stderr, "mqtt_auth_rhizo: disconnected from database\n");

	free(auth_data->salt);
	free(auth_data);
	return MOSQ_ERR_SUCCESS;
}

int mosquitto_auth_security_init(void *user_data, struct mosquitto_opt *opts, int opt_count, bool reload) {
	return MOSQ_ERR_SUCCESS;
}

int mosquitto_auth_security_cleanup(void *user_data, struct mosquitto_opt *opts, int opt_count, bool reload) {
	return MOSQ_ERR_SUCCESS;
}

int mosquitto_auth_acl_check(void *user_data, int access, struct mosquitto *client, const struct mosquitto_acl_msg *msg) {
	return MOSQ_ERR_SUCCESS;
}

int mosquitto_auth_unpwd_check(void *user_data, struct mosquitto *client, const char *username, const char *password) {
	AuthData *auth_data = (AuthData *) user_data;
	if (username == NULL || password == NULL) {
		return MOSQ_ERR_AUTH;
	}
	fprintf(stderr, "mqtt_auth_rhizo: username: %s, password: %c...\n", username, password[0]);

	// handle controller authentication
	if (strcmp(username, "controller") == 0) {
		int controller_id = auth_controller(auth_data->db, password, auth_data->salt);
		if (controller_id < 0) {
			fprintf(stderr, "mqtt_auth_rhizo: controller access denied\n");
			return MOSQ_ERR_AUTH;
		}
		fprintf(stderr, "mqtt_auth_rhizo: controller %d access allowed\n", controller_id);
	}

	return MOSQ_ERR_SUCCESS;
}
