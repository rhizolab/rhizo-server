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


int auth_controller(PGconn *db_conn, const char *secret_key, const char *salt) {
	int debug = 0;

	// use beginning and end of key to look up candidate keys in the database
	int key_len = strlen(secret_key);
	char key_part[7];
	for (int i = 0; i < 3; i++) {
		key_part[i] = secret_key[i];
		key_part[i + 3] = secret_key[key_len - 3 + i];
	}
	key_part[6] = 0;
	if (debug) {
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
		if (debug) {
			fprintf(stderr, "rhizo_access: found %d key record(s)\n", record_count);
		}

		// compute hash
		char input_hash[200];
		inner_password_hash(secret_key, salt, input_hash, 200);

		// check hashes
		for (int i = 0; i < record_count; i++) {
			char *controller_id = PQgetvalue(res, i, 0);
			char *key_hash = PQgetvalue(res, i, 1);
			int res = bcrypt_checkpw(input_hash, key_hash);
			if (res == 0) {
				found_controller_id = atoi(controller_id);
				break;
			} else if (res < 0) {
				fprintf(stderr, "rhizo_access: error using bcrypt\n");
			}
		}
	}
	PQclear(res);
	return found_controller_id;
}
