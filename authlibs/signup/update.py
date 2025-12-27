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
    debug += f"We will need to recreate plan {plan} rateplan {rateplan}\n"
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
        # Redirect user to Stripe to update their card
        return redirect(session.url, code=303)

    balance = c['balance']

    ss = stripe.Subscription.list(customer=custids[0])
    if (len(ss) > 0):
        return render_template('message.html',message="You already have an active subscription. No further action should be required.", 
        rawhtml="Click <a href='"+url_for("membershipupdate.fix2",digest=digest,now=now,email=email,updatecc=1)+"'>HERE</a> to update your credit card on-file.")

    # No active subscription in Stripe - need to create a new one
    # But first, we need the user to confirm their payment method via Stripe checkout
    # After that, fix_postpay will create the new subscription
    s = stripe.Subscription.retrieve(subids[0])
    price = s['items']['data'][0]['price']['id']
    
    # Store info needed for subscription creation and redirect to Stripe
    baseurl = current_app.config['globalConfig'].Config.get('General','baseurl')
    session = stripe.checkout.Session.create(
        customer = c,
        payment_method_types=["card"],
        mode="setup",
        success_url=baseurl+url_for('membershipupdate.fix_postpay')+"?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=baseurl+url_for("membershipupdate.payupdate")
    )
    return redirect(session.url, code=303)


@blueprint.route('/', methods=['GET'])
def payupdate():
    return render_template('payupdate.html')


# Validates email and sends a secure link to proceed with membership update
@blueprint.route('/fix', methods=['GET','POST'])
def fix():
    if 'email' not in request.form:
        return render_template('message.html', title="Update or Reactivate Membership",
            message="No email address specified")
    
    email = request.form['email'].strip()
    members = Member.query.filter(
        or_(
            func.lower(Member.alt_email) == func.lower(email),
            func.lower(Member.email) == func.lower(email)
        )
    ).all()

    if len(members) == 0:
        # Don't reveal whether email exists - always show same message
        return render_template('message.html', title="Update or Reactivate Membership",
            message="If a membership exists for that email address, a verification link will be sent shortly.")
    
    if len(members) > 1:
        return render_template('message.html', title="Update or Reactivate Membership",
            message="Multiple memberships were found with that email address. Please contact support for assistance.")
    
    # Use the email on file (not the one they typed, in case of alt_email match)
    member = members[0]
    email = member.email

    # Generate secure time-limited link
    now = int(datetime.utcnow().timestamp())
    secret_key = current_app.config['globalConfig'].Config.get('General','SecretKey')
    sha = hashlib.sha256()
    sha.update(secret_key.encode('utf-8'))
    sha.update(email.encode('utf-8'))
    sha.update(now.to_bytes(8, byteorder="big"))

    baseurl = current_app.config['globalConfig'].Config.get('General','baseurl')
    digest = base64.urlsafe_b64encode(sha.digest()).decode()
    url = baseurl + url_for("membershipupdate.fix2", now=now, digest=digest, email=email)

    # TODO: Send email with the verification link
    # For now, the URL is generated but email sending needs to be implemented
    # The link expires in 1 hour (checked in fix2)
    
    debug = ""
    #debug += url
    return render_template('message.html', debug=debug,title="Update or Reactivate Membership",
        message="If a membership exists for that email address, a verification link will be sent shortly.")


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
    stripe.api_key = current_app.config['globalConfig'].Config.get('Stripe','token')
    checkout_session_id = request.args.get('session_id')
    
    if not checkout_session_id:
        return render_template('message.html', title="Update or Reactivate Membership",
            message="Invalid session. Please start the process again.")
    
    try:
        checkout_session = stripe.checkout.Session.retrieve(checkout_session_id)
    except stripe.error.StripeError as e:
        return render_template('message.html', title="Update or Reactivate Membership",
            message=f"Error retrieving session: {e}")

    # Get the SetupIntent and Customer
    si = checkout_session['setup_intent']
    c = checkout_session['customer']

    # Set the new card as the default payment method
    try:
        si = stripe.SetupIntent.retrieve(si)
        stripe.Customer.modify(
            c,
            invoice_settings={
                'default_payment_method': si['payment_method']
            },
        )
    except stripe.error.StripeError as e:
        return render_template('message.html', title="Update or Reactivate Membership",
            message=f"Error setting default payment method: {e}")

    # Check if customer already has an active subscription
    ss = stripe.Subscription.list(customer=c)
    if len(ss['data']) >= 1:
        s = ss['data'][0]
        status = s['status']
        
        if status == "active":
            # Card updated, subscription is active - we're done
            return render_template('message.html', title="Update or Reactivate Membership",
                message="Your payment method has been updated and your membership is active. No further action required.")
        
        elif status == "past_due":
            # Try to pay the outstanding invoice
            try:
                invoices = stripe.Invoice.list(customer=c, status='open', limit=1)
                if len(invoices['data']) > 0:
                    stripe.Invoice.pay(invoices['data'][0]['id'])
                return render_template('message.html', title="Update or Reactivate Membership",
                    message="Your payment method has been updated and we've attempted to process your outstanding payment. Your membership should be reactivated shortly.")
            except stripe.error.StripeError as e:
                return render_template('message.html', title="Update or Reactivate Membership",
                    message=f"Your payment method was updated, but there was an error processing payment: {e}. Please contact support.")
        
        elif status == "unpaid":
            return render_template('message.html', title="Update or Reactivate Membership",
                message="Your payment method has been updated. Your subscription has unpaid invoices. Please contact support for assistance.")
        
        elif status == "paused" or s.get('pause_collection') is not None:
            return render_template('message.html', title="Update or Reactivate Membership",
                message="Your payment method has been updated. Your subscription is currently paused. Please contact support to resume.")
        
        elif status == "trialing":
            return render_template('message.html', title="Update or Reactivate Membership",
                message="Your payment method has been updated. Your membership is in a trial period and active.")
        
        else:
            return render_template('message.html', title="Update or Reactivate Membership",
                message=f"Your payment method has been updated. Subscription status: {status}. Please contact support if you need assistance.")
    
    # No active subscription - find the most recent ended one and create a new subscription
    ss = stripe.Subscription.list(customer=c, status="canceled")
    recent = None
    mostrecent = None
    for s in ss['data']:
        ended = s.ended_at or s.canceled_at
        if ended is not None and (recent is None or ended > recent):
            recent = ended
            mostrecent = s
    
    if mostrecent is None:
        return render_template('message.html', title="Update or Reactivate Membership",
            message="Your payment method has been updated, but no previous subscription was found. Please contact support to set up a new membership.")
    
    s = mostrecent
    
    # Create new subscription based on the old one
    # Note: Coupons applied to CUSTOMERS are automatically applied to new subscriptions
    try:
        sub = stripe.Subscription.create(
            customer=c,
            metadata=s['metadata'],
            description="Membership renewal",
            collection_method="charge_automatically",
            items=[
                {
                    "price": s.plan.id,
                }
            ],
        )
        
        # Update local database to reflect reactivated membership
        fixMemberSubscription(sub)
        
        return render_template('message.html', title="Membership Reactivated",
            message="Success! Your payment method has been updated and a new subscription has been created. Your membership is now active.")

    except stripe.error.StripeError as e:
        return render_template('message.html', title="Update or Reactivate Membership",
            message=f"Your payment method was updated, but there was an error creating a new subscription: {e}. Please contact support.")

def register_pages(app):
	app.register_blueprint(blueprint)
