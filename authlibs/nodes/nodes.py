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

blueprint = Blueprint("nodes", __name__, template_folder='templates', static_folder="static",url_prefix="/nodes")



@blueprint.route('/', methods=['GET'])
@login_required
def nodes():
	"""(Controller) Display Tools and controls"""
	nodes = _get_nodes()
	access = {}
	resources=Resource.query.all()
	return render_template('nodes.html',nodes=nodes,editable=True,node={},resources=resources)

@blueprint.route('/', methods=['POST'])
@login_required
@roles_required(['Admin','RATT'])
def nodes_create():
	"""(Controller) Create a node from an HTML form POST"""
	r = Tool()
        r.name = (request.form['input_name'])
        r.frontend = (request.form['input_frontend'])
        r.resource_id = (request.form['input_resource_id'])
	db.session.add(r)
        db.session.commit()
	flash("Created.")
	return redirect(url_for('nodes.nodes'))

@blueprint.route('/<string:node>', methods=['GET'])
@login_required
def nodes_show(node):
	"""(Controller) Display information about a given node"""
	r = Tool.query.filter(Tool.id==node).one_or_none()
	if not r:
		flash("Tool not found")
		return redirect(url_for('nodes.nodes'))
	readonly=False
	if (not current_user.privs('RATT')):
		readonly=True
	resources=Resource.query.all()
	return render_template('node_edit.html',node=r,resources=resources,readonly=readonly)

@blueprint.route('/<string:node>', methods=['POST'])
@login_required
@roles_required(['Admin','RATT'])
def nodes_update(node):
		"""(Controller) Update an existing node from HTML form POST"""
		tid = (node)
		r = Tool.query.filter(Tool.id==tid).one_or_none()
		if not r:
                    flash("Error: Tool not found")
                    return redirect(url_for('nodes.nodes'))
		r.name = (request.form['input_name'])
		r.frontend = (request.form['input_frontend'])
		r.resource_id = (request.form['input_resource_id'])
		db.session.commit()
		flash("Tool updated")
		return redirect(url_for('nodes.nodes'))

@blueprint.route('/<string:node>/delete', methods=['POST'])
@roles_required(['Admin','RATT'])
def node_delete(node):
		"""(Controller) Delete a node. Shocking."""
                r = Tool.query.filter(Tool.id == node).one()
                db.session.delete(r)
                db.session.commit()
		flash("Tool deleted.")
		return redirect(url_for('nodes.nodes'))

@blueprint.route('/<string:node>/list', methods=['GET'])
def node_showusers(node):
		"""(Controller) Display users who are authorized to use this node"""
		tid = (node)
		authusers = db.session.query(AccessByMember.id,AccessByMember.member_id,Member.member)
		authusers = authusers.outerjoin(Member,AccessByMember.member_id == Member.id)
		authusers = authusers.filter(AccessByMember.node_id == db.session.query(Tool.id).filter(Tool.name == rid))
		authusers = authusers.all()
		return render_template('node_users.html',node=rid,users=authusers)

#TODO: Create safestring converter to replace string; converter?
@blueprint.route('/<string:node>/log', methods=['GET','POST'])
@roles_required(['Admin','RATT'])
def logging(node):
	 """Endpoint for a node to log via API"""
	 # TODO - verify nodes against global list
	 if request.method == 'POST':
		# YYYY-MM-DD HH:MM:SS
		# TODO: Filter this for safety
		logdatetime = request.form['logdatetime']
		level = safestr(request.form['level'])
		# 'system' for node system, rfid for access messages
		userid = safestr(request.form['userid'])
		msg = safestr(request.form['msg'])
		sqlstr = "INSERT into logs (logdatetime,node,level,userid,msg) VALUES ('%s','%s','%s','%s','%s')" % (logdatetime,node,level,userid,msg)
		execute_db(sqlstr)
		get_db().commit()
		return render_template('logged.html')
	 else:
		if current_user.is_authenticated:
				r = safestr(node)
				sqlstr = "SELECT logdatetime,node,level,userid,msg from logs where node = '%s'" % r
				entries = query_db(sqlstr)
				return render_template('node_log.html',entries=entries)
		else:
				abort(401)


def _get_nodes():
	q = db.session.query(Tool.name,Tool.frontend,Tool.id)
	q = q.add_column(Resource.name.label("resource_name")).join(Resource,Resource.id==Tool.resource_id)
	return q.all()

def register_pages(app):
	app.register_blueprint(blueprint)
