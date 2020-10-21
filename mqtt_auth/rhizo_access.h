#ifndef RHIZO_ACCESS_H
#define RHIZO_ACCESS_H
#include <libpq-fe.h>


// this module provides C functions for checking controller and user authentication and permissions


#define ACCESS_LEVEL_NONE 0
#define ACCESS_LEVEL_READ 10
#define ACCESS_LEVEL_WRITE 20


int auth_controller(PGconn *db_conn, const char *secret_key, const char *password_salt, int *organization_id, int verbose);


// determines a controller's access level for a given path
int controller_access_level(PGconn *db_conn, const char *path, int controller_id, int controller_org_id);


// checks that a message token is valid; if valid returns user_id; if not valid, returns -1
// token format: token_version;user_id;unix_timestamp;base64(sha-512(user_id;unix_timestamp;msg_token_salt))
int check_token(const char *token, const char *msg_token_salt);


#endif  // RHIZO_ACCESS_H
