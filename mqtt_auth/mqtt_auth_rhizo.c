#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <libpq-fe.h>
#include <mosquitto.h>
#include <mosquitto_plugin.h>
#include <mosquitto_broker.h>  // for mosquitto_log_printf
#include <mosquitto_internal.h>  // for struct mosquitto
#include "rhizo_access.h"


typedef struct ClientInfo {
	unsigned long hash;
	char *password;
	int controller_id;
	int controller_org_id;
	int user_id;
} ClientInfo;


typedef struct AuthData {
	PGconn *db;
	char *password_salt;
	char *msg_token_salt;
	int verbose;
	ClientInfo *clients;
	int next_client_index;
} AuthData;


// TODO: need to support arbitrary number of client; use LRU cache or hash table?
#define MAX_CLIENTS 100


// via http://www.cse.yorku.ca/~oz/hash.html
unsigned long hash(const unsigned char *str) {
	unsigned long hash = 5381;
	int c = 0;
	while ((c = *str++)) {
		hash = ((hash << 5) + hash) + c;  // hash * 33 + c
	}
	return hash;
}


char *alloc_str_copy(const char *s) {
	char *result = (char *) malloc(strlen(s) + 1);
	strcpy(result, s);
	return result;
}


void store_client_info(AuthData *auth_data, const char *password, int controller_id, int controller_org_id, int user_id) {
	int h = hash((const unsigned char *) password);

	// if existing entry, update it
	for (int i = 0; i < MAX_CLIENTS; i++) {
		ClientInfo *ci = &auth_data->clients[i];
		if (ci->hash == h && strcmp(ci->password, password) == 0) {
			ci->controller_id = controller_id;
			ci->controller_org_id = controller_org_id;
			ci->user_id = user_id;
			if (auth_data->verbose) {
				fprintf(stderr, "mqtt_auth_rhizo: updated client data in slot %d\n", i);
			}
			return;
		}
	}

	// otherwise create a new one
	if (auth_data->next_client_index < MAX_CLIENTS) {
		ClientInfo *ci = &auth_data->clients[auth_data->next_client_index];
		ci->hash = h;
		ci->password = alloc_str_copy(password);
		ci->controller_id = controller_id;
		ci->controller_org_id = controller_org_id;
		ci->user_id = user_id;
		if (auth_data->verbose) {
			fprintf(stderr, "mqtt_auth_rhizo: stored client data in slot %d\n", auth_data->next_client_index);
		}
		auth_data->next_client_index++;
	} else {
		fprintf(stderr, "mqtt_auth_rhizo: too many clients\n");
	}
}


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

	// store data for future use
	AuthData *auth_data = (AuthData *) malloc(sizeof(AuthData));
	auth_data->db = db;
	auth_data->password_salt = alloc_str_copy(password_salt);
	auth_data->msg_token_salt = alloc_str_copy(msg_token_salt);
	auth_data->verbose = verbose;
	auth_data->clients = (ClientInfo *) malloc(MAX_CLIENTS * sizeof(ClientInfo));
	auth_data->next_client_index = 0;
	for (int i = 0; i < MAX_CLIENTS; i++) {
		auth_data->clients[i].password = NULL;
	}
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
	for (int i = 0; i < MAX_CLIENTS; i++) {
		if (auth_data->clients[i].password) {
			free(auth_data->clients[i].password);
		}
	}
	free(auth_data->clients);
	free(auth_data->password_salt);
	free(auth_data->msg_token_salt);
	free(auth_data);
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
	if (username == NULL || password == NULL) {
		return MOSQ_ERR_AUTH;
	}
	if (auth_data->verbose) {
		fprintf(stderr, "mqtt_auth_rhizo: username: %s, password: %c...\n", username, password[0]);
	}

	// handle key-based authentication (currently only supporting controller keys, not user keys)
	if (strcmp(username, "key") == 0) {
		int controller_org_id = -1;
		int controller_id = auth_controller(auth_data->db, password, auth_data->password_salt, &controller_org_id, auth_data->verbose);
		if (controller_id < 0) {
			fprintf(stderr, "mqtt_auth_rhizo: controller auth denied\n");
			return MOSQ_ERR_AUTH;
		} else {
			if (auth_data->verbose) {
				fprintf(stderr, "mqtt_auth_rhizo: controller %d auth allowed\n", controller_id);
			}
			//store_client_info(auth_data, password, controller_id, controller_org_id, 0);
			return MOSQ_ERR_SUCCESS;
		}
	}

	// handle token-based authentication (for user's accessing via browser)
	if (strcmp(username, "token") == 0) {
		int user_id = auth_user(auth_data->db, password, auth_data->msg_token_salt, auth_data->verbose);
		if (user_id >= 0) {
			if (auth_data->verbose) {
				fprintf(stderr, "mqtt_auth_rhizo: user %d auth ok\n", user_id);
			}
			//store_client_info(auth_data, password, 0, 0, user_id);
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
	AuthData *auth_data = (AuthData *) user_data;

	// find client info
	int h = hash((const unsigned char *) client->password);
	ClientInfo *client_info = NULL;
	for (int i = 0; i < MAX_CLIENTS; i++) {
		ClientInfo *ci = &auth_data->clients[i];
		if (ci->hash == h && strcmp(ci->password, client->password) == 0) {
			client_info = ci;
		}
	}
	if (client_info == NULL) {
		//fprintf(stderr, "mqtt_auth_rhizo: client info not found\n");
		//return MOSQ_ERR_ACL_DENIED;
		return MOSQ_ERR_SUCCESS;  // temp for testing
	}

	// compute access level according to permissions in database
	int access_level = ACCESS_LEVEL_NONE;
	if (client_info->controller_id >= 0) {  // controller access
		access_level = controller_access_level(auth_data->db, msg->topic, client_info->controller_id, client_info->controller_org_id, auth_data->verbose);
	} else if (client_info->user_id == 0) {  // inter-server connection
		access_level = ACCESS_LEVEL_WRITE;
	} else {  // user access
		access_level = user_access_level(auth_data->db, msg->topic, client_info->user_id, auth_data->verbose);
	}
	fprintf(stderr, "access path: %s, req level: %d, contr: %d, contr org: %d, user: %d, access: %d\n",
		msg->topic, access, client_info->controller_id, client_info->controller_org_id, client_info->user_id, access_level);
	return MOSQ_ERR_SUCCESS;  // temp for testing

	// check access level vs requested access
	if (access == MOSQ_ACL_READ) {  // requested read accesss
		if (access_level >= ACCESS_LEVEL_READ) {
			return MOSQ_ERR_SUCCESS;
		}
	} else {  // requested write access
		if (access_level >= ACCESS_LEVEL_WRITE) {
			return MOSQ_ERR_SUCCESS;
		}
	}
	return MOSQ_ERR_ACL_DENIED;
}
