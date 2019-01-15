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
from authlibs.db_models import db, User, Member

logging.basicConfig(stream=sys.stderr)



# Load general configuration from file

def get_config():
  defaults = {'ServerPort': 5000, 'ServerHost': '127.0.0.1'}
  Config = ConfigParser.ConfigParser(defaults)
  Config.read('makeit.ini')
  return Config

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
  SQLALCHEMY_DATABASE_URI = "sqlite:///"+Database
  SQLALCHEMY_TRACK_MODIFICATIONS = False

  # Load Waiver system data from file
  waiversystem = {}
  waiversystem['Apikey'] = Config.get('Smartwaiver','Apikey')

def authbackend_init(name):
  app = Flask(name)
  app.config.from_object(__name__+'.ConfigClass')
  app.globalConfig = GlobalConfig()
  db.init_app(app)
  user_manager = UserManager(app, db, User)
  return app
