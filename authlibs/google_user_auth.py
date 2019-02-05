from flask import Blueprint, redirect, url_for, session, flash, g
from flask_dance.contrib.google import make_google_blueprint, google
from flask_dance.consumer.backend.sqla import SQLAlchemyBackend, OAuthConsumerMixin
from flask_login import current_user, login_user, logout_user
from flask_dance.consumer import oauth_authorized
from sqlalchemy.orm.exc import NoResultFound
from oauthlib.oauth2.rfc6749.errors import InvalidClientIdError
from db_models import db, Member, OAuth, AnonymousMember
from flask_login import LoginManager
from flask_user import UserManager
from accesslib import quickSubscriptionCheck

import os
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE']='Yes'

""" 
TODO FIX BUG

You can (and probably should) set OAUTHLIB_RELAX_TOKEN_SCOPE when running in production.
"""
def our_login():
    # Do something like this but not this
    return redirect(url_for('login'))


def authinit(app):
    userauth = Blueprint('userauth', __name__)

    google_blueprint = make_google_blueprint(
        client_id=app.config['globalConfig'].Config.get("OAuth","GOOGLE_CLIENT_ID"),
        client_secret=app.config['globalConfig'].Config.get("OAuth","GOOGLE_CLIENT_SECRET"),
        scope=[#"https://www.googleapis.com/auth/plus.me",
        "https://www.googleapis.com/auth/userinfo.email"
        ],
        offline=True
        )

    google_blueprint.backend = SQLAlchemyBackend(OAuth, db.session,
                                                 user=current_user,
                                                 user_required=True)

    user_manager = UserManager(app, db, Member)
    user_manager.USER_ENABLE_AUTH0 = True
    user_manager.unauthenticated_view = our_login
    login_manager=LoginManager()
    login_manager.login_view="google.login"
    login_manager.init_app(app)
    login_manager.anonymous_user=AnonymousMember

    @login_manager.user_loader
    def load_user(user_id):
        if not user_id.lower().endswith("@makeitlabs.com"): return None
        mid = user_id.split("@")[0]
        return Member.query.filter(Member.member == mid).one_or_none()
        #return Member.get(user_id)

    @userauth.route("/google_login")
    def google_login():
        if not google.authorized:
            return redirect(url_for("google.login"))
        resp = google.get(SCOPE)
        assert resp.ok, resp.text
        return resp.text

    @oauth_authorized.connect_via(google_blueprint)
    def google_logged_in(blueprint, token):
        resp = google.get("/oauth2/v2/userinfo")
        if resp.ok:
            account_info_json = resp.json()
            email = account_info_json['email']
            print "EMAIL IS",email
            member=email.split("@")[0]
            if not email.endswith("@makeitlabs.com"):
                flash("Not a MakeIt Labs account",'warning')
                return redirect(url_for('login'))
            #query = Member.query.filter_by(Member.member.ilike(member))
            #if not query:
            query = Member.query.filter(Member.email==email)

            try:
                user = query.one()
                print "GOT USER",user
                sub = quickSubscriptionCheck(member_id=user.id)
                print "GOT SUB",sub
                if sub == "Active":
                        flash("Welcome!")
                        login_user(user, remember=True)
                else:
                        flash("Login Denied - "+sub,'danger')
                return redirect(url_for('index'))
            except NoResultFound:
                flash("Email adddress "+str(email)+" not found in member database")
                return redirect(url_for('index'))


    @userauth.route('/google_logout')
    def google_logout():
        """Revokes token and empties session."""
        if google.authorized:
            try:
                google.get(
                    'https://accounts.google.com/o/oauth2/revoke',
                    params={
                        'token':
                        google.token['access_token']},
                )
            except InvalidClientIdError:  # token expiration
                del google.token
                redirect(url_for('main.index'))
        session.clear()
        logout_user()
        return redirect(url_for('main.index'))

    app.register_blueprint(google_blueprint, url_prefix="/google_login")
