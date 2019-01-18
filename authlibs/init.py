"""
vim:tabstop=2:expandtab
MakeIt Labs Authorization System, v0.4

Flask, Configuration, SQLAlchemy and Database Initialization

"""

from flask import Flask, request, session, g, redirect, url_for, \
	abort, render_template, flash, Response
from flask_user import current_user, login_required, roles_required, UserManager, UserMixin, current_app 
from flask_sqlalchemy import SQLAlchemy
import logging
import sys
import ConfigParser
from db_models import db,  Member, Role, defined_roles, ApiKey
from datetime import datetime

# SET THIS 
GLOBAL_LOGGER_LEVEL = logging.DEBUG

logger = logging.getLogger(__name__)
logger.setLevel(GLOBAL_LOGGER_LEVEL)



# Load general configuration from file

def get_config():
  defaults = {'ServerPort': 5000, 'ServerHost': '127.0.0.1'}
  Config = ConfigParser.ConfigParser(defaults)
  Config.read('makeit.ini')
  return Config

def createDefaultRoles(app):
    for role in defined_roles:
      r = Role.query.filter(Role.name==role).one_or_none()
      if not r:
          r = Role(name=role)
          db.session.add(r)
    db.session.commit()

def createDefaultUsers(app):
    createDefaultRoles(app)
    """
    # Create default admin role and user if not present
    admin_role = Role.query.filter(Role.name=='Admin').first()
    if not User.query.filter(User.email == app.globalConfig.AdminUser).first():
        user = User(email=app.globalConfig.AdminUser,password=app.user_manager.hash_password(app.globalConfig.AdminPasswd),email_confirmed_at=datetime.utcnow())
        logger.debug("ADD USER "+str(user))
        db.session.add(user)
        user.roles.append(admin_role)
        db.session.commit()
    """
    # TODO - other default users?

class GlobalConfig(object):
  """ These are all Authbackend-Specifc. Reference via app.globalConfig 

      Anything in the ini file which is not explicitly stored as a variable here
      can be accessed at runtime with:

      app.globalConfig.Config.get("Category","itemname")
  """
  Config = get_config()
  ServerHost = Config.get('General','ServerHost')
  ServerPort = Config.getint('General','ServerPort')
  Database = Config.get('General','Database')
  AdminUser = Config.get('General','AdminUser')
  AdminPasswd = Config.get('General','AdminPassword')
  DeployType = Config.get('General','Deployment')
  Debug = Config.getboolean('General','Debug')

  """ Extract MQTT settings here (So we don't have to do every time we kick """

  mqtt_opts={}
  mqtt_base_topic = Config.get("MQTT","BaseTopic")
  mqtt_host = Config.get("MQTT","BrokerHost")
  mqtt_port = Config.getint("MQTT","BrokerPort")
  if Config.has_option("MQTT","keepalive"):
      mqtt_opts['keepalive']=Config.getint("MQTT","keepalive")
  if Config.has_option("MQTT","SSL") and Config.getboolean("MQTT","SSL"):
      mqtt_opts['tls']={}
      for (k,v) in Config.items("MQTT_SSL"):
          mqtt_opts['tls'][k]=v

  if Config.has_option("MQTT","username"):
      mqtt_opts['auth']={'username':app.globalConfig.Config.get("MQTT","username"),'password':app.globalConfig.Config.get("MQTT","password")}


class ConfigClass(object):
  """ These are all Flask-Defined. Reference via app.config """
  Config = get_config()
  ServerHost = Config.get('General','ServerHost')
  ServerPort = Config.getint('General','ServerPort')
  Database = Config.get('General','Database')
  LogDatabase = Config.get('General','LogDatabase')
  AdminUser = Config.get('General','AdminUser')
  AdminPasswd = Config.get('General','AdminPassword')
  DeployType = Config.get('General','Deployment')
  DEBUG = Config.getboolean('General','Debug')
  SECRET_KEY = Config.get('General','SecretKey')

  # Flask-User Settings
  USER_APP_NAME = 'Basic'
  USER_PASSLIB_CRYPTCONTEXT_SCHEMES=['bcrypt']
  # Don;t want to include these, but it depends on them, so..
  USER_ENABLE_EMAIL = True        # Enable email authentication
  USER_ENABLE_USERNAME = False    # Disable username authentication
  USER_EMAIL_SENDER_NAME = USER_APP_NAME
  USER_EMAIL_SENDER_EMAIL = "noreply@example.com"

  # SQLAlchemy setting
  SQLALCHEMY_BINDS = {
          'main': "sqlite:///"+Database,
          'logs': "sqlite:///"+LogDatabase,
    }
  SQLALCHEMY_TRACK_MODIFICATIONS = False

  # Load Waiver system data from file
  waiversystem = {}
  waiversystem['Apikey'] = Config.get('Smartwaiver','Apikey')

def authbackend_init(name):
  app = Flask(name)
  app.config.from_object(__name__+'.ConfigClass')
  app.globalConfig = GlobalConfig()
  db.init_app(app)
  user_manager = UserManager(app, db, Member)
  return app
