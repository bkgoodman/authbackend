#vim:shiftwidth=2:expandtab

from ..templateCommon import  *

from authlibs import accesslib
import stripe
import qrcode,io
from datetime import datetime,timedelta
from ..google_admin import genericEmailSender
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

def reactivate_subscription(customer, custid, subid, debug=""):
    """Reactivate a canceled subscription using the existing card on file."""
    stripe.api_key = current_app.config['globalConfig'].Config.get('Stripe','token')
    
    # Find the most recent ended subscription to get the plan details
    ss = stripe.Subscription.list(customer=custid, status="ended")
    recent = None
    mostrecent = None
    for s in ss['data']:
        if s.ended_at is not None and (recent is None or s.ended_at > recent):
            recent = s.ended_at
            mostrecent = s
        if s.canceled_at is not None and (recent is None or s.canceled_at > recent):
            recent = s.canceled_at
            mostrecent = s
    
    if mostrecent is None:
        return render_template('message.html', title="Error",
            message="Could not find a previous subscription to reactivate. Please contact support.")
    
    try:
        sub = stripe.Subscription.create(
            customer=custid,
            metadata=mostrecent['metadata'],
            description="Membership renewal",
            collection_method="charge_automatically",
            items=[
                {
                    "price": mostrecent.plan.id,
                }
            ],
        )
        # Update local database
        fixMemberSubscription(sub)
        return render_template('message.html', title="Membership Reactivated",
            message="Your membership has been successfully reactivated!")
    except BaseException as e:
        return render_template('message.html', title="Error",
            message=f"An error occurred while reactivating your subscription: {e}")

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
    active="false"
    plan = None
    rateplan = None
    if len(members)==0:
        return render_template('message.html',title="Update or Reactivate Membership",message="No membership found for that email address")

    fullname=""
    for m in members:
        fullname = m.member.replace("."," ")
        for s in Subscription.query.filter(Subscription.member_id == m.id).all():
            if s.active == "true":
                active = s.active
                plan = s.plan
                rateplan = s.rate_plan
                if s.subid not in subids: subids.append(s.subid)
                if s.customerid not in custids: custids.append(s.customerid)

    if len(subids)!=1:
        return render_template('message.html',message="Multiple subscriptions exist. Please email for assistance.")
    if len(custids)!=1:
        return render_template('message.html',message="Multiple customer records exist. Please email for assistance.")

    stripe.api_key = current_app.config['globalConfig'].Config.get('Stripe','token')
    stripe.api_version = '2020-08-27'

    c = stripe.Customer.retrieve(custids[0])
    default_pm = c['invoice_settings']['default_payment_method']
    has_card = default_pm is not None
    card_last4 = None
    if has_card:
        try:
            pm = stripe.PaymentMethod.retrieve(default_pm)
            if pm.card:
                card_last4 = pm.card.last4
        except:
            pass
    baseurl = current_app.config['globalConfig'].Config.get('General','baseurl')

    # Check for action parameter
    action = request.args.get('action')

    # Handle specific actions
    if action == 'updatecc':
        # Redirect to Stripe to update credit card
        session = stripe.checkout.Session.create(
            customer = c,
            payment_method_types=["card"],
            mode="setup",
            success_url=baseurl+url_for('membershipupdate.fix_postpay')+"?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=baseurl+url_for("membershipupdate.payupdate")
        )
        return redirect(session.url, code=303)

    if action == 'cancel':
        # Cancel the active subscription
        ss = stripe.Subscription.list(customer=custids[0])
        if len(ss['data']) > 0:
            try:
                stripe.Subscription.delete(ss['data'][0].id)
                return render_template('message.html', title="Membership Canceled",
                    message="Your membership has been canceled. You will retain access until the end of your current billing period.")
            except BaseException as e:
                return render_template('message.html', title="Error",
                    message=f"An error occurred while canceling your subscription: {e}")
        else:
            return render_template('message.html', title="No Active Subscription",
                message="No active subscription was found to cancel.")

    if action == 'reactivate':
        # Reactivate with existing card on file
        return reactivate_subscription(c, custids[0], subids[0], debug)

    if action == 'reactivate_newcard':
        # Update card first, then reactivate (handled in fix_postpay)
        session = stripe.checkout.Session.create(
            customer = c,
            payment_method_types=["card"],
            mode="setup",
            success_url=baseurl+url_for('membershipupdate.fix_postpay')+"?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=baseurl+url_for("membershipupdate.payupdate")
        )
        return redirect(session.url, code=303)

    # No action specified - show options based on membership status
    ss = stripe.Subscription.list(customer=custids[0])
    options = []

    if len(ss['data']) > 0:
        # Active subscription exists
        options.append({
            'label': 'Update Credit Card on File',
            'url': url_for('membershipupdate.fix2', digest=digest, now=now, email=email, action='updatecc'),
            'confirm': False
        })
        options.append({
            'label': 'Cancel Membership',
            'url': url_for('membershipupdate.fix2', digest=digest, now=now, email=email, action='cancel'),
            'confirm': True
        })
        message = "Your membership is currently active."
    else:
        # No active subscription - membership has been canceled
        message = "Your membership is currently inactive."
        if has_card:
            card_label = f'Reactivate with Existing Card (ending in {card_last4})' if card_last4 else 'Reactivate with Existing Card on File'
            options.append({
                'label': card_label,
                'url': url_for('membershipupdate.fix2', digest=digest, now=now, email=email, action='reactivate'),
                'confirm': True
            })
            options.append({
                'label': 'Update Card and Reactivate',
                'url': url_for('membershipupdate.fix2', digest=digest, now=now, email=email, action='reactivate_newcard'),
                'confirm': False
            })
        else:
            options.append({
                'label': 'Add Credit Card and Reactivate',
                'url': url_for('membershipupdate.fix2', digest=digest, now=now, email=email, action='reactivate_newcard'),
                'confirm': False
            })

    return render_template('fix2_confirm.html', fullname=fullname, email=email, options=options, message=message, debug=debug if current_app.config['globalConfig'].Config.get('General','Debug').lower() == 'true' else None)


@blueprint.route('/', methods=['GET'])
def payupdate():
    return render_template('payupdate.html')


# This doesn't do anything execpt send you a link
@blueprint.route('/fix', methods=['GET','POST'])
def fix():

    isDebug =  current_app.config['globalConfig'].Config.get('General','Debug').lower() == "true"
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
        emailtext=f"Membership found: {email} {altemail}\n"

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
        debug += f"Digest: {digest}\n"
        debug += f"URL: {url}\n"
        debug += f"Debug {isDebug} type: {type(isDebug)}\n"
        emailtext=f"Go to this URL to update your membership: {url}\n\n(Link will expire shortly)\n"

    message = ""
    if isDebug:
        debug += "\n\nDebug mode enabled - Email NOT sent - Email Text:\n\n"+emailtext
    else:
        debug = ""
        try:
            genericEmailSender("info@makeitlabs.com",email,"Fix Membership Link",emailtext)
            message="A message has been sent from info@makeitlabs.com to the email address on-file for this membership, if one has been found. (Make sure it does not go to spam folder)."
        except BaseException as e:
            print (f"Email error: {e}")
            message=f"An error has occured trying to send email - use this link directly, instead: {url}"
    return render_template('message.html',message=message,debug=debug)


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
        if s is None:
            debug += "No subscriptions have been found for you. Please email for help\n"
        else:
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
