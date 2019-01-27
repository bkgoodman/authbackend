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
blueprint = Blueprint("reports", __name__, template_folder='templates', static_folder="static",url_prefix="/reports")

# ------------------------------------------------------------
# Reporting controllers
# ------------------------------------------------------------

@blueprint.route('/', methods=['GET'])
@login_required
def reports():
    """(Controller) Display some pre-defined report options"""
    stats = getDataDiscrepancies()
    return render_template('reports.html',stats=stats)

# ------------------------------------------------------------
# Blacklist entries
# - Ignore bad pinpayments records, mainly
# ------------------------------------------------------------

@blueprint.route('/blacklist', methods=['GET'])
@login_required
@roles_required(['Admin','Finance'])
def blacklist():
    """(Controller) Show all the Blacklist entries"""
    sqlstr = "select entry,entrytype,reason,updated_date from blacklist"
    blacklist = query_db(sqlstr)
    return render_template('blacklist.html',blacklist=blacklist)


def register_pages(app):
	app.register_blueprint(blueprint)
