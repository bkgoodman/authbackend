#vim:shiftwidth=2:expandtab
import pprint
import sqlite3, re, time
from sqlalchemy import func
from flask import Flask, request, session, g, redirect, url_for, \
	abort, render_template, flash, Response,Blueprint
#from flask.ext.login import LoginManager, UserMixin, login_required,  current_user, login_user, logout_user
from flask_login import LoginManager, UserMixin, login_required,  current_user, login_user, logout_user
from flask_user import current_user, login_required, roles_required, UserManager, UserMixin, current_app
from ..db_models import Member, db, KVopt, Subscription, Waiver, AccessByMember,MemberTag, Role, UserRoles, Logs, Tool
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

blueprint = Blueprint("kvopts", __name__, template_folder='templates', static_folder="static",url_prefix="/kvopts")



# ----------------------------------------------------
# KVopt management (not including member access)
# Routes:
#  /kvopts - View
#  /kvopts/<name> - Details for specific kvopt
#  /kvopts/<name>/access - Show access for kvopt
# ------------------------------------------------------

@blueprint.route('/', methods=['GET'])
@login_required
def kvopts():
	"""(Controller) Display KVopts and controls"""
	kvopts = _get_kvopts()
	access = {}
	for x in kvopts:
		if x.description is None: x.description=""
		if x.options is None: x.options=""
		if x.default is None: x.default=""

	return render_template('kvopts.html',kvopts=kvopts,editable=True,kinds=KVopt.valid_kinds,rec={'kind':'string'})

@blueprint.route('/', methods=['POST'])
@login_required
@roles_required(['Admin','RATT'])
def kvopt_create():
	"""(Controller) Create a kvopt from an HTML form POST"""
	r = KVopt()
	r.keyname = (request.form['input_keyname'])
	r.default = (request.form['input_default'])
	r.options = (request.form['input_options'])
	r.kind = (request.form['input_kind'])
	r.description = (request.form['input_description'])
	r.displayOrder = (request.form['input_displayOrder'])
	if r.kind == "boolean": r.options=""
	db.session.add(r)
	db.session.commit()
	flash("Created.")
	return redirect(url_for('kvopts.kvopts'))

@blueprint.route('/<string:kvopt>', methods=['GET'])
@login_required
def kvopt_show(kvopt):
		"""(Controller) Display information about a given kvopt"""
		r = KVopt.query.filter(KVopt.keyname==kvopt).one_or_none()
		if not r:
                    flash("Parameter not found")
                    return redirect(url_for('kvopts.kvopts'))
                readonly=False
                if (not current_user.privs('RATT')):
                    readonly=True
		return render_template('kvopts_edit.html',rec=r,readonly=readonly,kinds=KVopt.valid_kinds)

@blueprint.route('/<string:kvopt>', methods=['POST'])
@login_required
@roles_required(['Admin','RATT'])
def kvopt_update(kvopt):
		"""(Controller) Update an existing kvopt from HTML form POST"""
		rname = (kvopt)
		r = KVopt.query.filter(KVopt.id==kvopt).one_or_none()
		if not r:
                    flash("Error: KVopt not found")
                    return redirect(url_for('kvopts.kvopts'))
		r.keyname = (request.form['input_keyname'])
		r.default = (request.form['input_default'])
		r.options = (request.form['input_options'])
		r.kind = (request.form['input_kind'])
		if r.kind == "boolean": r.options=""
		r.description = (request.form['input_description'])
		r.displayOrder = (request.form['input_displayOrder'])
		db.session.commit()
		flash("Parameter Updated")
		return redirect(url_for('kvopts.kvopts'))

@blueprint.route('/<string:kvopt>/delete', methods=['POST'])
@roles_required(['Admin','RATT'])
def kvopt_delete(kvopt):
		"""(Controller) Delete a kvopt. Shocking."""
                r = KVopt.query.filter(KVopt.id == kvopt).one()
                db.session.delete(r)
                db.session.commit()
		flash("Node parameter deleted.")
		return redirect(url_for('kvopts.kvopts'))



def _get_kvopts():
	q = KVopt.query.order_by(KVopt.displayOrder)
	return q.all()

def register_pages(app):
	app.register_blueprint(blueprint)
