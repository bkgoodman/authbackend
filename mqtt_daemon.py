#!/usr/bin/python2
"""
vim:tabstop=2:expandtab
MakeIt Labs Authorization System, v0.4

This is a daemon only used to log stuff via MQTT
"""

from authlibs.eventtypes import *
import sqlite3, re, time
from authlibs.db_models import db,  Role, UserRoles, Member, Resource, AccessByMember, Logs, Tool, UsageLog
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
from datetime import datetime
from authlibs.init import authbackend_init, createDefaultUsers




def get_mqtt_opts(app):
    opts={}
    ka=None
    base_topic = app.globalConfig.Config.get("MQTT","BaseTopic")
    host = app.globalConfig.Config.get("MQTT","BrokerHost")
    port = app.globalConfig.Config.getint("MQTT","BrokerPort")
    if app.globalConfig.Config.has_option("MQTT","keepalive"):
        opts['keepalive']=app.globalConfig.Config.getint("MQTT","keepalive")
    if app.globalConfig.Config.has_option("MQTT","SSL") and app.globalConfig.Config.getboolean("MQTT","SSL"):
        tls={}
        for (k,v) in app.globalConfig.Config.items("MQTT_SSL"):
            tls[k]=v
        opts['tls']=tls

    if app.globalConfig.Config.has_option("MQTT","username"):
        auth={'username':app.globalConfig.Config.get("MQTT","username"),'password':app.globalConfig.Config.get("MQTT","password")}
        opts['auth']=auth

    return (host,port,base_topic,opts)

def seconds_to_timespan(s):
    hours, remainder = divmod(s, 3600)
    minutes, seconds = divmod(remainder, 60)
    return '{:02}:{:02}:{:02}'.format(int(hours), int(minutes), int(seconds))

# The callback for when a PUBLISH message is received from the server.
# 2019-01-11 17:09:01.736307
#def on_message(msg):
def on_message(client,userdata,msg):
    tool_cache={}
    resource_cache={}
    member_cache={}
    if True: #try:
        with app.app_context():
            log=Logs()
            print "FROM WIRE",msg.topic,msg.payload
            message = json.loads(msg.payload)
            topic=msg.topic.split("/")

            # Is this a RATT status message?
            toolname=None
            member=None
            memberId=None
            toolId=None
            nodename=None
            nodeId=None
            resourceId=None
            log_event_type=None
            log_text=None

            # base_topic+"/control/broadcast/acl/update"
            if topic[0]=="ratt" and topic[1]=="control" and topic[2]=="broadcast" and topic[3]=="acl" and topic[4]=="update":
                print "CLEARING CACHE"
                tool_cache={}
                resource_cache={}
                member_cache={}
            elif topic[0]=="ratt" and topic[1]=="status":
                if topic[2]=="node":
                    t=Tool.query.filter(Tool.frontend==topic[3]).one()
                    toolname=t.name
                elif topic[2]=="tool":
                    toolname=topic[3]

            subt=topic[4]
            sst=topic[5]
            member=None
            if 'toolId' in message: toolId=message['toolId']
            if 'nodeId' in message: toolId=message['noolId']
            if 'toolname' in message: toolname=message['toolname']
            if 'nodename' in message: nodename=message['noolname']
            if 'member' in message: member=message['member']

            if toolname and toolname in tool_cache:
                toolId = tool_cache[toolname]['id']
                resourceId = tool_cache[toolname]['resource_id']
            elif toolname:
                t = db.session.query(Tool.id,Tool.resource_id).filter(Tool.name==toolname).first()
                if t:
                    tool_cache[toolname]={"id":t.id,"resource_id":t.resource_id}
                    toolId = tool_cache[toolname]['id']
                    resourceId = tool_cache[toolname]['resource_id']
            
            if member and member in member_cache:
                memberId = member_cache[member]
                print "CACHE",memberId,"FROM",member
            elif member:
                q = db.session.query(Member.id).filter(Member.member==member)
                m = q.first()
                print "QUERY MEMBER",q
                print "RETURNED",m.id
                if m:
                    print "CACHE",member,"=",m.id
                    member_cache[member]=m.id
                    memberId=m.id


            print "Tool",toolname,toolId,"Node",nodename,nodeId,"Member",member,memberId

            if subt=="wifi":
                    # TODO throttle these!
                    #log_event_type = RATTBE_LOGEVENT_SYSTEM_WIFI.id
                    pass
            elif subt=="system":
                if sst=="power":
                    state = message['state']  # lost | restored | shutdown
                    if state == "lost": log_event_type = RATTBE_LOGEVENT_SYSTEM_POWER_LOST.id
                    elif state == "restored": log_event_type = RATTBE_LOGEVENT_SYSTEM_POWER_RESTORED.id
                    elif state == "shutdown": log_event_type = RATTBE_LOGEVENT_SYSTEM_POWER_SHUTDOWN.id
                    else: 
                        log_event_type = RATTBE_LOGEVENT_SYSTEM_POWER_OTHER.id
                        log_tet = state
                        
                elif sst=="issue":
                    issue = message['issue'] # Text
                    log_event_type = RATTBE_LOGEVENT_TOOL_ISSUE.id
                    log_text = issue
            elif subt=="personality":
                if sst=="safety":
                    # member
                    reason = message['reason'] # Failure reason text
                    log_event_type = RATTBE_LOGEVENT_TOOL_SAFETY.id
                    log_text = reason
                elif sst=="activity":
                    # member
                    active = message['active'] # Bool
                    if active:
                        log_event_type = RATTBE_LOGEVENT_TOOL_ACTIVE.id
                    else:
                        log_event_type = RATTBE_LOGEVENT_TOOL_INACTIVE.id
                elif sst=="state":
                    phase = message['phase'] # ENTER, ACTIVE, EXIT 
                    state = message['state'] # Text
                elif sst=="lockout":
                    state = message['state'] # pending | locked | unlocked
                    if state=="pending": log_event_type = RATTBE_LOGEVENT_TOOL_LOCKOUT_PENDING.id
                    elif state=="locked": log_event_type = RATTBE_LOGEVENT_TOOL_LOCKOUT_LOCKED.id
                    elif state=="unlocked": log_event_type = RATTBE_LOGEVENT_TOOL_LOCKOUT_UNLOCKED.id
                    else: log_event_type=RATTBE_LOGEVENT_TOOL_LOCKOUT_OTHER.id
                    log_text = reason
                elif sst=="power":
                    powered = message['powered'].lower() == "True" # True or False
                    if powered:
                        log_event_type = RATTBE_LOGEVENT_TOOL_POWERON.id
                    else:
                        log_event_type = RATTBE_LOGEVENT_TOOL_POWEROFF.id
                elif sst=="login":
                    # member
                    usedPassword = False
                    if 'usedPassword' in message: usedPassword = message['usedPassword']
                    allowed = message['allowed'] # Bool

                    if allowed and usedPassword:
                        log_event_type = RATTBE_LOGEVENT_TOOL_LOGIN_COMBO.id
                    elif not allowed and usedPassword:
                        log_event_type = RATTBE_LOGEVENT_TOOL_PROHIBITED.id
                    elif allowed and not usedPassword:
                        log_event_type = RATTBE_LOGEVENT_TOOL_LOGIN.id
                    elif not allowed and not usedPassword:
                        log_event_type = RATTBE_LOGEVENT_TOOL_COMBO_FAILED.id

                    if 'error' in message:
                        error = message['error'] # Bool
                    else:
                        error = False
                    if 'errorText' in message:
                        errorText = message['errorText'] # text
                    else:
                        errorText=None

                    log_text = errorText

                elif sst=="logout":
                    print "LOGOUT"
                    log_event_type = RATTBE_LOGEVENT_TOOL_LOGOUT.id
                    reason = message['reason']
                    enabledSecs = message['enabledSecs']
                    activeSecs = message['activeSecs']
                    idleSecs = message['idleSecs']

                    log_text = "enabled {0} active {1} idle {2} - {3}".format(
                        seconds_to_timespan(enabledSecs),
                        seconds_to_timespan(activeSecs),
                        seconds_to_timespan(idleSecs),
                        reason)
                    usage= UsageLog()
                    usage.member_id = memberId
                    usage.tool_id = toolId
                    usage.resource_id = resourceId
                    usage.enabledSecs = enabledSecs
                    usage.activeSecs = activeSecs
                    usage.idleSecs = idleSecs
                    usage.timeReported = datetime.now()
                    db.session.add(usage)
                    db.session.commit()

            if log_event_type:
                logevent = Logs()
                logevent.member_id=memberId
                logevent.resource_id=resourceId
                logevent.tool_id=toolId
                logevent.time_reported=datetime.now()
                logevent.event_type = log_event_type
                logevent.message = log_text
                db.session.add(logevent)
                db.session.commit()
            print member,toolname,nodeId,log_event_type,log_text
            print
    else: # except BaseException as e:
        print "LOG ERROR",e,"PAYLOAD",msg.payload
        print "NOW4"

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument("--command",help="Special command",action="store_true")
    (args,extras) = parser.parse_known_args(sys.argv[1:])

    app=authbackend_init(__name__)

    with app.app_context():
      # The callback for when the client receives a CONNACK response from the server.
      (host,port,base_topic,opts) = get_mqtt_opts(app)
      while True:
          try:
            sub.callback(on_message, "ratt/#", hostname=host, port=port,**opts)
            sub.loop_forever()
            sub.loop_misc()
            time.sleep(1)
            msg = sub.simple("ratt/#", hostname=host,port=port,**opts)
            print("%s %s" % (msg.topic, msg.payload))
          except KeyboardInterrupt:    #on_message(msg)
            sys.exit(0)
          except:
            print "EXCEPT"
            time.sleep(1)


