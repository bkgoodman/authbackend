# authbackend

Some rough documentation as of December 2018.

## Install prerequisites

(Note: Ubuntu-flavored)

`sudo apt install libcurl4-openssl-dev libssl-dev`
`sudo apt install sqlite3 flask python-pycurl python-httplib2 python-auth2client`

`pip install flask-login`
`pip install flask-user`
`pip install stripe`
`pip install apiclient`
`pip install --upgrade google-api-python-client`
`pip install paho-mqtt`
`pip install pytz`
`pip install --upgrade oauth2client`

## Creating stub database

`sqlite3 makeit.db < schema.sql`

## Set up .ini file

`cp makeit.ini.example makeit.ini`

You might want to edit some things in the file before running the server. 

Make sure that if you are running a TEST server, that you set "Deployment:" 
to something other thatn "Production"

## Setup Database

The database is normally the makeit.db. You will probably need to copy this over from somewhere (i.e. live server).
If you don't have a "live" one to grab and use, you can create an example one with:

./migrate_db.py --overwrite makeit.db --testdata --nomigrate

This utility can also be used to migrate a database to a "new" schema - but this obviously will change drastically from
time-to-time, depending on which versions you are migrating to and form. The "--testdata" and "--testonly" flags won't
actually do any data migration, but will just give you a blank database with some test data in it.

You can also start with a VERY minimal database with:

python authserver.py --createdb

## Running development server

`python authserver.py`

This should start a server on `0.0.0.0:5000` which you can get to via browser or use the API calls.  The default user/password is admin/admin (configured in .ini file).

## Fix for newer versions of Flask library

If you get a similar error to:
```
Traceback (most recent call last):
  File "authserver.py", line 24, in <module>
    from flask.ext.login import LoginManager, UserMixin, login_required,  current_user, login_user, logout_user
ImportError: No module named ext.login
```

...you might have newer versions of the Flask library which have a different import syntax.

Change the import line in `authserver.py` to:
```python
from flask_login import LoginManager, UserMixin, login_required,  current_user, login_user, logout_user
```


## Using the CLI: 

Get info like:

python ./authserver --command help
