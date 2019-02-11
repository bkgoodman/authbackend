# vim:shiftwidth=2:noexpandtab

from ..templateCommon import  *

from authlibs.comments import comments
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
@roles_required(['Admin','RATT'])
def resource_create():
	"""(Controller) Create a resource from an HTML form POST"""
	r = Resource()
        r.name = (request.form['input_name'])
        r.short = (request.form['input_short'])
        r.description = (request.form['input_description'])
        r.owneremail = (request.form['input_owneremail'])
        r.slack_chan = (request.form['input_slack_chan'])
        r.slack_admin_chan = (request.form['input_slack_admin_chan'])
        r.info_url = (request.form['input_info_url'])
        r.info_text = (request.form['input_info_text'])
        r.slack_info_text = (request.form['input_slack_info_text'])
	db.session.add(r)
        db.session.commit()
	flash("Created.")
	return redirect(url_for('resources.resources'))

@blueprint.route('/<string:resource>', methods=['GET'])
@login_required
def resource_show(resource):
		"""(Controller) Display information about a given resource"""
		r = Resource.query.filter(Resource.name==resource).one_or_none()
		tools = Tool.query.filter(Tool.resource_id==r.id).all()
		if not r:
                    flash("Resource not found")
                    return redirect(url_for('resources.resources'))
                readonly=False
                if (not current_user.privs('RATT')):
                    readonly=True
		cc=comments.get_comments(resource_id=r.id)
		return render_template('resource_edit.html',rec=r,readonly=readonly,tools=tools,comments=cc)

@blueprint.route('/<string:resource>', methods=['POST'])
@login_required
@roles_required(['Admin','RATT'])
def resource_update(resource):
		"""(Controller) Update an existing resource from HTML form POST"""
		rname = (resource)
		r = Resource.query.filter(Resource.id==resource).one_or_none()
		if not r:
                    flash("Error: Resource not found")
                    return redirect(url_for('resources.resources'))
		r.name = (request.form['input_name'])
		r.short = (request.form['input_short'])
		r.description = (request.form['input_description'])
		r.owneremail = (request.form['input_owneremail'])
		r.slack_chan = (request.form['input_slack_chan'])
		r.slack_admin_chan = (request.form['input_slack_admin_chan'])
		r.info_url = (request.form['input_info_url'])
		r.info_text = (request.form['input_info_text'])
		r.slack_info_text = (request.form['input_slack_info_text'])
		db.session.commit()
		flash("Resource updated")
		return redirect(url_for('resources.resources'))

@blueprint.route('/<string:resource>/delete', methods=['POST'])
@roles_required(['Admin','RATT'])
def resource_delete(resource):
		"""(Controller) Delete a resource. Shocking."""
                r = Resource.query.filter(Resource.id == resource).one()
                db.session.delete(r)
                db.session.commit()
		flash("Resource deleted.")
		return redirect(url_for('resources.resources'))

@blueprint.route('/<string:resource>/list', methods=['GET'])
def resource_showusers(resource):
		"""(Controller) Display users who are authorized to use this resource"""
		rid = (resource)
		authusers = db.session.query(AccessByMember.id,AccessByMember.member_id,Member.member,AccessByMember.level)
		authusers = authusers.join(Member,AccessByMember.member_id == Member.id)
		authusers = authusers.filter(AccessByMember.resource_id == db.session.query(Resource.id).filter(Resource.name == rid))
		authusers = authusers.order_by(AccessByMember.level.desc())
		authusers = authusers.all()
		accrec=[]
		for x in authusers:
			level = accessLevelToString(x[3],blanks=[0,-1])
			accrec.append({'member_id':x[1],'member':x[2],'level':level})
			
		return render_template('resource_users.html',resource=rid,accrecs=accrec)

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


def _get_resources():
	q = db.session.query(Resource.name,Resource.owneremail, Resource.description, Resource.id)
	return q.all()

def register_pages(app):
	app.register_blueprint(blueprint)
