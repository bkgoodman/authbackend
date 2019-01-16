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
import logging
from flask_user import current_user, login_required, roles_required, UserManager, UserMixin, current_app
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
from authlibs.init import authbackend_init, get_config
from authlibs import cli
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
from authlibs.db_models import db, User, Role, UserRoles, Member, Resource, AccessByMember, Tool, Logs, UsageLog, Subscription, Waiver
import argparse

waiversystem = {}
waiversystem['Apikey'] = get_config().get('Smartwaiver','Apikey')

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
    
# RULE - only call this from web APIs - not internal functions
# Reason: If we have calls or scripts that act on many records,
# we probably shouldn't generate a million messages
def kick_backend():
    try:
      topic= app.globalConfig.mqtt_base_topic+"/control/broadcast/acl/update"
      mqtt_pub.single(topic, "update", hostname=app.globalConfig.mqtt_host,port=app.globalConfig.mqtt_port,**app.globalConfig.mqtt_opts)
    except BaseException as e:
        logger.warning("MQTT acl/update failed to publish: "+str(e))

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

'''
@login_manager.user_loader
def load_user(id):
    return User.get(id)
'''

def check_auth(username, password):
    """This function is called to check if a username /
    password combination is valid.
    """
    print "CHECK_AUTH",username,password
    if password == "" or password is None or not User.query.filter_by(email=username,api_key=password).first():
        print "BAD AUTH"
        return False
    else:
        print "GOOD AUTH"
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
    print "BLACKLIST: %s" % bad
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

def create_routes():
    @app.route('/new')
    @login_required
    def newroute():
        return "Hello new route"

    @app.route('/login')
    def login():
       return render_template('login.html')

    @app.route('/login/check', methods=['post'])
    def login_check():
        """Validate username and password from form against static credentials"""
        user = User.get(request.form['username'])
        if (user and user.password == request.form['password']):
            login_user(user)
        else:
            flash('Username or password incorrect')

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
       searchstr = safestr(request.form['searchstr'])
       members = membership.searchMembers(searchstr)
       return render_template('members.html',members=members,searchstr=searchstr)

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

        if request.method=="POST" and  request.form['SaveChanges'] == "Save":
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
            
        member=Member.query.filter(Member.member==mid).first()
        return render_template('member_edit.html',member=member)


    @app.route('/members/<string:id>', methods = ['GET'])
    @login_required
    def member_show(id):
       """Controller method to Display or modify a single user"""
       #TODO: Move member query functions to membership module
       access = {}
       mid = safestr(id)
       member=db.session.query(Member).outerjoin(Subscription).outerjoin(Waiver).filter(Member.member==mid).one()
     
       sqlstr = """select r.description, a.time_updated from resources r left join accessbymember a
                on r.id=a.resource_id 
                LEFT JOIN members m on a.member_id=m.id
                where a.is_active=1 and m.member='%s'""" % mid
       access = query_db(sqlstr)

       access=db.session.query(Resource).outerjoin(AccessByMember).outerjoin(Member)
       access = access.filter(Member.member == mid)
       access = access.filter(AccessByMember.active == 1)
       access = access.all()
       return render_template('member_show.html',member=member,access=access)

    @app.route('/members/<string:id>/access', methods = ['GET'])
    @login_required
    def member_editaccess(id):
        """Controller method to display gather current access details for a member and display the editing interface"""
        mid = safestr(id)
        sqlstr = "select tag_ident,tag_type,tag_name from tags_by_member where member_id = '%s'" % mid
        tags = query_db(sqlstr)
        sqlstr = """select * from resources r LEFT OUTER JOIN accessbymember a ON a.resource_id = r.id  AND a.member_id = (SELECT m.id FROM members m WHERE m.member='%s');""" % mid
        m = query_db(sqlstr)
        member = {}
        member['id'] = mid
        member['access']= m
        return render_template('member_access.html',member=member,tags=tags)

    @app.route('/members/<string:id>/access', methods = ['POST'])
    @login_required
    def member_setaccess(id):
        """Controller method to receive POST and update user access"""
        mid = safestr(id)
        access = {}
        for key in request.form:
            match = re.search(r"^access_(.+)",key)
            if match:
                access[match.group(1)] = 1
        clearAccess(mid)
        addAccess(mid,access)
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
    def resource_create():
       """(Controller) Create a resource from an HTML form POST"""
       res = {}
       res['name'] = safestr(request.form['rname'])
       res['description'] = safestr(request.form['rdesc'])
       res['owneremail'] = safeemail(request.form['rcontact'])
       result = _createResource(res)
       flash(result['message'])
       return redirect(url_for('resources'))

    @app.route('/resources/<string:resource>', methods=['GET'])
    @login_required
    def resource_show(resource):
        """(Controller) Display information about a given resource"""
        rname = safestr(resource)
        sqlstr = "SELECT name, owneremail, description from resources where name = '%s'" % rname
        print sqlstr
        r = query_db(sqlstr,(),True)
        print r
        return render_template('resource_edit.html',resource=r)

    @app.route('/resources/<string:resource>', methods=['POST'])
    @login_required
    def resource_update(resource):
        """(Controller) Update an existing resource from HTML form POST"""
        rname = safestr(resource)
        rdesc = safestr(request.form['rdescription'])
        remail = safestr(request.form['remail'])
        sqlstr = "update resources set description='%s',owneremail='%s', last_updated=Datetime('now') where name='%s'" % (rdesc,remail,rname)
        execute_db(sqlstr)
        get_db().commit()
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
        print "AUTHUSERS",authusers
        return render_template('resource_users.html',resource=rid,users=authusers)

    #TODO: Create safestring converter to replace string; converter?
    @app.route('/resources/<string:resource>/log', methods=['GET','POST'])
    def logging(resource):
       """Endpoint for a resource to log via API"""
       # TODO - verify resources against global list
       if request.method == 'POST':
        print "LOGGING FOR RESOURCE"
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
        print "Committed"
        return render_template('logged.html')
       else:
        print "QUERYING LOGS FOR RESOURCE"
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
    def payments():
        """(Controller) Show Payment system controls"""
        cdate = pay.getLastUpdatedDate()
        return render_template('payments.html',cdate=cdate)

    @app.route('/payments/manual', methods = ['GET'])
    @login_required
    def manual_payments():
       sqlstr = """select member,plan,expires_date,updated_date from payments where paysystem = 'manual'"""
       members = query_db(sqlstr)
       return render_template('payments_manual.html',members=members)


    @app.route('/payments/manual/extend/<member>', methods = ['GET'])
    @login_required
    def payments_manual_extend(member):
        safe_id = safestr(member)
        sqlstr = "update payments set expires_date=DATETIME(expires_date,'+31 days') where member = '%s' " % safe_id
        print(sqlstr)
        execute_db(sqlstr)
        get_db().commit()
        flash("Member %s was updated in the payments table" % safe_id)
        return redirect(url_for('manual_payments'))

    @app.route('/payments/manual/expire/<member>', methods = ['GET'])
    @login_required
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
    def test_payments():
       """(Controller) Validate the connection to the payment system(s)"""
       if pay.testPaymentSystems():
    	  flash("Payment system is reachable.")
       else:
    	  flash("Error: One or more Payment systems is Unreachable, review logs.")
       return redirect(url_for('payments'))

    @app.route('/payments/update', methods = ['GET'])
    @login_required
    def update_payments():
        """(Controller) Sync Payment data and update Member data (add missing, deactivate, etc)"""
        # TODO: Error handling
        pay.updatePaymentData()
        membership.syncWithSubscriptions()
        flash("Payment and Member data adjusted")
        return redirect(url_for('payments'))

    @app.route('/payments/<string:id>', methods=['GET'])
    @login_required
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
    def payments_fees():
        """(Controller) Charge Fee to a user, Schedule recurring Fee, view past paid fees"""
        f = request.args.get('days','90')
        # TODO: Member ID, pass in from member page?
        member = {}
        dt = """Datetime('now','-%s days')""" % f
        sqlstr = """select member, amount, fee_date, fee_name, fee_group, fee_description from feespaid where fee_date > %s""" % dt
        print(sqlstr)
        fees = query_db(sqlstr)
        return render_template('fees.html',days=f,member=member,fees=fees)

    @app.route("/payments/fees/charge", methods = ['POST'])
    @login_required
    def payments_fees_charge():
        """(Controller) Charge a one-time fee to a user"""
        fee = {}
        mandatory_fields = ['memberid','amount','name','description','group']
        print request
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
    # ------------------------------------------------------------

    @app.route('/logs', methods=['GET'])
    @login_required
    def show_logs():
        format='html'
        print request.values
        evt= get_events()
        q = db.session.query(Logs.time_reported,Logs.event_type,Member.firstname,Member.lastname,Tool.name.label("toolname"),Logs.message).outerjoin(Tool).outerjoin(Member).order_by(Logs.time_reported.desc())
        if ('start' in request.values):
            q=q.limit(request.values['limit'])
        elif request.values['limit']=="all":
            pass
        else:
            q=q.limit(200)
        if ('offset' in request.values):
            q=q.offset(request.values['offset'])
        if ('member' in request.values):
            q=q.filter(Member.mamber==request.values['member'])
        if ('tool' in request.values):
            q=q.filter(Tool.name==request.values['tool'])
        if ('memberid' in request.values):
            q=q.filter(Member.id==request.values['memberid'])
        if ('toolid' in request.values):
            q=q.filter(Tool.id==request.values['toolid'])
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
            print l.firstname,l.lastname,l.event_type,l.time_reported
            if l.lastname:
                r['user'] = l.lastname+", "+l.firstname
            else:
                r['user']=""
            if (l.event_type in evt):
                r['event']=evt[l.event_type]
            else:
                r['event']=l.event
            r['time'] = l.time_reported
            r['toolname'] = l.toolname
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
            users = google.searchEmail(emailstr)
            if users == []:
                # TODO: Change this to logging
                print "Member %s may need an account (%s.%s)" % (n['member'],n['firstname'],n['lastname'])
                ts = time.time()
                password = "%s-%d" % (n['lastname'],ts - (len(n['email']) * 314))
                print "Create with password %s and email to %s" % (password,n['email'])
                user = google.createUser(n['firstname'],n['lastname'],n['email'],password)
                google.sendWelcomeEmail(user,password,n['email'])
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
            users = google.searchEmail(emailstr)
            if users == []:
                # TODO: Change this to logging
                print "Member %s may need an account (%s.%s)" % (n['member'],n['firstname'],n['lastname'])
                ts = time.time()
                password = "%s-%d" % (n['lastname'],ts - (len(n['email']) * 314))
                print "Create with password %s and email to %s" % (password,n['email'])
                user = google.createUser(n['firstname'],n['lastname'],n['email'],password)
                google.sendWelcomeEmail(user,password,n['email'])
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
    def whoami():
        print dir(request)
        print "TYPE",type(current_user)
        print "TYPE",current_user.has_role('Admin')
        print "DIR",dir(current_user)
        user=None
        email=None
        if  request.authorization:
            user=User.query.filter(User.email==request.authorization.username).first()
            if user:
              email=user.email
        print email
        return json_dump("I don't know", 200, {'Content-type': 'text/plain'})

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


def init_db(app):
    # DB Models in db_models.py, init'd to SQLAlchemy
    db.init_app(app)

def createDefaultRoles(app):
    roles=['Admin','RATT']
    for role in roles:
      r = Role.query.filter(Role.name==role).first()
      if not r:
          r = Role(name=role)
          db.session.add(r)
    db.session.commit()

def createDefaultUsers(app):
    createDefaultRoles(app)
    # Create default admin role and user if not present
    admin_role = Role.query.filter(Role.name=='Admin').first()
    if not User.query.filter(User.email == app.globalConfig.AdminUser).first():
        user = User(email=app.globalConfig.AdminUser,password=app.user_manager.hash_password(app.globalConfig.AdminPasswd),email_confirmed_at=datetime.utcnow())
        logger.debug("ADD USER "+str(user))
        db.session.add(user)
        user.roles.append(admin_role)
        db.session.commit()
    # TODO - other default users?
        
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
    app.run(host=app.globalConfig.ServerHost, port=app.globalConfig.ServerPort, debug=app.globalConfig.Debug)
