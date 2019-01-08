#!/usr/bin/python2
"""
vim:tabstop=4:expandtab
MakeIt Labs Authorization System, v0.4
Author: bill.schongar@makeitlabs.com

A simple Flask-based system for managing Users, Resources and the relationships between them

Exposes both a UI as well as a few APIs for further integration.

Note: Currently all coded as procedural, rather than class-based because reasons. Deal.

TODO:
- Improved logging and error handling
- More input validation
- Check for any strings that need to be moved to INI file
- Consider Class-based approach
- Make more modular/streamlined
- Harden API security model (Allow OAuth, other?)
- More documentation
"""

import sqlite3, re, time
from flask import Flask, request, session, g, redirect, url_for, \
	abort, render_template, flash, Response
# NEwer login functionality
from flask_user import current_user, login_required, roles_required, UserManager, UserMixin, current_app
from flask_sqlalchemy import SQLAlchemy
#; older login functionality
#from flask.ext.login import LoginManager, UserMixin, login_required,  current_user, login_user, logout_user
from contextlib import closing
import pytz
import json
import pycurl, sys
import ConfigParser
import xml.etree.ElementTree as ET
from StringIO import StringIO
from authlibs import utilities as authutil
from authlibs import payments as pay
from authlibs import smartwaiver as waiver
from authlibs import google_admin as google
from authlibs import membership as membership
from json import dumps as json_dump
from json import loads as json_loads
from functools import wraps
import logging
logging.basicConfig(stream=sys.stderr)
import pprint
import paho.mqtt.publish as mqtt_pub
from datetime import datetime
from authlibs.db_models import db, User, Role, UserRoles, Member, Resource, MemberTag, AccessByMember, Blacklist, Waiver


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

# Load Waiver system data from file
waiversystem = {}
waiversystem['Apikey'] = Config.get('Smartwaiver','Apikey')

def create_app():
    # App setup
    app = Flask(__name__)
    app.config.from_object(__name__)
    app.secret_key = Config.get('General','SecretKey')
    return app

def connect_source_db():
    """Convenience method to connect to the globally-defined database"""
    con = sqlite3.connect("original.db",check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con

def connect_db():
    """Convenience method to connect to the globally-defined database"""
    con = sqlite3.connect(Database,check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con

def safestr(unsafe_str):
    """Sanitize input strings used in some operations"""
    keepcharacters = ('_','-','.')
    return "".join(c for c in unsafe_str if c.isalnum() or c in keepcharacters).rstrip()

def safeemail(unsafe_str):
    """Sanitize email addresses strings used in some oeprations"""
    keepcharacters = ('.','_','@','-')
    return "".join(c for c in unsafe_str if c.isalnum() or c in keepcharacters).rstrip()

def init_db():
    """Initialize database from SQL schema file if needed"""
    with closing(connect_db()) as db:
        with app.open_resource('flaskr.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()

def get_db():
    """Convenience method to get the current DB loaded by Flask, or connect to it if first access"""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = connect_db()
    return db

def get_source_db():
    db = getattr(g, '_source_database', None)
    if db is None:
        db = g._source_database = connect_source_db()
    return db

def query_source_db(query, args=(), one=False):
    """Convenience method to execute a basic SQL query against the current DB. Returns a dict unless optional args used"""
    cur = get_source_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv

def query_db(query, args=(), one=False):
    """Convenience method to execute a basic SQL query against the current DB. Returns a dict unless optional args used"""
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv

def execute_db(query):
    """Convenience method to execute a non-query SQL statement against the current DB."""
    cur = get_db().cursor()
    cur.execute(query)
    cur.close()

def createDefaultUsers(app):
    # Create default admin role and user if not present
    admin_role = Role.query.filter(Role.name=='Admin').first()
    if not admin_role:
        admin_role = Role(name='Admin')
    if not User.query.filter(User.email == AdminUser).first():
        user = User(email=AdminUser,password=user_manager.hash_password(AdminPasswd),email_confirmed_at=datetime.utcnow())
        app.logger.debug("ADD USER "+str(user))
        db.session.add(user)
        user.roles.append(admin_role)
        db.session.commit()
    # TODO - other default users?
# Start development web server

def process_source_table(table,columns):
        coldata={}
        for x in columns:
                coldata[x]=0
        rows= query_source_db("select * from {0};".format(table))
        for (i,x) in enumerate(rows):
            # print i,x
            for (ii,y) in enumerate(x):
                if y and y != "":
                    coldata[columns[ii]]+=1

        print table, coldata,"Total Rows",len(rows)

def get_slack_users():
        slackdata=json.load(open("../slackcli/allusers.txt"))
        slack_users={}
        discards=[]
        for x in slackdata['members']:
            u={}
            u['name']=x['name']
            if 'real_name' in x:
                #print x['name'],x['deleted'],x['is_app_user'],x['is_bot'],x['real_name']
                u['real_name']=x['real_name']
                #print u['real_name']
            else:
                #print x['name'],x['deleted'],x['is_app_user'],x['is_bot'],"NO REAL NAME"
                if 'real_name_normalized' in x:
                    #print x['real_name_normlized']
                    pass
                else:
                    print "NO REAL NAME FOR",x['name']
                pass
            if x['deleted']==False  and x['is_app_user']==False and x['is_bot'] == False and 'email' in x['profile']:
                u["email"]=x["profile"]["email"]
                if "first_name" in x['profile'] and "last_name" in x['profile']:
                    u["first_name"]=x["profile"]["first_name"]
                    u["last_name"]=x["profile"]["last_name"]
                else:
                    u["first_name"]=".".split(x["name"])[0].title()
                    u["last_name"]=".".split(x["name"])[-1].title()
                    u["first_name"]=x["name"].split(".")[0].title()
                    u["last_name"]=x["name"].split(".")[-1].title()
                u["phone"]=x["profile"]["phone"]
                u["real_name_normalized"]=x["profile"]["real_name_normalized"]
                u['name']=x['name']
                #print u['first_name'],u['last_name'],x['name']
                slack_users[x['name']]=u
            else:
                """
                print
                print "ERROR",x['name'],"was not migrated"
                print
                """
                discards.append(x['name'])
            
        #print "DISCARDS",discards
        #print "IMPORTS",len(slack_users)
        #for x in slack_users:
        #    print x,slack_users[x]
        return slack_users

if __name__ == '__main__':
    WRITE_DATABASE=False

    if WRITE_DATABASE:
        print """
        ******
        ****** WRITING DATABASE
        ******
        ****** PRESS CONTROL-C IF YOU DON'T WANT TO DESTROY IT!!!
        ******
        """
        time.sleep(5)

    app = create_app()
    db.init_app(app)
    user_manager = UserManager(app, db, User)
    with app.app_context():
        # Extensions like Flask-SQLAlchemy now know what the "current" app
        # is while within this block. Therefore, you can now run........
        db.create_all()
        if WRITE_DATABASE: createDefaultUsers(app)

        tables=[
        "accessbyid","logs","payments","waivers",
        "accessbymember","memberbycustomer","resources",
        "blacklist","members","subscriptions",
        "feespaid","members_Debug","tagsbymember"
        ]
        for t in tables:
            print "TABLE",t,"HAS", query_source_db("select COUNT(*) from {0};".format(t))[0][0],"ROWS"
                
        membercols=[
            'member',
            'alt_email',
            'firstname',
            'lastname',
            'phone',
            'plan',
            'updated_date',
            'access_enabled',
            'access_reason',
            'active',
            'nickname',
            'name',
            'created_date']

        process_source_table("members",membercols)
        resource_cols=[
            'name',
            'description',
            'owneremail',
            'last_updated'
        ]
        process_source_table("resources",resource_cols)

        accessbymember_cols =[
                'member',
                'resource', 
                'enabled',
                'updated_date',
                'level'
        ]
        process_source_table("accessbymember",accessbymember_cols)

        # CREATE TABLE accessbyid(resource,rfidtag,enabled,lastmodified);
        accessbyid_cols = [
            "resource","rfidtag","enabled","lastmodified"
        ]
        process_source_table("accessbyid",accessbyid_cols)

        # CREATE TABLE tagsbymember (member text, tagtype text, tagid text, updated_date text, tagname TEXT);
        tagsbymember_cols = [
            "member","tagtype","tagid","updated_date","tagname"
        ]
        process_source_table("tagsbymember",tagsbymember_cols)

                        

        """
            except BaseException as e:
                print
                print
                print "ERROR",x['name'],str(e)
                print
            """

        # Find odd slack users
        su = get_slack_users()
        for x in su:
            vv=x.split(".")
            if (len(vv)!=2): print x

        # Members to Slack IDs


        corrected_slack_ids={}
        slack_explicit_matches={}
        for x in open("explicit_slack_ids.txt").readlines():
            (a,b,c)=x.split()
            slack_explicit_matches[b]=c

        dbm = {}
        mc = ",".join(membercols)
        members = query_source_db("select "+mc+" from members;")
        match = {
                'no':0,
                'exact':0,
                'nodelim':0,
                'oddcase':0,
                'odddelim':0,
                'dotlast':0,
                'firstonly':0,
                'lastonly':0,
                'firstlast':0,
                'first0last':0,
                'explicit':0,
        }
        for x in  members:
            found = False
            if x[0] in su: 
                match['exact']+=1
                corrected_slack_ids[x[0]]=x[0]
                found=True
            if x[0] in slack_explicit_matches:
                match['explicit']+=1
                corrected_slack_ids[x[0]]=slack_explicit_matches[x[0]]
                found=True
            else:
                # case mismatch
                for yy in su:
                    if yy.lower() == x[0].lower():
                        match['oddcase']+=1
                        corrected_slack_ids[x[0]]=yy
                        found=True
            if not found:
                first=x[0].split(".")[0].lower()
                last=x[0].split(".")[-1].lower()
                for yy in su:
                    slack_first = su[yy]['first_name'].lower()
                    slack_last = su[yy]['last_name'].lower()
                    if yy.lower() == first+last:
                        match['nodelim']+=1
                        corrected_slack_ids[x[0]]=yy
                        found=True
                    if yy.lower() == first+"_"+last:
                        match['odddelim']+=1
                        corrected_slack_ids[x[0]]=yy
                        found=True
                    if (slack_first==first) and (slack_last==last):
                        match['firstlast']+=1
                        #print "PROBABLY",x[0],yy
                        # found=True Than's Mike Sullivan :(
                    if yy.lower() == first[0]+"."+last:
                        #print "DOTLAST POSSIBLY",x[0],yy
                        match['dotlast']+=1
                    if yy.lower() == first:
                        #print "FIRSTONLY POSSIBLY",x[0],yy
                        match['firstonly']+=1
                    if yy.lower() == last:
                        #print "LASTONLY POSSIBLY",x[0],yy
                        match['lastonly']+=1
                    if yy.lower().endswith(last):
                        #print "POSSIBLY",x[0],yy
                        match['lastonly']+=1
                    if (slack_first[0]==first[0]) and (slack_last==last):
                        match['first0last']+=1
                        #print "POSSIBLY",x[0],yy
            if not found:
                #print "No match for ",x[0]
                match['no']+=1
                
                

        print "Slack: ",match
        print "Loaded ",len(corrected_slack_ids),"Slack IDs"
            

        ##
        ## Okay build new "member" table..
        ##

        for x in  members:
            slack=None
            if x[0] in corrected_slack_ids:
                slack=corrected_slack_ids[x[0]]
            mem = Member()


            if slack:
                first=su[slack]['first_name']
                last=su[slack]['last_name']
                #print x[0],slack,first,last
            else:
                nm=x[0].split(".")

                if len(nm)==2:
                    first = nm[0]
                    last = nm[1]
                elif len(nm)==3:
                    first=nm[0]
                    last=nm[1]+nm[2]
                else:
                    first=""
                    last=""

            # 2019-01-03T18:35:22Z
            # 2017-06-12 13:44:39
            created=None
            if (x[12]):
                try:
                    created= datetime.strptime(x[12],"%Y-%m-%dT%H:%M:%SZ")
                    # TODO CONFIRT
                except BaseException as e:
                    print "ERROR",e
                    local = pytz.timezone ("America/New_York")
                    created= datetime.strptime(x[12],"%Y-%m-%d %H:%M:%S")
                    local_dt = local.localize(created, is_dst=None)
                    utc_dt = local_dt.astimezone(pytz.utc)

                mem.member = x[0]
                mem.email = x[0]+"@makeitlabs.com"
                mem.alt_email = x[1]
                mem.firstname = first
                mem.slack = slack
                mem.lastname = last
                mem.phone = x[4]
                mem.plan = x[5]
                mem.access_enabled = x[7]
                mem.access_reason = x[8]
                mem.active = x[9]
                mem.nickname = first
                mem.name = first+" "+last
                mem.time_created = created
                #print mem
                #print x[0],x[1],first,last,x[4],x[5],x[6],x[7],x[8],x[9],x[10],x[11],created
           
                if WRITE_DATABASE: db.session.add(mem)
        if WRITE_DATABASE: db.session.flush()
        if WRITE_DATABASE: db.session.commit()

        """
        mem.member = db.Column(db.String(50), unique=True)
        mem.email = db.Column(db.String(50))
        mem.alt_email = db.Column(db.String(50))
        mem.firstname = db.Column(db.String(50))
        mem.slack = db.Column(db.String(50))
        mem.lastname = db.Column(db.String(50))
        mem.phone = db.Column(db.String(50))
        mem.plan = db.Column(db.String(50))
        mem.updated_date = db.Column(db.DateTime())
        mem.access_enabled = db.Column(db.Integer())
        mem.access_reason = db.Column(db.String(50))
        mem.active = db.Column(db.Integer())
        mem.nickname = db.Column(db.String(50))
        mem.name = db.Column(db.String(50))
        mem.time_created = db.Column(db.DateTime(timezone=True), server_default=db.func.now())
        mem.time_updated = db.Column(db.DateTime(timezone=True), onupdate=db.func.now())
        """
        #
        # RESOURCES
        #

        dbr = {}
        mc = ",".join(resource_cols)
        print mc
        rez = query_source_db("select "+mc+" from resources;")

        for x in rez:
            #print x
            resources = Resource()
            resources.name = x[0]
            resources.description = x[1]
            resources.owneremail = x[2]
            #print resources
            if WRITE_DATABASE: db.session.add(resources)
        if WRITE_DATABASE: db.session.flush()
        if WRITE_DATABASE: db.session.commit()

        #
        # TAGS by member
        dbr = {}
        mc = ",".join(tagsbymember_cols)
        print mc
        recs = query_source_db("select "+mc+" from tagsbymember;")

        # "member","tagtype","tagid","updated_date","tagname"
        good=0
        bad=0
        for x in recs:
            newtag = MemberTag()
            mid = Member.query.filter(Member.member==x[0]).first()
            newtag.member_id=None
            if mid:
                newtag.member_id=mid.id
                good+=1
            else:
                #print "NO RECORD FOR",x
                bad+=1
            newtag.member=x[0]
            newtag.tag_type=x[1]
            newtag.tag_id=x[2]
            #newtag.updated_date
            newtag.tag_name=x[4]
            try:
                lastupdate= datetime.strptime(x[3],"%Y-%m-%d %H:%M:%S")
                local_dt = local.localize(lastupdate, is_dst=None)
            except:
                lastupdate= datetime.strptime(x[3],"%Y-%m-%d")
                local_dt = local.localize(lastupdate, is_dst=None)
            #print newtag,x,lastupdate
            if WRITE_DATABASE: db.session.add(newtag)
        if WRITE_DATABASE: db.session.flush()
        if WRITE_DATABASE: db.session.commit()

        print "FOBs migrated",good,"failed",bad

        ##
        ## AccessByMember
        ##

        # member
        # resource
        # enabled
        # updated_date
        # level
        mc = ",".join(accessbymember_cols)
        print mc
        recs = query_source_db("select "+mc+" from accessbymember;")
        good=0
        bad=0
        for x in recs:
            print "Access for ",x[0],x[1]
            acc = AccessByMember()
            mid = Member.query.filter(Member.member==x[0]).first()
            rid = Resource.query.filter(Resource.name==x[1]).first()
            if mid == None or rid == None:
                #print x,mid,rid
                bad+=1
            else:
                acc.member_id=mid.id
                acc.resource_id=rid.id
                good+=1
                acc.enabled=x[2]
                acc.level=0
                try:
                    acc.updated_date= datetime.strptime(x[3],"%Y-%m-%d %H:%M:%S")
                    local_dt = local.localize(lastupdate, is_dst=None)
                except:
                    # Sat Jan 21 11:46:19 2017
                    try:
                        acc.updated_date= datetime.strptime(x[3],"%a %b %d %H:%M:%S %Y")
                        local_dt = local.localize(lastupdate, is_dst=None)
                    except:
                        acc.updated_date= datetime.strptime(x[3],"%Y-%m-%d")
                        local_dt = local.localize(lastupdate, is_dst=None)
                if WRITE_DATABASE: db.session.add(acc)
                if WRITE_DATABASE: db.session.flush()
        if WRITE_DATABASE: db.session.commit()
        print "AccessByMember migrated",good,"failed",bad


        ##
        ## Blacklist
        ##

        mc = ",".join(['entry','entrytype','reason','updated_date'])
        print mc
        recs = query_source_db("select "+mc+" from blacklist;")
        for x in recs:
            print x
            bl = Blacklist()
            bl.entry=x[0]
            bl.entrytype=x[1]
            bl.reason=x[2]
            try:
                bl.updated_date= datetime.strptime(x[3],"%Y-%m-%d %H:%M:%S")
                local_dt = local.localize(lastupdate, is_dst=None)
            except:
                # Sat Jan 21 11:46:19 2017
                try:
                    bl.updated_date= datetime.strptime(x[3],"%a %b %d %H:%M:%S %Y")
                    local_dt = local.localize(lastupdate, is_dst=None)
                except:
                    bl.updated_date= datetime.strptime(x[3],"%Y-%m-%d")
                    local_dt = local.localize(lastupdate, is_dst=None)
            if WRITE_DATABASE: db.session.add(bl)
        if WRITE_DATABASE: db.session.flush()
        if WRITE_DATABASE: db.session.commit()

        ##
        ## Waivers
        ##

        mc = ",".join(['waiverid','firstname','lastname','email','created_date'])
        print mc
        recs = query_source_db("select "+mc+" from waivers;")
        good=0
        bad=0
        for x in recs:
            mid = Member.query.filter(Member.firstname==x[1]).filter(Member.lastname==x[2]).first()
            w = Waiver()
            if mid:
                #print "FOUND MATCH",mid.first().firstname,mid.first().lastname,x[1],x[2]
                #print "FOUND MATCH",mid.firstname,mid.lastname,x[1],x[2],mid.id
                w.memberid=mid.id
                good+=1
            else:
                bad+=1
            w.firstname=x[1]
            w.lastname=x[2]
            w.waiver_id=x[0]
            w.email=x[3]
            try:
                w.created_date= datetime.strptime(x[4],"%Y-%m-%d %H:%M:%S")
                local_dt = local.localize(lastupdate, is_dst=None)
            except:
                # Sat Jan 21 11:46:19 2017
                try:
                    w.created_date= datetime.strptime(x[4],"%a %b %d %H:%M:%S %Y")
                    local_dt = local.localize(lastupdate, is_dst=None)
                except:
                    w.created_date= datetime.strptime(x[4],"%Y-%m-%d")
                    local_dt = local.localize(lastupdate, is_dst=None)
            found=False
            if WRITE_DATABASE: db.session.add(w)
        if WRITE_DATABASE: db.session.flush()
        if WRITE_DATABASE: db.session.commit()
        print "waivers migrated",good,"nomatches",bad

    if not WRITE_DATABASE:
        print """
        ******
        ****** WRITING DATABASE WAS DISABLED
        ******
        """

