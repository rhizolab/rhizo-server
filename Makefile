#
# Generate a Balena-friendly Dockerfile from the default one. This just replaces the
# base image names with Balena's per-architecture ones.
#
Dockerfile.template: Dockerfile
	sed -e 's@^FROM python:\([0-9.]*\)-\([^ ]\)@FROM balenalib/%%BALENA_MACHINE_NAME%%-debian-python:\1-\2@' \
		-e 's@^FROM \(.*\) AS build$$@FROM \1-build AS build@' \
		< $< > $@

raspi-build: Dockerfile.template
	balena build -A aarch64 -d raspberrypi4-64
