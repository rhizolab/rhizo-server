BCRYPT    = /home/ubuntu/libbcrypt
MOSQ_SRC  = /home/ubuntu/mosquitto
INC       = -I/usr/include/postgresql -I$(BCRYPT) -I$(MOSQ_SRC) -I$(MOSQ_SRC)/src -I$(MOSQ_SRC)/lib
CFLAGS    = -Wall -Werror -fPIC
LIBS      = -lpq -lcrypto

all: mqtt_auth_rhizo.so test

mqtt_auth_rhizo.so: mqtt_auth_rhizo.o rhizo_access.o rhizo_access_util.o $(BCRYPT)/bcrypt.o $(BCRYPT)/crypt_blowfish/*.o
	$(CC) $(CFLAGS) $(INC) -shared $^ -o $@ $(LIBS)

test: test.c rhizo_access.o rhizo_access_util.o
	$(CC) $(CFLAGS) $(INC) $^ -o test $(LIBS) $(BCRYPT)/bcrypt.o $(BCRYPT)/crypt_blowfish/*.o

%.o: %.c
	$(CC) -c $(CFLAGS) $(DEBUG) $(INC) $< -o $@

clean:
	rm -f *.o *.so
