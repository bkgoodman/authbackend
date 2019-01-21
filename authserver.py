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
	abort, render_template, flash, Response, Markup
# NEwer login functionality
import logging
from werkzeug.contrib.fixers import ProxyFix
from flask_user import current_user, login_required, roles_required, UserManager, UserMixin, current_app
#from flask_oauth import OAuth
from flask_login import logout_user, login_user
from authlibs import eventtypes
from flask_sqlalchemy import SQLAlchemy
#; older login functionality
#from flask.ext.login import LoginManager, UserMixin, login_required,  current_user, login_user, logout_user
from contextlib import closing
import pycurl, sys
import ConfigParser
import xml.etree.ElementTree as ET
from authlibs.eventtypes import get_events
from StringIO import StringIO
from authlibs.init import authbackend_init, get_config, createDefaultUsers
from authlibs import cli
from authlibs import utilities as authutil
from authlibs import payments as pay
from authlibs import smartwaiver as waiver
from authlibs import google_admin as google_admin
from authlibs import membership as membership
from json import dumps as json_dump
from json import loads as json_loads
from functools import wraps
import logging
logging.basicConfig(stream=sys.stderr)
import pprint
import paho.mqtt.publish as mqtt_pub
from datetime import datetime
from authlibs.db_models import db, Role, UserRoles, Member, Resource, AccessByMember, Tool, Logs, UsageLog, Subscription, Waiver, MemberTag, ApiKey
import argparse
from authlibs.init import GLOBAL_LOGGER_LEVEL
from flask_dance.contrib.google import  google 
from flask_dance.consumer import oauth_authorized
import google_oauth

waiversystem = {}
waiversystem['Apikey'] = get_config().get('Smartwaiver','Apikey')

logger = logging.getLogger(__name__)
logger.setLevel(GLOBAL_LOGGER_LEVEL)
    
# RULE - only call this from web APIs - not internal functions
# Reason: If we have calls or scripts that act on many records,
# we probably shouldn't generate a million messages
def kick_backend():
    try:
      topic= app.globalConfig.mqtt_base_topic+"/control/broadcast/acl/update"
      mqtt_pub.single(topic, "update", hostname=app.globalConfig.mqtt_host,port=app.globalConfig.mqtt_port,**app.globalConfig.mqtt_opts)
    except BaseException as e:
        logger.debug("MQTT acl/update failed to publish: "+str(e))

def create_app():
    # App setup
    app = Flask(__name__)
    app.config.from_object(__name__)
    app.secret_key = Config.get('General','SecretKey')
    return app


# Login mechanism, using Flask-Login
# ;older login functionality
#login_manager = LoginManager()
#login_manager.init_app(app)
#login_manager.login_view = "login"


# Flask-Login use this to reload the user object from the user ID stored in the session

def check_auth(username, password):
    """This function is called to check if a username /
    password combination is valid.
    """
    if password == "" or password is None or not Member.query.filter_by(email=username,api_key=password).first():
        return False
    else:
        return True

def check_api_access(username,password):
    if password == "" or password is None or not ApiKey.query.filter_by(username=username,password=password).first():
        return False
    else:
        return True

def authenticate():
    """Sends a 401 response that enables basic auth"""
    return Response(
    'Could not verify your access level for that URL.\n'
    'You have to login with proper credentials', 401,
    {'WWW-Authenticate': 'Basic realm="Login Required"'})

def error_401():
    """Sends a 401 response that enables basic auth"""
    return Response(
    'What the hell. .\n'
    'You have to login with proper credentials', 401,
    {'WWW-Authenticate': 'Basic realm="Login Required"'})

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth:
            return error_401()
        if not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

# This is to allow non "member" accounts in via API
# NOTE we are decorating the one we are importing from flask-user
def api_only(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth:
            return error_401()
        if not check_api_access(auth.username, auth.password):
            return authenticate() # Send a "Login required" Error
        g.apikey=auth.username
        return f(*args, **kwargs)
    return decorated


def connect_db():
    """Convenience method to connect to the globally-defined database"""
    con = sqlite3.connect(app.globalConfig.Database,check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con

def safestr(unsafe_str):
    """Sanitize input strings used in some operations"""
    keepcharacters = ('_','-','.','@')
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

def clearAccess(mid):
    """Remove all existing access permissions for a given, known safe member id"""
    sqlstr = "DELETE from accessbymember where member_id = (SELECT m.id FROM members m WHERE member='%s');" % mid
    execute_db(sqlstr)
    get_db().commit()

def addAccess(mid,access):
    """Add access permissions from a list for a given, known safe member id"""
    # perms = []
    # Member.query.filter(Member.member=="0").first()
    uid = Member.query.filter(Member.member==mid).with_entities(Member.id)
    for resource in access:
        #print("Adding %s for %s" % (resource,mid))
        acc = AccessByMember()
        acc.member_id=uid
        acc.resource_id = Resource.query.filter(Resource.name==resource).with_entities(Resource.id)
        db.session.add(acc)
    db.session.commit()
    db.session.flush()

    
    """
    cur = get_db().cursor()
    cur.executemany('INSERT into accessbymember (resource,member,enabled,updated_date) VALUES (?,?,?,?)', perms)
    get_db().commit()
    """

def expireMember(memberid):
    """Mark a user inactive due to expiration"""
    # TODO - Determine if we should "disable" user as well
    # TODO- Make a batch operation using a join?
    m = safestr(memberid)
    sqlstr = "update members set active='false' where member='%s'" % m
    execute_db(sqlstr)
    get_db().commit()
    kick_backend()

def unexpireMember(memberid):
    """Mark a user active"""
    # TODO - Make this a batch operation?
    m = safestr(memberid)
    sqlstr = "update members set active='true' where member='%s'" % m
    execute_db(sqlstr)
    get_db().commit()
    kick_backend()

def _expirationSync():
    """Make sure all expirations match what's in the Payments database"""
    sqlstr = "update members set active='true',updated_date=DATETIME('now') where member in (select member from payments where expires_date < date('now'))"
    execute_db(sqlstr)
    get_db().commit()
    kick_backend()

def _createMember(m):
    """Add a member entry to the database"""
    sqlstr = "Select member from members where member = '%s'" % m['memberid']
    members = query_db(sqlstr)
    if members:
        return {'status': 'error','message':'That User ID already exists'}
    else:
        sqlstr = """insert into members (member,firstname,lastname,phone,plan,nickname,access_enabled,active)
                    VALUES ('%s','%s','%s','%s','','%s',0,0)
                 """ % (m['memberid'],m['firstname'],m['lastname'],m['phone'],m['nickname'])
        execute_db(sqlstr)
        get_db().commit()
    return {'status':'success','message':'Member %s was created' % m['memberid']}
    kick_backend()

def _createResource(r):
    """Add a resource to the database"""
    sqlstr = """insert into resources (name,description,owneremail)
            values ('%s','%s','%s')""" % (r['name'],r['description'],r['owneremail'])
    execute_db(sqlstr)
    get_db().commit()
    #TODO: Catch errors, etc
    return {'status':'success','message':'Resource successfully added'}

def _get_resources():
	sqlstr = "SELECT name, owneremail, description from resources"
	return query_db(sqlstr)

def _clearPaymentData(paytype):
    """Remove all payment data for the configured paysystem type from the payments table"""
    sql = "delete from payments where paysystem= '%s'" % paytype
    execute_db(sql)
    get_db().commit()

def _addPaymentData(subs,paytype):
    """From a JSON list of subscribers, add entries to the Payments table"""
    users = []
    # TEMP - only blacklisting old, unpurgeable records for now
    blacklist = query_db("select entry from blacklist")
    bad = []
    for b in blacklist:
        bad.append(b['entry'])
    for sub in subs:
        if sub['customerid'] in bad:
            print "BLACKLIST: IGNORING CUSTOMERID %s for %s" % (sub['customerid'],sub['userid'])
        else:
            users.append((sub['userid'],sub['email'],'pinpayments',sub['membertype'],sub['customerid'],sub['created'],sub['expires'],sub['updatedon'],time.strftime("%c")))
    cur = get_db().cursor()
    cur.executemany('INSERT into payments (member,email,paysystem,plan,customerid,created_date,expires_date,updated_date,checked_date) VALUES (?,?,?,?,?,?,?,?,?)', users)
    get_db().commit()
    kick_backend()

def _getResourceUsers(resource):
    """Given a Resource, return all users, their tags, and whether they are allowed or denied for the resource"""
    # Also provides some basic logic on various date fields to simplify later processing
    # - this could be done with raw calcs on the dates, if future editors are less comfortable with the SQL syntaxes used
	# Note: The final left join is to account for "max(expires_date)" equivalence without neededing a subquery
	# - yes, it's kind of odd, but it works

    sqlstr = """select t.member_id,t.tag_ident,m.plan,m.nickname,/*l.last_accessed,*/m.access_enabled as enabled, m.access_reason as reason,s.expires_date,a.resource_id,
        (case when a.resource_id is not null then 'allowed' else 'denied' end) as allowed,
        (case when s.expires_date < Datetime('now','-14 day') then 'true' else 'false' end) as past_due,
        (case when s.expires_date < Datetime('now') AND s.expires_date > Datetime('now','-13 day') then 'true' else 'false' end) as grace_period,
        (case when s.expires_date < Datetime('now','+2 day') then 'true' else 'false' end) as expires_soon,
        (case when a.level is not null then a.level else '0' end) as level,
        m.member, /* BKG */
        NULL as last_accessed
        from tags_by_member t join members m on t.member=m.member
        left outer join accessbymember a on a.member_id=t.member_id and a.resource_id=
              (SELECT id FROM resources WHERE name ="%s")
        left outer join subscriptions s on lower(s.name)=lower(m.stripe_name) and s.email=m.alt_email
        left join subscriptions s2 on lower(s.name)=lower(s2.name) and s.expires_date < s2.expires_date where s2.expires_date is null
        group by t.tag_ident;""" % (resource)
    
    """ REMOVED:
        /*  left outer join (select member,MAX(event_date) as last_accessed from logs where resource_id='%s' group by member) l on t.member = l.member */
    """
    users = query_db(sqlstr)
    return users


def getAccessControlList(resource):
    """Given a Resource, return what tags/users can/cannot access a reource and why as a JSON structure"""
    users = _getResourceUsers(resource)
    jsonarr = []
    resource_rec = Resource.query.filter(Resource.name==resource).first()
    if resource_rec is None or not resource_rec.info_text:
        resource_text = "See the Wiki for training information and resource manager contact info."
        if resource_rec and resource_rec.info_url:
            resrouce_text += " "+resource_rec.info_url
    else:   
        resource_text = resource_rec.info_text
    c = {'board': "Contact board@makeitlabs.com with any questions.",
         'orientation': 'Orientation is every Thursday at 7pm, or contact board@makeitlabs to schedule a convenient time',
         'resource': "See the Wiki for training information and resource manager contact info."}
    # TODO: Resource-specific contacts?
    # Now that we know explicit allowed/denied per resource, provide an message
    for u in users:
        warning = ""
        allowed = u['allowed']
        if u['past_due'] == 'true':
            warning = "Your membership expired (%s) and the grace period for access has ended. %s" % (u['expires_date'],c['board'])
            allowed = 'false'
        elif u['enabled'] == 0:
            if u['reason'] is not None:
                # This indicates an authorized admin has a specific reason for denying access to ALL resources
                warning = "This account has been disabled for a specific reason: %s. %s" % (u['reason'],c['board'])
            else:
                warning = "This account is not enabled. It may be newly added and not have a waiver on file. %s" % c['board']
            allowed = 'false'
        elif u['allowed'] == 'denied':
            # Special 'are you oriented' check
            if resource == 'frontdoor':
                warning = "You have a valid membership, but you must complete orientation for access. %s" % c['orientation']
            else:
                warning = "You do not have access to this resource. %s" % c['resource']
        elif u['grace_period'] == 'true':
            warning = """Your membership expired (%s) and you are in the temporary grace period. Correct this
            as soon as possible or you will lose all access! %s""" % (u['expires_date'],c['board'])
        #print dict(u)
        hashed_tag_id = authutil.hash_rfid(u['tag_ident'])
        jsonarr.append({'tagid':hashed_tag_id,'tag_ident':u['tag_ident'],'allowed':allowed,'warning':warning,'member':u['member'],'nickname':u['nickname'],'plan':u['plan'],'last_accessed':u['last_accessed'],'level':u['level']})
    return json_dump(jsonarr)


def _deactivateMembers():
    """Mark all users as inactive, to ensure we catch any that have been removed from Payments table"""
    sqlstr = "update members set active='false', updated_date=Datetime('now')"
    execute_db(sqlstr)
    get_db().commit()
    kick_backend()

def _syncMemberPlans():
    """Update Members table with currently paid-for plan from Payments"""
    sqlstr = """update members set plan = (select plan from payments where members.member=payments.member)
            where member in (select member from payments)"""
    execute_db(sqlstr)
    get_db().commit()
    kick_backend()

def _activatePaidMembers():
    """Set users who are not expired to active state"""
    # This will be problematic if users somehow have two entries in payments- manual and other
    sqlstr = """update members set active='true', updated_date=Datetime('now')
            where member in (select member from payments where expires_date > Datetime('now'))"""
    execute_db(sqlstr)
    get_db().commit()
    kick_backend()

def _updateMembersFromPayments(subs):
    """Bring Members table and up to date with latest user payment information. Requires Subscriber dict"""
    addMissingMembers(subs)
    _deactivateMembers()
    _syncMemberPlans()
    _activatePaidMembers()
    kick_backend()
    return True

def _updatePaymentsData():
    """Get the latest Payment system data and update Payments table. Return subscriber data structure."""
    for m in range:
      code

    subs = pay.getSubscriptions(paysystem)
    fsubs = pay.filterSubscribers(subs)
    _clearPaymentData('pinpayments')
    _addPaymentData(fsubs['valid'],'pinpayments')
    return fsubs

def add_member_tag(mid,ntag,tag_type,tag_name):
    """Associate a tag with a Member, given a known safe set of values"""
    sqlstr = "select tag_ident from tags_by_member where tag_ident = '%s' and tag_type = '%s'" % (ntag,tag_type)
    etags = query_db(sqlstr)
    if not etags:
        sqlstr = """insert into tags_by_member (member,tag_ident,tag_name,tag_type,updated_date)
                    values ('%s','%s','%s','%s',DATETIME('now'))""" % (mid,ntag,tag_name,tag_type)
        execute_db(sqlstr)
        get_db().commit()
        kick_backend()
        return True
    else:
        return False

def getDataDiscrepancies():
    """Extract some commonly used statistics about data not matching"""
    # Note" SQLLIte does not support full outer joins, so we have some duplication of effort...
    stats = {}
    sqlstr = """select m.member,m.active,m.plan,p.expires_date,p.updated_date from members m
            left outer join payments p on p.member=m.member where p.member is null order by m.member"""
    stats['members_nopayments'] = query_db(sqlstr)
    sqlstr = """select p.member,p.email,a.member from payments p left outer join accessbymember a
            on p.member=a.member where a.member is null and p.expires_date > Datetime('now') order by p.member"""
    stats['paid_noaccess'] = query_db(sqlstr)
    sqlstr = """select p.member,m.member from payments p left outer join members m on p.member=m.member
        where m.member is null"""
    stats['payments_nomembers'] = query_db(sqlstr)
    sqlstr = """select a.member from accessbymember a left outer join members m on a.member=m.member
            where m.member is null and a.member is not null group by a.member"""
    stats['access_nomembers'] = query_db(sqlstr)
    sqlstr = """select distinct(resource) as resource from accessbymember where resource not in (select name from resources)"""
    stats['access_noresource'] = query_db(sqlstr)
    sqlstr = "select DISTINCT(member) from tags_by_member where member not in (select member from members) order by member"
    stats['tags_nomembers'] = query_db(sqlstr)
    sqlstr = """select DISTINCT(a.member), p.expires_date from accessbymember a join payments p on a.member=p.member where
            p.expires_date < Datetime('now')"""
    stats['access_expired'] = query_db(sqlstr)
    sqlstr = """select member,expires_date from payments where expires_date > Datetime('now','-60 days')
                and expires_date < Datetime('now')"""
    stats['recently_expired'] = query_db(sqlstr)
    sqlstr = "select member,expires_date,customerid,count(*) from payments group by member having count(*) > 1"
    stats['duplicate_payments'] = query_db(sqlstr)
    return stats

def getLastWaiverId():
    """Retrieve the most recently created (last) waiver from the database"""
    sqlstr = "select waiverid from waivers order by created_date desc limit 1"
    w = query_db(sqlstr,"",True)
    return w['waiverid']

def _addWaivers(waiver_list):
    """Add list-based Waiver data into the waiver table in the database"""
    new_waivers = []
    for w in waiver_list:
        new_waivers.append((w['waiver_id'],w['email'],w['firstname'],w['lastname'],w['created_date']))
    if len(new_waivers) > 0:
        cur = get_db().cursor()
        cur.executemany('INSERT into waivers (waiverid,email,firstname,lastname,created_date) VALUES (?,?,?,?,?)', new_waivers)
        get_db().commit()
    return len(new_waivers)

def addNewWaivers():
    """Check the DB to get the most recent waiver, add any new ones, return count added"""
    last_waiverid = getLastWaiverId()
    waiver_dict = {'api_key': waiversystem['Apikey'],'waiver_id': last_waiverid}
    waivers = waiver.getWaivers(waiver_dict)
    return _addWaivers(waivers)


########
# Request filters
########

'''
@app.before_request
def before_request():
	#g.db = connect_db()
    pass

# TODO : Change this to app.teardown_appcontext so we don't keep closing the DB? Ramifications?
@app.teardown_request
def teardown_request(exception):
	#db = getattr(g,'db',None)
	#if db is not None:
		#db.close()
    pass
'''

########
# Routes
########

def testdata():
    text="""
    From Reqest: {0}
    Name: {1} 
    Email: {2}
    Authenticated {3}
    Active {4}
    Anonymous {5}
    ID  {6}
    """.format(request,current_user.member,current_user.email,current_user.is_authenticated,
            current_user.is_active,
            current_user.is_anonymous,
            current_user.get_id(),
            )
    return text, 200, {'Content-type': 'text/plain'}
def create_routes():
    @app.route('/whoami')
    @app.route('/test/anyone')
    def TestAnyone():
        return testdata()

    
    @app.route('/test/std')
    @login_required
    def TestStd():
        return testdata()

    @app.route('/test/oauth')
    #@google.authorization_required
    def TestOauth():
        return testdata()

    # THIS IS THE WRONG PAGE
    # Flask login uses /user/sign-in
    @app.route('/login')
    def login():
       return render_template('login.html')

    # BKG LOGIN CHECK - when do we use thigs?
    # This is from old flask-login module??
    @app.route('/login/check', methods=['post'])
    def login_check():
        """Validate username and password from form against static credentials"""
        user = Member.query.filter(Member.member.ilike(request.form['username'])).one_or_none()
        if not user or not  user.password:
            # User has no password - make the use oauth
            return redirect(url_for('google.login'))
        if (user and current_app.user_manager.verify_password( request.form['password'],user.password)):
            login_user(user)
        else:
            flash('Username or password incorrect')
            return redirect(url_for('login'))

        return redirect(url_for('index'))

    @app.route('/logout')
    @login_required
    def logout():
       """Seriously? What do you think logout() does?"""
       logout_user()
       flash("Thanks for visiting, you've been logged out.")
       return redirect(url_for('login'))

    @app.route("/index")
    @app.route('/')
    @login_required
    def index():
       """Main page, redirects to login if needed"""
       return render_template('index.html')

    @app.route('/search',methods=['GET','POST'])
    @login_required
    def search_members():
       """Takes input of searchstr from form, displays matching member list"""
       if 'searchstr' in request.form:
           searchstr = safestr(request.form['searchstr'])
       elif 'searchstr' in request.values:
           searchstr = safestr(request.values['searchstr'])

    
       members = membership.searchMembers(searchstr)
       return render_template('members.html',members=members,searchstr=searchstr)

    # resource is a DB model resource
    def getResourcePrivs(resource=None,member=None,resourcename=None,memberid=None):
        if resourcename:
            resource=Resource.query.filter(Resource.name==resourcename).one()
        if not member and not memberid:
            member=current_user
        p = AccessByMember.query.join(Resource,((Resource.id == resource.id) & (Resource.id == AccessByMember.resource_id))).join(Member,((AccessByMember.member_id == member.id) & (Member.id == member.id))).one_or_none()
        if p:
            return p.level
        else:
            return -1
        return 0


    #----------
    #
    # Brad's test stuff
    #
    #------------

    @app.route('/test', methods=['GET'])
    def bkgtest():
        names=['frontdoor','woodshop','laser']
        result={}
        for n in names:
            #result[n]=getResourcePrivs(Resource.query.filter(Resource.name==n).one())
            result[n]=getResourcePrivs(resourcename=n)
        return json_dump(result,indent=2), 200, {'Content-type': 'application/json'}

    @app.route('/admin', methods=['GET'])
    @login_required
    @roles_required('Admin')
    def admin_page():
        roles=Role.query.all()
        admins =Member.query.join(UserRoles,UserRoles.member_id == Member.id).join(Role,Role.id == UserRoles.role_id)
        admins = admins.add_column(Role.name).group_by(Member.member).all()
        roles=[]
        for x in admins:
            roles.append({'member':x[0],'role':x[1]})

        privs=AccessByMember.query.filter(AccessByMember.level>0).join(Member,Member.id==AccessByMember.member_id)
        privs = privs.join(Resource,Resource.id == AccessByMember.resource_id)
        privs = privs.add_columns(Resource.name,AccessByMember.level,Member.member)
        privs = privs.all()
        p=[]
        for x in privs:
            print "MEMBER",x[3]
            p.append({'member':x[3],'resource':x[1],'priv':AccessByMember.ACCESS_LEVEL[int(x[2])]})

        return render_template('admin_page.html',privs=p,roles=roles)
    # --------------------------------------
    # Member viewing and editing functions
    # Routes
    #  /members : Show (HTTP GET - members()), Create new (HTTP POST - member_add())
    #  /<memberid> - Show (HTTP GET - member_show()), Create new (HTTP POST - member_add())
    #  /<memberid>/access - Show current access and interface to change (GET), Change access (POST)
    #  /<memberid>/tags - Show tags associated with user (GET), Change tags (POST)
    #  /<memberid>/edit - Show current user base info and interface to adjust (GET), Change existing user (POST)
    # --------------------------------------

    @app.route('/members', methods = ['GET'])
    @login_required
    def members():
      members = {}
      return render_template('members.html',members=members)

    @app.route('/members', methods= ['POST'])
    @login_required
    def member_add():
        """Controller method for POST requests to add a user"""
        member = {}
        mandatory_fields = ['firstname','lastname','memberid','plan','payment']
        optional_fields = ['alt_email','phone','nickname']
        print request
        for f in mandatory_fields:
            member[f] = ''
            if f in request.form:
                member[f] = request.form[f]
            if member[f] == '':
                flash("Error: One or more mandatory fields not filled out")
                return redirect(url_for('members'))
        for f in optional_fields:
            member[f] = ''
            if f in request.form:
                member[f] = request.form[f]
        result = _createMember(member)
        flash(result['message'])
        if result['status'] == "success":
            return redirect(url_for('member_show',id=member['memberid']))
        else:
            return redirect(url_for('members'))

    # memberedit
    @app.route('/members/<string:id>/edit', methods = ['GET','POST'])
    @login_required
    def member_edit(id):
        mid = safestr(id)
        member = {}

        if request.method=="POST" and 'Unlink' in  request.form:
            s = Subscription.query.filter(Subscription.membership==request.form['membership']).one()
            s.member_id = None
            db.session.commit()
            btn = '''<form method="POST">
                    <input type="hidden" name="member_id" value="%s" />
                    <input type="hidden" name="membership" value="%s" />
                    <input type="submit" value="Undo" name="Undo" />
                    </form>''' % (request.form['member_id'],request.form['membership'])
            flash(Markup("Unlinked. %s" % btn))
        elif 'Undo' in request.form:
            # Relink cleared member ID
            s = Subscription.query.filter(Subscription.membership == request.form['membership']).one()
            s.member_id = request.form['member_id']
            db.session.commit()
            flash ("Undone.")
        elif request.method=="POST" and 'SaveChanges' in  request.form:
            flash ("Changes Saved (Please Review!)")
            m=Member.query.filter(Member.member==mid).first()
            f=request.form
            m.firstname= f['firstname']
            m.lastname= f['lastname']
            if f['phone'] == "None" or f['phone'].strip() == "":
                m.phone=None
            else:
              m.phone= f['phone']
            m.slack= f['slack']
            m.alt_email= f['alt_email']
            db.session.commit()
            
        #(member,subscription)=Member.query.outerjoin(Subscription).filter(Member.member==mid).first()
        member=db.session.query(Member,Subscription)
        member = member.outerjoin(Subscription).outerjoin(Waiver).filter(Member.member==mid)
        (member,subscription) = member.one()
        return render_template('member_edit.html',member=member,subscription=subscription)


    @app.route('/members/<string:id>', methods = ['GET'])
    @login_required
    def member_show(id):
       """Controller method to Display or modify a single user"""
       #TODO: Move member query functions to membership module
       access = {}
       mid = safestr(id)
       member=db.session.query(Member,Subscription)
       member = member.outerjoin(Subscription).outerjoin(Waiver).filter(Member.member==mid)
       (member,subscription) = member.one()
     
       access=db.session.query(Resource).outerjoin(AccessByMember).outerjoin(Member)
       access = access.filter(Member.member == mid)
       access = access.filter(AccessByMember.active == 1)
       access = access.all()
       return render_template('member_show.html',member=member,access=access,subscription=subscription)

    # See what rights the user has on the given resource
    # User and resource User and Resource class objects
    def getAccessLevel(user,resource):
        pass

    @app.route('/members/<string:id>/access', methods = ['GET'])
    @login_required
    def member_editaccess(id):
        """Controller method to display gather current access details for a member and display the editing interface"""
        mid = safestr(id)
        member = db.session.query(Member).filter(Member.member == mid).one()
        tags = MemberTag.query.filter(MemberTag.member_id == member.id).all()

        q = db.session.query(Resource).outerjoin(AccessByMember,((AccessByMember.resource_id == Resource.id) & (AccessByMember.member_id == member.id)))
        q = q.add_columns(AccessByMember.active,AccessByMember.level)

        roles=[]
        for r in db.session.query(Role.name).outerjoin(UserRoles,((UserRoles.role_id==Role.id) & (UserRoles.member_id == member.id))).add_column(UserRoles.id).all():
            roles.append({'name':r[0],'id':r[1]})


        # Put all the records together for renderer
        access = []
        for (r,active,level) in q.all():
            myPerms=getResourcePrivs(resource=r)
            if (current_user.privs('HeadRM')):
                myPerms=AccessByMember.LEVEL_ADMIN
            if not active: 
                level=0
            else:
                try:
                    level=int(level)
                except:
                    level=0
            levelText=AccessByMember.ACCESS_LEVEL[level]
            if level ==0:
                levelText=""
            access.append({'resource':r,'active':active,'level':level,'myPerms':myPerms,'levelText':levelText})
        return render_template('member_access.html',member=member,access=access,tags=tags,roles=roles)

    @app.route('/members/<string:id>/access', methods = ['POST'])
    @login_required
    def member_setaccess(id):
        """Controller method to receive POST and update user access"""
        mid = safestr(id)
        access = {}
        # Find all the items. If they were changed, and we are allowed
        # to change them - make it so in DB
        member = Member.query.filter(Member.member == mid).one()
        if ((member.id == current_user.id) and not (current_user.privs('Admin'))):
            flash("You can't change your own access")
            return redirect(url_for('member_editaccess',id=mid))
        if (('password1' in request.form and 'password2' in request.form) and
            (request.form['password1'] != "") and 
            current_user.privs('Admin')):
                if request.form['password1'] == request.form['password2']:
                    member.password=current_app.user_manager.hash_password(request.form['password1'])
                    flash("Password Changed")
                else:
                    flash("Password Mismatch")

        for key in request.form:
            if key.startswith("orgrole_") and current_user.privs('Admin'):
                r = key.replace("orgrole_","")
                oldval=request.form["orgrole_"+r] == "on"
                newval="role_"+r in request.form

                if oldval and not newval:
                    rr = UserRoles.query.filter(UserRoles.member_id == member.id).filter(UserRoles.role_id == db.session.query(Role.id).filter(Role.name == r)).one_or_none()
                    if rr: 
                        db.session.delete(rr)
                        flash("Removed %s privs" % r)
                elif newval and not oldval:
                    rr = UserRoles(member_id = member.id,role_id = db.session.query(Role.id).filter(Role.name == r))
                    flash("Added %s privs" % r)
                    db.session.add(rr)


            if key.startswith("orgaccess_"):
                oldcheck = request.form[key]=='on'
                r = key.replace("orgaccess_","")
                resource = Resource.query.filter(Resource.name==r).one()
                if current_user.privs('HeadRM'):
                    myPerms=AccessByMember.LEVEL_ADMIN
                else:
                    myPerms=getResourcePrivs(resource=resource)
                if "privs_"+r in request.form:
                    p = int(request.form['privs_'+r])
                else:
                    p = 0

                try:
                    alstr = AccessByMember.ACCESS_LEVEL[p]
                except:
                    alstr = "???"

                newcheck=False
                if "access_"+r in request.form:
                    newcheck=True

                # TODO do we have privs to do this?? (Check levels too)
                # TODO Don't allow someone to "demote" someone of higher privledge
                if myPerms >= 1:
                    # Find existing privs or not
                    # There are THREE levels of privileges at play here:
                    # acc.level - The OLD level for this record
                    # p - the NEW level we are trying to change to
                    # myPerm - The permissions level of the user making this change

                    # Find existing record
                    acc = AccessByMember.query.filter(AccessByMember.member_id == member.id)
                    acc = acc.filter(resource.id == AccessByMember.resource_id)
                    acc = acc.one_or_none()

                    if acc is None and newcheck == False:
                        # Was off - and no change - Do nothing
                        continue
                    elif acc is None and newcheck == True:
                        # Was off - but we turned it on - Create new one
                        db.session.add(Logs(member_id=member.id,resource_id=resource.id,event_type=eventtypes.RATTBE_LOGEVENT_RESOURCE_ACCESS_GRANTED.id))
                        acc = AccessByMember(member_id=member.id,resource_id=resource.id)
                        db.session.add(acc)
                    elif acc and newcheck == False and p<=myPerms:
                        flash("You aren't authorized to disable %s privs on %s" % (alstr,r))

                    if (p>=myPerms):
                        flash("You aren't authorized to grant %s privs on %s" % (alstr,r))
                    elif (acc.level >= myPerms):
                        flash("You aren't authorized to demote %s privs on %s" % (alstr,r))
                    elif acc.level != p:
                        db.session.add(Logs(member_id=member.id,resource_id=resource.id,event_type=eventtypes.RATTBE_LOGEVENT_RESOURCE_PRIV_CHANGE.id,message=alstr))
                        acc.level=p

                    if acc and newcheck == False and acc.level < myPerms:
                        #delete
                        db.session.add(Logs(member_id=mm.id,resource_id=resource.id,event_type=eventtypes.RATTBE_LOGEVENT_RESOURCE_ACCESS_REVOKED.id))
                        db.session.delete(acc)


        db.session.commit()
        flash("Member access updated")
        kick_backend()
        return redirect(url_for('member_editaccess',id=mid))

    @app.route('/members/<string:id>/tags', methods = ['GET'])
    @login_required
    def member_tags(id):
        """Controller method to gather and display tags associated with a memberid"""
        mid = safestr(id)
        sqlstr = "select tag_ident,tag_type,tag_name from tags_by_member where member = '%s'" % mid
        tags = query_db(sqlstr)
        return render_template('member_tags.html',mid=mid,tags=tags)

    @app.route('/updatebackends', methods = ['GET'])
    @login_required
    def update_backends():
        kick_backend()
        flash("Backend Update Request Send")
        return redirect(url_for('index'))

    @app.route('/members/<string:id>/tags', methods = ['POST'])
    @login_required
    def member_tagadd(id):
        """(Controller) method for POST to add tag for a user, making sure they are not duplicates"""
        mid = safestr(id)
        ntag = safestr(request.form['newtag'])
        ntagtype = safestr(request.form['newtagtype'])
        ntagname = safestr(request.form['newtagname'])
        ntag = authutil.rfid_validate(ntag)
        if ntag is None:
            flash("ERROR: The specified RFID tag is invalid, must be 10-digit all-numeric")
        else:
            if add_member_tag(mid,ntag,ntagtype,ntagname):
                kick_backend()
                flash("Tag added.")
            else:
                flash("Error: That tag is already associated with a user")
        return redirect(url_for('member_tags',id=mid))

    @app.route('/members/<string:id>/tags/delete/<string:tag_ident>', methods = ['GET'])
    @login_required
    def member_tagdelete(id,tag_ident):
        """(Controller) Delete a Tag from a Member (HTTP GET, for use from a href link)"""
        mid = safestr(id)
        tid = authutil.rfid_validate(tag_ident)
        if not tid:
            flash("Invalid Tag - Must be 10 digit numeric")
        else:
          sqlstr = "delete from tags_by_member where tag_ident = '%s' and member = '%s'" % (tid,mid)
          execute_db(sqlstr)
          get_db().commit()
          kick_backend()
          flash("If that tag was associated with the current user, it was removed")
        return redirect(url_for('member_tags',id=mid))

    @app.route('/tools/<string:id>', methods=['GET','POST'])
    @app.route('/tools', methods=['GET','POST'])
    @login_required
    @roles_required('Admin')
    def toolcfg(id=None,add=False,edit=False):
       """(Controller) Display Resources and controls"""
       edittool=None
       if id:
           edit=True
           edittool=Tool.query.filter(Tool.id==int(id)).first()
       if 'Add' in request.form:
           tool = Tool()
           tool.name = request.form['name']
           tool.resource_id = request.form['tooltypeid']
           tool.frontend = request.form['frontend']
           db.session.add(tool)
           db.session.commit()
           flash('Added')
       if 'Save' in request.form:
           tool = Tool.query.filter(Tool.id==id).one()
           tool.name = request.form['name']
           tool.resource_id = request.form['tooltypeid']
           tool.frontend = request.form['frontend']
           db.session.commit()
           flash('Saved')

       
       # THIS SHOULD WORK BUT DOESNT
       # query = db.session.query(Tool).add_column(Resource.name.label("resname")).join(Resource)
       query = db.session.query(Tool,Tool.id,Tool.name,Tool.frontend,Tool.resource_id,Resource.name.label("resname")).join(Resource)
       
       tools=query.all()
       resources= Resource.query.all()
       return render_template('tools.html',tools=tools,resources=resources,add=add,edit=edit,tool=edittool)

    # ----------------------------------------------------
    # Resource management (not including member access)
    # Routes:
    #  /resources - View
    #  /resources/<name> - Details for specific resource
    #  /resources/<name>/access - Show access for resource
    # ------------------------------------------------------

    @app.route('/resources', methods=['GET'])
    @login_required
    def resources():
       """(Controller) Display Resources and controls"""
       resources = _get_resources()
       access = {}
       return render_template('resources.html',resources=resources,access=access,editable=True)

    @app.route('/resources', methods=['POST'])
    @login_required
    @roles_required('Admin')
    def resource_create():
       """(Controller) Create a resource from an HTML form POST"""
       res = {}
       res['name'] = safestr(request.form['rname'])
       res['description'] = safestr(request.form['rdesc'])
       res['owneremail'] = safeemail(request.form['remail'])
       res['slack_chan'] = safestr(request.form['slack_chan'])
       res['slack_admin_chan'] = safestr(request.form['slack_admin_chan'])
       res['info_url'] = safestr(request.form['info_url'])
       res['info_text'] = safestr(request.form['info_text'])
       res['slack_info_text'] = safestr(request.form['slack_info_text'])
       result = _createResource(res)
       flash(result['message'])
       return redirect(url_for('resources'))

    @app.route('/resources/<string:resource>', methods=['GET'])
    @login_required
    def resource_show(resource):
        """(Controller) Display information about a given resource"""
        r = Resource.query.filter(Resource.name==resource).one_or_none()
        if not r:
            flash("Resource not found")
            return redirect(url_for('resources'))
        return render_template('resource_edit.html',resource=r)

    @app.route('/resources/<string:resource>', methods=['POST'])
    @login_required
    @roles_required('Admin')
    def resource_update(resource):
        """(Controller) Update an existing resource from HTML form POST"""
        rname = safestr(resource)
        r = Resource.query.filter(Resource.name==resource).one_or_none()
        if not r:
            flash("Error: Resource not found")
            return redirect(url_for('resources'))
        r.description = (request.form['rdesc'])
        r.owneremail = safeemail(request.form['remail'])
        r.slack_chan = safestr(request.form['slack_chan'])
        r.slack_admin_chan = safestr(request.form['slack_admin_chan'])
        r.info_url = safestr(request.form['info_url'])
        r.info_text = safestr(request.form['info_text'])
        r.slack_info_text = safestr(request.form['slack_info_text'])
        db.session.commit()
        flash("Resource updated")
        return redirect(url_for('resources'))

    @app.route('/resources/<string:resource>/delete', methods=['POST'])
    def resource_delete(resource):
        """(Controller) Delete a resource. Shocking."""
        rname = safestr(resource)
        sqlstr = "delete from resources where name='%s'" % rname
        execute_db(sqlstr)
        get_db().commit()
        flash("Resource deleted.")
        return redirect(url_for('resources'))

    @app.route('/resources/<string:resource>/list', methods=['GET'])
    def resource_showusers(resource):
        """(Controller) Display users who are authorized to use this resource"""
        rid = safestr(resource)
        #sqlstr = "select member from accessbymember where resource='%s'" % rid
        #authusers = query_db(sqlstr)
        sqlstr = "select a.id,a.member_id,m.member AS member from accessbymember a LEFT JOIN Members m ON m.id == a.member_id WHERE a.resource_id = (SELECT id FROM resources WHERE name='%s');" % rid
        authusers = query_db(sqlstr)
        return render_template('resource_users.html',resource=rid,users=authusers)

    #TODO: Create safestring converter to replace string; converter?
    @app.route('/resources/<string:resource>/log', methods=['GET','POST'])
    @roles_required('Admin','RATT')
    def logging(resource):
       """Endpoint for a resource to log via API"""
       # TODO - verify resources against global list
       if request.method == 'POST':
        # YYYY-MM-DD HH:MM:SS
        # TODO: Filter this for safety
        logdatetime = request.form['logdatetime']
        level = safestr(request.form['level'])
        # 'system' for resource system, rfid for access messages
        userid = safestr(request.form['userid'])
        msg = safestr(request.form['msg'])
        sqlstr = "INSERT into logs (logdatetime,resource,level,userid,msg) VALUES ('%s','%s','%s','%s','%s')" % (logdatetime,resource,level,userid,msg)
        execute_db(sqlstr)
        get_db().commit()
        return render_template('logged.html')
       else:
        if current_user.is_authenticated:
            r = safestr(resource)
            sqlstr = "SELECT logdatetime,resource,level,userid,msg from logs where resource = '%s'" % r
            entries = query_db(sqlstr)
            return render_template('resource_log.html',entries=entries)
        else:
            abort(401)


    # ------------------------------------------------
    # Payments controllers
    # Routes:
    #  /payments - Show payments options
    # ------------------------------------------------

    @app.route('/payments', methods = ['GET'])
    @login_required
    @roles_required(['Admin','Finamce'])
    def payments():
        """(Controller) Show Payment system controls"""
        cdate = pay.getLastUpdatedDate()
        return render_template('payments.html',cdate=cdate)

    # "Missing" payments - i.e. subcriptions without a known member
    @app.route('/payments/missing/assign/<string:assign>', methods = ['GET'])
    @app.route('/payments/missing', methods = ['GET','POST'])
    @login_required
    @roles_required(['Admin','Finamce'])
    def payments_missing(assign=None):
        """Find subscriptions with no members"""
        if 'Undo' in request.form:
            s = Subscription.query.filter(Subscription.membership == request.form['membership']).one()
            s.member_id = None
            db.session.commit()
            flash ("Undone.")
        if 'Assign' in request.form:
            if 'member' not in request.form or 'membership' not in request.form:
                flash("Must select a member and a subscription to link")
            elif request.form['member']=="" or request.form['membership']=="":
                flash("Must select a member and a subscription to link")
            else:
                s = Subscription.query.filter(Subscription.membership == request.form['membership']).one()
                s.member_id = db.session.query(Member.id).filter(Member.member == request.form['member'])
                db.session.commit()
                btn = '<form method="POST"><input type="hidden" name="membership" value="%s" /><input type="submit" value="Undo" name="Undo" /></form>' % request.form['membership']
                flash(Markup("Linked %s to %s %s" % (request.form['member'],request.form['membership'],btn)))

        subscriptions = Subscription.query.filter(Subscription.member_id == None).all()
        members = Member.query.outerjoin(Subscription).filter(Subscription.member_id == None)
        if 'applymemberfilter' in request.form:
            members = members.filter(Member.member.ilike("%"+request.form['memberfilter']+"%"))
        members = members.all()
        """Find members with no members"""


        return render_template('payments_missing.html',subscriptions=subscriptions,members=members)

    @app.route('/payments/manual', methods = ['GET'])
    @login_required
    @roles_required(['Admin','Finamce'])
    def manual_payments():
       sqlstr = """select member,plan,expires_date,updated_date from payments where paysystem = 'manual'"""
       members = query_db(sqlstr)
       return render_template('payments_manual.html',members=members)


    @app.route('/payments/manual/extend/<member>', methods = ['GET'])
    @login_required
    @roles_required(['Admin','Finamce'])
    def payments_manual_extend(member):
        safe_id = safestr(member)
        sqlstr = "update payments set expires_date=DATETIME(expires_date,'+31 days') where member = '%s' " % safe_id
        execute_db(sqlstr)
        get_db().commit()
        flash("Member %s was updated in the payments table" % safe_id)
        return redirect(url_for('manual_payments'))

    @app.route('/payments/manual/expire/<member>', methods = ['GET'])
    @login_required
    @roles_required(['Admin','Finamce'])
    def payments_manual_expire(member):
        safe_id = safestr(member)
        sqlstr = "update payments set expires_date=datetime('now')  where member = '%s' " % safe_id
        execute_db(sqlstr)
        get_db().commit()
        # TODO: EXPIRE MEMBER FROM ACCESS CONTROLS
        flash("Member %s was forcibly expired" % safe_id)
        return redirect(url_for('manual_payments'))

    @app.route('/payments/manual/delete/<member>', methods = ['GET'])
    @login_required
    @roles_required(['Admin','Finamce'])
    def payments_manual_delete(member):
        safe_id = safestr(member)
        sqlstr = "delete from payments where member = '%s' " % safe_id
        execute_db(sqlstr)
        get_db().commit()
         # TODO: EXPIRE MEMBER FROM ACCESS CONTROLS
        flash("Member %s was deleted from the payments table" % safe_id)
        return redirect(url_for('manual_payments'))

    @app.route('/payments/test', methods = ['GET'])
    @login_required
    @roles_required(['Admin','Finamce'])
    def test_payments():
       """(Controller) Validate the connection to the payment system(s)"""
       if pay.testPaymentSystems():
    	  flash("Payment system is reachable.")
       else:
    	  flash("Error: One or more Payment systems is Unreachable, review logs.")
       return redirect(url_for('payments'))

    @app.route('/payments/membership/<string:membership>', methods = ['GET'])
    @login_required
    @roles_required(['Admin','Finamce'])
    def payment_membership(membership):
       (subscription,member)=db.session.query(Subscription,Member).outerjoin(Member).filter(Subscription.membership==membership).one_or_none()
       return render_template('payments_membership.html',subscription=subscription,member=member)

    @app.route('/payments/update', methods = ['GET'])
    @login_required
    @roles_required(['Admin','Finamce'])
    def update_payments():
        """(Controller) Sync Payment data and update Member data (add missing, deactivate, etc)"""
        # TODO: Error handling
        pay.updatePaymentData()
        membership.syncWithSubscriptions()
        flash("Payment and Member data adjusted")
        return redirect(url_for('payments'))

    @app.route('/payments/<string:id>', methods=['GET'])
    @login_required
    @roles_required(['Admin','Finamce'])
    def payments_member(id):
        pid = safestr(id)
        # Note: When debugging Payments system duplication, there may be multiple records
        #  Display template is set up to handle that scenario
        sqlstr = """select p.member, m.firstname, m.lastname, p.email, p.paysystem, p.plan, p.customerid,
                p.expires_date, p.updated_date, p.checked_date, p.created_date from payments p join
                members m on m.member=p.member where p.member='%s'""" % pid
        #user = Subscription.query.filter(
        return render_template('payments_member.html',user=user)
    @app.route('/payments/reports', methods = ['GET'])
    @login_required
    @roles_required(['Admin','Finance'])
    def payments_reports():
        """(Controller) View various Payment data attributes"""
        f = request.args.get('filter','')
        sqlstr = "select * from payments"
        if f !='':
            if f == 'expired':
                sqlstr = sqlstr + " where expires_date < Datetime('now')"
            elif f == 'notexpired':
                sqlstr = sqlstr + " where expires_date > Datetime('now')"
            elif f == 'recentexpired':
                sqlstr = sqlstr + " where expires_date > Datetime('now','-180 days') AND expires_date < Datetime('now')"
            elif f == 'recentexpired':
                sqlstr = sqlstr + " where expires_date > Datetime('now','-180 days') AND expires_date < Datetime('now')"
        payments = query_db(sqlstr)
        return render_template('payments_reports.html',f=f,payments=payments)

    @app.route('/payments/fees', methods = ['GET'])
    @login_required
    @roles_required(['Admin','Finance'])
    def payments_fees():
        """(Controller) Charge Fee to a user, Schedule recurring Fee, view past paid fees"""
        f = request.args.get('days','90')
        # TODO: Member ID, pass in from member page?
        member = {}
        dt = """Datetime('now','-%s days')""" % f
        sqlstr = """select member, amount, fee_date, fee_name, fee_group, fee_description from feespaid where fee_date > %s""" % dt
        fees = query_db(sqlstr)
        return render_template('fees.html',days=f,member=member,fees=fees)

    @app.route("/payments/fees/charge", methods = ['POST'])
    @login_required
    @roles_required(['Admin','Finance'])
    def payments_fees_charge():
        """(Controller) Charge a one-time fee to a user"""
        fee = {}
        mandatory_fields = ['memberid','amount','name','description','group']
        for f in mandatory_fields:
            fee[f] = ''
            if f in request.form:
                fee[f] = safestr(request.form[f])
                print(fee[f])
            if fee[f] == '':
                flash("Error: One or more mandatory fields not filled out")
                return redirect(url_for('payments_fees'))
        # Validate member
        sqlstr = "Select customerid from payments where member = '%s'" % fee['memberid']
        members = query_db(sqlstr,"",True)
        if members:
            # Force validation of currency value
            try:
                "{:.2f}".format(float(fee['amount']))
                ## TODO: Still need to create the actual charge
                result = pay.chargeFee(paysystem,members['customerid'],fee['name'],fee['group'],fee['description'],fee['amount'])
                if result['success'] == True:
                    # TODO: Record fee charge
                    flash("Fee successfully charged and recorded")
                else:
                    flash("Error: Could not charge fee")
            except ValueError:
                flash("Amount must be a currency value such as 75 or 13.11")
            #
        else:
            flash("Error: Memberid does not exist. Make sure you have the right one..")
        return redirect(url_for('payments_fees'))

    # ------------------------------------------------------------
    # Blacklist entries
    # - Ignore bad pinpayments records, mainly
    # ------------------------------------------------------------

    @app.route('/blacklist', methods=['GET'])
    @login_required
    @roles_required(['Admin','Finance'])
    def blacklist_show():
        """(Controller) Show all the Blacklist entries"""
        sqlstr = "select entry,entrytype,reason,updated_date from blacklist"
        blacklist = query_db(sqlstr)
        return render_template('blacklist.html',blacklist=blacklist)


    # ------------------------------------------------------------
    # Reporting controllers
    # ------------------------------------------------------------

    @app.route('/reports', methods=['GET'])
    @login_required
    def reports():
        """(Controller) Display some pre-defined report options"""
        stats = getDataDiscrepancies()
        return render_template('reports.html',stats=stats)

    # ------------------------------------------------------------
    # Waiver controllers
    # ------------------------------------------------------------

    @app.route('/waivers', methods=['GET'])
    @login_required
    def waivers():
        sqlstr = "select waiver_id,email,firstname,lastname,created_date from waivers"
        waivers = query_db(sqlstr)
        return render_template('waivers.html',waivers=waivers)

    @app.route('/waivers/update', methods=['GET'])
    @login_required
    def waivers_update():
        """(Controller) Update list of waivers in the database. Can take a while."""
        updated = addNewWaivers()
        flash("Waivers added: %s" % updated)
        return redirect(url_for('waivers'))

    # ------------------------------------------------------------
    # Logs  
    #
    # Things log like crazy. Therefore logs are designed to
    # be cheap to write, and to be compartimentalizable so
    # that they don't interfere with other stuff.
    #
    # So we put logs in a separate databse. Maybe someday this
    # could be a completely different type of datastore.
    #
    # Because of this, we can't do relational queries between
    # the log and main databases. 
    #
    # Because of all this, logs are expensive to read. This might
    # not be too bad because we don't read them all that often.
    # ------------------------------------------------------------

    @app.route('/logs', methods=['GET'])
    @login_required
    def show_logs():
        limit = 200
        offset = 0
        format='html'
        evt= get_events()
        #q = db.session.query(Logs.time_reported,Logs.event_type,Member.firstname,Member.lastname,Tool.name.label("toolname"),Logs.message).outerjoin(Tool).outerjoin(Member).order_by(Logs.time_reported.desc())

        # Query main DB to Build relational tables
        tools={}
        members={}
        resources={}
        for t in Tool.query.all():
            tools[t.id] = t.name
        for r in Resource.query.all():
            resources[r.id] = r.name
        for m in Member.query.all():
            members[m.id] = {
                    'member': m.member,
                    'first': m.firstname,
                    'last': m.lastname
                    }

        q = db.session.query(Logs).order_by(Logs.time_reported.desc())

        if ('offset' in request.values):
            limit=int(request.values['offset'])

        if ('limit' in request.values):
          if request.values['limit']!="all":
            limit=int(request.values['limit'])
          else:
            limit = 200

        if limit>0: w=q.limit(limit)
        if offset>0: w=q.offset(offset)

        if ('member' in request.values):
            q=q.filter(Logs.member_id==members[request.values['member']])
        if ('memberid' in request.values):
            q=q.filter(Logs.member_id==request.values['memberid'])
        if ('resource' in request.values):
            q=q.filter(Logs.resource_id==resources[request.values['resource']])
        if ('resourceid' in request.values):
            q=q.filter(Logs.resource_id==request.values['resourceid'])
        if ('tool' in request.values):
            q=q.filter(Logs.tool_id==tools[request.values['tool']])
        if ('toolid' in request.values):
            q=q.filter(Logs.tool_id==request.values['toolid'])
        if ('before' in request.values):
            q=q.filter(Logs.time_reported<=request.values['before'])
        if ('after' in request.values):
            q=q.filter(Logs.time_reported>=request.values['after'])
        if ('format' in request.values):
            format=request.values['format']
        dbq = q.all()
        logs=[]
        for l in dbq:
            r={}
            r['time']=l.time_logged
            if l.member_id in members:
                r['user'] = members[l.member_id]['last']+", "+members[l.member_id]['first']
            else:
                r['user']="Member #"+str(l.member_id)
            
            if l.tool_id in tools:
                r['tool'] = tools[l.tool_id]
            else:
                r['tool']="Tool #"+str(l.tool_id)
            
            if l.resource_id in resources:
                r['resource'] = resources[l.resource_id]
            else:
                r['resource']="Resource #"+str(l.resource_id)

            if (l.event_type in evt):
                r['event']=evt[l.event_type]
            else:
                r['event']=l.event
            if l.message:
                r['message']=l.message
            else:
                r['message']=""
            logs.append(r)

        # if format=="csv":
        #    return Response(stream_with_context(generate(),content_type='text/csv'))
        return render_template('logs.html',logs=logs)


    # ------------------------------------------------------------
    # Google Accounts and Welcome Letters
    # -----------------------------------------------------------

    def _createNewGoogleAccounts():
        """Check for any user created in the last 3 days who does not have a Makeitlabs.com account"""
        sqlstr = "select m.member,m.firstname,m.lastname,p.email from members m inner join payments p on m.member=p.member where p.created_date >= Datetime('now','-3 day') and p.expires_date >= Datetime('now')"
        newusers = query_db(sqlstr)
        for n in newusers:
            # Using emailstr search to get around wierd hierarchical name mismatch
            emailstr = "%s.%s@makeitlabs.com" % (n['firstname'],n['lastname'])
            users = google_admin.searchEmail(emailstr)
            if users == []:
                # TODO: Change this to logging
                print "Member %s may need an account (%s.%s)" % (n['member'],n['firstname'],n['lastname'])
                ts = time.time()
                password = "%s-%d" % (n['lastname'],ts - (len(n['email']) * 314))
                print "Create with password %s and email to %s" % (password,n['email'])
                user = google_admin.createUser(n['firstname'],n['lastname'],n['email'],password)
                google_admin.sendWelcomeEmail(user,password,n['email'])
                print("Welcome email sent")
            else:
                print "Member appears to have an account: %s" % users

    def _createNewGoogleAccounts():
        """Check for any user created in the last 3 days who does not have a Makeitlabs.com account"""
        sqlstr = "select m.member,m.firstname,m.lastname,p.email from members m inner join payments p on m.member=p.member where p.created_date >= Datetime('now','-3 day') and p.expires_date >= Datetime('now')"
        newusers = query_db(sqlstr)
        for n in newusers:
            # Using emailstr search to get around wierd hierarchical name mismatch
            emailstr = "%s.%s@makeitlabs.com" % (n['firstname'],n['lastname'])
            users = google_admin.searchEmail(emailstr)
            if users == []:
                # TODO: Change this to logging
                print "Member %s may need an account (%s.%s)" % (n['member'],n['firstname'],n['lastname'])
                ts = time.time()
                password = "%s-%d" % (n['lastname'],ts - (len(n['email']) * 314))
                print "Create with password %s and email to %s" % (password,n['email'])
                user = google_admin.createUser(n['firstname'],n['lastname'],n['email'],password)
                google_admin.sendWelcomeEmail(user,password,n['email'])
                print("Welcome email sent")
            else:
                print "Member appears to have an account: %s" % users

    # ------------------------------------------------------------
    # API Routes - Stable, versioned URIs for outside integrations
    # Version 1:
    # /api/v1/
    #        /members -  List of all memberids, supports filtering and output formats
    # ----------------------------------------------------------------

    @app.route('/api/v1/reloadacl', methods=['GET'])
    @requires_auth
    def api_v1_reloadacl():
        kick_backend()
        return json_dump({'status':'success'}), 200, {'Content-type': 'application/json'}

    @app.route('/api/v1/whoami', methods=['GET'])
    @api_only
    def whoami():
        return json_dump("You have a valid API key %s" % g.apikey, 200, {'Content-type': 'text/plain'})

    @app.route('/api/v3/test', methods=['GET'])
    @requires_auth
    def api_v3_test():
        return("Hello world")

    @app.route('/api/v1/members', methods=['GET'])
    @login_required
    def api_v1_members():
        """(API) Return a list of all members. either in CSV or JSON"""
        sqlstr = "select m.member,m.plan,m.updated_date,s.expires_date from members m inner join subscriptions s on lower(s.name)=lower(m.stripe_name) and s.email=m.alt_email"
        outformat = request.args.get('output','json')
        filters = {}
        filters['active'] = safestr(request.args.get('active',''))
        filters['access_enabled'] = safestr(request.args.get('enabled',''))
        filters['expired'] = safestr(request.args.get('expired',''))
        filters['plan'] = safestr(request.args.get('plan',''))
        fstring = ""
        if len(filters) > 0:
            fstrings = []
            for f in filters:
                if f == 'active' or f == 'access_enabled':
                    if filters[f] == "true" or filters[f] == "false":
                        fstrings.append("%s='%s'" % (f,filters[f]))
                if f == 'expired':
                    if filters[f] == 'true':
                        fstrings.append("p.expires_date < Datetime('now')")
                    if filters[f] == 'false':
                        fstrings.append("p.expires_date >= Datetime('now')")
                if f == 'plan':
                    if filters[f] in ('pro','hobbyist'):
                        fstrings.append("m.plan='%s'" % filters[f])
            if len(fstrings) > 0:
                fstring = ' AND '.join(fstrings)
                sqlstr = sqlstr + " where " + fstring
        print(sqlstr)
        members = query_db(sqlstr)
        output = ""
        jsonarr = []
        for m in members:
            if outformat == 'csv':
                output = output + "%s,%s,%s,%s\n" % (m['member'],m['plan'],m['updated_date'],m['expires_date'])
            elif outformat == 'json':
                jsonarr.append({'member':m['member'],'plan':m['plan'], 'updated_date': m['updated_date'], 'expires_date': m['expires_date']})
        if outformat == 'csv':
            ctype = "text/plain; charset=utf-8"
        elif outformat == 'json':
            ctype = "application/json"
            output = json_dump(jsonarr)
        return output, 200, {'Content-Type': '%s' % ctype, 'Content-Language': 'en'}

    @app.route('/api/v1/members/<string:id>', methods=['GET'])
    @login_required
    def api_v1_showmember(id):
        """(API) Return details about a member, currently JSON only"""
        mid = safestr(id)
        outformat = request.args.get('output','json')
        sqlstr = """select m.member, m.plan, m.alt_email, m.firstname, m.lastname, m.phone, s.expires_date
                from members m inner join subscriptions s on lower(s.name)=lower(m.stripe_name) and s.email=m.alt_email where m.member='%s'""" % mid
        m = query_db(sqlstr,"",True)
        if outformat == 'json':
            output = {'member': m['member'],'plan': m['plan'],'alt_email': m['plan'],
                      'firstname': m['firstname'],'lastname': m['lastname'],
                      'phone': m['phone'],'expires_date': m['expires_date']}
            return json_dump(output), 200, {'Content-type': 'application/json'}

    @app.route('/api/v1/resources/<string:id>/acl', methods=['GET'])
    @requires_auth
    def api_v1_show_resource_acl(id):
        """(API) Return a list of all tags, their associazted users, and whether they are allowed at this resource"""
        rid = safestr(id)
        # Note: Returns all so resource can know who tried to access it and failed, w/o further lookup
        output = getAccessControlList(rid)
        return output, 200, {'Content-Type': 'application/json', 'Content-Language': 'en'}

    @app.route('/api/v0/resources/<string:id>/acl', methods=['GET'])
    #@requires_auth
    def api_v0_show_resource_acl(id):
        """(API) Return a list of all tags, their associated users, and whether they are allowed at this resource"""
        rid = safestr(id)
        # Note: Returns all so resource can know who tried to access it and failed, w/o further lookup
        #users = _getResourceUsers(rid)
        users = json_loads(getAccessControlList(rid))
        outformat = request.args.get('output','csv')
        if outformat == 'csv':
            outstr = "username,key,value,allowed,hashedCard,lastAccessed"
            for u in users:
                outstr += "\n%s,%s,%s,%s,%s,%s" % (u['member'],'0',u['level'],"allowed" if u['allowed'] == "allowed" else "denied",u['tagid'],'2011-06-21T05:12:25')
            return outstr, 200, {'Content-Type': 'text/plain', 'Content-Language': 'en'}

    @app.route('/api/v1/logs/<string:id>', methods=['POST'])
    #@requires_auth
    def api_v1_log_resource_create(id):
        rid = safestr(id)
        entry = {}
        # Default all to blank, since needed for SQL
        for opt in ['event','timestamp','memberid','message','ip']:
            entry[opt] = ''
        for k in request.form:
            entry[k] = safestr(request.form[k])
        return "work in progress"

    @app.route('/api/v1/payments/update', methods=['GET'])
    def api_v1_payments_update():
        """(API) Local host-only API for forcing payment data updates via cron. Not ideal, but avoiding other schedulers"""
        # Simplistic, and not incredibly secure, host-only filter
        host_addr = str.split(request.environ['HTTP_HOST'],':')
        if request.environ['REMOTE_ADDR'] == host_addr[0]:
            pay.updatePaymentData()
            membership.syncWithSubscriptions()
            return "Completed."
        else:
            return "API not available to %s expecting %s" % (request.environ['REMOTE_ADDR'], host_addr[0])

    @app.route('/api/v1/test', methods=['GET'])
    def api_test():
        host_addr = str.split(request.environ['HTTP_HOST'],':')
        print host_addr
        str1 = pprint.pformat(request.environ,depth=5)
        print(str1)
        if request.environ['REMOTE_ADDR'] == host_addr[0]:
            return "Yay, right host"
        else:
            return "Boo, wrong host"

    """

    @app.route('/oauthlogin')
    @oauth_authorized.connect_via(app.google_bp)
    def oauth_login():
        resp_json = google_flask.get("/oauth2/v2/userinfo").json()
        print resp_json
        return "Completed."

    @app.route('/oauthlogin2')
    @google_flask.authorization_required
    def oauth_login2():
        resp_json = google_flask.get("/oauth2/v2/userinfo").json()
        print resp_json
        return "Completed @{login}."

    @app.route("/google_oauth_authorize")
    def google_oauth_authorize():
        callback=url_for('google_oauth_authorize', _external=True)
        return google_flask.authorize(callback=callback)
    """


def init_db(app):
    # DB Models in db_models.py, init'd to SQLAlchemy
    db.init_app(app)

def has_no_empty_params(rule):
    defaults = rule.defaults if rule.defaults is not None else ()
    arguments = rule.arguments if rule.arguments is not None else ()
    return len(defaults) >= len(arguments)


def site_map(app):
    links = []
    for rule in app.url_map.iter_rules():
        # Filter out rules we can't navigate to in a browser
        print rule
        # and rules that require parameters
        
# Start development web server
if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument("--createdb",help="Create new db if none exists",action="store_true")
    parser.add_argument("--command",help="Special command",action="store_true")
    (args,extras) = parser.parse_known_args(sys.argv[1:])

    app=authbackend_init(__name__)


    with app.app_context():
        # Extensions like Flask-SQLAlchemy now know what the "current" app
        # is while within this block. Therefore, you can now run........
        if (args.createdb):
          db.create_all()
          createDefaultUsers(app)
        try:
          db.session.query("* from test_database").all()
          app.jinja_env.globals['TESTDB'] = "YES"
        except:
            pass
        if app.globalConfig.DeployType.lower() != "production":
          app.jinja_env.globals['DEPLOYTYPE'] = app.globalConfig.DeployType
          kick_backend()
        if  args.command:
            cli.cli_command(extras,app=app,um=app.user_manager)
            sys.exit(0)
        create_routes()
        #print site_map(app)
    #app.login_manager.login_view="test"
    #print app.login_manager.login_view
    app.run(host=app.globalConfig.ServerHost, port=app.globalConfig.ServerPort, debug=app.globalConfig.Debug)
