# vim:shiftwidth=2:expandtab
import pprint
import sqlite3, re, time
from flask import Flask, request, session, g, redirect, url_for, \
	abort, render_template, flash, Response,Blueprint
#from flask.ext.login import LoginManager, UserMixin, login_required,  current_user, login_user, logout_user
from flask_login import LoginManager, UserMixin, login_required,  current_user, login_user, logout_user
from flask_user import current_user, login_required, roles_required, UserManager, UserMixin, current_app
from ..db_models import Member, db, Resource, Subscription, Waiver, AccessByMember,MemberTag, Role, UserRoles, Logs
from functools import wraps
import json
#from .. import requireauth as requireauth
from .. import utilities as authutil
from ..utilities import _safestr as safestr
from authlibs import eventtypes

import logging
from authlibs.init import GLOBAL_LOGGER_LEVEL
logger = logging.getLogger(__name__)
logger.setLevel(GLOBAL_LOGGER_LEVEL)


# You must call this modules "register_pages" with main app's "create_rotues"
blueprint = Blueprint("api", __name__, template_folder='templates', static_folder="static",url_prefix="/api")

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
    if password == "" or password is None or not ApiKey.query.filter_by(username=username,password=password).first():
        return False
    else:
        return True

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
		outformat = request.args.get('output','json')
		sqlstr = """select m.member, m.plan, m.alt_email, m.firstname, m.lastname, m.phone, s.expires_date
						from members m inner join subscriptions s on lower(s.name)=lower(m.stripe_name) and s.email=m.alt_email where m.member='%s'""" % mid
		m = query_db(sqlstr,"",True)
		if outformat == 'json':
				output = {'member': m['member'],'plan': m['plan'],'alt_email': m['plan'],
									'firstname': m['firstname'],'lastname': m['lastname'],
									'phone': m['phone'],'expires_date': m['expires_date']}
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

@blueprint.route('/v1/logs/<string:id>', methods=['POST'])
@api_only
def api_v1_log_resource_create(id):
		rid = safestr(id)
		entry = {}
		# Default all to blank, since needed for SQL
		for opt in ['event','timestamp','memberid','message','ip']:
				entry[opt] = ''
		for k in request.form:
				entry[k] = safestr(request.form[k])
		return "work in progress"

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
		print host_addr
		str1 = pprint.pformat(request.environ,depth=5)
		print(str1)
		if request.environ['REMOTE_ADDR'] == host_addr[0]:
				return "Yay, right host"
		else:
				return "Boo, wrong host"

def register_pages(app):
	app.register_blueprint(blueprint)
