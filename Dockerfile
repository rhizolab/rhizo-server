# Install dependencies using a separate container. For regular Docker builds, this doesn't
# really make much difference, but for Balena builds, our Makefile replaces the  base image
# with one that includes compilers and header files that aren't included in the minimal
# Python image that gets deployed to devices.
FROM python:3.8.5-buster AS build

WORKDIR /rhizo-server

# Install expensive dependencies as a separate build step so we don't have to repeat it if
# cheaper dependencies are added/removed.
COPY requirements-prebuild.txt ./
RUN pip install -r requirements-prebuild.txt
RUN pip install psycopg2-binary

# Install remaining dependencies
COPY requirements.txt ./
RUN pip install -r requirements.txt

# uncomment to install flow-server extension dependencies
#RUN pip install rauth python-jose requests

COPY sample_settings sample_settings
COPY prep_config.py ./

# add the config
RUN python prep_config.py \
    && echo "DISCLAIMER = 'This is pre-release code; the API and database structure will probably change.'" >> settings/config.py

# For Balena, our Makefile replaces this with a Balena base image that does not include
# build tools such as compilers.
FROM python:3.8.5-buster

WORKDIR /rhizo-server

COPY --from=build /usr/local/lib/python3.8/site-packages /usr/local/lib/python3.8/site-packages

# copy in the app source
COPY run.py run_worker.py ./
COPY main main
COPY --from=build /rhizo-server/settings settings

# create an empty extensions folder
RUN mkdir extensions && touch extensions/__init__.py

EXPOSE 5000

# run the server in unbuffered output mode
CMD [ "python", "-u", "run.py", "-s" ]
