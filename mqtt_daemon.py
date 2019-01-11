#!/usr/bin/python2
"""
vim:tabstop=2:expandtab
MakeIt Labs Authorization System, v0.4

This is a daemon only used to log stuff via MQTT
"""

import sqlite3, re, time
from authlibs.db_models import db, User, Role, UserRoles, Member, Resource, AccessByMember, Logs
import argparse
from flask import Flask, request, session, g, redirect, url_for, \
	abort, render_template, flash, Response
from flask_user import current_user, login_required, roles_required, UserManager, UserMixin, current_app
from flask_sqlalchemy import SQLAlchemy
from authlibs import utilities as authutil
import json
import ConfigParser,sys,os
import paho.mqtt.client as mqtt
import paho.mqtt.subscribe as sub

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

# The callback for when a PUBLISH message is received from the server.
# 2019-01-11 17:09:01.736307
def on_message(msg):
    print msg
    if True: #try:
        with app.app_context():
            log=Logs()
            message = json.loads(msg.payload)
            if ('member_id' in message):
                log.member_id = message['member_id']
            elif 'member' in message:
                log.member_id = Member.query.filter(Member.member==message['member']).with_entities(Member.id)
            if ('resource_id' in message):
                log.resource_id = message['resource_id']
            elif 'resource' in message:
                log.resource_id = Resource.query.filter(Resource.name==message['resource']).with_entities(Resource.id)
            if ('admin_id' in message):
                log.doneby = message['admin_id']
            elif 'admin' in message:
                log.doneby = User.query.filter(User.email==message['admin']).with_entities(User.id)
            if 'when' in message:
                log.time_reported = authutil.parse_datetime(message['when'])
            if 'event_code' in message:
                log.event_code = message['event_code']
            db.session.add(log)
            db.session.commit()
        print log
    else: # except BaseException as e:
        print "LOG ERROR",e,"PAYLOAD",msg.payload
        print "NOW4"

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument("--command",help="Special command",action="store_true")
    (args,extras) = parser.parse_known_args(sys.argv[1:])

    app = create_app()
    db.init_app(app)
    user_manager = UserManager(app, db, User)
    with app.app_context():
      print User.query.first()
      # The callback for when the client receives a CONNACK response from the server.
      (host,port,base_topic,opts) = get_mqtt_opts()
      """
      def on_connect(client, userdata, flags, rc):
          print("Connected with result code "+str(rc))

          # Subscribing in on_connect() means that if we lose the connection and
          # reconnect then subscriptions will be renewed.
          #client.subscribe("$SYS/#")

          client.subscribe("ratt/log/#")

      client = mqtt.Client()
      client.on_connect = on_connect
      client.userdata = {'app':app}
      client.on_message = on_message

      print "CONNECING"
      client.connect(host,port,60)
      print "CONNECTED"

      # Blocking call that processes network traffic, dispatches callbacks and
      # handles reconnecting.
      # Other loop*() functions are available that give a threaded interface and a
      # manual interface.
      client.loop_forever()
      """
      while True:
        if True: #try:
            msg = sub.simple("ratt/log/#", hostname=host,port=port,**opts)
            print("%s %s" % (msg.topic, msg.payload))
            on_message(msg)
        else: #except:
            time.sleep(1)


