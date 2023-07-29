
## WARNING
##
## This script is only used to pull live productin data and migrate to staging
## It should NEVER be run on a production system - hence the following checks
## 

if [ `hostname` != "staging" ] ; then  echo WRONG MACHINE ; exit -1 ; fi
if [ `pwd` != "/var/www/authbackend" ] ; then  echo WRONG DIRECTORY ; exit -1 ; fi
set -e 1
set -x 1
scp -i ~bkg/.ssh/id_rsa bkg@auth:/var/www/authbackend/makeit.db .
scp -i ~bkg/.ssh/id_rsa bkg@auth:/var/www/authbackend/log.db .


###
### Database migration from 2.1 to 2.2
###

# Already in 2.1
#sqlite3 makeit.db 'CREATE TABLE binchoice (
#        id INTEGER NOT NULL,
#        member_id INTEGER NOT NULL,
#        location_id INTEGER NOT NULL,
#        rank  INTEGER NOT NULL,
#        PRIMARY KEY (id),
#        FOREIGN KEY(member_id) REFERENCES members (id) ON DELETE CASCADE,
#        FOREIGN KEY(location_id) REFERENCES prostorelocations (id) ON DELETE CASCADE
#);'

echo sqlite3 makeit.db '
ALTER TABLE resources ADD COLUMN prodcode VARCHAR(50);
ALTER TABLE resources ADD COLUMN price INTEGER;
ALTER TABLE resources ADD COLUMN price_pro INTEGER;
ALTER TABLE resources ADD COLUMN free_min INTEGER;
ALTER TABLE resources ADD COLUMN free_min_pro INTEGER;
'

echo sqlite3 log.db '
ALTER TABLE usageLog ADD COLUMN payTier INTEGER;
'


###
### All this is TEMPORARY stuff only for STAGING 
### Do NOT Do this in production!!!! 
###

#sqlite3 makeit.db '
#INSERT INTO storageGrid VALUES(8,"Garage","Garage",6,8);
#INSERT INTO storageGrid VALUES(9,"Cleanspace","Cleanspace",4,2);
#INSERT INTO purchasable VALUES(10,"Broken Drill Bit","Broken Drill Bit",2000,"prod_MIERLuABAuCcLR","Broken Drill Bit","#test-resource-admins",5);
#'


# Changes Brad to use my Test Stripe Account
# Test CC for Brad
sqlite3 makeit.db 'update subscriptions set customerid="cus_MN5oo9gAnx3Vtn" where member_id=13;' 
# Invalid Test CC for Berndt
sqlite3 makeit.db 'update subscriptions set customerid="cus_NxyWLTzuDOM62R" where member_id=470;' 
#sqlite3 makeit.db 'update resources set price=1500 where id=36;' 
#sqlite3 makeit.db 'update resources set price_pro=1000, prodcode="prod_NoaY9dJVuAh41m" where id=36;' 
sqlite3 makeit.db 'update resources set prodcode="prod_NoaY9dJVuAh41m" where id=36;' 
#sqlite3 makeit.db 'update resources set free_min_pro=30 where id=36;' 

# Waterjet Product code for Brad Strip Test prod_NoaY9dJVuAh41m


# Debug data
sqlite3 log.db 'insert into log (member_id,resource_id,event_type,time_logged,time_reported,message) VALUES (13,36,3031,"2023-02-01 00:00:00","2023-02-01 00:00:00","Test Billed");'
sqlite3 log.db 'insert into log (member_id,resource_id,event_type,time_logged,time_reported,message) VALUES (13,36,3031,"2023-03-01 00:00:00","2023-03-01 00:00:00","Test Billed");'
sqlite3 log.db 'insert into log (member_id,resource_id,event_type,time_logged,time_reported,message) VALUES (13,36,3031,"2023-04-01 00:00:00","2023-04-01 00:00:00","Test Billed");'
sqlite3 log.db 'insert into log (member_id,resource_id,event_type,time_logged,time_reported,message) VALUES (13,36,3031,"2023-05-01 00:00:00","2023-05-01 00:00:00","Test Billed");'
sqlite3 log.db 'insert into usagelog (member_id,resource_id,tool_id,time_logged,time_reported,idleSecs,activeSecs,enabledSecs) VALUES (13,36,5024,"2023-04-28 01:00:00","2023-04-28 01:00:00",3600,1800,3600);'
sqlite3 log.db 'insert into usagelog (member_id,resource_id,tool_id,time_logged,time_reported,idleSecs,activeSecs,enabledSecs) VALUES (13,36,5024,"2023-05-01 01:00:00","2023-05-01 01:00:00",3600,1800,3600);'
sqlite3 log.db 'insert into usagelog (member_id,resource_id,tool_id,time_logged,time_reported,idleSecs,activeSecs,enabledSecs) VALUES (13,36,5024,"2023-05-01 02:00:00","2023-05-01 02:00:00",3600,1800,3600);'
sqlite3 log.db 'insert into usagelog (member_id,resource_id,tool_id,time_logged,time_reported,idleSecs,activeSecs,enabledSecs) VALUES (13,36,5024,"2023-05-02 02:00:00","2023-05-02 00:00:00",3600,1800,3600);'
sqlite3 log.db 'insert into usagelog (member_id,resource_id,tool_id,time_logged,time_reported,idleSecs,activeSecs,enabledSecs) VALUES (13,36,5024,"2023-05-30 02:00:00","2023-05-30 00:00:00",3600,1800,3600);'

sqlite3 log.db 'insert into log (member_id,resource_id,event_type,time_logged,time_reported,message) VALUES (239,36,3031,"2023-04-01 00:00:00","2023-04-01 00:00:00","Test Billed");'
sqlite3 log.db 'insert into log (member_id,resource_id,event_type,time_logged,time_reported,message) VALUES (239,36,3031,"2023-05-01 00:00:00","2023-05-01 00:00:00","Test Billed");'
sqlite3 log.db 'insert into usagelog (member_id,resource_id,tool_id,time_logged,time_reported,idleSecs,activeSecs,enabledSecs) VALUES (239,36,5024,"2023-04-28 01:00:00","2023-04-28 01:00:00",3600,1800,3600);'
sqlite3 log.db 'insert into usagelog (member_id,resource_id,tool_id,time_logged,time_reported,idleSecs,activeSecs,enabledSecs,payTier) VALUES (239,36,5024,"2023-05-01 01:00:00","2023-05-01 01:00:00",3600,1800,3600,1);'
sqlite3 log.db 'insert into usagelog (member_id,resource_id,tool_id,time_logged,time_reported,idleSecs,activeSecs,enabledSecs,payTier) VALUES (239,36,5024,"2023-05-01 02:00:00","2023-05-01 02:00:00",3600,1800,3600,0);'

sqlite3 log.db 'insert into usagelog (member_id,resource_id,tool_id,time_logged,time_reported,idleSecs,activeSecs,enabledSecs) VALUES (470,36,5024,"2023-04-28 01:00:00","2023-04-28 01:00:00",3600,1800,3600);'


echo "DONT FORGET TO:"
echo pip install --upgrade stripe
