#!/usr/bin/python2
"""
vim:tabstop=2:expandtab
MakeIt Labs Authorization System, v0.4

This is a daemon only used to log stuff via MQTT
"""

import sqlite3, re, time
from authlibs.db_models import db, User, Role, UserRoles, Member, Resource, AccessByMember
import argparse
from flask import Flask, request, session, g, redirect, url_for, \
	abort, render_template, flash, Response
from flask_user import current_user, login_required, roles_required, UserManager, UserMixin, current_app
from flask_sqlalchemy import SQLAlchemy
import ConfigParser,sys,os
import paho.mqtt.publish as mqtt_pub
import json
from datetime import datetime

# Load general configuration from file
defaults = {'ServerPort': 5000, 'ServerHost': '127.0.0.1'}
Config = ConfigParser.ConfigParser(defaults)
Config.read('makeit.ini')
ServerHost = Config.get('General','ServerHost')
ServerPort = Config.getint('General','ServerPort')
Database = Config.get('General','Database')
AdminUser = Config.get('General','AdminUser')
AdminPasswd = Config.get('General','AdminPassword')
DeployType = Config.get('General','Deployment')
DEBUG = Config.getboolean('General','Debug')

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

def create_app():
    # App setup
    app = Flask(__name__)
    app.config.from_object(__name__)
    app.secret_key = Config.get('General','SecretKey')
    return app


def get_mqtt_opts():
    opts={}
    ka=None
    base_topic = Config.get("MQTT","BaseTopic")
    host = Config.get("MQTT","BrokerHost")
    port = Config.getint("MQTT","BrokerPort")
    if Config.has_option("MQTT","keepalive"):
        opts['keepalive']=Config.getint("MQTT","keepalive")
    if Config.has_option("MQTT","SSL") and Config.getboolean("MQTT","SSL"):
        tls={}
        for (k,v) in Config.items("MQTT_SSL"):
            tls[k]=v
        opts['tls']=tls

    if Config.has_option("MQTT","username"):
        auth={'username':Config.get("MQTT","username"),'password':Config.get("MQTT","password")}
        opts['auth']=auth

    return (host,port,base_topic,opts)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument("--command",help="Special command",action="store_true")
    (args,extras) = parser.parse_known_args(sys.argv[1:])

    app = create_app()
    db.init_app(app)
    user_manager = UserManager(app, db, User)
    with app.app_context():
        print User.query.first()
        (host,port,base_topic,opts) = get_mqtt_opts()
            
        try:
              topic= base_topic+"/log/log"
              message= {
                        'member':'Brad.Goodman',
                        'resource':'laser',
                        'event_code':0,
                        'message':'Logged in',
                        'admin':None,
                        'when':str(datetime.now())
                      }

              mqtt_pub.single(topic, json.dumps(message), hostname=host,port=port,**opts)
              print "PUBLISHED "+topic,host,port,opts
        except BaseException as e:
                current_app.logger.warning("Publish fail "+str(e))

