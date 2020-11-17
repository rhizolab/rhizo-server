#include <string.h>
#include <stdlib.h>
#include <openssl/sha.h>
#include "rhizo_access_util.h"


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


// compute the inner hash of a password using system's salt
// (adapted from function with same name in our python codebase)
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
