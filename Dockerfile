FROM python:2.7.15

WORKDIR /rhizo-server

# install dependencies
COPY requirements.txt ./
RUN pip install -r requirements.txt
RUN pip install psycopg2-binary
RUN pip install rauth

# copy in the app source
COPY . .

# add the config
RUN python prep_config.py
RUN echo "DISCLAIMER = 'This is pre-release code; the API and database structure will probably change.'" >> settings/config.py

# create an empty extensions folder
RUN mkdir extensions
RUN touch extensions/__init__.py

# run the server in unbuffered output mode
EXPOSE 80
CMD [ "python", "-u", "run.py", "-s" ]