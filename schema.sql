CREATE TABLE accessbyid(resource,rfidtag,enabled,lastmodified);
CREATE TABLE resources (name,description,owneremail, last_updated text);
CREATE TABLE blacklist (entry TEXT, entrytype text, reason TEXT, updated_date TEXT);
CREATE TABLE payments (member TEXT, paysystem TEXT, plan TEXT, customerid TEXT, expires_date TEXT, updated_date TEXT, checked_date TEXT, created_date text, email text);
CREATE TABLE members (
member TEXT, 
alt_email TEXT, 
firstname TEXT,
lastname TEXT, 
phone TEXT,
plan TEXT,
updated_date TEXT, 
access_enabled INTEGER, 
access_reason TEXT,
active INTEGER, nickname text, name text, created_date text);
CREATE TABLE tagsbymember (member text, tagtype text, tagid text, updated_date text, tagname TEXT);
CREATE TABLE accessbymember (member text, resource text, enabled text, updated_date text, level);
CREATE TABLE waivers (waiverid TEXT, created_date TEXT, email TEXT, firstname TEXT, lastname TEXT);
CREATE TABLE logs (member text, resource text, event_date text, event_type text, message text);
CREATE TABLE subscriptions (paysystem text, subid text, customerid text, name text, email text, planname text, plantype text, expires_date text, updated_date text, created_date text, checked_date text, active text);
CREATE TABLE feespaid (member,amount,fee_date,fee_name,fee_group,fee_description);
CREATE TABLE memberbycustomer (membername text, customerid text, paysystem text, memberid text);
CREATE TABLE members_Debug(
  member TEXT,
  alt_email TEXT,
  firstname TEXT,
  lastname TEXT,
  phone TEXT,
  "plan" TEXT,
  updated_date TEXT,
  access_enabled INT,
  access_reason TEXT,
  active INT,
  nickname TEXT,
  name TEXT,
  created_date TEXT
);
