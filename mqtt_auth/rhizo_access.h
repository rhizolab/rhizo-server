#ifndef RHIZO_ACCESS_H
#define RHIZO_ACCESS_H
#include <libpq-fe.h>


// this module provides C functions for checking controller and user authentication and permissions


#define ACCESS_LEVEL_NONE 0
#define ACCESS_LEVEL_READ 10
#define ACCESS_LEVEL_WRITE 20


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


AuthData *create_auth_data(PGconn *db, const char *password_salt, const char *msg_token_salt, int verbose);


void free_auth_data(AuthData *auth_data);


int auth_controller(AuthData *auth_data, const char *secret_key);


// returns the user ID if token is valid; otherwise returns -1
// token format: token_version,unix_timestamp,key_id,nonce,base64(sha-512(unix_timestamp,key_id,nonce,msg_token_salt,key_hash))
int auth_user(AuthData *auth_data, const char *token);


int access_level(AuthData *auth_data, const char *topic, const char *password);


#endif  // RHIZO_ACCESS_H
