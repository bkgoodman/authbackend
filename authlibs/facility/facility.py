# vim:shiftwidth=2


from ..templateCommon import  *
from authlibs.comments import comments
from datetime import datetime
from authlibs import ago
import stripe
import redis
import json
import datetime
from authlibs.slackutils import send_slack_message

blueprint = Blueprint("facility", __name__, template_folder='templates', static_folder="static",url_prefix="/facility")



@blueprint.route('/minisplits', methods=['GET','POST'])
@login_required
def minisplit():
    r = redis.Redis()
    minisplits=[]
    now=datetime.datetime.now()
    utc = dateutil.tz.gettz('UTC')
    eastern = dateutil.tz.gettz('US/Eastern')
    for m in (r.keys("minisplit/*")):
        ms = r.get(m)
        j = json.loads(ms)
        dt_obj = datetime.datetime.strptime(j['time'], '%a %b %d %H:%M:%S %Y')

        axx=dt_obj.replace(tzinfo=utc).astimezone(eastern).replace(tzinfo=None)
        acl=ago.ago(axx,now)
        minisplits.append({
            'name': m.decode('utf-8'),
            'setPoint': j['setpoint'],
            'roomTemp': j['roomTemp'],
            'mode': j['mode'],
            'power': j['power'],
            'fan': j['fan'],
            'rssid': j['rssid'],
            'fwversion': j['fw'],
            'lastupdate':acl[0],
            'lastupdate2':acl[1]
            })
    return render_template('minisplits.html',minisplits=minisplits)

def register_pages(app):
	app.register_blueprint(blueprint)
