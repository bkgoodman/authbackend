# vim:shiftwidth=2:expandtab
import pprint
import sqlite3, re, time
from flask import Flask, request, session, g, redirect, url_for, \
	abort, render_template, flash, Response,Blueprint
#from flask.ext.login import LoginManager, UserMixin, login_required,  current_user, login_user, logout_user
from flask_login import LoginManager, UserMixin, login_required,  current_user, login_user, logout_user
from ..db_models import Member, db, Resource
from functools import wraps
import json
#from .. import requireauth as requireauth
from .. import utilities as authutil

from authlibs.init import GLOBAL_LOGGER_LEVEL

import logging
logger = logging.getLogger(__name__)
logger.setLevel(GLOBAL_LOGGER_LEVEL)

# ------------------------------------------------------------
# API Routes - Stable, versioned URIs for outside integrations
# Version 1:
# /api/v1/
#        /members -  List of all memberids, supports filtering and output formats
# ----------------------------------------------------------------

blueprint = Blueprint("authorize", __name__, template_folder='templates', static_folder="static",url_prefix="/authorize")

@blueprint.route('/', methods=['GET','POST'])
@login_required
def authorize():
    """(API) Return a list of all members. either in CSV or JSON"""
    #print request.form
    others={}
    if "authorize" in request.form:
      members=[]
      resources=[]
      i=0
      while "memberid_"+str(i) in request.form:
        temp = request.form['memberid_'+str(i)]
        members.append(temp)
        i+=1
      i=0
      while "resource_"+str(i) in request.form:
        temp = request.form['resource_'+str(i)]
        resources.append(temp)
        i+=1
      #print "MEMBERS",members
      #print "RESOURCES",resources
      if len(members) == 0:
        others['error']="No members specified to authorize"
      elif len(resources) == 0:
        others['error']="No resources specified to authorize"
      else:
          others['message']="Authorized "+" ".join(members)+" on "+" ".join(resources)
    if 'search' in request.form and (request.form['search'] != ""):
      searchstr = authutil._safestr(request.form['search'])
      sstr = "%"+searchstr+"%"
      members = Member.query.filter(((Member.member.ilike(searchstr))) | (Member.alt_email.ilike(sstr))).all()
    else:
      members = []

    resources = Resource.query.all()
    res=[]
    for r in resources:
        (level,levelText)=authutil.getResourcePrivs(resource=r)
        res.append({'resource':r,'level':level,'levelText':levelText})

    return render_template("authorize.html",members=members,resources=res,**others)

@blueprint.route("/membersearch/<string:search>",methods=['GET'])
@login_required
def membersearch(search):
  sstr = authutil._safestr(search)
  sstr = "%"+sstr+"%"
  res = db.session.query(Member.member,Member.firstname,Member.lastname,Member.alt_email)
  res = res.filter((Member.firstname.ilike(sstr) | Member.lastname.ilike(sstr) | Member.alt_email.ilike(sstr) | Member.member.ilike(sstr)))
  res = res.all()
  result=[]
  for x in res:
    result.append({'member':x[0],'firstname':x[1],'lastname':x[2],'email':x[3]})
  return json.dumps(result)

def register_pages(app):
	app.register_blueprint(blueprint)
