from templateCommon import *



def ubersearch(ss):
	result = []
	if ss == "": return []

	for x in Member.query.filter((Member.member.ilike('%'+ss+'%') | Member.alt_email.ilike('%'+ss+'%') | Member.firstname.ilike('%'+ss+'%') | Member.lastname.ilike('%'+ss+'%'))).all():
		result.append({
			'title':"%s %s" % (x.firstname,x.lastname),
			'in':"Member",
			'url':url_for("members.member_show",id=x.member)
		})

	for x in Resource.query.filter((Resource.name.ilike('%'+ss+'%') | Resource.description.ilike('%'+ss+'%'))).all():
		result.append({
			'title':"%s" % (x.name),
			'in':"Resource",
			'url':url_for("resources.resource_show",resource=x.name)
		})

	for x in Tool.query.filter((Tool.name.ilike('%'+ss+'%') | Resource.description.ilike('%'+ss+'%'))).all():
		result.append({
			'title':"%s" % (x.name),
			'in':"Tool",
			'url':url_for("tools.tools_show",tool=x.name)
		})

	for x in Node.query.filter(Node.name.ilike('%'+ss+'%')).all():
		result.append({
			'title':"%s" % (x.name),
			'in':"Node",
			'url':url_for("nodes.nodes_show",node=x.name)
		})
	return result
	

def cli_ubersearch(cmd,**kwargs):
	for x in  ubersearch(cmd[1]):
			print "%s %s %s" %(x['title'],x['in'],x['url'])
