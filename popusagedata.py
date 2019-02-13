#!/usr/bin/python


from authlibs.templateCommon import *
from authlibs.init import authbackend_init
import argparse
import datetime
import random

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument("--createdb",help="Create new db if none exists",action="store_true")
    parser.add_argument("--command",help="Special command",action="store_true")
    (args,extras) = parser.parse_known_args(sys.argv[1:])

    app=authbackend_init(__name__)

    with app.app_context():
			#print Resource.query.all()

			now=datetime.datetime.now()
			dt=datetime.datetime.now()-datetime.timedelta(days=35)


			uids=[]
			for u in ('testuser','testarm','testrm','testtrainer'):
							uids.append(Member.query.filter(Member.member==u).one().id)

			(tid,rid) = db.session.query(Tool.id,Tool.resource_id).filter(Tool.name=="TestTool").one()

			print "UIDs",uids,"TID",tid,"RID",rid
			while (dt < datetime.datetime.now()):
				idle = random.randint(1,30)
				active = random.randint(1,30)
				enabled = idle+active
				dt += datetime.timedelta(minutes=enabled)

				db.session.add(UsageLog(time_logged = dt,
								time_reported = dt,
								tool_id = tid,
								resource_id = rid,
								member_id = uids[random.randint(0,len(uids)-1)],
								idleSecs = idle,
								activeSecs = active,
								enabledSecs = enabled))

				unused  = random.randint(5,60*4)
				dt += datetime.timedelta(minutes=unused)
			db.session.commit()

			
			
