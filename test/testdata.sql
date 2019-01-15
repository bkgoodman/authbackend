PRAGMA foreign_keys=OFF;
/* If this is in your database - you are running a test server! */
CREATE TABLE test_database (test);

/* Stuff we ADD to database just to TEST */
INSERT INTO users VALUES(2,1,'api','2019-01-13 13:38:13.748915','s33krit','admin','2019-01-13 13:38:13','','s33krit');
INSERT INTO tools VALUES(7,'testtool','simhostid',1);


/****
 **** PRACTICES FOR ADDING TEST DATA
 ****
 **** 1. Use record numbers starting w/ 5000
 **** 2. Use OBVIOUS, self-desribing fake names
 **** 3. Use fake key fobs (not numbers of real fobs) - unless you have a need to test physical fobs
 **** 4. DO NOT inject fake payment data. Use stripe test APIs if you need to. (Some users here match Stripe test data)
 ****
 ****/

/* TEST USERS */
INSERT INTO members VALUES(5000,'Testy.Testerson','Testy.Testerson@makeitlabs.com','test@example.com','Testy','Testy.Testerson','Testerson',NULL,'hobbyist',NULL,NULL,'true','Testy','Testy Testerson','2017-08-03 06:35:09.000000',NULL);
INSERT INTO members VALUES(5001,'First.User','fuser@makeitlabs.com','fu@example.com','First','fuser','User',NULL,'pro',NULL,NULL,'true','First','First User','2017-08-03 06:35:09.000000',NULL);
INSERT INTO members VALUES(5002,'bill.tester','billtester@makeitlabs.com','tester_foo123@makeitlabs.com','Bill','bill.tester','Tester',NULL,'pro',NULL,NULL,'true','Bill','Bill Tester','2017-08-03 06:35:09.000000',NULL);

/* Add Fake Resrouces */
INSERT INTO resources VALUES(5000,'TestResource','TestData','anyone@example.com',NULL,NULL,NULL,NULL,NULL,NULL);

INSERT INTO tags_by_member VALUES(5000,'1111111111','rfid','keyfob2',NULL,'Testy.Testerson',5000);
INSERT INTO tags_by_member VALUES(5001,'2222222222','rfid','keyfob2',NULL,'First.User',5001);
INSERT INTO tags_by_member VALUES(5002,'3333333333','rfid','keyfob2',NULL,'bill.tester',5002);
INSERT INTO waivers VALUES(5000,'56915b7086917','Testy','Testerson','test@example.com',5000,'2016-01-09 19:11:44.000000');

/* Some of these reference "real" database records - they might get purged if we didn't migrate
   any of that data into this db */

INSERT INTO accessbymember VALUES(5000,5000,1,1,'2019-01-13 03:59:59',NULL,'','','','admin',0);
INSERT INTO accessbymember VALUES(5001,5000,3,1,'2019-01-13 03:59:59',NULL,'','','','admin',0);
INSERT INTO accessbymember VALUES(5002,5000,6,1,'2019-01-13 03:59:59',NULL,'','','','admin',0);
INSERT INTO accessbymember VALUES(5003,5000,5000,1,'2019-01-13 03:59:59',NULL,'','','','admin',0);

INSERT INTO accessbymember VALUES(5005,5001,1,1,'2019-01-13 03:59:59',NULL,'','','','admin',0);
INSERT INTO accessbymember VALUES(5006,5002,1,1,'2019-01-13 03:59:59',NULL,'','','','admin',0);
INSERT INTO accessbymember VALUES(5007,5002,3,1,'2019-01-13 03:59:59',NULL,'','','','admin',0);
INSERT INTO accessbymember VALUES(5008,5002,6,1,'2019-01-13 03:59:59',NULL,'','','','admin',0);
INSERT INTO accessbymember VALUES(5009,5002,5000,1,'2019-01-13 03:59:59',NULL,'','','','admin',0);

