#!/usr/bin/python

import os, sys, subprocess, re
DENIED="""asef.asdfasdf DENYLING
names.nasd denying
names.nasd denying
names.nasd denying
names.nasd denying"""

for x in DENIED.split("\n"):
	name = x.split()[0]
	(f,l)=name.split(".",2)
	print f,l
	f=subprocess.Popen(["grep","-i",l,"stripedebug.txt"],stdout=subprocess.PIPE)
	for x in  f.stdout.readlines(): print x.strip()
	f.wait()
	f=subprocess.Popen(["grep","-i",l,"memberpaysync_debug.txt"],stdout=subprocess.PIPE)
	for x in  f.stdout.readlines(): print x.strip()
	f.wait()

	

	print 
