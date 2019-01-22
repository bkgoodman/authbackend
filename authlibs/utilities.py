#!/usr/bin/env python
# Utilities for MakeIt Labs

import hashlib
import string
import sqlite3
import re
import pytz
from datetime import datetime,date
from flask_user import current_user
from db_models import db, AccessByMember, Member, Resource
    
def hash_rfid(rfid):
    "Given an integer RFID, create a hashed value for storage"
    if rfid == 'None':
        return None
    else:
        try:
            m = hashlib.sha224()
            rfidStr = "%.10d"%(int(rfid))
            m.update(str(rfidStr).encode())
            return m.hexdigest()
        except:
            return None
def rfid_validate(ntag):
	result=None
	if ntag is None: return None
	if len(ntag) != 10: return None
	try:
		result=int(ntag)
	except:
		return None
	return result

def _utcTimestampToDatetime(ts):
    """Convert a UTC timestamp to my local time"""
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%dT%H:%M:%SZ")

def _safeemail(unsafe_str):
    """Sanitize email addresses strings used in some oeprations"""
    keepcharacters = ('.','_','@','-')
    return "".join(c for c in unsafe_str if c.isalnum() or c in keepcharacters).strip()

def _safestr(s):
    """Sanitize input strings used in some operations"""
    keepcharacters = ('-',' ','.')
    return "".join(c for c in s if c.isalnum() or c in keepcharacters).strip()

def _joinNameString(s):
    '''Replace all numerics and non-alphanumerics in a name string, then concatenate using . ''' 
    newstr = re.findall(r"[\w]+",s)
    #newid = m['name'].replace(" ",".")
    return ".".join(newstr)

def alertAdmins(severity,msg):
    '''Alert admins of an issue. Intended to be configurable for notification mechanisms'''
    pass

def nameToFirstLast(namestr):
    names = namestr.split(".")
    first = names[0]
    last = " ".join(names[1:])
    return {'first': first, 'last': last}

def parse_datetime(dt):
  tz=pytz.timezone("America/New_York")
  try:
    xx= datetime.strptime(dt,"%Y-%m-%dT%H:%M:%SZ")
    result = pytz.utc.localize(xx, is_dst=None).astimezone(tz).replace(tzinfo=None)
  except:
    try:
        result= datetime.strptime(dt,"%Y-%m-%d %H:%M:%S")
    except:
        # Sat Jan 21 11:46:19 2017
        try:
            result= datetime.strptime(dt,"%a %b %d %H:%M:%S %Y")
        except:
            try:
                result= datetime.strptime(dt,"%Y-%m-%d")
            except:
                #2019-01-11 17:09:01.736307
                result= datetime.strptime(dt,"%Y-%m-%d %H:%M:%S.%f")
  return result

# resource is a DB model resource
def getResourcePrivs(resource=None,member=None,resourcename=None,memberid=None):
    if resourcename:
        resource=Resource.query.filter(Resource.name==resourcename).one()
    if not member and not memberid:
        member=current_user
    p = AccessByMember.query.join(Resource,((Resource.id == resource.id) & (Resource.id == AccessByMember.resource_id))).join(Member,((AccessByMember.member_id == member.id) & (Member.id == member.id))).one_or_none()
    if p:
        level= p.level
    else:
        level = -1

    if (member and member.privs('HeadRM')):
        level=AccessByMember.LEVEL_ADMIN
    if member and member.active.lower() != "true": 
        level=0
    else:
        try:
            level=int(level)
        except:
            level=0

    if level == -1:
        levelText="No Access"
    else:
        try:
            levelText=AccessByMember.ACCESS_LEVEL[level]
        except:
            levelText="#"+str(level)

    return (level,levelText)

