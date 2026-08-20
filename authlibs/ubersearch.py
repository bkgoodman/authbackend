# vim:tabstop=2:shiftwidth=2:expandtab
from .templateCommon import *

from .accesslib import addQuickAccessQuery


def ubersearch(searchstr,only=None,membertypes=None):
  result = []
  if searchstr == "": return []

  if not only or 'members' in only:
          mq = 	Member.query.filter((Member.member.ilike('%'+searchstr+'%') | Member.nickname.ilike('%'+searchstr+'%') | Member.alt_email.ilike('%'+searchstr+'%') | Member.slack.ilike('%'+searchstr+'%') | Member.firstname.ilike('%'+searchstr+'%') | Member.plates.ilike('%'+searchstr+'%') | Member.lastname.ilike('%'+searchstr+'%') | Member.group.ilike('%'+searchstr+'%')))
          mq = addQuickAccessQuery(mq)

          mq = mq.outerjoin(Subscription,Subscription.member_id == Member.id)
          seen_members = set()
          for r in mq.all():
            (x,s) = r
            if x.id in seen_members: continue
            seen_members.add(x.id)
            if not membertypes or s in membertypes:
                    is_inactive = ((s == "No Subscription") or (s == "Expired"))
                    has_group = bool(x.group and x.group.strip())
                    grp = x.group.strip() if has_group else ""
                    if is_inactive:
                      in_text = f"Inactive ({grp})" if has_group else "Inactive"
                    else:
                      in_text = grp if has_group else ""
                    result.append({
                      'title':"%s %s" % (x.firstname or "", x.lastname or "").strip(),
                      'in': in_text,
                      'id':x.id,
                      'member':x.member,
                      'url':url_for("members.member_show",id=x.member)
                    })

  if not only or 'resources' in only:
          for x in Resource.query.filter((Resource.name.ilike('%'+searchstr+'%') | Resource.description.ilike('%'+searchstr+'%'))).all():
            result.append({
              'title':"%s" % (x.name),
              'in':"Resource",
              'short':x.short,
              'id':x.id,
              'url':url_for("resources.resource_show",resource=x.name)
            })

  if not only or 'tools' in only:
          for x in Tool.query.filter((Tool.name.ilike('%'+searchstr+'%'))).all():
            result.append({
              'title':"%s" % (x.name),
              'in':"Tool",
              'short':x.short,
              'id':x.id,
              'url':url_for("tools.tools_show",tool=x.id)
            })

  if not only or 'nodes' in only:
          for x in Node.query.filter(Node.name.ilike('%'+searchstr+'%')).all():
            result.append({
              'title':"%s" % (x.name),
              'in':"Node",
              'id':x.id,
              'url':url_for("nodes.nodes_show",node=x.id)
            })
  return result
	

def cli_ubersearch(cmd,**kwargs):
	for x in  ubersearch(cmd[1]):
			print ("%s %s %s" %(x['title'],x['in'],x['url']))
