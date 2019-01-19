#!/usr/bin/python

"""
Get from: https://www.digicert.com/CACerts/DigiCertGlobalRootCA.crt
export WEBSOCKET_CLIENT_CA_BUNDLE=DigiCertGlobalRootCA.crt

If your SlackClient is old, you might need to modify it with:

import logging
logger = logging.getLogger('websockets.server')
logger.setLevel(logging.ERROR)
logger.addHandler(logging.StreamHandler())

(If you see a logger error loading it - this is the fix)

"""

import os,time,json,datetime,sys
import linecache
from authlibs import init

import logging
logger = logging.getLogger(__name__)
streamHandler = logging.StreamHandler()
streamHandler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - SLACKBOT - %(name)s - %(levelname)s - %(message)s')
streamHandler.setFormatter(formatter)

log_events=[]
logger.addHandler(streamHandler)

logger.info("Files copied")
print "LOAD"
from slackclient import SlackClient
print "DONE"

Config = init.get_config()
slack_token = Config.get('Slack','BOT_API_TOKEN')
sc = SlackClient(slack_token)

def oxfordlist(lst,conjunction="or"):
	text=""
	if len(lst)==0:
		return ""
	if len(lst)==1:
		return(lst[0])
	text = ", ".join(lst[:-1])
	text += " "+conjunction+" "+lst[-1]
	return text

def get_users(sc):
	users={}
	all_users = sc.api_call("users.list")
	#print json.dumps(all_users,indent=2)
	for m in all_users['members']:
		p = m['profile']
		if not m['is_bot'] and not m['deleted']:
			if type(m['real_name']) == "set": m['real_name']=m['real_name'][0]
			if type(m['name']) == "set": m['name']=m['name'][0]
			#print type(m['real_name']),type(m['name']),type(m['id'])
			users[m['name']]={"name":m['real_name'],"slack_id":m['id']}

	return users

def matchusers(sc,user,ctx,pattern):
	users = get_users(sc)
	v=""

	if 'quids' not in ctx:
		ctx['quids']={}

	for x in users:
		if users[x]['name'].lower().find(pattern.lower()) >= 0:
			for q in range(0,99):
				f= "{0:02d}".format(q)
				if f not in ctx['quids']: break
			
			v += users[x]['name']+" "+x+" ["+f+"]\n"
			ctx['quids'][f]=x
	if v=="": 
		return ""
	else:
	 return v

def cancel_callbacks(ctx):
	if 'confirm_callback' in ctx: del ctx['confirm_callback']
	if 'cancel_callback' in ctx: del ctx['cancel_callback']

def authorize_confirm(sc,user,ctx):
	cancel_callbacks(ctx)
	text = "Authorized "+oxfordlist(ctx['authorize_users'],conjunction="and")+" on "+oxfordlist(ctx['authorize_resources'],conjunction="and")+".\n\n(Not really, but pretend that I did)."
	return text

def on_resource(sc,user,ctx,*s):
	if 'authorize_users' not in ctx:
		return "Use the \"authorize\" command to say who you're trying to authorize, first"
	if len(s) < 2:
		return "Authorize on what resource? (Type \"on <resources...>\""
	resources = s[1:]
	text = "Authorize "+oxfordlist(ctx['authorize_users'],conjunction="and")+" on "+oxfordlist(resources,conjunction="and")+"? Type \"ok\" to confirm"
	ctx['confirm_callback']=authorize_confirm
	ctx['authorize_resources']=resources
	return text
	
	

def authorize(sc,user,ctx,*s):
	error=""
	allusers = get_users(sc)
	if len(s) <2:
		return "`USAGE: authorize <usersids..> [on <resources...>]`"
		
	res=False
	users=[]
	resources=[]
	for x in s[1:]:
		if x.lower() == "on":
			res=True
		elif res == False:
			users.append(x)
		else:
			resources.append(x)
	
	names=[]
	for uid in users:
		u=uid
		print "Handling",u
		if 'quids' in ctx:
			for q in ctx['quids']:
				print "COMPARE",q,u,ctx['quids'][q]
				if q==u:
					u=ctx['quids'][q]
		if u in allusers:
			names.append(allusers[u]['name'])
		else:
			print "USERID",u,"NOT IN ALLMACHES"
			if len(u)>=3:
				possible = matchusers(sc,user,ctx,u)
			else:
				possible=""
			error+=u+" is not a valid userid. "
			if possible != "":
				error+="Did you mean one of:\n```\n"+possible+"\n```\n"
			print "match",u,"got",error
	
	if error != "":
		return error+"\n(Correct, or select from above list and try again)"

	if (len(names)==0):
		return "You must specify users to authorized on"
	ctx['authorize_users']=names
	if (len(resources)==0):
		return "Authorize "+oxfordlist(names,conjunction="and")+" on what resource? (Type \"on <resources...>\")"
	text = "Authorize "+oxfordlist(names,conjunction="and")+" on "+oxfordlist(resources,conjunction="and")+"? Type \"ok\" to confirm"
	ctx['confirm_callback']=authorize_confirm
	ctx['authorize_resources']=resources
	return text

	return "DOne"
def divzero(sc,user,ctx,*s):
	x = 0/0
	return "Tadah!"

def quickids(sc,user,ctx,*s):
	if 'quids' not in ctx:
		return "No IDs cached"

	users = get_users(sc)
	text=""
	for q in ctx['quids']:
		if ctx['quids'][q] in users:
			text += users[ctx['quids'][q]]['name']+" "+q+"\n"
	return "```"+text+"```"
		
	
def resources(sc,user,ctx,*s):
	return "None yet :white_frowning_face:"

def default_cancel_callback (sc,user,ctx):
	del ctx['cancel_callback']
	return "Canceled"

def cancel(sc,user,ctx,*s):
	if 'cancel_callback' not in ctx:
		return "Nothing pending to cancel"
	return ctx['cancel_callback'](sc,user,ctx)

def confirm(sc,user,ctx,*s):
	if 'confirm_callback' not in ctx:
		return "Nothing pending to confirm"
	return ctx['confirm_callback'](sc,user,ctx)

def userid(sc,user,ctx,*s):
	if len(s)!=2:
		return "USAGE: userid <patternid>"
	v= matchusers(sc,user,ctx,s[1])
	if v=="":
		return "None Found :white_frowning_face:"
	else:
		return "```"+v+"```"

def show_event_log(sc,user,ctx,*s):
	global log_events
	text="```"
	for x in log_events:
		text += x+"\n"
	text+="```"
	return text
	
def ping(sc,user,ctx,*s):
	display_name=user['user']['profile']['display_name']
	return "Hello "+str(display_name)+" I am alive at "+str(datetime.datetime.now())

def help_cb(sc,user,ctx,*s):
	text = '```'
	if (len(s) == 2):
		text="```Unrecognized command. Type `help` for a list of commands"
		for x in verbs:
			if s[1].lower()==x['name'].lower():
				text = "*"+x['name']+"*\n```"
				if 'usage' in x:
					text += "Usage: "+x['usage']+"\n"
				if 'detail' in x:
					text += x['detail']+"\n\n"
				elif 'desc' in x:
					text += x['desc']+"\n\n"
	else:
		text= "Enter one of the following, or `help {command}` for more detail:\n```"

		for x in sorted(verbs,key=lambda x:x['name']):
			if 'callback' in x:
				if 'usage' in x:
					text += x['usage']+ "  -- "+x['desc']+"\n"
				elif 'desc' in x:
					text += x['name']+" - "+x['desc']+"\n"
				else:
					text += x['name'] +"\n"

		text+= "\nOther help topics:\n"
		for x in sorted(verbs,key=lambda x:x['name']):
			if 'callback' not in x:
				if 'desc' in x:
					text += x['name'] + " - "+x['desc']+"\n"
				else:
					text += x['name']
	text += '```'
	return text
	
# Dont specify a callback to just create a help topic

# usage is the command line - not used for help topics
# desc is SHORT info - MANDIRORY  quick description
# detail is the LONG detain (optional)

verbs = [
	{	'name':"authorize", 
		'callback':authorize,
		'usage':"authorize <userids...> [on <resrouces..>]",
		'desc':"Authorize a user to use a tool/resource",
		'detail':"Authorize one or more users on one or more resources. Specify user ids (or quick IDs) from \"userid\" command. Will try to match a user name, but if there is any ambiguity, it will fail (create quick IDs for possible matches) - and require you to retry. If you don't specify the resources, you'll have to afterwards."
	},
	{	'name':"userid", 
		'callback':userid,
		'usage':"userid <pattern>",
		'desc':"Find user's ID",
		'detail':"Search for a user's ID by specifying a portion of it - like \"Jo\" to find \"Joe\", \"Jon\", \"John\", etc. Command will return a list of matching users, their IDs, and temporary \"quick IDs\" that can be used to reduce keystrokes like \"01\""
	},
	{	'name':"resources", 
		'callback':resources,
		'usage':"resources",
		'desc':"List all resources"
	},
	{	'name':"divzero", 
		'callback':divzero,
		'desc':"Divide a number by zero"
	},
	{	'name':"divzero2", 
		'callback':divzero,
		'usage':"divzero",
		'desc':"Divide a number by zero"
	},
	{	'name':"divthree", 
		'callback':divzero,
		'desc':"Divide a number by zero"
	},
	{	'name':"quickid", 
		'callback':quickids,
		'desc':"Show quickids",
		'detail':"QuickIDs are TEMPORARY user ids used to make you need to type less. They are aways in the form of \"00\" (two digits). They are automatcally created by commands such as \"userid\" and \"authorize\" which lookup ids based on partial matches. Use them whenever user IDs are required. The \"quickid\" command will show you what is in your cache. These are short lived, and will always disappear shortly after used."
	},
	{	'name':"log", 
		'callback':show_event_log,
		'desc':"Show slackbot command log"
	},
	{	'name':"ping", 
		'callback':ping,
		'desc':"Just see if I'm alive"
	},
	{	'name':"confirm", 
		'callback':confirm,
		'desc':"Confirm a request",
		'detail':'When do tell me to do something - I will verify the request and ask you to confirm it. Type \"confirm\" or \"yes\" or \"ok\" to do it',
		'aliases':['ok','yes']
	},
	{	'name':"cancel", 
		'callback':cancel,
		'desc':"cancel a request",
		'detail':'When do tell me to do something - I will verify the request and ask you to confirm it. This is one way to explicitly cancel it',
		'aliases':['no']
	},
	{	'name':"user", 
		'desc':"email or slack id",
		'detail':"A slack or email id in the format of firstname.lastname, or a \"quick id\" as returned from the \"userid\" command like \"01\". Use \"userid\" command to help find a user's ID"
	},
	{	'name':"on", 
		'callback':on_resource,
		'desc':"Say what resources you are authorizing users on",
		'detail':"this is the second-half of a sequence you would have started with the \"authorize\" command"
	},
	{
		'name':"resource", 
		"desc":"Tool or resoruce",
		'detail':"Short name/id of a tool or resource, like \"laser\" or \"lift\". Use \"resources\" command to see a list"
	},
	{'name':"help", 'callback':help_cb,'aliases':['?']}
]

def prune_contexts(contexts):
	now=datetime.datetime.now()
	d=[]
	for x in contexts:
		ctx=contexts[x]
		#print x,now-ctx['lastUsed']
		if ((now-ctx['lastUsed']) > datetime.timedelta(minutes=15)):
			d.append(x)
	for x in d:
		print "DELETE CONTEXT",x
		del contexts[x]

def log_event(name,message):
	global log_events
	logstr=str(datetime.datetime.now())+" "+name+" "+message
	log_events.append(logstr)
	print logstr
	open("slackbot.log","a").write(logstr+"\n")
	if len(log_events)>40:
		log_events=log_events[1:]
	

keepgoing=True
while keepgoing:
	log_event("<system>","Reconnect")
	if sc.rtm_connect():
		sc.server.websocket.sock.setblocking(1)
		contexts={}
		#print json.dumps(get_users(sc),indent=2)
		all_users = sc.api_call("users.setPresence",presence="active")
		while sc.server.connected is True and keepgoing is True:
			try:
				l= sc.rtm_read()
			except KeyboardInterrupt:
				log_event("<System>", "Keyboard Interrupt")
				keepgoing=False
				sys.exit(0)
			except BaseException as e:
				log_event("<Exception>", str(e))
				break
			#print "READ",l
			for msg in l:
				if 'type' in msg and (msg['type'] == "message"):
					try:
						text="???"
						#print "Message from ",msg['user'],msg['text'],msg['channel']
						chan = msg['channel']
						if chan not in contexts:
							contexts[chan]={}
						contexts[chan]['lastUsed']=datetime.datetime.now()
						userinfo= sc.api_call("users.info",user=msg['user'])
						#print json.dumps(userinfo,indent=2)
						display_name=userinfo['user']['profile']['display_name']
						display_name_norm=userinfo['user']['profile']['display_name_normalized']
						email=userinfo['user']['profile']['email']
						#print json.dumps(msg,indent=2)
						m = msg['text'].strip().replace("\s+"," ").split()
						if len(m)==0:
							m=[""]
						matches=[]
						cb=None
						exact=None
						for v in verbs:
							#if (m[0].lower().startswith(v['name'].lower())) and 'callback' in v: 	
							cmds=[v['name'].lower()]
							if 'aliases' in v:
								for a in v['aliases']: cmds.append(a.lower())
							for cmd in cmds:
								if (cmd.startswith(m[0].lower())) and 'callback' in v: 	
									matches.append(v['name'])
									cb=v['callback']
									if m[0].lower() == v['name'].lower():
										exact=cb
									
						if exact:
							log_event( display_name,msg['text'])
							text=exact(sc,userinfo,contexts[chan],*m)
						elif len(matches)==1:
							log_event( display_name,msg['text'])
							text=cb(sc,userinfo,contexts[chan],*m)
						elif len(matches)==0:
							text="Unknown command. Type `help` for help"
						else: 
							text="Ambiguous command: Did you mean "
							text += oxfordlist(matches)
							text += "?\n(`help` for more)"
						
					except Exception as e:
						text = "Epic fail: ```"+str(e)+"```"
						log_event( "<Error>",str(e))

					sc.rtm_send_message(msg['channel'],text)
			prune_contexts(contexts)
			sys.stdout.flush()
	else:
		print "Connection Failed"
	time.sleep(2)
	print "RETRY"

