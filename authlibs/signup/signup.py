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
import redis
from pytz import UTC
from flask import make_response

blueprint = Blueprint("signup", __name__, template_folder='templates', static_folder="static",url_prefix="/signup")


@blueprint.route('/', methods=['GET','POST'])
def signup():

    debug = "DEBUG\n"
    for (k,v) in request.form.items():
        debug += f"Form Key: {k} Value {v}\n"
    for (k,v) in request.args.items():
        debug += f"Args Key: {k} Value: {v}\n"

    return render_template('signup.html',debug=debug)

@blueprint.route('/gift', methods=['GET','POST'])
def gift():

    debug = "DEBUG\n"
    for (k,v) in request.form.items():
        debug += f"Form Key: {k} Value {v}\n"
    for (k,v) in request.args.items():
        debug += f"Args Key: {k} Value: {v}\n"

    return render_template('gift.html',debug=debug)

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

# Process user form to redeem a membership
@blueprint.route('/redeem_activate', methods=['POST'])
def redeem_activate():
    # Re-Verify that gift purchase is valid and has not been redeemed


    stripe.api_key = current_app.config['globalConfig'].Config.get('Stripe','token')
    # Create Subscription

    addMember(sub,plantype,sessiondata['firstname'],sessiondata['lastname'],
            sessiondata['email'],checkout_session['subscription'])

    db.session.commit()
    createMissingMemberAccounts([mm],isTest=False)

    # Mark gift purchase as Redeemed
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

@blueprint.route('/gift_payment', methods=['GET','POST'])
def gift_payment():
    try:
        r = redis.Redis()
        debug = "gift_payment\n"
        for (k,v) in request.form.items():
            debug += f"Form Key: {k} Value {v}\n"
        for (k,v) in request.args.items():
            debug += f"Args Key: {k} Value: {v}\n"

        discounts=[]
        line_item = {
                    "price": "3mogift",
                    "quantity": 1,
                }

        recipname = ""
        if request.form.get("gift_to") is not None:
            recipname = request.form.get("gift_to")

        giftfrom = ""
        if request.form.get("gift_from") is not None:
            giftfrom = request.form.get("gift_from")

        customtext = ""
        if recipname != "":
            customtext = "Gift membership for "+recipname
        
        stripe.api_key = current_app.config['globalConfig'].Config.get('Stripe','token')
        baseurl = current_app.config['globalConfig'].Config.get('General','baseurl')
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            customer_email=request.form.get("email"),
            line_items=[ line_item ],
            mode="payment",
            custom_text={"submit":{"message":f"Enter YOUR information above. {customtext}"}},
            payment_intent_data={
                "metadata": {
                    "recipient":recipname,
                    "giftfrom":giftfrom
                    },
                "description": f"Gift Membership for {recipname}"
                },
            discounts = discounts,
            success_url=baseurl+url_for('signup.gift_postpay')+"?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=baseurl+url_for('signup.gift_failure')
        )
        logger.warning("FORM DATA: "+str(request.form.items()))
        logger.warning("SESSION INFO: "+str(session))
        logger.warning("Session ID: "+str(session['id']))


        sessiondata = {
                "gift_from":request.form.get("gift_from"),
                "phone":request.form.get("phone"),
                "email":request.form.get("email"),
                "gift_to":request.form.get("gift_to"),
                "to_email":request.form.get("to_email")
                }
                
        r.set("checkoutsession/"+session['id'],json.dumps(sessiondata))
        r.expire("checkoutsession/"+session['id'],3600)
    except BaseException as e:
        flash(f"Error: {e}",'danger')
        return redirect(url_for("signup.gift"))

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

@blueprint.route('/gift_failure', methods=['GET','POST'])
def gift_failure():
    debug = "GIFT FAILURE\n"
    for (k,v) in request.form.items():
        debug += f"Form Key: {k} Value {v}\n"
    for (k,v) in request.args.items():
        debug += f"Args Key: {k} Value: {v}\n"

    return render_template('debug.html',debug=debug)

@blueprint.route('/gift_postpay', methods=['GET','POST'])
def gift_postpay():
    debug = "GIFT POSTPAY\n"
    for (k,v) in request.form.items():
        debug += f"Form Key: {k} Value {v}\n"
    for (k,v) in request.args.items():
        debug += f"Args Key: {k} Value: {v}\n"

    stripe.api_key = current_app.config['globalConfig'].Config.get('Stripe','token')
    checkout_session_id = request.args.get('session_id')
    checkout_session = stripe.checkout.Session.retrieve(checkout_session_id)

    debug += f"\n\nid: {checkout_session['id']}\n"
    debug += f"object: {checkout_session['object']}\n"
    debug += f"payment code: {checkout_session['payment_intent']}\n"
    debug += f"object: {checkout_session}\n"

    r = redis.Redis()
    ses = r.get("checkoutsession/"+checkout_session['id'])
    if ses is None:
        debug += "No session data"
    sessiondata = json.loads(ses)
    debug += "Session data: "+ses.decode('utf8')
    opts = {
        "gift_to":sessiondata['gift_to'],
        "gift_from":sessiondata['gift_from'],
        "code":checkout_session['payment_intent'],
        "baseurl": current_app.config['globalConfig'].Config.get('General','baseurl')
            }

    return render_template('gift_post.html',debug=debug, **opts)

@blueprint.route("/redeem",methods=['POST','GET'])
@blueprint.route("/redeem/<string:code>",methods=['GET'])
def redeem(code=None):
    if 'code' in request.form:
        code = request.form.get('code')
    if code is None:
        return render_template('redeem_code.html')
    stripe.api_key = current_app.config['globalConfig'].Config.get('Stripe','token')
    debug=f"code = {code}"
    try:
        pi = stripe.PaymentIntent.retrieve(code)
        md = pi['metadata']
        debug += "\n\n"+str(md)

        if 'activated' in md:
            flash ('This gift membership has already been activated. if you believe you have received this message in error, please email info@makeitlabs.com for help.','danger')
            return redirect(url_for("signup.redeem"))

        return render_template('redeem.html',gift_to=md['recipient'],debug=debug,code=code)
    except stripe.error.InvalidRequestError as e:
        flash ("The specified redemption code does not exist.  If you believe you have received this message in error, please email info@makeitlabs.com for help.",'danger')
        return redirect(url_for("signup.redeem"))

    except BaseException as e:
        debug += f"\nError getting code: {e} {type(e)}"

    debug += "\n\nPlease email info@makeitlabs.com for more assitance"
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
        mode="payment",
        success_url="success?session_id={CHECKOUT_SESSION_ID}",
        cancel_url="https://yourwebsite.com/cancel",
    )
    return redirect(checkout_session.url, code=303)
    #return jsonify({"session_id": session.id})


@blueprint.route("/modify")
def modify():
    url = current_app.config['globalConfig'].Config.get('Stripe','modify_billing_url')
    return redirect(url, code=303)


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
