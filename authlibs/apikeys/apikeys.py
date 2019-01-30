#vim:shiftwidth=2:expandtab
import pprint
import random,string
import sqlite3, re, time
from flask import Flask, request, session, g, redirect, url_for, \
	abort, render_template, flash, Response,Blueprint
#from flask.ext.login import LoginManager, UserMixin, login_required,  current_user, login_user, logout_user
from flask_login import LoginManager, UserMixin, login_required,  current_user, login_user, logout_user
from flask_user import current_user, login_required, roles_required, UserManager, UserMixin, current_app
from ..db_models import Member, db, Resource, ApiKey, Subscription, Waiver, AccessByMember,MemberTag, Role, UserRoles, Logs, Node
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

blueprint = Blueprint("apikeys", __name__, template_folder='templates', static_folder="static",url_prefix="/apikeys")



@blueprint.route('/', methods=['GET'])
@login_required
@roles_required(['Admin','RATT'])
def apikeys():
	"""(Controller) Display ApiKeys and controls"""
	apikeys = _get_apikeys()
	return render_template('apikeys.html',apikeys=apikeys,editable=True,apikey={},create=True)

@blueprint.route('/', methods=['POST'])
@login_required
@roles_required(['Admin','RATT'])
def apikeys_create():
  """(Controller) Create a apikey from an HTML form POST"""
  newpw=""
  r = ApiKey()
  r.name = (request.form['input_name'])
  r.username = (request.form['input_username'])
  pwgen  = (request.form['pwgen'])
  if pwgen == "manual":
    pw1  = (request.form['input_newpw1']).strip()
    pw2  = (request.form['input_newpw2']).strip()
    if (pw1 != pw2):
      flash ("Passwords Mismatch")
      return redirect(url_for('apikeys.apikeys'))
    elif pw1 == "":
      flash ("Manual password was not specified")
      return redirect(url_for('apikeys.apikeys'))
  else:
    pw1 = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(12))
    newpw = "New password is: "+pw1
  r.password = current_app.user_manager.hash_password(pw1)
  db.session.add(r)
  db.session.commit()
  flash("Created. "+newpw)
  return redirect(url_for('apikeys.apikeys'))

@blueprint.route('/<string:apikey>', methods=['GET'])
@login_required
def apikeys_show(apikey):
	"""(Controller) Display information about a given apikey"""
	r = ApiKey.query.filter(ApiKey.id==apikey).one_or_none()
	if not r:
		flash("ApiKey not found")
		return redirect(url_for('apikeys.apikeys'))
	return render_template('apikey_edit.html',apikey=r)

@blueprint.route('/<string:apikey>', methods=['POST'])
@login_required
@roles_required(['Admin','RATT'])
def apikeys_update(apikey):
  """(Controller) Update an existing apikey from HTML form POST"""
  tid = (apikey)
  r = ApiKey.query.filter(ApiKey.id==tid).one_or_none()
  if not r:
                  flash("Error: ApiKey not found")
                  return redirect(url_for('apikeys.apikeys'))
  r.name = (request.form['input_name'])
  pwgen  = (request.form['pwgen'])
  newpw=""
  if pwgen == "manual":
    pw1  = (request.form['input_newpw1']).strip()
    pw2  = (request.form['input_newpw2']).strip()
    if (pw1 != pw2):
      flash ("Passwords Mismatch")
      return redirect(url_for('apikeys.apikeys'))
    elif pw1 == "":
      flash ("Manual password was not specified")
      return redirect(url_for('apikeys.apikeys'))
    r.password = current_app.user_manager.hash_password(pw1)
  elif pwgen == "auto":
    pw1 = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(12))
    newpw = "New password is: "+pw1
    r.password = current_app.user_manager.hash_password(pw1)
  db.session.commit()
  flash("ApiKey updated. "+newpw)
  return redirect(url_for('apikeys.apikeys'))

@blueprint.route('/<string:apikey>/delete', methods=['POST'])
@roles_required(['Admin','RATT'])
def apikey_delete(apikey):
		"""(Controller) Delete a apikey. Shocking."""
                r = ApiKey.query.filter(ApiKey.id == apikey).one()
                db.session.delete(r)
                db.session.commit()
		flash("ApiKey deleted.")
		return redirect(url_for('apikeys.apikeys'))

@blueprint.route('/<string:apikey>/list', methods=['GET'])
def apikey_showusers(apikey):
		"""(Controller) Display users who are authorized to use this apikey"""
		tid = (apikey)
		authusers = db.session.query(AccessByMember.id,AccessByMember.member_id,Member.member)
		authusers = authusers.outerjoin(Member,AccessByMember.member_id == Member.id)
		authusers = authusers.filter(AccessByMember.apikey_id == db.session.query(ApiKey.id).filter(ApiKey.name == rid))
		authusers = authusers.all()
		return render_template('apikey_users.html',apikey=rid,users=authusers)


def _get_apikeys():
	return ApiKey.query.all()

def register_pages(app):
	app.register_blueprint(blueprint)
