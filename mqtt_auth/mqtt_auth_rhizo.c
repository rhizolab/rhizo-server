#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <libpq-fe.h>
#define WITH_ADNS  // needed for getting mosquitto struct to match installed mosquitto
#include <mosquitto.h>
#include <mosquitto_plugin.h>
#include <mosquitto_broker.h>  // for mosquitto_log_printf
#include <mosquitto_internal.h>  // for struct mosquitto
#include "rhizo_access.h"
#include "rhizo_access_util.h"  // remove?


// ======== mosquitto plugin callbacks ========


int mosquitto_auth_plugin_version(void) {
	return MOSQ_AUTH_PLUGIN_VERSION;
}


int mosquitto_auth_plugin_init(void **user_data, struct mosquitto_opt *opts, int opt_count) {
	fprintf(stderr, "mqtt_auth_rhizo: plugin init\n");

	// TODO: would be nice to use these instead of fprintf(stderr), but need to figure out settings to see them
	mosquitto_log_printf(MOSQ_LOG_WARNING, "test log warning\n");
	mosquitto_log_printf(MOSQ_LOG_NOTICE, "test log notice\n");
	mosquitto_log_printf(MOSQ_LOG_INFO, "test log info\n");
	mosquitto_log_printf(MOSQ_LOG_DEBUG, "test log debug\n");

	// read options
	const char *db_name = NULL;
	const char *db_host = NULL;
	const char *db_username = NULL;
	const char *db_password = NULL;
	const char *password_salt = NULL;
	const char *msg_token_salt = NULL;
	int verbose = 0;
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
		} else if (strcmp(opt->key, "password_salt") == 0) {
			password_salt = opt->value;
		} else if (strcmp(opt->key, "msg_token_salt") == 0) {
			msg_token_salt = opt->value;
		} else if (strcmp(opt->key, "verbose") == 0) {
			verbose = atoi(opt->value);
		}
	}

	// check options
	if (db_name == NULL || db_host == NULL || db_username == NULL || db_password == NULL || password_salt == NULL || msg_token_salt == NULL) {
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
	if (verbose) {
		fprintf(stderr, "mqtt_auth_rhizo: connected to the database %s\n", db_name);
	}

	// create an object to store data between plugin calls
	AuthData *auth_data = create_auth_data(db, password_salt, msg_token_salt, verbose);
	*user_data = auth_data;
	return MOSQ_ERR_SUCCESS;
}


int mosquitto_auth_plugin_cleanup(void *user_data, struct mosquitto_opt *opts, int opt_count) {
	AuthData *auth_data = (AuthData *) user_data;

	// disconnect from database
	PQfinish(auth_data->db);
	if (auth_data->verbose) {
		fprintf(stderr, "mqtt_auth_rhizo: disconnected from database\n");
	}

	// deallocate plugin data
	free_auth_data(auth_data);
	return MOSQ_ERR_SUCCESS;
}


int mosquitto_auth_security_init(void *user_data, struct mosquitto_opt *opts, int opt_count, bool reload) {
	return MOSQ_ERR_SUCCESS;
}


int mosquitto_auth_security_cleanup(void *user_data, struct mosquitto_opt *opts, int opt_count, bool reload) {
	return MOSQ_ERR_SUCCESS;
}


int mosquitto_auth_unpwd_check(void *user_data, struct mosquitto *client, const char *username, const char *password) {
	AuthData *auth_data = (AuthData *) user_data;
	if (username == NULL || password == NULL || username[0] == 0 || password[0] == 0) {  // we require a username and password
		return MOSQ_ERR_AUTH;
	}
	if (auth_data->verbose) {
		fprintf(stderr, "mqtt_auth_rhizo: username: %s, password: %c...\n", username, password[0] ? password[0] : '_');
	}

	// handle key-based authentication (currently only supporting controller keys, not user keys)
	if (strcmp(username, "key") == 0) {
		int controller_id = auth_controller(auth_data, password);
		if (controller_id < 0) {
			fprintf(stderr, "mqtt_auth_rhizo: controller auth denied\n");
			return MOSQ_ERR_AUTH;
		} else {
			if (auth_data->verbose) {
				fprintf(stderr, "mqtt_auth_rhizo: controller %d auth allowed\n", controller_id);
			}
			return MOSQ_ERR_SUCCESS;
		}
	}

	// handle token-based authentication (for user's accessing via browser)
	if (strcmp(username, "token") == 0) {
		int user_id = auth_user(auth_data, password);
		if (user_id >= 0) {
			if (auth_data->verbose) {
				fprintf(stderr, "mqtt_auth_rhizo: user %d auth ok\n", user_id);
			}
			return MOSQ_ERR_SUCCESS;
		} else {
			fprintf(stderr, "mqtt_auth_rhizo: token auth denied\n");
			return MOSQ_ERR_AUTH;
		}
	}

	// deny access if didn't pass above checks
	return MOSQ_ERR_AUTH;
}


int mosquitto_auth_acl_check(void *user_data, int access, struct mosquitto *client, const struct mosquitto_acl_msg *msg) {
	const char *password = client->username;  // TODO: fix compilation so that the struct we're using matches what we're receiving
	AuthData *auth_data = (AuthData *) user_data;
	int server_access_level = access_level(auth_data, msg->topic, password);

	// check server access level vs requested access
	if (access == MOSQ_ACL_READ) {  // requested read accesss
		if (server_access_level >= ACCESS_LEVEL_READ) {
			return MOSQ_ERR_SUCCESS;
		}
	} else {  // requested write access
		if (server_access_level >= ACCESS_LEVEL_WRITE) {
			return MOSQ_ERR_SUCCESS;
		}
	}
	if (auth_data->verbose) {
		fprintf(stderr, "mqtt_auth_rhizo: access denied on topic: %s, pw: %c...\n", msg->topic, password[0] ? password[0] : '_');
	}
	return MOSQ_ERR_ACL_DENIED;
}
