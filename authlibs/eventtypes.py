import inspect,sys
#vim:tabstop=2:expandtab

class RATTBE_LOGEVENT_UNKNOWN:
    id= 0
    desc= 'Unknown Event'

class RATTBE_LOGEVENT_CONFIG_OTHER:
    id=1000
    desc='Other Event'

class RATTBE_LOGEVENT_SYSTEM_OTHER:
    id=2000
    desc='Other System Event'

class RATTBE_LOGEVENT_SYSTEM_WIFI:
    id=2001
    desc='Wifi Status'

class RATTBE_LOGEVENT_SYSTEM_POWER_LOST:
    id=2002
    desc='Power Loss'

class RATTBE_LOGEVENT_SYSTEM_POWER_RESTORED:
    id=2003
    desc='Power Restored'

class RATTBE_LOGEVENT_SYSTEM_POWER_SHUTDOWN:
    id=2004
    desc='Shutdown'

class RATTBE_LOGEVENT_SYSTEM_POWER_OTHER:
    id=2005
    desc='Other Power Event'


class RATTBE_LOGEVENT_TOOL_OTHER:
    id=3000
    desc='Other Tool Event'

class RATTBE_LOGEVENT_TOOL_ISSUE:
    id=3001
    desc='Other Tool Issue'

class RATTBE_LOGEVENT_TOOL_SAFETY:
    id=3002
    desc='Tool Safety'

class RATTBE_LOGEVENT_TOOL_ACTIVE:
    id=3003
    desc='Tool Active'

class RATTBE_LOGEVENT_TOOL_INACTIVE:
    id=3004
    desc='Tool Inactive'

class RATTBE_LOGEVENT_TOOL_LOCKOUT_PENDING:
    id=3005
    desc='Lockout Pending'

class RATTBE_LOGEVENT_TOOL_LOCKOUT_LOCKED:
    id=3006
    desc='Locked-out'

class RATTBE_LOGEVENT_TOOL_LOCKOUT_UNLOCKED:
    id=3007
    desc='Lockout removed'

class RATTBE_LOGEVENT_TOOL_LOCKOUT_OTHER:
    id=3008
    desc='Lockout other'


class RATTBE_LOGEVENT_TOOL_POWERON:
    id=3009
    desc="Tool Powered On"

class RATTBE_LOGEVENT_TOOL_POWEROFF:
    id=3010
    desc="Tool Powered Off"

class RATTBE_LOGEVENT_TOOL_LOGIN_COMBO:
    id=3011
    desc="Login (via. combo/passcode)"

class RATTBE_LOGEVENT_TOOL_PROHIBITED:
    id=3012
    desc="Access Denied"

class RATTBE_LOGEVENT_TOOL_LOGIN:
    id=3013
    desc="Logged in"

class RATTBE_LOGEVENT_TOOL_COMBO_FAILED:
    id=3014
    desc="Incorrect Passcode attempt"

class RATTBE_LOGEVENT_TOOL_LOGOUT:
    id=3015
    desc="Logged-out"


def get_events():
		"""
		print RATTBE_LOGEVENT_UNKNOWN
		print RATTBE_LOGEVENT_UNKNOWN.id
		print RATTBE_LOGEVENT_UNKNOWN.desc
		print dir(__package__)
		print __package__.__doc__
		"""

    events_by_id={}
    for (name,cl) in inspect.getmembers(sys.modules[__name__], inspect.isclass):
        events_by_id[cl.id]=cl.desc
    return events_by_id

if __name__=="__main__":
    print get_events()
