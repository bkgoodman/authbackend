#vim:shiftwidth=2:expandtab

from ..templateCommon import  *

from authlibs import accesslib
import stripe
from datetime import datetime,timedelta
from ..membership import createMissingMemberAccounts
import calendar
import json
import pickle
import re
import redis
from pytz import UTC

blueprint = Blueprint("signup", __name__, template_folder='templates', static_folder="static",url_prefix="/signup")


@blueprint.route('/', methods=['GET','POST'])
def signup():

    debug = "DEBUG\n"
    for (k,v) in request.form.items():
        debug += f"Form Key: {k} Value {v}\n"
    for (k,v) in request.args.items():
        debug += f"Args Key: {k} Value: {v}\n"

    return render_template('signup.html',debug=debug)

def addMember(sub,plantype,firstname,lastname,email,subscription):
    name= sessiondata['firstname']+" "+sessiondata['lastname']
    membership = "stripe:"+name.replace(" ",".")+":"+sessiondata['email']
    expires = datetime.utcfromtimestamp(sub['current_period_end'])
    created = datetime.utcfromtimestamp(sub['created'])
    updated = datetime.utcnow()

    # Add Subscription to Database
    s=Subscription(membership=membership)
    s.paysystem = "stripe"
    s.subid = checkout_session['subscription']
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
    logger.debug("Adding new member %s for subscription %s MemberID %s" % (name, subscription,mm.id))
    s.member_id=mm.id
    db.session.add(s)
    db.session.add(Logs(member_id=mm.id,event_type=eventtypes.RATTBE_LOGEVENT_CONFIG_NEW_MEMBER_PAYSYS.id))
    return (s,mm)

@blueprint.route('/postpay', methods=['GET','POST'])
def postpay():

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

    addMember(sub,plantype,sessiondata['firstname'],sessiondata['lastname'],
            sessiondata['email'],checkout_session['subscription'])

    if (plan == "produo"):
        addMember(sub,plantype,sessiondata['firstname2'],sessiondata['lastname2'],
            sessiondata['email2'],checkout_session['subscription'])


    db.session.commit()

    createMissingMemberAccounts([mm],isTest=False)
    return render_template('complete.html',debug=debug,email=sessiondata['email'],mtype=sessiondata['mtype'])

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
    logger.warning("FORM DATA: "+str(request.form.items()))
    logger.warning("SESSION INFO: "+str(session))
    logger.warning("Session ID: "+str(session['id']))


    sessiondata = {
            "firstname":request.form.get("firstname"),
            "lastname":request.form.get("lastname"),
            "phone":request.form.get("phone"),
            "email":request.form.get("email"),
            "mtype":mtype
            }
    if (mtype == "produo"):
        sessiondata["firstname2"] = request.form.get("firstname2"),
        sessiondata["lastname2"] = request.form.get("lastname2"),
        sessiondata["phone2"] = request.form.get("phone2"),
        sessiondata["email2"] = request.form.get("email2"),
            
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
        mode="payment",
        success_url="success?session_id={CHECKOUT_SESSION_ID}",
        cancel_url="https://yourwebsite.com/cancel",
    )
    return redirect(checkout_session.url, code=303)
    #return jsonify({"session_id": session.id})



"""

Customer billing managment portal???
we need to get the customer id elsewhere

@app.route('/create-portal-session', methods=['POST'])
def customer_portal():
    # For demonstration purposes, we're using the Checkout session to retrieve the customer ID.
    # Typically this is stored alongside the authenticated user in your database.
    checkout_session_id = request.form.get('session_id')
    checkout_session = stripe.checkout.Session.retrieve(checkout_session_id)

    # This is the URL to which the customer will be redirected after they are
    # done managing their billing with the portal.
    return_url = YOUR_DOMAIN

    portalSession = stripe.billing_portal.Session.create(
        customer=checkout_session.customer,
        return_url=return_url,
    )
    return redirect(portalSession.url, code=303)
"""

def register_pages(app):
	app.register_blueprint(blueprint)
