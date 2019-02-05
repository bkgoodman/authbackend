#vim:shiftwidth=2:expandtab

from ..templateCommon import  *
waiversystem = {}

# ------------------------------------------------------------
# API Routes - Stable, versioned URIs for outside integrations
# Version 1:
# /api/v1/
#        /members -  List of all memberids, supports filtering and output formats
# ----------------------------------------------------------------

# You must call this modules "register_pages" with main app's "create_rotues"
blueprint = Blueprint("waivers", __name__, template_folder='templates', static_folder="static",url_prefix="/waivers")

# ------------------------------------------------------------
# Waiver controllers
# ------------------------------------------------------------

@blueprint.route('/', methods=['GET'])
@login_required
def waivers():
		waivers = Waiver.query
		#waivers = waivers.add_column(Member.member).outerjoin(Member,Member.id == Waiver.member_id)
		waivers = waivers.all()
		return render_template('waivers.html',waivers=waivers)

@blueprint.route('/update', methods=['GET'])
@login_required
def waivers_update():
		"""(Controller) Update list of waivers in the database. Can take a while."""
		updated = addNewWaivers()
		flash("Waivers added: %s" % updated)
		return redirect(url_for('waivers.waivers'))

###
### Utilities
###


def _addWaivers(waiver_list):
    """Add list-based Waiver data into the waiver table in the database"""
    for w in waiver_list:
      n = Waiver()
      n.waiver_id= w['waiver_id']
      n.email=w['email']
      n.firstname=w['firstname']
      n.lastname=w['lastname']
      n.created_date=authutil.parse_datetime(w['created_date'])
      db.session.add(n)
    db.session.commit()
    return len(waiver_list)

def addNewWaivers():
    """Check the DB to get the most recent waiver, add any new ones, return count added"""
    last_waiverid = waiver.getLastWaiverId()
    waiver_dict = {'api_key': waiversystem['Apikey'],'waiver_id': last_waiverid}
    waivers = waiver.getWaivers(waiver_dict)
    return _addWaivers(waivers)



def register_pages(app):
	app.register_blueprint(blueprint)
	waiversystem['Apikey'] = app.config['globalConfig'].Config.get('Smartwaiver','Apikey')
