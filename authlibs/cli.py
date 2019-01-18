# vim:tabstop=2:expandtab

# Command Line Interface

from datetime import datetime
import random,string
from flask_user import current_user, login_required, roles_required, UserManager, UserMixin, current_app
from authlibs.db_models import db, ApiKey,  Role, UserRoles, Member, Resource, AccessByMember
from authlibs.payments import cli_updatepayments
from authlibs.membership import cli_syncmemberpayments
from flask_sqlalchemy import SQLAlchemy
from init import GLOBAL_LOGGER_LEVEL

import logging
logger = logging.getLogger(__name__)
logger.setLevel(GLOBAL_LOGGER_LEVEL)

def do_help(cmd=None,**kwargs):
		print "Commands"
		for x in commands: print "  ",commands[x]['usage']

def addadmin(cmd,**kwargs):
  admin_role = Role.query.filter(Role.name=='Admin').first()
  if not admin_role:
      admin_role = Role(name='Admin')
  user = User(email=cmd[1],password=user_manager.hash_password(cmd[2]),email_confirmed_at=datetime.utcnow())
  db.session.add(user)
  user.roles.append(admin_role)
  db.session.commit()
  app.logger.debug("ADD USER "+str(cmd[1]))

def addapikey(cmd,**kwargs):
  print "CMD IS",cmd
  apikey = ApiKey(username=cmd[1],name=cmd[2])
  if (len(cmd) >=4):
    apikey.password=cmd[3]
  else:
    apikey.password = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(12))
    print "API Key is",apikey.password
  db.session.add(apikey)
  db.session.commit()
  logger.info("Added API key "+str(cmd[1]))

def hashpw(cmd,**kwargs):
  print kwargs['um'].hash_password(cmd[1])

def deleteadmin(cmd,**kwargs):
  User.query.filter(User.email==cmd[1]).delete()
  db.session.commit()

def changepassword(cmd,**kwargs):
  user = Member.query.filter(Member.email==cmd[1]).first()
  user.password=kwargs['um'].hash_password(cmd[2])
  db.session.commit()

def activate(cmd,**kwargs):
  user = Member.query.filter(Member.email==cmd[1]).first()
  user.email_confirmed_at = datetime.utcnow()
  db.session.commit()

def deactivate(cmd,**kwargs):
  user = Member.query.filter(Member.email==cmd[1]).first()
  db.session.commit()

def changekey(cmd,**kwargs):
  user = User.query.filter(User.email==cmd[1]).first()
  user.api_key=cmd[2]
  print "Set",user.email,user.api_key
  db.session.commit()

def revoke(cmd, **kwargs):
    x=UserRoles.query.join(Member)
    x = x.join(Role)
    x = x.filter(Member.email == cmd[1])
    x = x.filter(Role.name.ilike(cmd[2]))
    x = x.one()
    db.session.commit()

def grant(cmd, **kwargs):
    member = Member.query.filter(Member.email==cmd[1]).one()
    member.roles.append(Role.query.filter(Role.name.ilike(cmd[2])).one())
    db.session.commit()

def showadmins(cmd,**kwargs):
    #for x in Role.query.join(UserRoles).join(Member).add_column(Member.member).all():
    for x in db.session.query(Member.member).outerjoin(UserRoles).outerjoin(Role).add_column(Role.name).filter(Role.id!=None).all():
        print x
  
commands = {
	"addadmin":{
		'usage':"addadmin {username} {password}  -- Add adimin",
		'cmd':addadmin
	},
	"addapikey":{
		'usage':"addapikey {name} {username} [password]  -- Add API user w/ login token",
		'cmd':addapikey
	},
	"listadmins":{
		'usage':"listadmins -- show admin users",
		'cmd':showadmins
	},
	"hashpw":{
		'usage':"hashpw {password} -- Return a hashed password",
		'cmd':hashpw
	},
	"changepassword":{
		'usage':"changepassword -- Change password",
		'cmd':changepassword
	},
	"changekey":{
		'usage':"changekey -- Change API key",
		'cmd':changekey
	},
	"help":{
		'usage':"listadmins -- show admin users",
		'cmd':do_help
	},
	"deleteadmin":{
		'usage':"deleteadmin -- Delete admin account",
		'cmd':deleteadmin
	},
	"updatepayments":{
		'usage':"updatepayments -- Update payment data",
		'cmd':cli_updatepayments
	},
	"memberpaysync":{
		'usage':"memberpaysync [--test] [--force] [--help]  -- Reconcile payment and member data",
		'cmd':cli_syncmemberpayments
	},
	"grant":{
		'usage':"grant {email@makeitlabs.com} {priv} -- Grant a Backend GUI Privlage to user",
		'cmd':grant
	},
	"revoke":{
		'usage':"revoke {email@makeitlabs.com} {priv} -- Revoke a Backend GUI Privlage to user",
		'cmd':revoke
	},
	"activate":{
		'usage':"activate {email@makeitlabs.com} -- Activate a GUI account (Confirm email, activate)",
		'cmd':activate
	},
	"deactivate":{
		'usage':"deactivate {email@makeitlabs.com} -- Dectivate a GUI account",
		'cmd':deactivate
	}
}


def cli_command(cmd,**kwargs):
	if len(cmd)==0:
    return do_help()

  if cmd[0] in commands:
      with kwargs['app'].app_context():
        return (commands[cmd[0]]['cmd'](cmd,**kwargs))
	
	do_help()
	
