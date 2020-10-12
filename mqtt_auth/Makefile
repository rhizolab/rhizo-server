BCRYPT    = /home/ubuntu/libbcrypt
INC       = -I/usr/include/postgresql -I$(BCRYPT)
CFLAGS    = -Wall -Werror -fPIC
LIBS      = -lpq -lcrypto

all: mqtt_auth_rhizo.so test

mqtt_auth_rhizo.so: mqtt_auth_rhizo.o rhizo_access.o $(BCRYPT)/bcrypt.o $(BCRYPT)/crypt_blowfish/*.o
	$(CC) $(CFLAGS) $(INC) -shared $^ -o $@ $(LIBS)

test: test.c rhizo_access.o
	$(CC) $(CFLAGS) $(INC) $^ -o test $(LIBS) $(BCRYPT)/bcrypt.o $(BCRYPT)/crypt_blowfish/*.o

%.o: %.c
	$(CC) -c $(CFLAGS) $(DEBUG) $(INC) $< -o $@

clean:
	rm -f *.o *.so
