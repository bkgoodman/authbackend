# vim:shiftwidth=2:noexpandtab

from ..templateCommon import  *

from authlibs import accesslib
from authlibs.comments import comments
from json import dumps as json_dumps
import datetime

blueprint = Blueprint("graphs", __name__, template_folder='templates', static_folder="static",url_prefix="/resource/graphs/api")

def daynum(dt):
	return (dt - datetime.datetime(2000,1,1)).days

@blueprint.route('/v1/weekly/<string:id>', methods=['GET'])
@login_required
def weekly(id):
	"""(Controller) Display information about a given resource"""
	tools = Tool.query.filter(Tool.resource_id==id).all()
	r = Resource.query.filter(Resource.id==id).one()

	if not current_user.privs('HeadRM','RATT') and accesslib.user_privs_on_resource(member=current_user,resource=r) < AccessByMember.LEVEL_ARM:
		return "NOAccess",403

	q = UsageLog.query.filter(UsageLog.time_logged>=datetime.datetime.now()-datetime.timedelta(days=9))
	q = q.filter(UsageLog.time_logged<=datetime.datetime.now()+datetime.timedelta(days=1))
	q = q.order_by(UsageLog.time_logged)
	q = q.filter(UsageLog.resource_id == r.id)
	q = q.all()

	dow=['Mon','Tues','Wed','Thurs','Fri','Sat','Sun']
	data=[['Day','Enabled','Active','Idle']]
	now = datetime.datetime.now()
	nowday = daynum(now)
	daydata=[]
	for _ in range (0,7):
		daydata.append({'dow':"??",'enabled':0,'active':0,'idle':0})

	for x in q:
		t = x.time_logged
		dn = daynum(t)
		daydelta = nowday-dn
		if ((daydelta <=7) and (daydelta >= 1)):
			daydata[daydelta-1]['enabled'] += x.enabledSecs
			daydata[daydelta-1]['idle'] += x.idleSecs
			daydata[daydelta-1]['active'] += x.activeSecs

	for i in range(0,7):
		daydata[i]['dow'] = dow[(i+now.weekday())%7]
	for x in daydata:
		data.append([x['dow'],x['enabled'],x['active'],x['idle']])
	out={'data':data,'type':'area','opts':{
		'title':"Weekly stuff",
		'hAxis':{'title': 'Day',  'titleTextStyle': {'color': '#333'}},
		'vAxis': {'minValue': 0}
		}}
	return json_dumps(out)

@blueprint.route('/v1/monthly/<string:id>', methods=['GET'])
@login_required
def monthly(id):
	"""(Controller) Display information about a given resource"""
	tools = Tool.query.filter(Tool.resource_id==id).all()
	r = Resource.query.filter(Resource.id==id).one()

	if not current_user.privs('HeadRM','RATT') and accesslib.user_privs_on_resource(member=current_user,resource=r) < AccessByMember.LEVEL_ARM:
		return "NOAccess",403

	q = UsageLog.query.filter(UsageLog.time_logged>=datetime.datetime.now()-datetime.timedelta(days=32))
	q = q.filter(UsageLog.time_logged<=datetime.datetime.now()+datetime.timedelta(days=1))
	q = q.order_by(UsageLog.time_logged)
	q = q.filter(UsageLog.resource_id == r.id)
	q = q.all()

	dow=['Mon','Tues','Wed','Thurs','Fri','Sat','Sun']
	data=[['Day','Enabled','Active','Idle']]
	now = datetime.datetime.now()
	nowday = daynum(now)
	daydata=[]
	for _ in range (0,30):
		daydata.append({'dom':"??",'enabled':0,'active':0,'idle':0})

	for x in q:
		t = x.time_logged
		dn = daynum(t)
		daydelta = nowday-dn
		if ((daydelta <=30) and (daydelta >= 1)):
			daydata[daydelta-1]['enabled'] += x.enabledSecs
			daydata[daydelta-1]['idle'] += x.idleSecs
			daydata[daydelta-1]['active'] += x.activeSecs
			daydata[daydelta-1]['dom'] = x.time_logged.day

	for x in daydata:
		y= [str(x['dom']),x['enabled'],x['active'],x['idle']]
		data.append(y);
	out={'data':data,'type':'area','opts':{
		'title':"Monthy Usage Data`",
		'hAxis':{'title': 'Day',  'titleTextStyle': {'color': '#333'}},
		'vAxis': {'minValue': 0}
		}}
	return json_dumps(out)

@blueprint.route('/v1/weekUsers/<string:id>', methods=['GET'])
@login_required
def weekUsers(id):
	"""(Controller) Display information about a given resource"""
	tools = Tool.query.filter(Tool.resource_id==id).all()
	r = Resource.query.filter(Resource.id==id).one()

	if not current_user.privs('HeadRM','RATT') and accesslib.user_privs_on_resource(member=current_user,resource=r) < AccessByMember.LEVEL_ARM:
		return "NOAccess",403

	q = UsageLog.query.filter(UsageLog.time_logged>=datetime.datetime.now()-datetime.timedelta(days=8))
	q = q.filter(UsageLog.time_logged<=datetime.datetime.now()+datetime.timedelta(days=1))
	q = q.group_by(UsageLog.member_id)
	q = q.filter(UsageLog.resource_id == r.id)
	q = q.add_column(func.sum(UsageLog.enabledSecs).label('enabled'))
	q = q.add_column(func.sum(UsageLog.idleSecs).label('idle'))
	q = q.add_column(func.sum(UsageLog.activeSecs).label('active'))
	q = q.add_column(UsageLog.member_id.label('memberid'))
	q = q.all()

	data=[]
	totalenabled=0
	for x in q:
		print x
		data.append({'member_id':x.memberid,'enabled':x.enabled})
		totalenabled += x.enabled

	out = []
	for x in sorted(data,key=lambda x:x['enabled']):
		out.append(x)

	if len(out)> 10:
		out=out[0:9]
		toptotal=0
		for x in out:
			toptotal += x['enabled']
		out.append({'member_id':0,'enabled':totalenabled-toptotal})

	# Find usernames

	for x in out:
		if x['member_id']==0:
			x['member'] = 'Total'
		else:
			x['member'] = Member.query.filter(Member.id == x['member_id']).one().member
	
	out2=[['Member','Enabled']]
	for x in out:
		out2.append([x['member'],x['enabled']])

	out={'data':out2,'type':'pie','opts':{
		'title':"Monthy Top Users`",
		'hAxis':{'title': 'Name',  'titleTextStyle': {'color': '#333'}},
		'vAxis': {'minValue': 0}
		}}
	out = json_dumps(out)
	return out,200

def register_pages(app):
	app.register_blueprint(blueprint)
