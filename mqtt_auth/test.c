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
	printf("key: %s, len: %ld\n", key, strlen(key));

	// load server's password salt
	file = fopen("salt.txt", "r");
	char salt[100];
	fscanf(file, "%s", salt);
	fclose(file);
	printf("salt len: %ld\n", strlen(salt));

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
	int controller_id = auth_controller(db, key, salt);
	printf("auth_controller result: %d\n", controller_id);

	// clean up
	PQfinish(db);
	return 0;
}
