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

# ------------------------------------------------------------
# API Routes - Stable, versioned URIs for outside integrations
# Version 1:
# /api/v1/
#        /members -  List of all memberids, supports filtering and output formats
# ----------------------------------------------------------------

# TODO BKG FIX - Change "memb" to "members" once we've depricated the old handlers
blueprint = Blueprint("members", __name__, template_folder='templates', static_folder="static",url_prefix="/members2")

# --------------------------------------
# Member viewing and editing functions
# Routes
#  /members : Show (HTTP GET - members()), Create new (HTTP POST - member_add())
#  /<memberid> - Show (HTTP GET - member_show()), Create new (HTTP POST - member_add())
#  /<memberid>/access - Show current access and interface to change (GET), Change access (POST)
#  /<memberid>/tags - Show tags associated with user (GET), Change tags (POST)
#  /<memberid>/edit - Show current user base info and interface to adjust (GET), Change existing user (POST)
# --------------------------------------

@blueprint.route('/', methods = ['GET'])
@login_required
def members():
	members = {}
	return render_template('members.html',members=members)

@blueprint.route('/members', methods= ['POST'])
@login_required
@roles_required(['Admin','Useredit'])
def member_add():
		"""Controller method for POST requests to add a user"""
		member = {}
		mandatory_fields = ['firstname','lastname','memberid','plan','payment']
		optional_fields = ['alt_email','phone','nickname']
		print request
		for f in mandatory_fields:
				member[f] = ''
				if f in request.form:
						member[f] = request.form[f]
				if member[f] == '':
						flash("Error: One or more mandatory fields not filled out")
						return redirect(url_for('members'))
		for f in optional_fields:
				member[f] = ''
				if f in request.form:
						member[f] = request.form[f]
		result = _createMember(member)
		flash(result['message'])
		if result['status'] == "success":
				return redirect(url_for('members.member_show',id=member['memberid']))
		else:
				return redirect(url_for('members.members'))

# memberedit
@blueprint.route('/<string:id>/edit', methods = ['GET','POST'])
@login_required
def member_edit(id):
		mid = authutil._safestr(id)
		member = {}

		if request.method=="POST" and 'Unlink' in  request.form:
				s = Subscription.query.filter(Subscription.membership==request.form['membership']).one()
				s.member_id = None
				db.session.commit()
				btn = '''<form method="POST">
								<input type="hidden" name="member_id" value="%s" />
								<input type="hidden" name="membership" value="%s" />
								<input type="submit" value="Undo" name="Undo" />
								</form>''' % (request.form['member_id'],request.form['membership'])
				flash(Markup("Unlinked. %s" % btn))
		elif 'Undo' in request.form:
				# Relink cleared member ID
				s = Subscription.query.filter(Subscription.membership == request.form['membership']).one()
				s.member_id = request.form['member_id']
				db.session.commit()
				flash ("Undone.")
		elif request.method=="POST" and 'SaveChanges' in  request.form:
				flash ("Changes Saved (Please Review!)")
				m=Member.query.filter(Member.member==mid).first()
				f=request.form
				m.firstname= f['firstname']
				m.lastname= f['lastname']
				if f['phone'] == "None" or f['phone'].strip() == "":
						m.phone=None
				else:
					m.phone= f['phone']
				m.slack= f['slack']
				m.alt_email= f['alt_email']
				db.session.commit()
				
		#(member,subscription)=Member.query.outerjoin(Subscription).filter(Member.member==mid).first()
		member=db.session.query(Member,Subscription)
		member = member.outerjoin(Subscription).outerjoin(Waiver).filter(Member.member==mid)
		r = member.one_or_none()
                if not r:
                    flash("Member not found")
                    return redirect(url_for("members.members"))

		(member,subscription) = r
		access=db.session.query(Resource).add_column(AccessByMember.level).outerjoin(AccessByMember).outerjoin(Member)
		access = access.filter(Member.member == mid)
		access = access.filter(AccessByMember.active == 1)
		access = access.all()
                print access

                acc =[]
                for a in access:
                    print "AY IS",a
                    (r,level) = a
                    acc.append({'description':r.name,'level':authutil.accessLevelString(level,user="",noaccess="")})
		return render_template('member_edit.html',member=member,subscription=subscription,access=acc)


@blueprint.route('/<string:id>', methods = ['GET'])
@login_required
def member_show(id):
	 """Controller method to Display or modify a single user"""
	 #TODO: Move member query functions to membership module
	 access = {}
	 mid = authutil._safestr(id)
	 member=db.session.query(Member,Subscription)
	 member = member.outerjoin(Subscription).outerjoin(Waiver).filter(Member.member==mid)
	 res = member.one_or_none()
 
	 if res:
		 (member,subscription) = res
		 access=db.session.query(Resource).outerjoin(AccessByMember).outerjoin(Member)
		 access = access.filter(Member.member == mid)
		 access = access.filter(AccessByMember.active == 1)
		 access = access.all()
		 return render_template('member_show.html',member=member,access=access,subscription=subscription)
	 else:
		flash("Member not found")
		return redirect(url_for("members.members"))

# See what rights the user has on the given resource
# User and resource User and Resource class objects
def getAccessLevel(user,resource):
		pass

@blueprint.route('/<string:id>/access', methods = ['GET'])
@login_required
def member_editaccess(id):
		"""Controller method to display gather current access details for a member and display the editing interface"""
		mid = safestr(id)
		member = db.session.query(Member).filter(Member.member == mid).one()
		tags = MemberTag.query.filter(MemberTag.member_id == member.id).all()

		q = db.session.query(Resource).outerjoin(AccessByMember,((AccessByMember.resource_id == Resource.id) & (AccessByMember.member_id == member.id)))
		q = q.add_columns(AccessByMember.active,AccessByMember.level)

		roles=[]
		for r in db.session.query(Role.name).outerjoin(UserRoles,((UserRoles.role_id==Role.id) & (UserRoles.member_id == member.id))).add_column(UserRoles.id).all():
				roles.append({'name':r[0],'id':r[1]})


		# Put all the records together for renderer
		access = []
		for (r,active,level) in q.all():
				(myPerms,levelTxt)=authutil.getResourcePrivs(resource=r)
				if not active: 
						level=0
				else:
						try:
								level=int(level)
						except:
								level=0
				levelText=AccessByMember.ACCESS_LEVEL[level]
				if level ==0:
						levelText=""
				access.append({'resource':r,'active':active,'level':level,'myPerms':myPerms,'levelText':levelText})
		return render_template('member_access.html',member=member,access=access,tags=tags,roles=roles)

@blueprint.route('/<string:id>/access', methods = ['POST'])
@login_required
def member_setaccess(id):
		"""Controller method to receive POST and update user access"""
		mid = safestr(id)
		access = {}
		# Find all the items. If they were changed, and we are allowed
		# to change them - make it so in DB
		member = Member.query.filter(Member.member == mid).one()
		if ((member.id == current_user.id) and not (current_user.privs('Admin'))):
				flash("You can't change your own access")
				return redirect(url_for('member_editaccess',id=mid))
		if (('password1' in request.form and 'password2' in request.form) and
				(request.form['password1'] != "") and 
				current_user.privs('Admin')):
						if request.form['password1'] == request.form['password2']:
								member.password=current_app.user_manager.hash_password(request.form['password1'])
								flash("Password Changed")
						else:
								flash("Password Mismatch")

		for key in request.form:
				if key.startswith("orgrole_") and current_user.privs('Admin'):
						r = key.replace("orgrole_","")
						oldval=request.form["orgrole_"+r] == "on"
						newval="role_"+r in request.form

						if oldval and not newval:
								rr = UserRoles.query.filter(UserRoles.member_id == member.id).filter(UserRoles.role_id == db.session.query(Role.id).filter(Role.name == r)).one_or_none()
								if rr: 
										db.session.delete(rr)
										flash("Removed %s privs" % r)
						elif newval and not oldval:
								rr = UserRoles(member_id = member.id,role_id = db.session.query(Role.id).filter(Role.name == r))
								flash("Added %s privs" % r)
								db.session.add(rr)


				if key.startswith("orgaccess_"):
						oldcheck = request.form[key]=='on'
						r = key.replace("orgaccess_","")
						resource = Resource.query.filter(Resource.name==r).one()
                                                (myPerms,alstr) = authutil.getResourcePrivs(resource=resource)
						if "privs_"+r in request.form:
								p = int(request.form['privs_'+r])
						else:
								p = 0

						try:
								alstr = AccessByMember.ACCESS_LEVEL[p]
						except:
								alstr = "???"

						newcheck=False
						if "access_"+r in request.form:
								newcheck=True

						# TODO do we have privs to do this?? (Check levels too)
						# TODO Don't allow someone to "demote" someone of higher privledge
						if myPerms >= 1:
								# Find existing privs or not
								# There are THREE levels of privileges at play here:
								# acc.level - The OLD level for this record
								# p - the NEW level we are trying to change to
								# myPerm - The permissions level of the user making this change

								# Find existing record
								acc = AccessByMember.query.filter(AccessByMember.member_id == member.id)
								acc = acc.filter(resource.id == AccessByMember.resource_id)
								acc = acc.one_or_none()

								if acc is None and newcheck == False:
										# Was off - and no change - Do nothing
										continue
								elif acc is None and newcheck == True:
										# Was off - but we turned it on - Create new one
										db.session.add(Logs(member_id=member.id,resource_id=resource.id,event_type=eventtypes.RATTBE_LOGEVENT_RESOURCE_ACCESS_GRANTED.id))
										acc = AccessByMember(member_id=member.id,resource_id=resource.id)
										db.session.add(acc)
								elif acc and newcheck == False and p<=myPerms:
										flash("You aren't authorized to disable %s privs on %s" % (alstr,r))

								if (p>=myPerms):
										flash("You aren't authorized to grant %s privs on %s" % (alstr,r))
								elif (acc.level >= myPerms):
										flash("You aren't authorized to demote %s privs on %s" % (alstr,r))
								elif acc.level != p:
										db.session.add(Logs(member_id=member.id,resource_id=resource.id,event_type=eventtypes.RATTBE_LOGEVENT_RESOURCE_PRIV_CHANGE.id,message=alstr))
										acc.level=p

								if acc and newcheck == False and acc.level < myPerms:
										#delete
										db.session.add(Logs(member_id=mm.id,resource_id=resource.id,event_type=eventtypes.RATTBE_LOGEVENT_RESOURCE_ACCESS_REVOKED.id))
										db.session.delete(acc)


		db.session.commit()
		flash("Member access updated")
		authutil.kick_backend()
		return redirect(url_for('member_editaccess',id=mid))

@blueprint.route('/<string:id>/tags', methods = ['GET'])
@login_required
def member_tags(id):
		"""Controller method to gather and display tags associated with a memberid"""
		mid = safestr(id)
		sqlstr = "select tag_ident,tag_type,tag_name from tags_by_member where member = '%s'" % mid
		tags = query_db(sqlstr)
		return render_template('member_tags.html',mid=mid,tags=tags)

@blueprint.route('/updatebackends', methods = ['GET'])
@login_required
def update_backends():
		authutil.kick_backend()
		flash("Backend Update Request Send")
		return redirect(url_for('index'))

@blueprint.route('/<string:id>/tags', methods = ['POST'])
@login_required
def member_tagadd(id):
		"""(Controller) method for POST to add tag for a user, making sure they are not duplicates"""
		mid = safestr(id)
		ntag = safestr(request.form['newtag'])
		ntagtype = safestr(request.form['newtagtype'])
		ntagname = safestr(request.form['newtagname'])
		ntag = authutil.rfid_validate(ntag)
		if ntag is None:
				flash("ERROR: The specified RFID tag is invalid, must be 10-digit all-numeric")
		else:
				if add_member_tag(mid,ntag,ntagtype,ntagname):
						authutil.kick_backend()
						flash("Tag added.")
				else:
						flash("Error: That tag is already associated with a user")
		return redirect(url_for('member_tags',id=mid))

@blueprint.route('/<string:id>/tags/delete/<string:tag_ident>', methods = ['GET'])
@login_required
def member_tagdelete(id,tag_ident):
		"""(Controller) Delete a Tag from a Member (HTTP GET, for use from a href link)"""
		mid = safestr(id)
		tid = authutil.rfid_validate(tag_ident)
		if not tid:
				flash("Invalid Tag - Must be 10 digit numeric")
		else:
			sqlstr = "delete from tags_by_member where tag_ident = '%s' and member = '%s'" % (tid,mid)
			execute_db(sqlstr)
			get_db().commit()
			authutil.kick_backend()
			flash("If that tag was associated with the current user, it was removed")
		return redirect(url_for('member_tags',id=mid))

def register_pages(app):
	app.register_blueprint(blueprint)