# vim:shiftwidth=2:expandtab
import pprint
import sqlite3, re, time
from flask import Flask, request, session, g, redirect, url_for, \
	abort, render_template, flash, Response,Blueprint
#from flask.ext.login import LoginManager, UserMixin, login_required,  current_user, login_user, logout_user
from flask_login import LoginManager, UserMixin, login_required,  current_user, login_user, logout_user
from flask_user import current_user, login_required, roles_required, UserManager, UserMixin, current_app
from ..db_models import Member, db, Resource, Tool, Subscription, Waiver, AccessByMember,MemberTag, Role, UserRoles, Logs
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

blueprint = Blueprint("tools", __name__, template_folder='templates', static_folder="static",url_prefix="/tools")



@blueprint.route('/', methods=['GET'])
@login_required
def tools():
	 """(Controller) Display Tools and controls"""
	 tools = _get_tools()
	 access = {}
	 return render_template('tools.html',tools=tools,editable=True)

@blueprint.route('/', methods=['POST'])
@login_required
@roles_required(['Admin','RATT'])
def tools_create():
	"""(Controller) Create a tool from an HTML form POST"""
	r = Tool()
        r.name = (request.form['input_name'])
        r.frontend = (request.form['input_frontend'])
        r.resource_id = (request.form['input_resource_id'])
	db.session.add(r)
        db.session.commit()
	flash("Created.")
	return redirect(url_for('tools.tools'))

@blueprint.route('/<string:tool>', methods=['GET'])
@login_required
def tools_show(tool):
	"""(Controller) Display information about a given tool"""
	r = Tool.query.filter(Tool.id==tool).one_or_none()
	if not r:
		flash("Tool not found")
		return redirect(url_for('tools.tools'))
	readonly=False
	if (not current_user.privs('RATT')):
		readonly=True
	resources=Resource.query.all()
	return render_template('tool_edit.html',tool=r,resources=resources,readonly=readonly)

@blueprint.route('/<string:tool>', methods=['POST'])
@login_required
@roles_required(['Admin','RATT'])
def tools_update(tool):
		"""(Controller) Update an existing tool from HTML form POST"""
		tid = (tool)
		r = Tool.query.filter(Tool.id==tid).one_or_none()
		if not r:
                    flash("Error: Tool not found")
                    return redirect(url_for('tools.tools'))
		r.name = (request.form['input_name'])
		r.frontend = (request.form['input_frontend'])
		r.resource_id = (request.form['input_resource_id'])
		db.session.commit()
		flash("Tool updated")
		return redirect(url_for('tools.tools'))

@blueprint.route('/<string:tool>/delete', methods=['POST'])
@roles_required(['Admin','RATT'])
def tool_delete(tool):
		"""(Controller) Delete a tool. Shocking."""
                r = Tool.query.filter(Tool.id == tool).one()
                db.session.delete(r)
                db.session.commit()
		flash("Tool deleted.")
		return redirect(url_for('tools.tools'))

@blueprint.route('/<string:tool>/list', methods=['GET'])
def tool_showusers(tool):
		"""(Controller) Display users who are authorized to use this tool"""
		tid = (tool)
		authusers = db.session.query(AccessByMember.id,AccessByMember.member_id,Member.member)
		authusers = authusers.outerjoin(Member,AccessByMember.member_id == Member.id)
		authusers = authusers.filter(AccessByMember.tool_id == db.session.query(Tool.id).filter(Tool.name == rid))
		authusers = authusers.all()
		return render_template('tool_users.html',tool=rid,users=authusers)

#TODO: Create safestring converter to replace string; converter?
@blueprint.route('/<string:tool>/log', methods=['GET','POST'])
@roles_required(['Admin','RATT'])
def logging(tool):
	 """Endpoint for a tool to log via API"""
	 # TODO - verify tools against global list
	 if request.method == 'POST':
		# YYYY-MM-DD HH:MM:SS
		# TODO: Filter this for safety
		logdatetime = request.form['logdatetime']
		level = safestr(request.form['level'])
		# 'system' for tool system, rfid for access messages
		userid = safestr(request.form['userid'])
		msg = safestr(request.form['msg'])
		sqlstr = "INSERT into logs (logdatetime,tool,level,userid,msg) VALUES ('%s','%s','%s','%s','%s')" % (logdatetime,tool,level,userid,msg)
		execute_db(sqlstr)
		get_db().commit()
		return render_template('logged.html')
	 else:
		if current_user.is_authenticated:
				r = safestr(tool)
				sqlstr = "SELECT logdatetime,tool,level,userid,msg from logs where tool = '%s'" % r
				entries = query_db(sqlstr)
				return render_template('tool_log.html',entries=entries)
		else:
				abort(401)


def _get_tools():
	q = db.session.query(Tool.name,Tool.frontend,Tool.id)
	q = q.add_column(Resource.name.label("resource_name")).join(Resource,Resource.id==Tool.resource_id)
	return q.all()

def register_pages(app):
	app.register_blueprint(blueprint)
