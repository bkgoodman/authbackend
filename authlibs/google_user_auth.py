from flask import Blueprint, redirect, url_for, session
from flask_dance.contrib.google import make_google_blueprint, google
from flask_dance.consumer.backend.sqla import SQLAlchemyBackend
from flask_login import current_user, login_user, logout_user
from flask_dance.consumer import oauth_authorized
from sqlalchemy.orm.exc import NoResultFound
from oauthlib.oauth2.rfc6749.errors import InvalidClientIdError
from db_models import db, Member

SCOPE1="https://www.googleapis.com/auth/plus.me"
SCOPE2="https://www.googleapis.com/plus/v1/people/me"
SCOPE3="https://www.googleapis.com/auth/userinfo.profile"
SCOPE4="https://www.googleapis.com/auth/userinfo.email"
SCOPE7="https://www.googleapis.com/auth/plus.login"
#SCOPE5="https://www.googleapis.com/auth/userinfo"
#SCOPE6="https://www.googleapis.com/oauth2/v1/userinfo"

SCOPE=SCOPE7
def authinit(app):
    userauth = Blueprint('userauth', __name__)

    google_blueprint = make_google_blueprint(
        client_id=app.globalConfig.Config.get("OAuth","GOOGLE_CLIENT_ID"),
        client_secret=app.globalConfig.Config.get("OAuth","GOOGLE_CLIENT_SECRET"),
        #scope=['https://www.googleapis.com/auth/userinfo.email'],
        scope=[
        "https://www.googleapis.com/auth/plus.me",
        "https://www.googleapis.com/auth/userinfo.email",
    ],
        offline=True
        )

    """,
            "https://www.googleapis.com/auth/plus.profile.agerange.read",
            "https://www.googleapis.com/auth/userinfo.profile",
            "https://www.googleapis.com/auth/plus.me",
            "https://www.googleapis.com/auth/plus.profile.language.read"],
            """
    """
    google_blueprint.backend = SQLAlchemyBackend(user.UserAuth, db.session,
                                                 user=current_user,
                                                 user_required=False)

    """
    app.register_blueprint(google_blueprint, url_prefix="/google_login")

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
            query = User.query.filter_by(email=email)

            try:
                user = query.one()
            except NoResultFound:
                user = User()
                user.name = account_info_json['name']
                user.email = account_info_json['email']
                db.session.add(user)
                db.session.commit()
            login_user(Member, remember=True)


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
