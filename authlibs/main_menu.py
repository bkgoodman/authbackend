from flask import url_for

''' If "img" is missing - will not appear in index page, only menu '''

def main_menu():
	return [
		{
			'url':url_for('members.members'),
			'img':url_for("static",filename="office.png"),
			'alt':"View, Create or Edit members and their access",
			'title':'Members and Access'
		},
		{
			'url':url_for('payments.payments'),
			'img':url_for("static",filename="finance.png"),
			'alt':"View or Test Payment System integration",
			'title':'Payment System'
		},
		{
			'url':url_for('resources.resources'),
			'img':url_for("static",filename="building.png"),
			'alt':"View, Create or Modify Resources",
			'title':'Resources'
		},
		{
			'url':url_for('reports.reports'),
			'img':url_for("static",filename="data.png"),
			'alt':"View reports",
			'title':'Reports'
		},
		{
			'url':url_for('waivers.waivers'),
			'img':url_for("static",filename="contract.png"),
			'alt':"View Waiver Data",
			'title':'Waivers'
		},
		{
			'url':url_for('logs.logs'),
			'img':url_for("static",filename="logs.png"),
			'alt':"View Logs",
			'title':'View Logs'
		},
		{
			'url':url_for('members.admin_page'),
			'img':url_for("static",filename="rattcfg.png"),
			'alt':"Admin Page",
			'title':'Configure Front-Ends'
		},
		{
			'url':url_for('tools.toolcfg'),
			'img':url_for("static",filename="toolcfg.png"),
			'alt':"Configure Tools",
			'title':'Configure Tools'
		}
	]
