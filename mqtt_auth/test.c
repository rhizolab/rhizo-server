#include <stdio.h>
#include <string.h>
#include "rhizo_access.h"


int main(int argc, char *argv[]) {
	printf("rhizo access test program\n");

	// load test key
	FILE *file = fopen("key.txt", "r");
	char key[100];
	fscanf(file, "%s", key);
	fclose(file);
	printf("key: %c..., len: %ld\n", key[0], strlen(key));

	// load token
	file = fopen("token.txt", "r");
	char token[200];
	fscanf(file, "%s", token);
	fclose(file);
	printf("token: %c..., len: %ld\n", token[0], strlen(token));

	// load test path
	file = fopen("path.txt", "r");
	char path[100];
	fscanf(file, "%s", path);
	fclose(file);
	printf("path: %s\n", path);

	// load server's password salt
	file = fopen("password-salt.txt", "r");
	char password_salt[100];
	fscanf(file, "%s", password_salt);
	fclose(file);
	printf("password salt: %c..., len: %ld\n", password_salt[0], strlen(password_salt));

	// load server's message token salt
	file = fopen("msg-token-salt.txt", "r");
	char msg_token_salt[100];
	fscanf(file, "%s", msg_token_salt);
	fclose(file);
	printf("msg token salt: %c..., len: %ld\n", msg_token_salt[0], strlen(msg_token_salt));

	// load DB connection string
	file = fopen("conn.txt", "r");
	char conn[200];
	fgets(conn, 200, file);
	fclose(file);

	// open database 
	PGconn *db = PQconnectdb(conn);
	if (PQstatus(db) == CONNECTION_BAD) {
		printf("unable to connect to the database\n");
		return -1;
	}

	// check key
	int controller_org_id = -1;
	int controller_id = auth_controller(db, key, password_salt, &controller_org_id, 1);
	printf("auth_controller result: %d; org: %d\n", controller_id, controller_org_id);

	// check controller access level
	int level = controller_access_level(db, path + 1, controller_id, controller_org_id, 1);
	printf("controller_access_level result: %d\n", level);
	if (level != ACCESS_LEVEL_WRITE) {
		printf("** errror **\n");
		return -1;
	}

	// check user access token
	int user_id = auth_user(db, "1;2;3;abc", msg_token_salt, 1);
	printf("dummy token check: %d\n", user_id);
	if (user_id != -1) {
		printf("** errror **\n");
		return -1;
	}
	user_id = auth_user(db, token, msg_token_salt, 1);
	printf("loaded token check: %d\n", user_id);
	if (user_id < 0) {
		printf("** errror **\n");
		return -1;
	}

	// check user access level
	level = user_access_level(db, path + 1, user_id, 1);
	printf("user_access_level result: %d\n", level);
	if (level != ACCESS_LEVEL_WRITE) {
		printf("** errror **\n");
		return -1;
	}

	// clean up
	PQfinish(db);
	printf("test done\n");
	return 0;
}
