/* Stuff we ADD to database just to TEST */
INSERT INTO users VALUES(2,1,'api','2019-01-13 13:38:13.748915','s33krit','admin','2019-01-13 13:38:13','','s33krit');
INSERT INTO tools VALUES(7,'testtool','simhostid',1);


/* TEST USERS */
INSERT INTO members VALUES(5000,'Testy.Testerson','Testy.Testerson@makeitlabs.com','test@example.com','Testy','Testy.Testerson','Testerson',NULL,'hobbyist',NULL,NULL,'true','Testy','Testy Testerson','2017-08-03 06:35:09.000000',NULL);
INSERT INTO tags_by_member VALUES(5000,'1111111111','rfid','keyfob2',NULL,'Testy.Testerson',5000);
INSERT INTO waivers VALUES(5000,'56915b7086917','Testy','Testerson','test@example.com',5000,'2016-01-09 19:11:44.000000');

INSERT INTO accessbymember VALUES(5000,5000,1,1,'2019-01-13 03:59:59',NULL,'','','','admin',0);
