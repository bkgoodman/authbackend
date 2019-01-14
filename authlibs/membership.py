#!/usr/bin/env python
# vim:tabstop=2:expandtab
# Membership-related functions, to decouple from UI

import config
import dbutil
import utilities
import random
from collections import defaultdict
import config
import sys
import argparse
import ConfigParser
from flask import current_app

import logging
logger = logging.getLogger(__name__)

import google_admin as google

def syncWithSubscriptions(istest=False):
  '''Use the latest Subscription data to ensure Membership list is up to date'''
  addMissingMembers()
  createMissingMemberAccounts(isTest,False)
  

def searchMembers(searchstr):
  sstr = "%" + searchstr + "%"
  sqlstr = "SELECT * FROM  members WHERE stripe_name LIKE '%s' OR member LIKE '%s' or firstname LIKE '%s' or lastname LIKE '%s' or slack LIKE '%s'" % (sstr, sstr, sstr, sstr, sstr)
  current_app.logger.debug(sqlstr)
  return dbutil.query_db(sqlstr)


def createMember(m):
    """Add a member entry to the database"""
    if 'memberid' not in m or m['memberid'] != '':
        m['memberid'] = m['firstname'] + "." + m['lastname']
    sqlstr = "Select member from members where member = '%s'" % m['memberid']
    members = dbutil.query_db(sqlstr)
    if members:
        return {'status': 'error','message':'That User ID already exists'}
    else:
        # TODO: Handle missing values?
        sqlstr = """insert into members (member,firstname,lastname,phone,plan,nickname,updated_date,access_enabled,active)
                    VALUES ('%s','%s','%s','%s','','%s',DATETIME('now'),'0','0')
                 """ % (m['memberid'],m['firstname'],m['lastname'],m['phone'],m['nickname'])
        dbutil.execute_db(sqlstr)
        dbutil.get_db().commit()
    return {'status':'success','message':'Member %s was created' % m['memberid']}

def getMissingMembers():
    """Return details from active Subscriptions for name+email combination not in Members table"""
    sqlstr = """select s.name as stripe_name,s.email,s.subid,s.plan,s.customerid,s.active,s.created_date from subscriptions s left outer
    join members m on s.name=m.stripe_name and s.email=m.alt_email where m.stripe_name is null and s.active = 'true' and s.plan NOT IN ('workspace','trial') order by s.created_date"""
    missing = dbutil.query_db(sqlstr)

    sqlstr = """SELECT count(*) FROM subscriptions s 
    LEFT OUTER JOIN members m on s.name=m.stripe_name AND s.email=m.alt_email WHERE
    m.stripe_name IS NULL AND s.active = 'true' AND s.plan NOT IN ('workspace','trial') ORDER BY s.created_date"""
    matched = dbutil.query_db(sqlstr)
    return missing
    
def addMissingMembers():
    logger.info("Checking for any Subscriptions without a matching Membership entry")
    missing = getMissingMembers()
    members = []
    sqlstr = "select entry,entrytype from blacklist"
    bl_entries = dbutil.query_db(sqlstr)
    ignorelist = []
    for b in bl_entries:
        ignorelist.append(b['entry'])
    for p in missing:
        if p['subid'] in ignorelist:
            logger.info("Explicitly ignoring subscription id %s" % p['subid'])
            continue
        elif p['email'] in ignorelist:
            logger.info("Explicitly ignoring email %s" % p['email'])
            continue
        elif p['customerid'] in ignorelist:
            logger.info("Explicitly ignoring customer id %s" % p['customerid'])
            continue
        else:
            logger.info("Missing member: %s (%s) (%s)" % (p['stripe_name'],p['email'],p['created_date']))
            members.append((p['stripe_name'],p['email'],p['plan'],p['active'],p['created_date']))
    if len(members) > 0:
        logger.info("There were %i members missing, adding records now." % len(members))
        cur = dbutil.get_db().cursor()
        cur.executemany('INSERT into members (stripe_name,alt_email,plan,active,time_created) VALUES (?,?,?,?,?)', members)
        dbutil.get_db().commit()
        cur.close()
    else:
        logging.info("No members were missing. Hurrah!")

def getUnusedMemberId(m,memberids):
  # Create a userid in our default format - concatenate name with "."
  newid = utilities._joinNameString(m['stripe_name'])
  incr = 0
  while memberids[newid] == 1:
    incr = incr + 1
    newid = "%s%d" % (newid,incr)
  return newid

def googleEmailExists(m,memberid):
  # Member ID is available, check if existing account. If so, manual data check is required for now.
  search = google.searchEmail(memberid)
  logger.debug(search)
  return (len(search > 0))
  
  
def createMissingMemberAccounts(isTest=True,searchGoogle=False):
    """For any Member without a Member ID, create one (includes Google Domain account). If we can't, notify admins"""
    sqlstr = """select m.member, m.stripe_name, m.alt_email from members m order by m.time_created"""
    members = dbutil.query_db(sqlstr)
    
    # Mark used memberids
    memberids = defaultdict(int)
    for m in members:
      if m['member'] is not None:
        memberids[m['member']] = 1
    
    for m in members:
      if m['member'] is None:
        # Handle duplicate names through numeric additions
        memberid = getUnusedMemberId(m,memberids)
        if searchGoogle and googleEmailExists(m,memberid):
          msg = "Manual intervention required: %s (%s) needs an account created. Memberid %s is not used, but has an account." % (m['stripe_name'],m['alt_email'],memberid)
          logger.error(msg)
          continue
          
        # We're in testing mode, so populating old accounts where the id is not a dupe but the account exists
        sqlstr = "update members set member='%s' where stripe_name='%s' and alt_email='%s'" % (memberid,m['stripe_name'],m['alt_email'])
        dbutil.execute_db(sqlstr)
        logger.info("Adding member Id %s to database for user %s" % (memberid,m['stripe_name']))
            
        # Create the account
        if isTest:
            logger.warn("Need to see if we really need an account for %s (%s) or if this is a data issue" % (memberid,m['alt_email']))
        else:
            nameparts = utilities.nameToFirstLast(m['stripe_name'])
            # - Use first portion of name as Firstname, all remaining as Familyname
            password = "%s%d%d" % (nameparts['last'],random.randint(1,100000),len(nameparts['last']))
            google.createUser(nameparts['first'],nameparts['last'],memberid,m['alt_email'],password)
            google.sendWelcomeEmail(memberid,password,m['alt_email'])
        

        
def _syncMemberPlans():
    """Update Members table with currently paid-for plan from Subscriptions"""
    # Will this work when someone is on multiple subscriptions?
    sqlstr = """update members set plan = (select plan from subscriptions where members.name=subscriptions.name and members.email=subscriptions.email)
            where name in (select name from subscriptions)"""
    execute_db(sqlstr)
    get_db().commit()
    

def addMissingMembers_new(subs):
    """Add to Members table any members in Subscriptions but not in Members"""
    # Find all (Name + Email) keys where we don't have a member
    sqlstr = """select s.name, s.email, s.customerid select p.member from subscriptions p
            left outer join members m on p.member=m.member where m.member is null"""
    members = query_db(sqlstr)
    sqlstr2 = "select entry,entrytype from blacklist"
    bl_entries = query_db(sqlstr2)
    missingids = []
    users = []
    for m in members:
        missingids.append(m['member'])
    ignorelist = []
    for b in bl_entries:
        ignorelist.append(b['entry'])
    sqlstr3 = "select "
    for s in subs:
        if s['userid'] in missingids:
            if s['customerid'] in ignorelist:
                print("Customer ID is in the ignore list")
                continue
            users.append((s['userid'],s['firstname'],s['lastname'],s['membertype'],s['phone'],s['email'],"Datetime('now')"))
    if len(users) > 0:
        cur = get_db().cursor()
        cur.executemany('INSERT into members (member,firstname,lastname,plan,phone,alt_email,updated_date) VALUES (?,?,?,?,?,?,?)', users)
        get_db().commit()
    return len(users)    


if __name__ == "__main__":

    logging.basicConfig(stream=sys.stdout, level=logging.INFO)
    defaults = {'ServerPort': 5000, 'ServerHost': '127.0.0.1'}
    Config = ConfigParser.ConfigParser(defaults)
    Config.read('makeit.ini')
    ServerHost = Config.get('General','ServerHost')
    ServerPort = Config.getint('General','ServerPort')
    Database = Config.get('General','Database')
    AdminUser = Config.get('General','AdminUser')
    AdminPasswd = Config.get('General','AdminPassword')
    DeployType = Config.get('General','Deployment')
    DEBUG = Config.getboolean('General','Debug')

    parser=argparse.ArgumentParser()
    parser.add_argument("--test",help="DO NOT create Goole and Slack accounts",action="store_true")
    parser.add_argument("--force",help="Force it to create Google and Slack accounts - even in non-production environments",action="store_true")
    (args,extras) = parser.parse_known_args(sys.argv[1:])

    isTest=False
    if DeployType.lower() != "production":
      if not args.force:
        logger.info( "Non-production environments - no accounts will be created")
        isTest=True
      else:
        logger.info( "Non-production environments - but you are FORCING account creation")

    syncWithSubscriptions(isTest)  
