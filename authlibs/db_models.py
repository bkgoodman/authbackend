# Database models
# vim:expandtab:tabstop=4
# Single file containing all required DB models, for now
from flask_sqlalchemy import SQLAlchemy
from flask_user import UserManager, UserMixin
import random, string

db = SQLAlchemy()

# Define User Data model
class User(db.Model,UserMixin):
    __tablename__ = 'users';
    rnd_api_key = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(12))
    id = db.Column(db.Integer, primary_key=True)
    active = db.Column('is_active',db.Boolean(), nullable=False, server_default='1')
    email = db.Column(db.String(25),nullable=False, unique=True, server_default='')
    email_confirmed_at = db.Column(db.DateTime())
    password = db.Column(db.String(255),nullable=False)
    created_by = db.Column(db.String(25), nullable=False, server_default='admin')
    created_on = db.Column(db.DateTime(timezone=True), server_default=db.func.now())
    comment = db.Column(db.String(255), nullable=True, server_default='')
    api_key = db.Column(db.String(255), nullable=True, server_default=rnd_api_key)
    roles= db.relationship('Role', secondary = 'user_roles')

class AccessByMember(db.Model):
    __tablename__ = 'accessbymember'
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer(), db.ForeignKey('members.id', ondelete='CASCADE'),nullable=False)
    resource_id = db.Column(db.Integer(), db.ForeignKey('resources.id', ondelete='CASCADE'),nullable=False)
    active = db.Column('is_active',db.Boolean(), nullable=False, server_default='1')
    time_created = db.Column(db.DateTime(timezone=True), server_default=db.func.now())
    time_updated = db.Column(db.DateTime(timezone=True), onupdate=db.func.now())
    comment = db.Column(db.String(255), nullable=True, server_default='')
    lockouts = db.Column(db.String(255), nullable=True, server_default='')
    permissions = db.Column(db.String(255), nullable=True, server_default='')
    created_by = db.Column(db.String(25), nullable=False, server_default='admin')
    level = db.Column(db.Integer(),default=0)
    __table_args__ = (db.UniqueConstraint('member_id', 'resource_id', name='_member_resource_uc'),)
    
class Logs(db.Model):
    __tablename__ = 'logs'
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer(), db.ForeignKey('members.id', ondelete='CASCADE'))
    resource_id = db.Column(db.Integer(), db.ForeignKey('resources.id', ondelete='CASCADE'))
    doneby = db.Column(db.Integer(), db.ForeignKey('users.id', ondelete='CASCADE'))
    event_type = db.Column(db.String(50))
    message = db.Column(db.String(100))

# Define roles
class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer(), primary_key=True)
    name = db.Column(db.String(50), unique=True)

# Define User to Role Mapping
class UserRoles(db.Model):
    __tablename__ = 'user_roles'
    id = db.Column(db.Integer(), primary_key=True)
    member_id = db.Column(db.Integer(), db.ForeignKey('users.id', ondelete='CASCADE'))
    role_id = db.Column(db.Integer(), db.ForeignKey('roles.id', ondelete='CASCADE'))

class Resource(db.Model):
    __tablename__ = 'resources'
    id = db.Column(db.Integer(), primary_key=True)
    name = db.Column(db.String(50), unique=True)
    description = db.Column(db.String(50))
    owneremail = db.Column(db.String(50))
    last_updated = db.Column(db.DateTime(timezone=True), onupdate=db.func.now())
    slack_chan = db.Column(db.String(50))
    slack_admin_chan = db.Column(db.String(50))

class ResourceAlias(db.Model):
    __tablename__ = 'resourcealiases'
    id = db.Column(db.Integer(), primary_key=True)
    alias = db.Column(db.String(50), unique=True)
    resource_id = db.Column(db.Integer(), db.ForeignKey('resources.id', ondelete='CASCADE'))


# Members and their data
class Member(db.Model):
    __tablename__ = 'members'
    id = db.Column(db.Integer(), primary_key=True)
    member = db.Column(db.String(50), unique=True)
    email = db.Column(db.String(50))
    alt_email = db.Column(db.String(50))
    firstname = db.Column(db.String(50))
    slack = db.Column(db.String(50))
    lastname = db.Column(db.String(50))
    phone = db.Column(db.String(50))
    plan = db.Column(db.String(50))
    access_enabled = db.Column(db.Integer())
    access_reason = db.Column(db.String(50))
    active = db.Column(db.Integer())
    nickname = db.Column(db.String(50))
    stripe_name = db.Column(db.String(50))
    time_created = db.Column(db.DateTime(timezone=True), server_default=db.func.now())
    time_updated = db.Column(db.DateTime(timezone=True), onupdate=db.func.now())

class Subscription(db.Model):
    __tablename__ = 'subscriptions'
    id = db.Column(db.Integer(), primary_key=True)
    paysystem = db.Column(db.String(50))
    subid = db.Column(db.String(50))
    customerid = db.Column(db.String(50))
    name = db.Column(db.String(50))
    email = db.Column(db.String(50))
    # NOTE CHANGE FROM PLANNAME" to PLAN
    plan = db.Column(db.String(50))
    expires_date = db.Column(db.DateTime())
    created_date = db.Column(db.DateTime())
    updated_date = db.Column(db.DateTime(timezone=True), onupdate=db.func.now())
    checked_date = db.Column(db.DateTime())
    active = db.Column(db.Integer())

# Waiver Data
class Waiver(db.Model):
    __tablename__ = 'waivers'
    id = db.Column(db.Integer(), primary_key=True)
    waiver_id = db.Column(db.String(50))
    firstname = db.Column(db.String(50))
    lastname = db.Column(db.String(50))
    email = db.Column(db.String(50))
    member_id = db.Column(db.Integer(), db.ForeignKey('members.id'))
    created_date = db.Column(db.DateTime())

# RFID data
class MemberTag(db.Model):
    # TODO: Handle change from tagsbymember
    __tablename__ = 'tags_by_member'
    id = db.Column(db.Integer(), primary_key=True)
    tag_id = db.Column(db.String(50))
    tag_type = db.Column(db.String(50))
    tag_name = db.Column(db.String(50))
    updated_date = db.Column(db.DateTime(timezone=True), onupdate=db.func.now())
    member = db.Column(db.String(50))
    member_id = db.Column(db.Integer(), db.ForeignKey('members.id', ondelete='CASCADE'))
    # member_id MIGHT not exist if user is gone, but "member" should be ok

class Blacklist(db.Model):
    # TODO: Handle change from tagsbymember
    __tablename__ = 'blacklist'
    id = db.Column(db.Integer(), primary_key=True)
    entry = db.Column(db.String(50))
    entrytype = db.Column(db.String(50))
    reason = db.Column(db.String(50))
    updated_date = db.Column(db.DateTime(timezone=True), onupdate=db.func.now())
