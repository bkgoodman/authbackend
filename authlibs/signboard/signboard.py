#vim:shiftwidth=2:expandtab

from ..templateCommon import  *

from authlibs.comments import comments
from authlibs import accesslib
from flask import make_response
import datetime
import hashlib
import binascii

blueprint = Blueprint("signs", __name__, template_folder='templates', static_folder="static",url_prefix="/signs")



@blueprint.route('/', methods=['GET'])
@roles_required(['Admin','Useredit',"Signpost"])
@login_required
def signs():
	"""(Controller) Display Signs and controls"""
	signs = _get_signs()
	start_datetime=datetime.datetime.now()
	end_datetime=datetime.datetime.now()+datetime.timedelta(days=7)
	return render_template('signs.html',signs=signs,default_start=start_datetime,default_end=end_datetime)

@blueprint.route('/', methods=['POST'])
@login_required
@roles_required(['Admin','Useredit',"Signpost"])
def signs_create():
    r = Sign()
    if sign_write(r,request):
      db.session.add(r)
      db.session.commit()
      flash("Created.")
    return redirect(url_for('signs.signs'))

@blueprint.route('/<string:sign>', methods=['POST'])
@login_required
@roles_required(['Admin','Useredit',"Signpost"])
def signs_update(sign):
    tid = (sign)
    r = Sign.query.filter(Sign.id==tid).one_or_none()
    if not r:
                flash("Error: Sign not found","danger")
                return redirect(url_for('signs.signs'))

    if sign_write(r,request):
        db.session.commit()
        flash("Sign updated")
    return redirect(url_for('signs.signs'))

# Worker for Create and Update
# returns TRUE if record should persist (by CALLER)
def sign_write(r,request):
    r.start = datetime.datetime.strptime(request.form['input_start'], "%Y-%m-%dT%H:%M")
    r.end = datetime.datetime.strptime(request.form['input_end'], "%Y-%m-%dT%H:%M")
    farend = r.start + datetime.timedelta(days=31)

    print (f"GOT END {r.end}\n")
    if (r.start >= r.end):
        flash("End date must be AFTER start date","danger")
        return False

    if (r.end > farend):
        flash("Post duration is is too long. Max 30 days","danger")
        return False

    if (request.form['input_s_what'].strip() == ""):
        flash("Must have an event title","danger")
        return False
    else:
      r.s_what = (request.form['input_s_what'])


    if (request.form['input_s_where'].strip() == ""):
      r.s_where = None
    else:
      r.s_where = (request.form['input_s_where'])

    if (request.form['input_s_when'].strip() == ""):
      r.s_when = None
    else:
      r.s_when = (request.form['input_s_when'])

    r.s_desc = (request.form['input_s_desc'])
    if (request.form['input_s_desc'].strip() == ""):
      r.s_desc = None
    else:
      r.s_desc = (request.form['input_s_desc'])

    if (request.form['input_s_qr'].strip() == ""):
      r.s_qr = None
    else:
      r.s_qr = (request.form['input_s_qr'])

    r.s_qr_desc = (request.form['input_s_qr_desc'])
    if (request.form['input_s_qr_desc'].strip() == ""):
      r.s_qr_desc = None
    else:
      r.s_qr_desc = (request.form['input_s_qr_desc'])

    if r.s_qr is None:
        r.s_qr_desc=None

    r.priority = int(request.form['input_priority'])
    if ('input_retain' in request.form):
        r.retain = 1
    else:
        r.retain=0

    return True


@blueprint.route('/<string:sign>', methods=['GET'])
@login_required
def signs_show(sign):
    """(Controller) Display information about a given sign"""
    r = Sign.query.filter(Sign.id==sign).one_or_none()
    if not r:
        flash("Sign not found")
        return redirect(url_for('signs.signs'))

    start = r.start
    end=r.end
    return render_template('sign_edit.html',rec=r,default_start = start , default_end = end)


@blueprint.route('/<string:sign>/delete', methods=['POST'])
@roles_required(['Admin','Useredit',"Signpost"])
def sign_delete(sign):
        """(Controller) Delete a sign. Shocking."""
        r = Sign.query.filter(Sign.id == sign).one()
        db.session.delete(r)
        db.session.commit()
        flash("Sign deleted.")
        return redirect(url_for('signs.signs'))


def fingerprint_seq(seq):
    # Serialize in a deterministic way
    # Ensure every element is a string or int; convert others if needed.
    h = hashlib.blake2b(seq.encode("utf-8"), digest_size=8)
    return h.hexdigest()

# Show LIVE signboard
@blueprint.route('/_signboard')
def signboard():
    return do_signboard()

# Show DEBUG signboard
@blueprint.route('/_signboard_debug')
def signboard_debug():
    return do_signboard(debug=True)

# Worker for live of debug signboards
def do_signboard(debug=False):
    signs = _get_signs()
    # Make two lists. A PRIMARY that contains all valid posts
    # and a SECONDARY that contains valid posts that are only "always"
    # If the secondary list is empty - display the PRIMARY
    primary=[]
    secondary=[]

    now = datetime.datetime.now()
    for s in signs:
        if s.start < now < s.end:
            match s.priority:
                case 0: # Always
                    primary.append(s)
                case 1: # If nothing else
                    secondary.append(s)
                case 2: # Debug/Test only
                    if debug:
                        primary.append(s)

        elif now > s.end and s.retain == 0:
            # If after time and no retain, delete
            db.session.delete(s)
            

    # Choose list to display
    if primary:
        go = primary
    elif secondary:
        go = secondary
    else:
        go = [{'s_what': "Welcome to MakeIt Labs!"}]


    db.session.commit()
    html =  render_template('welcome.html',signs=go)
    response = make_response(html)
    response.headers['X-Page-Hash'] = fingerprint_seq(html)
    return response

def _get_signs():
    return  Sign.query.all()

def register_pages(app):
	app.register_blueprint(blueprint)
