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
from StringIO import StringIO
from authlibs.init import authbackend_init, get_config, createDefaultUsers
from authlibs import cli
from authlibs import utilities as authutil
from authlibs import payments as pay
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
from  authlibs import slackutils
from authlibs.main_menu import main_menu

""" GET PAGES"""

from authlibs.auth import auth
from authlibs.members import members
from authlibs.resources import resources as resource_pages
from authlibs.logs import logs as log_pages
from authlibs.waivers import waivers 
from authlibs.api import api 

logger = logging.getLogger(__name__)
logger.setLevel(GLOBAL_LOGGER_LEVEL)
    

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

    @app.route('/test/admin')
    @roles_required('Admin')
    def TestAdmin():
        return testdata()

    @app.route('/test/useredit')
    @roles_required(['Admin','Useredit'])
    def TestUseredit():
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
       return render_template('index.html',menu=main_menu())

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
    ### DEPREICATED TODO FIX BKG - Use one in "utiliteis"
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
        if  args.command:
            cli.cli_command(extras,app=app,um=app.user_manager)
            sys.exit(0)

				# Register Pages

        authutil.kick_backend()
        create_routes()
        auth.register_pages(app)
        members.register_pages(app)
        resource_pages.register_pages(app)
        log_pages.register_pages(app)
        waivers.register_pages(app)
        api.register_pages(app)

        slackutils.create_routes(app)
        #print site_map(app)
    #app.login_manager.login_view="test"
    #print app.login_manager.login_view
    app.run(host=app.globalConfig.ServerHost, port=app.globalConfig.ServerPort, debug=app.globalConfig.Debug)
