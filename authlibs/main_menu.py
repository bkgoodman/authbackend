from flask import url_for
from flask_user import current_user

''' If "img" is missing - will not appear in index page, only menu '''

def main_menu():
	menu= [
		{
			'url':url_for('authorize.authorize'),
			'title':"Authorize Users"
		},
		{
			'url':url_for('members.members'),
			'img':url_for("static",filename="office.png"),
			'alt':"View, Create or Edit members and their access",
			'title':"Members"
		},
		{
			'privs':'RATT',
			'url':url_for('resources.resources'),
			'img':url_for("static",filename="building.png"),
			'alt':"View, Create or Modify Resources",
			'title':"Resources"
		},
		{
			'url':url_for('logs.logs'),
			'img':url_for("static",filename="logs.png"),
			'alt':"View Logs",
			'title':"Logs"
		},
		{
			'privs':'RATT',
			'url':url_for('tools.tools'),
			'img':url_for("static",filename="toolcfg.png"),
			'alt':"Configure Tools",
			'title':"Tools"
		},
		{
			'privs':'Useredit',
			'url':url_for('waivers.waivers'),
			'img':url_for("static",filename="contract.png"),
			'alt':"View Waiver Data",
			'title':"Waivers"
		},
		{
			'privs':'Useredit',
			'url':url_for('slack_page'),
			'title':"Slack"
		},
		{
			'privs':'Finance',
			'url':url_for('payments.payments'),
			'img':url_for("static",filename="finance.png"),
			'alt':"View or Test Payment System integration",
			'title':"Payments"
		},
		{
			'privs':'Finance',
			'url':url_for('reports.blacklist'),
			'img':url_for("static",filename="data.png"),
			'alt':"View reports",
			'title':"Blacklists"
		},
		{
			'url':url_for('reports.reports'),
			'title':"Reports"
		},
		{
			'privs':'Admin',
			'url':url_for('members.admin_page'),
			'title':"Admin Roles"
		},
		{
			'privs':'RATT',
			'url':url_for('nodes.nodes'),
			'img':url_for("static",filename="rattcfg.png"),
			'alt':"Admin Page",
			'title':"Nodes"
		},
		{
			'privs':'RATT',
			'url':url_for('apikeys.apikeys'),
			'title':"API Keys",
		},
		{
			'privs':'RATT',
			'url':url_for('kvopts.kvopts'),
			'title':"Node Parameters",
		}
	]

        result = []
        for m in menu:
            if 'privs' not in m:
                result.append(m)
            else:
                if current_user.privs(m['privs']):
                    result.append(m)
        return sorted(result,key=lambda x:x['title'])
