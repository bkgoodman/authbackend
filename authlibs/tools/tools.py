# vim:shiftwidth=2:expandtab
import pprint
import sqlite3, re, time
from flask import Flask, request, session, g, redirect, url_for, \
	abort, render_template, flash, Response,Blueprint
#from flask.ext.login import LoginManager, UserMixin, login_required,  current_user, login_user, logout_user
from flask_login import LoginManager, UserMixin, login_required,  current_user, login_user, logout_user
from flask_user import current_user, login_required, roles_required, UserManager, UserMixin, current_app
from ..db_models import Member, db, Resource, Subscription, Waiver, AccessByMember,MemberTag, Role, UserRoles, Logs, ApiKey
from functools import wraps
import json
#from .. import requireauth as requireauth
from .. import utilities as authutil
from ..utilities import _safestr as safestr
from authlibs import eventtypes
from json import dumps as json_dump
from json import loads as json_loads
from authlibs import payments as pay

import logging
from authlibs.init import GLOBAL_LOGGER_LEVEL
logger = logging.getLogger(__name__)
logger.setLevel(GLOBAL_LOGGER_LEVEL)
from sqlalchemy import case, DateTime


# You must call this modules "register_pages" with main app's "create_rotues"
blueprint = Blueprint("tools", __name__, template_folder='templates', static_folder="static",url_prefix="/tools")


@blueprint.route('/<string:id>', methods=['GET','POST'])
@blueprint.route('/', methods=['GET','POST'])
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




def register_pages(app):
	app.register_blueprint(blueprint)
