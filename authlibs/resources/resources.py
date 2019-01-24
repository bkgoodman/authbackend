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
from ..utilities import _safeemail as safeemail
from authlibs import eventtypes

import logging
from authlibs.init import GLOBAL_LOGGER_LEVEL
logger = logging.getLogger(__name__)
logger.setLevel(GLOBAL_LOGGER_LEVEL)

blueprint = Blueprint("resources", __name__, template_folder='templates', static_folder="static",url_prefix="/resources")



# ----------------------------------------------------
# Resource management (not including member access)
# Routes:
#  /resources - View
#  /resources/<name> - Details for specific resource
#  /resources/<name>/access - Show access for resource
# ------------------------------------------------------

@blueprint.route('/', methods=['GET'])
@login_required
def resources():
	 """(Controller) Display Resources and controls"""
	 resources = _get_resources()
	 access = {}
	 return render_template('resources.html',resources=resources,access=access,editable=True)

@blueprint.route('/', methods=['POST'])
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
	 return redirect(url_for('resources.resources'))

@blueprint.route('/<string:resource>', methods=['GET'])
@login_required
def resource_show(resource):
		"""(Controller) Display information about a given resource"""
		r = Resource.query.filter(Resource.name==resource).one_or_none()
		if not r:
				flash("Resource not found")
				return redirect(url_for('resources.resources'))
		return render_template('resource_edit.html',resource=r)

@blueprint.route('/<string:resource>', methods=['POST'])
@login_required
@roles_required(['Admin','RATT'])
def resource_update(resource):
		"""(Controller) Update an existing resource from HTML form POST"""
		rname = safestr(resource)
		r = Resource.query.filter(Resource.name==resource).one_or_none()
		if not r:
				flash("Error: Resource not found")
				return redirect(url_for('resources.resources'))
		r.description = (request.form['rdesc'])
		r.owneremail = safeemail(request.form['remail'])
		r.slack_chan = safestr(request.form['slack_chan'])
		r.slack_admin_chan = safestr(request.form['slack_admin_chan'])
		r.info_url = safestr(request.form['info_url'])
		r.info_text = safestr(request.form['info_text'])
		r.slack_info_text = safestr(request.form['slack_info_text'])
		db.session.commit()
		flash("Resource updated")
		return redirect(url_for('resources.resources'))

@blueprint.route('/<string:resource>/delete', methods=['POST'])
def resource_delete(resource):
		"""(Controller) Delete a resource. Shocking."""
		rname = safestr(resource)
		sqlstr = "delete from resources where name='%s'" % rname
		execute_db(sqlstr)
		get_db().commit()
		flash("Resource deleted.")
		return redirect(url_for('resources.resources'))

@blueprint.route('/<string:resource>/list', methods=['GET'])
def resource_showusers(resource):
		"""(Controller) Display users who are authorized to use this resource"""
		rid = safestr(resource)
		authusers = db.session.query(AccessByMember.id,AccessByMember.member_id,Member.member)
		authusers = authusers.outerjoin(Member,AccessByMember.member_id == Member.id)
		authusers = authusers.filter(AccessByMember.resource_id == db.session.query(Resource.id).filter(Resource.name == rid))
		authusers = authusers.all()
		return render_template('resource_users.html',resource=rid,users=authusers)

#TODO: Create safestring converter to replace string; converter?
@blueprint.route('/<string:resource>/log', methods=['GET','POST'])
@roles_required(['Admin','RATT'])
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

def _createResource(r):
    """Add a resource to the database"""
    sqlstr = """insert into resources (name,description,owneremail)
            values ('%s','%s','%s')""" % (r['name'],r['description'],r['owneremail'])
    execute_db(sqlstr)
    get_db().commit()
    #TODO: Catch errors, etc
    return {'status':'success','message':'Resource successfully added'}

def _get_resources():
	q = db.session.query(Resource.name,Resource.owneremail, Resource.description).all()
	return q

def register_pages(app):
	app.register_blueprint(blueprint)
