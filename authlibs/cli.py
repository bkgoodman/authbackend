# vim:tabstop=2:expandtab

# Command Line Interface

from datetime import datetime
import random,string
from flask_user import current_user, login_required, roles_required, UserManager, UserMixin, current_app
from authlibs.db_models import db, User, Role, UserRoles, Member, Resource, AccessByMember
from flask_sqlalchemy import SQLAlchemy

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
  admin_role = Role.query.filter(Role.name=='Admin').first()
  if not admin_role:
      admin_role = Role(name='Admin')
  user = User(email=cmd[1],password=cmd[2],email_confirmed_at=datetime.utcnow())
  if (len(cmd) >=4):
    user.api_key=cmd[3]
  else:
    user.api_key = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(12))
    print "API Key is",user.api_key
  db.session.add(user)
  user.roles.append(admin_role)
  db.session.commit()
  kwargs['app'].logger.debug("ADD USER "+str(cmd[1]))

def hashpw(cmd,**kwargs):
  print kwargs['um'].hash_password(cmd[1])

def deleteadmin(cmd,**kwargs):
  User.query.filter(User.email==cmd[1]).delete()
  db.session.commit()

def changepassword(cmd,**kwargs):
  user = User.query.filter(User.email==cmd[1]).first()
  user.password=kwargs['um'].hash_password(cmd[2])
  db.session.commit()

def changekey(cmd,**kwargs):
  user = User.query.filter(User.email==cmd[1]).first()
  user.api_key=cmd[2]
  print "Set",user.email,user.api_key
  db.session.commit()
  
def showadmins(cmd,**kwargs):
  for x in User.query.all():
    print x.email,x.password,x.api_key

commands = {
	"addadmin":{
		'usage':"addadmin {username} {password}  -- Add adimin",
		'cmd':addadmin
	},
	"addapikey":{
		'usage':"addapi {username} password [api_key]  -- Add API user w/ login token",
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
	}
}


def cli_command(cmd,**kwargs):
	if len(cmd)==0:
    return do_help()

  if cmd[0] in commands:
      with kwargs['app'].app_context():
        return (commands[cmd[0]]['cmd'](cmd,**kwargs))
	
	do_help()
	
