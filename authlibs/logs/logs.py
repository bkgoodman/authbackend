# vim:shiftwidth=2:expandtab
import pprint
import sqlite3, re, time
from flask import Flask, request, session, g, redirect, url_for, \
	abort, render_template, flash, Response,Blueprint
#from flask.ext.login import LoginManager, UserMixin, login_required,  current_user, login_user, logout_user
from authlibs.eventtypes import get_events
from flask_login import LoginManager, UserMixin, login_required,  current_user, login_user, logout_user
from flask_user import current_user, login_required, roles_required, UserManager, UserMixin, current_app
from ..db_models import Member, db, Resource, Subscription, Waiver, AccessByMember,MemberTag, Role, UserRoles, Logs, Tool, Node
from functools import wraps
import json
#from .. import requireauth as requireauth
from .. import utilities as authutil
from ..utilities import _safestr as safestr
from authlibs import eventtypes
from sqlalchemy import or_

import logging
from authlibs.init import GLOBAL_LOGGER_LEVEL
logger = logging.getLogger(__name__)
logger.setLevel(GLOBAL_LOGGER_LEVEL)

# ------------------------------------------------------------
# API Routes - Stable, versioned URIs for outside integrations
# Version 1:
# /api/v1/
#        /members -  List of all memberids, supports filtering and output formats
# ----------------------------------------------------------------

# You must call this modules "register_pages" with main app's "create_rotues"
blueprint = Blueprint("logs", __name__, template_folder='templates', static_folder="static",url_prefix="/logs")

# --------------------------------------
# Routes
#  /test : Show (HTTP GET - members()), Create new (HTTP POST - member_add())
#  /test/<id> - Some ID
# --------------------------------------

# ------------------------------------------------------------
# Logs  
#
# Things log like crazy. Therefore logs are designed to
# be cheap to write, and to be compartimentalizable so
# that they don't interfere with other stuff.
#
# So we put logs in a separate databse. Maybe someday this
# could be a completely different type of datastore.
#
# Because of this, we can't do relational queries between
# the log and main databases. 
#
# Because of all this, logs are expensive to read. This might
# not be too bad because we don't read them all that often.
# ------------------------------------------------------------

@blueprint.route('/', methods=['GET'])
@login_required
def logs():
		limit = 200
		offset = 0
		format='html'
		evt= get_events()
		# Query main DB to Build relational tables
		tools={}
		members={}
		resources={}
		nodes={}
		for t in Tool.query.all():
				tools[t.id] = t.name
		for r in Resource.query.all():
				resources[r.id] = r.name
		for n in Node.query.all():
				nodes[n.id] = n.name
		for m in Member.query.all():
				members[m.id] = {
								'member': m.member,
								'first': m.firstname,
								'last': m.lastname
								}

		# Start Query
		q = db.session.query(Logs).order_by(Logs.time_reported.desc())

		# Handle form post query format
		for x in request.values:
			print x

		# Resource Filter
		filter_group = list()
		for x in request.values:
			if x.startswith("input_resource_"):
				filter_group.append((Logs.resource_id == x.replace("input_resource_","")))
		if (len(filter_group)>=1):
			q = q.filter(or_(*filter_group))
				
		# Member Filter
		filter_group = list()
		for x in request.values:
			if x.startswith("input_member_"):
				filter_group.append((Logs.member_id == x.replace("input_member_","")))
		if (len(filter_group)>=1):
			q = q.filter(or_(*filter_group))

		# Tool Filter
		filter_group = list()
		for x in request.values:
			if x.startswith("input_tool_"):
				filter_group.append((Logs.tool_id == x.replace("input_tool_","")))
		if (len(filter_group)>=1):
			q = q.filter(or_(*filter_group))

		# Node Filter
		filter_group = list()
		for x in request.values:
			if x.startswith("input_node_"):
				filter_group.append((Logs.node_id == x.replace("input_node_","")))
		if (len(filter_group)>=1):
			q = q.filter(or_(*filter_group))
	
		# Normal query format

		if ('offset' in request.values):
				limit=int(request.values['offset'])

		if ('limit' in request.values):
			if request.values['limit']!="all":
				limit=int(request.values['limit'])
			else:
				limit = 200

		if limit>0: w=q.limit(limit)
		if offset>0: w=q.offset(offset)

		if ('member' in request.values):
				q=q.filter((Logs.member_id==members[request.values['member']]) | (Logs.doneby==members[request.values['member']]))
		if ('memberid' in request.values):
				q=q.filter((Logs.member_id==request.values['memberid']) | (Logs.doneby==request.values['memberid']))
		if ('resource' in request.values):
				q=q.filter(Logs.resource_id==resources[request.values['resource']])
		if ('resourceid' in request.values):
				q=q.filter(Logs.resource_id==request.values['resourceid'])
		if ('tool' in request.values):
				q=q.filter(Logs.tool_id==tools[request.values['tool']])
		if ('toolid' in request.values):
				q=q.filter(Logs.tool_id==request.values['toolid'])
		if ('before' in request.values):
				q=q.filter(Logs.time_reported<=request.values['before'])
		if ('after' in request.values):
				q=q.filter(Logs.time_reported>=request.values['after'])
		if ('format' in request.values):
				format=request.values['format']
		print "LOG QUERY",q
		dbq = q.all()
		logs=[]
		for l in dbq:
				r={}
				r['when']=l.time_logged
				if not l.member_id:
					l.member_id=""
				elif l.member_id in members:
						r['user'] = members[l.member_id]['last']+", "+members[l.member_id]['first']
						r['member_id']=members[l.member_id]['member']
				else:
						r['user']="Member #"+str(l.member_id)
				
				r['tool_id'] = l.tool_id
				if not l.tool_id:
						r['tool'] = ""
				elif l.tool_id in tools:
						r['tool'] = tools[l.tool_id]
				else:
						r['tool']="Tool #"+str(l.tool_id)
				

				r['node_id']=l.node_id
				if not l.node_id:
						r['node']=""
				elif l.node_id in nodes:
						r['node'] = nodes[l.node_id]
				else:
						r['node']="Node #"+str(l.node_id)


				if not l.resource_id:
						r['resource']=""
				elif l.resource_id in resources:
						r['resource'] = resources[l.resource_id]
				else:
						r['resource']="Resource #"+str(l.resource_id)

				if (l.event_type in evt):
						r['event']=evt[l.event_type]
				else:
						r['event']=l.event_type

				if l.message:
						r['message']=l.message
				else:
						r['message']=""

				if not l.doneby:
						r['doneby'] = ""
						r['admin_id']=""
				elif l.doneby in members:
						if not members[l.doneby]['last']:
							r['doneby'] = members[l.doneby]['member']
						else:
							r['doneby'] = str(members[l.doneby]['last'])+", "+str(members[l.doneby]['first'])
						r['admin_id']=members[l.doneby]['member']
				else:
						r['doneby']="Member #"+str(l.doneby)
				logs.append(r)

		# if format=="csv":
		#    return Response(stream_with_context(generate(),content_type='text/csv'))
		resources=Resource.query.all()
		tools=Tool.query.all()
		nodes=Node.query.all()
		return render_template('logs.html',logs=logs,resources=resources,tools=tools,nodes=nodes)



def register_pages(app):
	app.register_blueprint(blueprint)
