#ifndef RHIZO_ACCESS_H
#define RHIZO_ACCESS_H
#include <libpq-fe.h>


// this module provides C functions for checking controller and user authentication and permissions


int auth_controller(PGconn *db, const char *secret_key, const char *salt);


#endif  // RHIZO_ACCESS_H
