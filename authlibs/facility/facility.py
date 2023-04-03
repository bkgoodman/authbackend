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
import paho.mqtt.publish as mqtt_pub

blueprint = Blueprint("facility", __name__, template_folder='templates', static_folder="static",url_prefix="/facility")


temperatures=[50,55,60,65,68,70,72,74,76,80,85]

# Take a temperature, make sure it best-fits into one of the "temperature" buckets

def round_to_closest(number, value1, value2):
    if abs(number - value1) < abs(number - value2):
        return value1
    else:
        return value2

def normalize_temp(temp):
        if (temp < temperatures[0]):
            return temperatures[0]
        if (temp > temperatures[-1]):
            return temperatures[-1]

        for (h,l) in [(temperatures[i],temperatures[i+1]) for (i,z) in enumerate(temperatures[0:-1])]: 
            if ((temp >= h) and (temp < l)):
                return round_to_closest(temp,l,h)
        return 0

@blueprint.route('/minisplits', methods=['GET','POST'])
@login_required
def minisplit():
    # First, process POST data if any
    if request.method == "POST" and 'override' in request.form:
        try:
          gc= current_app.config['globalConfig']
          topic=  "facility/minisplit/request/"+request.form['override']
          command={'do_override':True}
          message = json.dumps(command)
          mqtt_pub.single(topic, message, hostname=gc.mqtt_host,port=gc.mqtt_port,**gc.mqtt_opts)
          flash("Override Enabled","success")
        except BaseException as e:
            flash("Error updating Minisplit","warning")
            logger.debug("MQTT minisplit failed to publish: "+str(e))
        return redirect(url_for('facility.minisplit'))
    elif request.method == "POST" and 'cancelOverride' in request.form:
        try:
          gc= current_app.config['globalConfig']
          topic=  "facility/minisplit/request/"+request.form['cancelOverride']
          command={'cancel_override':True}
          message = json.dumps(command)
          mqtt_pub.single(topic, message, hostname=gc.mqtt_host,port=gc.mqtt_port,**gc.mqtt_opts)
          flash("Override Canceled","success")
        except BaseException as e:
            flash("Error updating Minisplit","warning")
            logger.debug("MQTT minisplit failed to publish: "+str(e))
        return redirect(url_for('facility.minisplit'))
        return redirect(url_for('facility.minisplit'))

    elif request.method == "POST" and current_user.privs('Facilities'):
        command = {}
        if 'power' in request.form:
            command['power'] = request.form['power'].upper()
        if 'fan' in request.form:
            command['fan'] = request.form['fan'].upper()
        if 'mode' in request.form:
            command['mode'] = request.form['mode'].upper()
        if 'temp' in request.form:
            command['temp'] = int(request.form['temp'])
        if 'managed' in request.form:
            command['managed'] = request.form['managed']
        if 'managed_setpoint' in request.form:
            command['managed_setpoint'] = int(request.form['managed_setpoint'])
        if 'managed_setpoint_unoccupied' in request.form:
            command['managed_setpoint_unoccupied'] = int(request.form['managed_setpoint_unoccupied'])
        if 'override_setpoint' in request.form:
            command['override_setpoint'] = int(request.form['override_setpoint'])
        if 'override_time' in request.form:
            command['override_time'] = int(request.form['override_time'])
        if 'ir_interval' in request.form:
            command['ir_interval'] = int(request.form['ir_interval'])
        try:
          gc= current_app.config['globalConfig']
          topic=  "facility/minisplit/request/"+request.form['minisplit']
          message = json.dumps(command)
          mqtt_pub.single(topic, message, hostname=gc.mqtt_host,port=gc.mqtt_port,**gc.mqtt_opts)
        except BaseException as e:
            flash("Error updating Minisplit","warning")
            logger.debug("MQTT minisplit failed to publish: "+str(e))
        return redirect(url_for('facility.minisplit'))

    r = redis.Redis()
    minisplits=[]
    now=datetime.datetime.now()
    utc = dateutil.tz.gettz('UTC')
    eastern = dateutil.tz.gettz('US/Eastern')
    for m in (r.keys("minisplit/*")):
        ms = r.get(m)
        j = json.loads(ms)
        if (j['override_end'] != ""):
            ovend_obj = datetime.datetime.strptime(j['override_end'], '%a %b %d %H:%M:%S %Y')
            axx=ovend_obj.replace(tzinfo=utc).astimezone(eastern).replace(tzinfo=None)
            ovend=ago.ago(axx,now)
        else:
            ovend=["","",""]
        dt_obj = datetime.datetime.strptime(j['time'], '%a %b %d %H:%M:%S %Y')

        axx=dt_obj.replace(tzinfo=utc).astimezone(eastern).replace(tzinfo=None)
        acl=ago.ago(axx,now)
        minisplits.append({
            'name': m.decode('utf-8').replace("minisplit/",""),
            'rawSetPoint': j['setpoint'],
            'setPoint': normalize_temp(j['setpoint']),
            'roomTemp': j['roomTemp'],
            'mode': j['mode'],
            'power': j['power'],
            'managed': j['managed'],
            'managed_setpoint': normalize_temp(j['managed_setpoint']),
            'managed_setpoint_unoccupied': normalize_temp(j['managed_setpoint_unoccupied']),
            'override_temp': normalize_temp(j['override_temp']),
            'override_time': j['override_time'],
            'ir_interval': j['ir_interval'],
            'fan': j['fan'],
            'ipaddr': j['ip'],
            'rssid': j['rssid'],
            'fwversion': j['fw'],
            'lastupdate':acl[0],
            'lastupdate2':acl[1],
            'override_end':ovend[0],
            'override_end_ago':ovend[1],
            'operating':j['operating']
            })
    return render_template('minisplits.html',minisplits=minisplits,temperatures=temperatures)

def register_pages(app):
	app.register_blueprint(blueprint)
