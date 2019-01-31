#!/usr/bin/python

import os,sys,json,subprocess,re



olds = json.load(open("doorbot-v1-api.acl"))
news = json.load(open("new_doorbot_v1.acl"))

print olds[0].keys()

oldmembers={}
newmembers={}
accesschange=0
nochange=0
denied=0
granted=0
nc_allowed=0
nc_denied=0


for i in olds:
    oldmembers[i['member']]=i
for i in news:
    newmembers[i['member']]=i


for x in oldmembers:
    if x not in newmembers:
        print x,"NOT in newmembers"

for x in newmembers:
    if x not in oldmembers:
        print x,"NOT in oldmembers"

for x in newmembers:
    if x in oldmembers:
        if newmembers[x]['tagid'] != oldmembers[x]['tagid']:
            print x,"TAG id changed"

for x in newmembers:
    if x in oldmembers:
        if newmembers[x]['allowed'] != oldmembers[x]['allowed']:
            accesschange+=1
            if oldmembers[x]['allowed'] == 'false' and newmembers[x]['allowed'] == 'allowed':
                desc = "GRANTING"
                granted += 1
            elif oldmembers[x]['allowed'] == 'allowed' and newmembers[x]['allowed'] == 'false':
                desc = "DENYING"
                denied += 1
            else:
                desc = "CHANGE from "+oldmembers[x]['allowed']+" TO "+newmembers[x]['allowed']
            print x,desc
            print "WAS",oldmembers[x]['warning']
            print "NEW",newmembers[x]['warning']
            print
        else:
            nochange+=1
            if oldmembers[x]['allowed'] == 'allowed':
                nc_allowed +=1
            else:
                nc_denied += 1

print len(oldmembers),"OLD members"
print len(newmembers),"NEW members"
print "ACCESS CHANGES", accesschange,"GRANTED",granted,"DENIED",denied,"NO-CHANGE",nochange
print "UNCHANGED: Total",nochange,"allowed",nc_allowed,"denied",nc_denied
