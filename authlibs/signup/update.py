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

blueprint = Blueprint("membershipupdate", __name__, template_folder='templates', static_folder="static",url_prefix="/membershipupdate")
# This is the one that will actually do something, that you will
# Get to only after receiving the link from the "fix" page, below
@blueprint.route('/fix2/<string:digest>/<int:now>/<string:email>', methods=['GET','POST'])
def fix2(digest,now,email):
    debug=f"{digest}\n{now}\n{email}"
    message=""

    # Verify digest
    secret_key =  current_app.config['globalConfig'].Config.get('General','SecretKey')
    sha = hashlib.sha256()
    sha.update(secret_key.encode('utf-8'))
    sha.update(email.encode('utf-8'))
    sha.update(now.to_bytes(8,byteorder="big"))

    calc_digest = base64.urlsafe_b64encode(sha.digest()).decode()

    if (calc_digest != digest):
        return render_template('message.html',title="Update or Reactivate Membership",message="Invalid Link")

    currenttime = int(datetime.utcnow().timestamp())
    if ((now+3600) < currenttime):
        return render_template('message.html',title="Update or Reactivate Membership",message="Link has expired. Please try again.")

    # See if we can find a valid membership
    members = Member.query.filter(
        or_(
            func.lower(Member.alt_email) == func.lower(email),
            func.lower(Member.email) == func.lower(email)
        )
    ).all()
    debug += str(members)
    debug += "\n\n"

    textmsg=""
    custids=[]
    subids=[]
    active=0
    plan = None
    rateplan = None
    if len(members)==0:
        return render_template('message.html',title="Update or Reactivate Membership",message="No membership found for that email address")

    fullname=""
    for m in members:
        fullname = m.member.replace("."," ")
        for s in Subscription.query.filter(Subscription.member_id == m.id).all():
            active = s.active
            plan = s.plan
            rateplan = s.rate_plan
            if s.subid not in subids: subids.append(s.subid)
            if s.customerid not in custids: custids.append(s.customerid)

    if len(subids)!=1:
        return render_template('message.html',message="Multiple subscriptions exist. Please email for assistance.")
    if len(custids)!=1:
        return render_template('message.html',message="Multiple customer records exist. Please email for assistance.")

    """
    if active == "true":
        # TODO - allow simple credit card update
        return render_template('debug.html',debug="Click here to update active credit-card on-file")
    debug += f"Active is {active} {type(active)}\n"
    """

    # Member needs a new subscription
    debug += f"We will need to recreate plan {plan} rateplan {rateplan} Active: {active}\n"
    stripe.api_key = current_app.config['globalConfig'].Config.get('Stripe','token')
    stripe.api_version = '2020-08-27'

    c = stripe.Customer.retrieve(custids[0])
    if c['invoice_settings']['default_payment_method'] is None or request.args.get('updatecc') is not None:
        ## NO CARD ON FILE - MAKE USER SPECIFY ONE
        baseurl = current_app.config['globalConfig'].Config.get('General','baseurl')
        session = stripe.checkout.Session.create(
            customer = c,
            payment_method_types=["card"],
            mode="setup",
            success_url=baseurl+url_for('membershipupdate.fix_postpay')+"?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=baseurl+url_for("membershipupdate.payupdate")
        )
        debug += f"Customer: {c}\n"
        #return redirect(session.url, code=303)
        debug += f"Update cc URL: {session.url}\n"
        # TODO Go to this link
        return render_template('debug.html', debug=debug)

    balance = c['balance']

    ss = stripe.Subscription.list(customer=custids[0])
    if (len(ss) > 0):
        return render_template('message.html',message="You already have an active subscription. No further action should be required.", 
        rawhtml="Click <a href='"+url_for("membershipupdate.fix2",digest=digest,now=now,email=email,updatecc=1)+"'>HERE</a> to update your credit card on-file.")

    s = stripe.Subscription.retrieve(subids[0])
    price = s['items']['data'][0]['price']['id']
    debug += f"Price is {price}\n"
    debug += str(s)

    return render_template('message.html',message=message,debug=debug)


@blueprint.route('/', methods=['GET'])
def payupdate():
    return render_template('payupdate.html')


# This doesn't do anything execpt send you a link
@blueprint.route('/fix', methods=['GET','POST'])
def fix():

    debug = "FIX\n"
    emailtext = ""
    for (k,v) in request.form.items():
        debug += f"Form Key: {k} Value {v}\n"
    for (k,v) in request.args.items():
        debug += f"Args Key: {k} Value: {v}\n"

    if 'email' not in request.form:
        debug += "No email address specified\n"
        return render_template('message.html',message="No email address specified")
    email = request.form['email'].strip()
    members = Member.query.filter(
        or_(
            func.lower(Member.alt_email) == func.lower(email),
            func.lower(Member.email) == func.lower(email)
        )
    ).all()
    debug += str(members)

    if len(members)==0:
        emailtext="No membership with that email was found.\n"
    elif len(members)>1:
        emailtext="Multiple memberships were found with that email address. Please specify which you are trying to reactivate.\n"
    else:
        altemail = members[0].alt_email
        email = members[0].email
        emailtext=f"Membership found: {email} {altemail}"

    now = int(datetime.utcnow().timestamp())
    secret_key =  current_app.config['globalConfig'].Config.get('General','SecretKey')
    sha = hashlib.sha256()
    sha.update(secret_key.encode('utf-8'))
    sha.update(email.encode('utf-8'))
    sha.update(now.to_bytes(8,byteorder="big"))

    baseurl = current_app.config['globalConfig'].Config.get('General','baseurl')
    digest = base64.urlsafe_b64encode(sha.digest()).decode()
    url = baseurl+url_for("membershipupdate.fix2",now=now,digest=digest,email=email)
    debug += f"UTCNOW: {now}\n"
    debug += f"SecretKe: {secret_key}\n"
    debug += f"Digest: {digest}\n"
    debug += f"URL: {url}\n"
    debug += "\n\nEmail Text:\n\n"+emailtext
    return render_template('message.html',message="A message will be sent to the email address on-file for this membership, if one has been found.",debug=debug)


# Takes Stripe Subscription Object and subcription id
# Returns subscription and member object
# TODO
def fixMemberSubscription(sub):

    expires = datetime.utcfromtimestamp(sub['current_period_end'])
    created = datetime.utcfromtimestamp(sub['created'])
    updated = datetime.utcnow()
    s = Subscription.query.filter(Subscription.customerid == sub['customer']).one()

    # Add Subscription to Database
    s.paysystem = "stripe"
    s.subid = sub.id
    s.rate_plan = sub['plan']['id']
    s.expires_date = expires
    s.created_date = created
    s.updated_date = updated
    s.checked_date = datetime.utcnow()
    s.active = 'true'
    db.session.commit()

    db.session.add(Logs(member_id=s.member_id,event_type=eventtypes.RATTBE_LOGEVENT_MEMBER_REACTIVATED.id))
    authutil.kick_backend()
    return

def sanistring(str):
    if str is None:
        return ""
    return str.strip()

# This is where we get AFTER we have gone through stripe to give it
# an updated credit card
@blueprint.route('/fix_postpay', methods=['GET','POST'])
def fix_postpay():
    # TODO ADD BETTER TEMPLATE
    stripe.api_key = current_app.config['globalConfig'].Config.get('Stripe','token')
    checkout_session_id = request.args.get('session_id')
    checkout_session = stripe.checkout.Session.retrieve(checkout_session_id)

    debug = "Postpay\n"
    debug += f"\n\nid: {checkout_session['id']}\n"
    debug += f"object: {checkout_session['object']}\n"
    debug += f"payment code: {checkout_session['payment_intent']}\n"
    debug += f"object: {checkout_session}\n"

    # Get the SetupIntent and Cust
    # Make it the DEFAULT payment
    si = checkout_session['setup_intent']
    c = checkout_session['customer']

    try:
        si = stripe.SetupIntent.retrieve(si)
        debug += f"si: {si}\n"
        xx = stripe.Customer.modify(
            c,
            invoice_settings={
                'default_payment_method': si['payment_method']
            },
        )
        debug += f"modify: {xx}\n"

    except BaseException as e:
        debug += f"Error in setting default: {e}\n"

    # Now let's look at subscriptions:
    ss = stripe.Subscription.list(customer=c)
    if (len(ss['data']) == 1):
        s = ss['data'][0]
        debug += f"\n\n\nSUBSCRIPTION\n\n\n{s}\n"
        subid = s['items']['data'][0]['subscription']
        if (s['status'] == "paused" or s['pause_collection'] is not None):
            debug += f"You have an active PAUSED\n"
        elif (s['status'] == "trialing"):
            debug += f"You have an active TRIALING\n"
        elif (s['status'] == "unpaid"):
            debug += f"You have an active UNPAID\n"
        elif (s['status'] == "active"):
            debug += f"You have an active subscription SubID: {subid}\n"
            ## Try to pay this
        # We're done
    else:
        debug += f"No active subscription - let's find most recent one\n"
        ss = stripe.Subscription.list(customer=c,status="ended")
        recent = None
        mostrecent = None
        for s in ss['data']:
            debug += f"Inactive sub: {s.id} {s.cancel_at} {s.ended_at} {s.metadata} Plan: {s.plan} Discounts: {s.discounts}\n"
            if s.ended_at is not None and (recent is None or s.ended_at > recent):
                recent = s.ended_at 
                mostrecent = s
            if s.canceled_at is not None and (recent is None or s.canceled_at > recent):
                recent = s.canceled_at 
                mostrecent = s
        s = mostrecent
        if s is not None:
            debug += f"RECENT sub: {s.id} {s.cancel_at} {s.ended_at} {s.metadata} Plan: {s.plan.id}\n\n"
            debug += f"{s}\n"


            # Plan.id should be same is s.items.data[0].price.id,
            d = []
            """

            Military pro coupons are applied to CUSTOMERS.
            They are automatically applied to subuscriptions
            without us doing so to the subscruptions themselves

            if len(s.discounts) > 0:
                if s.discounts == 'militarypro';
                    d = [{"coupon":"militarypro}]
            """

            try:
                sub = stripe.Subscription.create(
                    customer=c,
                    metadata= s['metadata'],
                    description="Membership renewal",
                    collection_method="charge_automatically",
                    items = [
                        {
                            "price" : s.plan.id,
                            "discounts": d,
                            }
                        ],
                )
                debug += f"NewSub: {sub}\n"

                # If we got here succesfully - make sure membership is reactivated for user.
                fixMemberSubscription(sub)


            except BaseException as e:
                debug += f"Error Creating new subscription: {e}\n"



    return render_template('debug.html',debug=debug)

def register_pages(app):
	app.register_blueprint(blueprint)
