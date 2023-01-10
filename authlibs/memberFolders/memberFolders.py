# vim:tabstop=2:shiftwidth=2:expandtab

from ..templateCommon import *

from authlibs import accesslib

from authlibs.ubersearch import ubersearch
from authlibs import membership
from authlibs import payments
from authlibs.waivers.waivers import cli_waivers,connect_waivers
from authlibs.slackutils import automatch_missing_slack_ids,add_user_to_channel,send_slack_message
from authlibs.members.notices import send_all_notices
import base64
import random,string
import tempfile
import subprocess
import datetime
import os
import stat as statmod
from .. import ago
import math
from flask import send_from_directory,send_file,after_this_request
from werkzeug.utils import secure_filename

import paramiko,tempfile


# You must call this modules "register_pages" with main app's "create_rotues"
blueprint = Blueprint("memberFolders", __name__, template_folder='templates', static_folder="static",url_prefix="/memberFolders")


def getFolderConfig():
    config = {}
    error = None
    if current_app.config['globalConfig'].Config.has_option('MemberFolders','method'):
        config['method'] = current_app.config['globalConfig'].Config.get('MemberFolders','method')
    else:
        return (None,"Internal Error: Member folder method undefined")

    if current_app.config['globalConfig'].Config.has_option('MemberFolders','user'):
        config['user'] = current_app.config['globalConfig'].Config.get('MemberFolders','user')
    else:
        return (None,"Internal Error: Member folder user undefined")

    if current_app.config['globalConfig'].Config.has_option('MemberFolders','password'):
        config['password'] = current_app.config['globalConfig'].Config.get('MemberFolders','password')
    else:
        return (None,"Internal Error: Member folder password undefined")

    if current_app.config['globalConfig'].Config.has_option('MemberFolders','server'):
        config['server'] = current_app.config['globalConfig'].Config.get('MemberFolders','server')
    else:
        return (None,"Internal Error: Member folder server undefined")

    if current_app.config['globalConfig'].Config.has_option('MemberFolders','base'):
        config['base'] = current_app.config['globalConfig'].Config.get('MemberFolders','base')
    else:
        return (None,"Internal Error: Member folder base undefined")

    if current_app.config['globalConfig'].Config.has_option('MemberFolders','cache'):
        config['cache'] = current_app.config['globalConfig'].Config.get('MemberFolders','cache')
    else:
        return (None,"Internal Error: Member folder cache undefined")

    if config['cache'][-1] != '/': config['cache']+= "/"

    if (current_user.memberFolder is None) or (current_user.memberFolder.strip() == ""):
        return (None,"Please ask an administrator to set up your member folder")

    if not os.path.isdir(config['cache']):
        return (None,"Internal Error: Cache Directory does not exist")

    return (config,None)


def sizeunit(val):
  if val==0: return "0b"
  units=['b','k','M','G','T','P','E','Z']
  l = math.log10(val)
  i = int(math.floor(l/3))
  u = units[int(i)]
  r = i*3
  d = math.pow(10,r)
  #print val,l,i,val/d,u
  s = "{0:4.0f}{1}".format(round(val/d),u)
  #print val,"=",s
  return s

@blueprint.route('/folder', methods=['GET'])
@login_required
def folder():
  #print ("ROOT FOLDER")
  return infolder("")

@blueprint.route('/folder/', methods=['GET'])
@blueprint.route('/folder', methods=['GET'])
@blueprint.route('/folder/<path:folder>', methods=['GET'])
@login_required
def infolder(folder=""):
    #print ("INFOLDER",folder)
    if folder.find("../") != -1 or folder.find("/..") != -1:
      flash("Invalid Filename","warning")
    (config,error) = getFolderConfig()
    if (error is not None):
      flash(error,"warning")
      return redirect(url_for("index"))
    path = config['base']+"/"+current_user.memberFolder+"/"+folder
    files = []

    with paramiko.Transport((config['server'],22)) as transport:
        transport.connect(None,config['user'],config['password'])
        with paramiko.SFTPClient.from_transport(transport) as sftp:
            for entry in sftp.listdir_attr(path):
                mode = entry.st_mode
                print ("ENTRY",entry)
                print ("ENTRY",entry.attr,entry.filename)
                print ("ENTRY",mode)
                print ("ENTRY",dir(entry))
                ext = entry.filename.split(".")[-1]
                created = datetime.datetime.fromtimestamp(entry.st_mtime)
                (ago1, ago2, ago3) = ago.ago(created,datetime.datetime.now())
                fullpath = folder+entry.filename
                files.append({
                    'name':entry.filename,
                    'size':entry.st_size,
                    'sizeText':sizeunit(entry.st_size),
                    'ago1':ago1,
                    'ago2':ago2,
                    'ago3':ago3,
                    'type':"",
                    'ext':ext,
                    'dir': True if (mode & statmod.S_IFDIR) else False,
                    'path':fullpath,
                    'lastmod':entry.st_mtime
                  })

    top = folder.split("/")
    if folder == "":
      up=None
    elif len(top)==1:
      up=""
    else:
      up = "/"+("/".join(top[:-1]))
    return render_template('folder.html',up=up,folder=folder,member=current_user,files=files)


@blueprint.route('/download/<path:filename>', methods=['GET'])
@login_required
def download(filename):
    @after_this_request
    def delete_after(response):
        try:
            os.remove(tempfilePath)
        except:
            pass
        return response

    if filename.find("../") != -1 or filename.find("/..") != -1:
      flash("Invalid Filename","warning")
      return redirect(url_for("memberFolders.folder",folder=""))
    (config,error) = getFolderConfig()
    if (error is not None):
      flash(error,"warning")
      return redirect(url_for("index"))
    path = config['base']+"/"+current_user.memberFolder+"/"+filename
    fn = os.path.split(path)[-1]
    files = []
    ext = filename.split(".")[-1]
    tempfileName = next(tempfile._get_candidate_names())+"."+ext
    tempfilePath = config['cache']+"/"+tempfileName
    path = config['base']+"/"+current_user.memberFolder+"/"+filename
    with paramiko.Transport((config['server'],22)) as transport:
        transport.connect(None,config['user'],config['password'])
        with paramiko.SFTPClient.from_transport(transport) as sftp:
            sftp.get(path,tempfilePath)

    ##XX = send_file(tempfilename,attachment_filename=fn,as_attachment=True)
   
    print  ("SENDING",config['cache'], fn)
    #return redirect(url_for("memberFolders.infolder"))
    ## return XX
    return send_from_directory(config['cache'], tempfileName, attachment_filename=fn, as_attachment=True)

@blueprint.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_file():

    (config,error) = getFolderConfig()
    if (error is not None):
      flash(error,"warning")
      return redirect(url_for("index"))

    folder=""
    if request.form and 'folder' in request.form:
      folder = request.form['folder']
      srcfolder = folder
    #print ("FOLDER IS",folder)
    if folder != "":
      if not folder.endswith("/"):
        #print ("AMMENDING FOLDER")
        folder += "/"
    if folder.find("../") != -1 or folder.find("/..") != -1:
      flash("Invalid Filename","warning")
      return redirect(url_for("memberFolders.folder",folder=""))
    #print ("UPLOADING TO FOLDER",folder)
    if request.method == 'POST':
        # check if the post request has the file part
        if 'file' not in request.files:
            flash('No file part')
            return redirect(url_for("memberFolders.infolder",folder=srcfolder))
        file = request.files['file']
        # if user does not select file, browser also
        # submit an empty part without filename
        if file.filename == '':
            flash('No selected file')
            return redirect(url_for("memberFolders.infolder",folder=srcfolder))
        if file:
            filename = secure_filename(file.filename)
            #print ("SAVE TO",filename)
            tempfileName = next(tempfile._get_candidate_names())
            tempfilePath = config['cache']+tempfileName
            file.save(tempfilePath)

            path = config['base']+"/"+current_user.memberFolder+"/"+folder+filename
            try:
                with paramiko.Transport((config['server'],22)) as transport:
                    transport.connect(None,config['user'],config['password'])
                    with paramiko.SFTPClient.from_transport(transport) as sftp:
                        print("SFTP",tempfilePath,path)
                        sftp.put(tempfilePath,path)
                os.remove(tempfilePath)
                flash("File saved","success")
            except BaseException as e:
                flash(f"Upload error: {e}","danger")
            return redirect(url_for('memberFolders.infolder', folder=srcfolder))
    flash("No file posted")
    return redirect(url_for('memberFolders.infolder', folder=srcfolder))

def register_pages(app):
	app.register_blueprint(blueprint)

