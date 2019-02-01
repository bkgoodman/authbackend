# vim:shiftwidth=2:expandtab
import pprint
import sqlite3, re, time
from flask import Flask, request, session, g, redirect, url_for, \
	abort, render_template, flash, Response,Blueprint
#from flask.ext.login import LoginManager, UserMixin, login_required,  current_user, login_user, logout_user
from flask_login import LoginManager, UserMixin, login_required,  current_user, login_user, logout_user
from flask_user import current_user, login_required, roles_required, UserManager, UserMixin, current_app
from ..db_models import Member, db, Resource, Subscription, Waiver, AccessByMember,MemberTag, Role, UserRoles, Logs, ApiKey, Node, NodeConfig, KVopt, Tool
from functools import wraps
import json
#from .. import requireauth as requireauth
from .. import utilities as authutil
from ..utilities import _safestr as safestr
from authlibs import eventtypes
from json import dumps as json_dump
from json import loads as json_loads

import logging
from authlibs.init import GLOBAL_LOGGER_LEVEL
logger = logging.getLogger(__name__)
logger.setLevel(GLOBAL_LOGGER_LEVEL)
from sqlalchemy import case, DateTime


# You must call this modules "register_pages" with main app's "create_rotues"
blueprint = Blueprint("api", __name__, template_folder='templates', static_folder="static",url_prefix="/api")


def authenticate():
    """Sends a 401 response that enables basic auth"""
    return Response(
    'Could not verify your access level for that URL.\n'
    'You have to login with proper credentials', 401,
    {'WWW-Authenticate': 'Basic realm="Login Required"'})

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


def check_api_access(username,password):
    a= ApiKey.query.filter_by(username=username).one_or_none()
    if not a:
        return False
    if not a.password:
        return False
    if current_app.user_manager.verify_password( password,a.password):
        return True
    else:
        return False

# ------------------------------------------------------------
# API Routes - Stable, versioned URIs for outside integrations
# Version 1:
# /api/v1/
#        /members -  List of all memberids, supports filtering and output formats
# ----------------------------------------------------------------

@blueprint.route('/v1/reloadacl', methods=['GET'])
@api_only
def api_v1_reloadacl():
		authutil.kick_backend()
		return json_dump({'status':'success'}), 200, {'Content-type': 'application/json'}

@blueprint.route('/v1/whoami', methods=['GET'])
@api_only
def whoami():
		return json_dump("You have a valid API key %s" % g.apikey, 200, {'Content-type': 'text/plain'})

@blueprint.route('/v1/node/<string:node>/config', methods=['GET'])
@api_only
def api_v1_nodeconfig(node):
		result = {'status':'success'}
		n = Node.query.filter(Node.name == node).one_or_none()
		if not n:
			result['status']='error'
			result['message']='Node not found'
			return json_dump(result, 200, {'Content-type': 'text/plain'})

		result['mac']=n.mac
		result['name']=n.name

		kv = KVopt.query.add_column(NodeConfig.value).outerjoin(NodeConfig,((NodeConfig.node_id == n.id) & (NodeConfig.key_id == KVopt.id))).all()
		result['params']={}
		for (k,v) in kv:
			sp = k.keyname.split(".")
			val=""
			if v is not None: val = v
			if k.kind.lower() == "boolean":
				if not v:
					val = False
				elif v.lower() in ('on','yes','true','1'):
					val=True
				else:
					val=False
			elif k.kind.lower() == "integer":
				try:
					val=int(v)
				except:
					val=0
			
			i = result['params']
			for kk in sp[:-1]:
				if kk not in i:
					i[kk]={}
				i=i[kk]
				
			i[sp[-1]]=val

		result['tools']=[]
		tools= Tool.query.add_columns(Resource.name).add_column(Resource.id)
		tools = tools.filter(Tool.node_id==n.id).join(Resource,Resource.id==Tool.resource_id)
		tools = tools.all()
		for x in tools:
			(t,resname,rid) =x
			tl={}
			tl['name']=t.name
			tl['resource_id']=rid
			tl['resource']=resname
			tl['id']=t.id
			result['tools'].append(tl)

		#print json_dump(result,indent=2)
		return json_dump(result, 200, {'Content-type': 'text/plain'})

@blueprint.route('/v1/mac/<string:mac>/config', methods=['GET'])
@api_only
def api_v1_macconfig(mac):
		n = Node.query.filter(Node.mac == mac).one_or_none()
		result = {'status':'success'}
		if not n:
			result['status']='error'
			result['message']='Node not found'
			return json_dump(result, 200, {'Content-type': 'text/plain'})
		return api_v1_nodeconfig(n.name)
	

@blueprint.route('/v3/test', methods=['GET'])
@login_required
def api_v3_test():
		return("Hello world")

# NOTE this requires LOGIN (not API) access because it
# is used by javascript to dynamically find members
@blueprint.route('/v1/members', methods=['GET'])
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

@blueprint.route('/v1/members/<string:id>', methods=['GET'])
@api_only
def api_v1_showmember(id):
		"""(API) Return details about a member, currently JSON only"""
		mid = safestr(id)
		#outformat = request.args.get('output','json')
                outformat = 'json'
                m = Member.query.filter(Member.member==mid).one_or_none()
                if not m:
				return "Does not exist", 404, {'Content-type': 'application/json'}
                output = {'member': m.member,
                        'plan': m.plan,
                        'alt_email': m.plan,
                        'firstname': m.firstname,
                        'lastname': m.lastname,
                        'phone': m.phone}
		return json_dump(output), 200, {'Content-type': 'application/json'}

@blueprint.route('/v1/resources/<string:id>/acl', methods=['GET'])
@api_only
def api_v1_show_resource_acl(id):
		"""(API) Return a list of all tags, their associazted users, and whether they are allowed at this resource"""
		rid = safestr(id)
		# Note: Returns all so resource can know who tried to access it and failed, w/o further lookup
		output = getAccessControlList(rid)
		return output, 200, {'Content-Type': 'application/json', 'Content-Language': 'en'}

@blueprint.route('/v0/resources/<string:id>/acl', methods=['GET'])
@api_only
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


@blueprint.route('/v1/payments/update', methods=['GET'])
@api_only
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

@blueprint.route('/v1/test', methods=['GET'])
@api_only
def api_test():
		host_addr = str.split(request.environ['HTTP_HOST'],':')
		str1 = pprint.pformat(request.environ,depth=5)
		if request.environ['REMOTE_ADDR'] == host_addr[0]:
				return "Yay, right host"
		else:
				return "Boo, wrong host"

def error_401():
    """Sends a 401 response that enables basic auth"""
    return Response(
    'What the hell. .\n'
    'You have to login with proper credentials', 401,
    {'WWW-Authenticate': 'Basic realm="Login Required"'})

###
## ACL HANDLERS
###

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
    #users = db.session.execute(sqlstr)

    q = db.session.query(MemberTag,MemberTag.tag_ident,Member.plan,Member.nickname,Member.access_enabled,Member.access_reason)
    q = q.add_column(case([(AccessByMember.resource_id !=  None, 'allowed')], else_ = 'denied').label('allowed'))
    # TODO Disable user it no subscription at all??? Only with other "plantype" logic to figure out "free" memberships
    q = q.add_column(case([((Subscription.expires_date < db.func.DateTime('now','-14 days')), 'true')], else_ = 'false').label('past_due'))
    q = q.add_column(case([((Subscription.expires_date < db.func.DateTime('now') & (Subscription.expires_date > db.func.DateTime('now','-13 day'))), 'true')], else_ = 'false').label('grace_period'))
    q = q.add_column(case([(Subscription.expires_date < db.func.DateTime('now','+2 days'), 'true')], else_ = 'false').label('expires_soon'))
    q = q.add_column(case([(AccessByMember.level != None , AccessByMember.level )], else_ = 0).label('level'))
    q = q.add_column(Member.member)
		# BKG DEBUG LINES
    q = q.add_column(MemberTag.member_id)
    q = q.add_column(Subscription.membership)
    q = q.add_column(Subscription.expires_date)
    q = q.outerjoin(Member,Member.id == MemberTag.member_id)

    rid = db.session.query(Resource.id).filter(Resource.name == resource)
    q = q.outerjoin(AccessByMember, ((AccessByMember.member_id == MemberTag.member_id) & (AccessByMember.resource_id == rid)))
    q = q.outerjoin(Subscription, Subscription.member_id == Member.id)
    q = q.group_by(MemberTag.tag_ident)

    # TODO BUG BKG We nuked the multi subscription line - becasue we nuked multiple subscriptions in the payment import
    # Logic here was:
    # left join subscriptions s2 on lower(s.name)=lower(s2.name) and s.expires_date < s2.expires_date where s2.expires_date is null
    val =  q.all()

    #print "RECORDS",len(val)

    # TEMP TODO - SQLalchemy returning set of tuples - turn into a dict for now
    result =[]
    for y in val:
        x = y[1:]
        #print "REC",x
        result.append({
            'tag_ident':x[0],
            'plan':x[1],
            'nickname':x[2],
            'enabled':x[3],
            'access_reason':x[4],
            'allowed':x[5],
            'past_due':x[6],
            'grace_period':x[7],
            'expires_soon':x[8],
            'level':x[9],
            'member':x[10],
            'member_id':x[11],
            'membership':x[12],
            'expires_date':x[13],
            'last_accessed':"" # We may never want to report this for many reasons
            })

    # TODO Do we want to deal with adding people with implicit (Admin, RATT, HeadRM) permissions? This could be a LOT of extra queries

    return result


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
        # BKG TODO WARNING I added this first check to see if we had a valid sub
        if u['membership'] is None:
            warning = "You do not have a current subscription. Check your payment plan. %s" % (c['board'])
            allowed = 'false'
        elif u['past_due'] == 'true':
            if 'expires_date' in u:
                warning = "Your membership expired (%s) and the grace period for access has ended. %s" % (u['expires_date'],c['board'])
            else:
                warning = "Membership Past due - no expiration date"
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
        jsonarr.append({'tagid':hashed_tag_id,'tag_ident':u['tag_ident'],'allowed':allowed,'warning':warning,'member':u['member'],'nickname':u['nickname'],'plan':u['plan'],'last_accessed':u['last_accessed'],'level':u['level'],'raw_tag_id':u['tag_ident']})
    return json_dump(jsonarr,indent=2)

#####
##
##  CLI handlers for API access
##
#####

def cli_addapikey(cmd,**kwargs):
  print "CMD IS",cmd
  apikey = ApiKey(username=cmd[1],name=cmd[2])
  if (len(cmd) >=4):
    apikey.password=cmd[3]
  else:
    apikey.password = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(12))
    print "API Key is",apikey.password
  apikey.password = current_app.user_manager.hash_password( apikey.password)
  db.session.add(apikey)
  db.session.commit()
  logger.info("Added API key "+str(cmd[1]))

def cli_deleteapikey(cmd,**kwargs):
  apikey = ApiKey.query.filter(ApiKey.name == cmd[1]).one()
  db.session.delete(apikey)
  db.session.commit()
  logger.info("API key deleted"+str(cmd[1]))

def cli_changeapikey(cmd,**kwargs):
  apikey = ApiKey.query.filter(ApiKey.name == cmd[1]).one()
  apikey.password = current_app.user_manager.hash_password( cmd[2])
  db.session.commit()
  logger.info("Change API key password"+str(cmd[1]))

def cli_listapikeys(cmd,**kwargs):
  apikey = ApiKey.query.all()
  for x in apikey:
      print "Name:",x.name,"Username:",x.username


def access_query(resource_id,member_id=None):
    q = db.session.query(MemberTag,MemberTag.tag_ident,Member.plan,Member.nickname,Member.access_enabled,Member.access_reason)
    q = q.add_column(case([(AccessByMember.resource_id !=  None, 'allowed')], else_ = 'denied').label('allowed'))
    # TODO Disable user it no subscription at all??? Only with other "plantype" logic to figure out "free" memberships
    q = q.add_column(case([((Subscription.expires_date < db.func.DateTime('now','-14 days')), 'true')], else_ = 'false').label('past_due'))
    q = q.add_column(case([((Subscription.expires_date < db.func.DateTime('now') & (Subscription.expires_date > db.func.DateTime('now','-13 day'))), 'true')], else_ = 'false').label('grace_period'))
    q = q.add_column(case([(Subscription.expires_date < db.func.DateTime('now','+2 days'), 'true')], else_ = 'false').label('expires_soon'))
    q = q.add_column(case([(AccessByMember.level != None , AccessByMember.level )], else_ = 0).label('level'))
    q = q.add_column(Member.member)

    # BKG DEBUG LINES
    q = q.add_column(MemberTag.member_id)
    q = q.add_column(Subscription.membership)
    q = q.add_column(Subscription.expires_date)
    # BKG DEBUG ITEMS
    q = q.outerjoin(Member,Member.id == MemberTag.member_id)

    if member_id:
        q = q.filter(MemberTag.member_id == member_id)

    if resource_id:
        q = q.outerjoin(AccessByMember, ((AccessByMember.member_id == MemberTag.member_id) & (AccessByMember.resource_id == resource_id)))
    else:
        q = q.outerjoin(AccessByMember, (AccessByMember.member_id == MemberTag.member_id))

    q = q.outerjoin(Subscription, Subscription.member_id == Member.id)
    q = q.group_by(MemberTag.tag_ident)

    return q
    
def cli_querytest(cmd,**kwargs):
    q = Member.query.filter(Member.member.ilike("%"+cmd[1]+"%")).first()
    print "Member:",q.member
    mid = q.id

    r = Resource.query.filter(Resource.name.ilike("%"+cmd[2]+"%")).first()
    print "Resrouce:",r.name
    rid = r.id

    q = access_query(member_id=mid,resource_id=rid)
    val = q.all()

    result =[]
    for y in val:
        x = y[1:]
        #print "REC",x
        result.append({
            'tag_ident':x[0],
            'plan':x[1],
            'nickname':x[2],
            'enabled':x[3],
            'access_reason':x[4],
            'allowed':x[5],
            'past_due':x[6],
            'grace_period':x[7],
            'expires_soon':x[8],
            'level':x[9],
            'member':x[10],
            'member_id':x[11],
            'membership':x[12],
            'expires_date':x[13],
            'last_accessed':"" # We may never want to report this for many reasons
            })
    print result

def register_pages(app):
	app.register_blueprint(blueprint)
