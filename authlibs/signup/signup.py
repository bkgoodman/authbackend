#vim:shiftwidth=2:expandtab

from ..templateCommon import  *

from authlibs import accesslib
import stripe
import qrcode,io
from datetime import datetime,timedelta
from ..membership import createMissingMemberAccounts
import calendar
import json
import pickle
import re
import socket
import redis
import hashlib
import base64
from pytz import UTC
from flask import make_response

blueprint = Blueprint("signup", __name__, template_folder='templates', static_folder="static",url_prefix="/signup")

# New Mebership Signup - Self Service Portal

# Takes Stripe Subscription Object and subcription id
# Returns subscription and member object
def addMember(sub,plantype,firstname,lastname,email):
    name= firstname+" "+lastname
    membership = "stripe:"+name.replace(" ",".")+":"+email
    expires = datetime.utcfromtimestamp(sub['current_period_end'])
    created = datetime.utcfromtimestamp(sub['created'])
    updated = datetime.utcnow()

    # Add Subscription to Database
    s=Subscription(membership=membership)
    s.paysystem = "stripe"
    s.subid = sub.id
    s.customerid = sub['customer']
    s.name = (firstname+" "+lastname)
    s.email = email
    s.plan = plantype
    s.rate_plan = sub['plan']['id']
    s.expires_date = expires
    s.created_date = created
    s.updated_date = updated
    s.membership = membership
    s.checked_date = datetime.utcnow()
    s.active = 'true'

    # Add Member to Database
    mm = Member()
    mm.member = (firstname+" "+lastname).replace(" ",".")
    mm.firstname = firstname
    mm.lastname = lastname
    mm.alt_email = email
    mm.active = 'true'
    mm.plan = plantype
    mm.stripe_name = firstname+" "+lastname
    mm.time_created = created
    mm.time_updated = updated
    mm.email_confirmed_at = datetime.now()
    db.session.add(mm)
    db.session.flush()

    logger.debug("Adding new member %s for subscription %s MemberID %s" % (name, sub.id,mm.id))
    s.member_id=mm.id
    db.session.add(s)
    db.session.add(Logs(member_id=mm.id,event_type=eventtypes.RATTBE_LOGEVENT_CONFIG_NEW_MEMBER_PAYSYS.id))
    return (s,mm)

@blueprint.route('/howdiduhear', methods=['GET','POST'])
def howdiduhear():
    return render_template('wherediduhear.html',where=where,what=what,stuff=stuff,iam=iam)

@blueprint.route('/postpay', methods=['GET','POST'])
def postpay():
    where = [
                {'name':'holidaystroll', 'text':"Nashua Holiday Stroll" },
                {'name':'lksr', 'text':"Lowell Kinetic Sculpture Race" },
                {'name':'makeitfest', 'text':"MakeIt Fest" },
                {'name':'member', 'text':"From another Member" },
                {'name':'social', 'text':"Social Media" },
            ]
    what = [
                {'name':'art', 'text':"Art (Painting, Drawing, Airbrushing, etc." },
                {'name':'blacksmithing', 'text':"Blacksmithing" },
                {'name':'jewelry', 'text':"Jewelry Making and Soft Metals" },
                {'name':'glasswork', 'text':"Glasswork" },
                {'name':'photography', 'text':"Photography & Darkroom" },
                {'name':'pottery', 'text':"Pottery" },
                {'name':'woodworking', 'text':"Woodworking (General, turning & routing)"},
                {'name':'auto', 'text':"Automotive" },
                {'name':'welding', 'text':"Welding" },
                {'name':'machining', 'text':"Machining and Metalwork" },
                {'name':'laser', 'text':"Laser Cutting (wood, metal, acrylic, etc.)" },
                {'name':'ham', 'text':"Radio Operator (Ham)"},
                {'name':'production', 'text':"Procducer (Video, Audio, Podcast, etc)."},
                {'name':'3dprinting', 'text':"3d Printing" },
                {'name':'design', 'text':"CAD & other software tools for physical design" },
                {'name':'software', 'text':"Software (Writing software, web design, etc.)"},
                {'name':'electronics', 'text':"Electronics (Hardware, PCB design, Arduino, etc.)"}
            ]
    stuff = [
                {'name':'learning', 'text':"Taking Classes and Workshops" },
                {'name':'community', 'text':"Community and social events" },
                {'name':'collaberation', 'text':"Partipating in group projects" },
                {'name':'volunteer', 'text':"Volunteering & helping in operation of our lab" },
                {'name':'making', 'text':"Making stuff" },
                {'name':'fixing', 'text':"Fixing/Repairing stuff" },
                {'name':'teaching', 'text':"Teaching Classes and Workshops" },
            ]
    iam = [
                {'name':'engineer', 'text':"Engineer" },
                {'name':'artist', 'text':"Artist" },
                {'name':'hacker', 'text':"Hacker" },
                {'name':'teacher', 'text':"Teacher" },
                {'name':'student', 'text':"Student (lifelong)" },
                {'name':'builder', 'text':"Builder" },
                {'name':'fixer', 'text':"Fixer" },
                {'name':'handson', 'text':"Hands-On" },
                {'name':'madscientist', 'text':"Scientist (Mad)" },
                {'name':'othercientist', 'text':"Scientist (Other)" },
            ]

    debug = "POSTPAY\n"
    for (k,v) in request.form.items():
        debug += f"Form Key: {k} Value {v}\n"
    for (k,v) in request.args.items():
        debug += f"Args Key: {k} Value: {v}\n"

    stripe.api_key = current_app.config['globalConfig'].Config.get('Stripe','token')
    checkout_session_id = request.args.get('session_id')
    checkout_session = stripe.checkout.Session.retrieve(checkout_session_id)
    
    debug += "\n\n"+str(dir(checkout_session))
    debug += "\n\n"+str(dict(checkout_session))

    debug += f"\n\nid: {checkout_session['id']}\n"
    debug += f"object: {checkout_session['object']}\n"
    debug += f"subscription: {checkout_session['subscription']}\n"

    r = redis.Redis()
    ses = r.get("checkoutsession/"+checkout_session['id'])
    if ses is None:
        debug += "No session data"
    sessiondata = json.loads(ses)
    debug += "Session data: "+ses.decode('utf8')
    
    # Now we have a real Stripe subscription, and the data the user registered with.
    # Put it all together.

    
    names = sessiondata['firstname']+" "+sessiondata['lastname']
    print ("Names is: "+names)
    print ("firstname2 is: ",sessiondata['firstname2'])
    print ("lastname2 is: ",sessiondata['lastname2'])
    emails = sessiondata['email']
    if sessiondata['mtype'] == 'produo':
        names += ", "+sessiondata['firstname2']+" "+sessiondata['lastname2']
        emails += ", "+sessiondata['email2']

    stripe.Subscription.modify(
      checkout_session['subscription'],
      metadata={
          "emails": emails,
          "names": names
          }
    )

    sub =  stripe.Subscription.retrieve(checkout_session['subscription'])
    debug += "\n\nSubscription:\n\n"
    debug += str(sub)

    # Add subscription data into Redis for quick reference for 

    sessiondata['subscription'] = checkout_session['subscription']

    r.set("checkoutsession/"+checkout_session['id'],json.dumps(sessiondata))
    r.expire("checkoutsession/"+checkout_session['id'],600)

    plan = sub['plan']['id']
    planname = "hobbyist"
    if plan in ['hobbyist']:
        plantype = "hobbyist"
    elif plan in ['free','pro','produo','board','resourcemgr']:
        plantype = 'pro'
    elif "group_pro" in plan:
        plantype = 'pro'
    elif "group" in plan:
        plantype = 'hobbyist'

    isTest = socket.gethostname()  == "staging"
    isError=False
    try:
        (s,mm) = addMember(sub,plantype,sessiondata['firstname'],sessiondata['lastname'],
                sessiondata['email'])
        createMissingMemberAccounts([mm],isTest=isTest)

        if (plan == "produo"):
            (s,mm) = addMember(sub,plantype,sessiondata['firstname2'],sessiondata['lastname2'],
                sessiondata['email2'])
            createMissingMemberAccounts([mm],isTest=isTest)
        db.session.commit()
    except BaseException as e:
        print (f"Signup error: {sessiondata['email']}: {e}\n")
        isError=True


    return render_template('complete.html',debug=debug,email=sessiondata['email'],
            mtype=sessiondata['mtype'],isError=isError,where=where,what=what,stuff=stuff,iam=iam)

@blueprint.route('/survey',methods=['POST'])
def survey():

    results = datetime.now().isoformat()+": "
    for x in request.form:
        if x.startswith("other_"):
            s = request.form.get(x).replace("\"","'")
            s = s.replace(" ","_")
            results += f"{x}: \"{s}\" "
        else:
            results += f"{x} "

    with open("survey.txt","a") as fd:
        fd.write(results+"\n")
    return render_template('survey_complete.html',results=results)

@blueprint.route('/payment', methods=['GET','POST'])
def payment():
    r = redis.Redis()
    debug = "payment\n"
    for (k,v) in request.form.items():
        debug += f"Form Key: {k} Value {v}\n"
    for (k,v) in request.args.items():
        debug += f"Args Key: {k} Value: {v}\n"

    #return render_template('debug.html',debug=debug)

    mtype = request.form.get("membershipType")

    if (mtype == "produo"):
        if (
                (request.form.get("firstname2").strip() == "") or
                (request.form.get("lastname2").strip() == "") or
                (request.form.get("email2").strip() == "") or
                (request.form.get("phone2").strip() == "")):
            flash("Please make sure ALL fields are complete")
            return redirect(url_for("signup.signup"))

    discounts=[]
    line_item = {
                "price": mtype,  # or "hobbiest"
                "quantity": 1,
            }
    if mtype == "militarypro":
        line_item['price'] = "pro"
        discounts = [
                {
                    "coupon": "militarypro"
                    }
                ]
    stripe.api_key = current_app.config['globalConfig'].Config.get('Stripe','token')
    baseurl = current_app.config['globalConfig'].Config.get('General','baseurl')
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[ line_item ],
        mode="subscription",
        discounts = discounts,
        success_url=baseurl+url_for('signup.postpay')+"?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=baseurl+url_for('signup.failure')
    )

    sessiondata = {
            "firstname":request.form.get("firstname"),
            "lastname":request.form.get("lastname"),
            "phone":request.form.get("phone"),
            "email":request.form.get("email"),
            "mtype":mtype
            }
    if (mtype == "produo"):
        sessiondata["firstname2"] = request.form.get("firstname2")
        sessiondata["lastname2"] = request.form.get("lastname2")
        sessiondata["phone2"] = request.form.get("phone2")
        sessiondata["email2"] = request.form.get("email2")
            
    r.set("checkoutsession/"+session['id'],json.dumps(sessiondata))
    r.expire("checkoutsession/"+session['id'],600)
    return redirect(session.url, code=303)

@blueprint.route('/success', methods=['GET','POST'])
def success():
    debug = "SUCCESS\n"
    for (k,v) in request.form.items():
        debug += f"Form Key: {k} Value {v}\n"
    for (k,v) in request.args.items():
        debug += f"Args Key: {k} Value: {v}\n"

    return render_template('debug.html',debug=debug)

@blueprint.route('/failure', methods=['GET','POST'])
def failure():
    debug = "FAILURE\n"
    for (k,v) in request.form.items():
        debug += f"Form Key: {k} Value {v}\n"
    for (k,v) in request.args.items():
        debug += f"Args Key: {k} Value: {v}\n"

    return render_template('debug.html',debug=debug)

@blueprint.route("/qrcode/<string:code>")
def qr(code):
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
    baseurl = current_app.config['globalConfig'].Config.get('General','baseurl')
    qr.add_data(baseurl+url_for("signup.redeem",code=code))
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    byte_data = buffer.getvalue()
    response = make_response(byte_data)
    response.headers['Content-Type'] = 'image/png'
    return response

@blueprint.route("/start_payment_session")
def start_payment_session():
    stripe.api_key = current_app.config['globalConfig'].Config.get('Stripe','token')
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        metadata = {
            "firstname":request.form.get('firstname'),
            "lastname":request.form.get('lastname'),
            },
        custom_fields = [
                {
                    "key":"XXfirstname",
                    "label":"XXfirstname",
                    "type":"text"
                },
                {
                    "key":"lll",
                    "label":"lll",
                    "type":"text"
                }
            ],
        line_items=[
            {
                "price": "pro",  # or "hobbiest"
                "quantity": 1,
            }
        ],
        mode="subscription",
        success_url="success?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=baseurl+url_for("signup.payupdate")
    )
    return redirect(checkout_session.url, code=303)
    #return jsonify({"session_id": session.id})


@blueprint.route("/modify")
def modify():
    url = current_app.config['globalConfig'].Config.get('Stripe','modify_billing_url')
    return redirect(url, code=303)

@blueprint.route('/', methods=['GET','POST'])
def signup():

    debug = "DEBUG\n"
    for (k,v) in request.form.items():
        debug += f"Form Key: {k} Value {v}\n"
    for (k,v) in request.args.items():
        debug += f"Args Key: {k} Value: {v}\n"

    return render_template('signup.html',debug=debug)

def register_pages(app):
	app.register_blueprint(blueprint)
