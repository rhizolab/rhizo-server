#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <openssl/sha.h>
#include <bcrypt.h>
#include "rhizo_access.h"


// adapted from https://github.com/jpmens/mosquitto-auth-plug
static char base64[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
int base64_encode(const void *data, int size, char *output, int output_len) {
	char *p = output;
	unsigned char *q = (unsigned char*)data;
	if (output_len < size*4/3+4)
		return -1;
	for(int i = 0; i < size;){
		int c=q[i++];
		c*=256;
		if(i < size)
			c+=q[i];
		i++;
		c*=256;
		if(i < size)
			c+=q[i];
		i++;
		p[0]=base64[(c&0x00fc0000) >> 18];
		p[1]=base64[(c&0x0003f000) >> 12];
		p[2]=base64[(c&0x00000fc0) >> 6];
		p[3]=base64[(c&0x0000003f) >> 0];
		if(i > size)
			p[3]='=';
		if(i > size+1)
			p[2]='=';
		p+=4;
	}
	*p=0;
	return 0;
}


// compute the inner hash of a password using system's salt
void inner_password_hash(const char *password, const char *salt, char *hash, int hash_len) {

	// concatenate password and salt
	int pw_len = strlen(password);
	char *combined = (char *) malloc(pw_len + strlen(salt) + 1);
	strcpy(combined, password);
	strcpy(combined + pw_len, salt);

	// compute SHA-512 hash
	unsigned char raw_hash[SHA512_DIGEST_LENGTH];
	SHA512((unsigned char *) combined, strlen(combined), raw_hash);

	// base64 encode the result
	base64_encode(raw_hash, SHA512_DIGEST_LENGTH, hash, hash_len);  // TODO: would be cleaner to encode directly into 'hash'
	free(combined);
}


int root_resource_id(PGconn *db_conn, int resource_id) {
	char query_sql[200];
	snprintf(query_sql, 200, "SELECT parent_id FROM resources WHERE id=%d;", resource_id);

	// run the query
	PGresult *res = PQexec(db_conn, query_sql);
	if (PQresultStatus(res) != PGRES_TUPLES_OK) {
		fprintf(stderr, "rhizo_access: postgres error: %s\n", PQresStatus(PQresultStatus(res)));
		fprintf(stderr, "rhizo_access: postgres error: %s\n", PQresultErrorMessage(res));
	}

	// check result records
	int parent_id = -1;
	if (PQresultStatus(res) == PGRES_TUPLES_OK && PQntuples(res) >= 1) {
		const char *val = PQgetvalue(res, 0, 0);
		if (val[0]) {  // if not NULL
			parent_id = atoi(PQgetvalue(res, 0, 0));
		}
	}
	PQclear(res);
	int root_id = -1;
	if (parent_id >= 0) {
		root_id = root_resource_id(db_conn, parent_id);
	} else {
		root_id = resource_id;  // no parent, so we've found the root
	}
	return root_id;
}


int auth_controller(PGconn *db_conn, const char *secret_key, const char *password_salt, int *organization_id, int verbose) {

	// use beginning and end of key to look up candidate keys in the database
	int key_len = strlen(secret_key);
	char key_part[7];
	for (int i = 0; i < 3; i++) {
		key_part[i] = secret_key[i];
		key_part[i + 3] = secret_key[key_len - 3 + i];
	}
	key_part[6] = 0;
	if (verbose) {
		fprintf(stderr, "rhizo_access: checking controller auth; key part: %s\n", key_part);
	}

	// prepare a query string
	char *key_part_escaped = PQescapeLiteral(db_conn, key_part, strlen(key_part));  // try to avoid SQL injection attacks
	if (key_part_escaped == NULL) {
		return -1;
	}
	char query_sql[200];
	snprintf(query_sql, 200, "SELECT access_as_controller_id, key_hash FROM keys WHERE key_part=%s AND revocation_timestamp IS NULL;", key_part_escaped);
	PQfreemem(key_part_escaped);

	// run the query
	PGresult *res = PQexec(db_conn, query_sql);
	if (PQresultStatus(res) != PGRES_TUPLES_OK) {
		fprintf(stderr, "rhizo_access: postgres error: %s\n", PQresStatus(PQresultStatus(res)));
		fprintf(stderr, "rhizo_access: postgres error: %s\n", PQresultErrorMessage(res));
	}

	// check result records
	int found_controller_id = -1;
	if (PQresultStatus(res) == PGRES_TUPLES_OK && PQntuples(res) >= 1) {
		int record_count = PQntuples(res);
		if (verbose) {
			fprintf(stderr, "rhizo_access: found %d key record(s)\n", record_count);
		}

		// compute hash
		char input_hash[200];
		inner_password_hash(secret_key, password_salt, input_hash, 200);

		// check hashes
		for (int i = 0; i < record_count; i++) {
			char *key_hash = PQgetvalue(res, i, 1);
			int check = bcrypt_checkpw(input_hash, key_hash);
			if (check == 0) {
				found_controller_id = atoi(PQgetvalue(res, i, 0));
				break;
			} else if (check < 0) {
				fprintf(stderr, "rhizo_access: error using bcrypt\n");
			}
		}
	}
	PQclear(res);

	// determine which organization contains/owns the controller
	if (found_controller_id >= 0) {
		*organization_id = root_resource_id(db_conn, found_controller_id);
	}
	return found_controller_id;
}


// look up information about the organization with the given path;
// permissions string will be allocated and must be free'd outside (if not NULL)
int organization_info(PGconn *db_conn, const char *path, char **permissions) {
	*permissions = NULL;
	path += 1;  // skip initial slash
	char *slash = strchr(path, '/');
	int len = slash - path;
	if (len > 100) len = 100;  // reconsider this
	char organization_name[101];
	strncpy(organization_name, path, len);
	organization_name[len] = 0;

	// prepare a query string
	char *org_name_escaped = PQescapeLiteral(db_conn, organization_name, len);  // try to avoid SQL injection attacks
	if (org_name_escaped == NULL) {
		return -1;
	}
	char query_sql[200];
	snprintf(query_sql, 200, "SELECT id, permissions FROM resources WHERE name=%s AND parent_id IS NULL;", org_name_escaped);
	PQfreemem(org_name_escaped);

	// run the query
	PGresult *res = PQexec(db_conn, query_sql);
	if (PQresultStatus(res) != PGRES_TUPLES_OK) {
		fprintf(stderr, "rhizo_access: postgres error: %s\n", PQresStatus(PQresultStatus(res)));
		fprintf(stderr, "rhizo_access: postgres error: %s\n", PQresultErrorMessage(res));
	}

	// get organization info
	int resource_id = -1;
	if (PQresultStatus(res) == PGRES_TUPLES_OK && PQntuples(res) >= 1) {
		resource_id = atoi(PQgetvalue(res, 0, 0));
		char *p = PQgetvalue(res, 0, 1);
		*permissions = (char *) malloc(strlen(p) + 1);
		strcpy(*permissions, p);
	}
	PQclear(res);
	return resource_id;
}


// determines a controller's access level for a given path
int controller_access_level(PGconn *db_conn, const char *path, int controller_id, int controller_org_id) {

	// for now we just check that topic path organization matches controller organization
	char *permissions = NULL;
	int org_id = organization_info(db_conn, path, &permissions);
	if (org_id < 0) {
		return ACCESS_LEVEL_NONE;
	}
	if (org_id != controller_org_id) {
		free(permissions);
		return ACCESS_LEVEL_NONE;
	}
	fprintf(stderr, "rhizo_access: org id: %d, permissions: %s\n", org_id, permissions);
	free(permissions);
	return ACCESS_LEVEL_WRITE;
}


// checks that a message token is valid; if valid returns user_id; if not valid, returns -1
// token format: token_version;user_id;unix_timestamp;base64(sha-512(user_id;unix_timestamp;msg_token_salt))
int check_token(const char *token, const char *msg_token_salt) {

	// parse the token
	int token_version = -1;
	int user_id = -1;
	int unix_timestamp = -1;
	char given_body[200];
	char token_copy[200];
	strncpy(token_copy, token, 200);
	sscanf(token, "%d;%d;%d;%s", &token_version, &user_id, &unix_timestamp, given_body);

	// check token format
	if (token_version != 1 || user_id < 0 || unix_timestamp <= 0 || strlen(given_body) < 1) {
		fprintf(stderr, "rhizo_access: invalid token format\n");
	}

	// compute token hash contents
	char contents[200];
	snprintf(contents, 200, "%d;%d;%s", user_id, unix_timestamp, msg_token_salt);

	// compute SHA-512 hash
	unsigned char raw_hash[SHA512_DIGEST_LENGTH];
	SHA512((unsigned char *) contents, strlen(contents), raw_hash);

	// base64 encode the result
	char computed_body[200];
	base64_encode(raw_hash, SHA512_DIGEST_LENGTH, computed_body, 200);

	// if computed body matches given body, token is valid and we can return the given user ID
	if (strcmp(computed_body, given_body) == 0) {
		return user_id;
	} else {
		return -1;
	}
}
