#ifndef RHIZO_ACCESS_H
#define RHIZO_ACCESS_H
#include <libpq-fe.h>


// this module provides C functions for checking controller and user authentication and permissions


#define ACCESS_LEVEL_NONE 0
#define ACCESS_LEVEL_READ 10
#define ACCESS_LEVEL_WRITE 20


#define MAX_CLIENTS 500


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


int auth_controller(PGconn *db_conn, const char *secret_key, const char *password_salt, int *organization_id, int verbose);


// determines a controller's access level for a given path
int controller_access_level(PGconn *db_conn, const char *path, int controller_id, int controller_org_id, int verbose);


// returns the user ID if token is valid; otherwise returns -1
// token format: token_version,unix_timestamp,key_id,nonce,base64(sha-512(unix_timestamp,key_id,nonce,msg_token_salt,key_hash))
int auth_user(PGconn *db_conn, const char *token, const char *msg_token_salt, int verbose);


// determines a user's access level for a given path (without leading slash)
int user_access_level(PGconn *db_conn, const char *path, int user_id, int verbose);


#endif  // RHIZO_ACCESS_H
