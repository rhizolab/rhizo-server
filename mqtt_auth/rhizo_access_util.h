#ifndef RHIZO_ACCESS_UTIL_H
#define RHIZO_ACCESS_UTIL_H


int base64_encode(const void *data, int size, char *output, int output_len);


unsigned long hash(const unsigned char *str);


char *alloc_str_copy(const char *s);


// compute the inner hash of a password using system's salt
// (adapted from function with same name in our python codebase)
void inner_password_hash(const char *password, const char *salt, char *hash, int hash_len);


#endif  // RHIZO_ACCESS_UTIL_H
