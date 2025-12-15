#vim:shiftwidth=2:expandtab

from ..templateCommon import  *

from authlibs.comments import comments
from authlibs import accesslib

blueprint = Blueprint("calendars", __name__, template_folder='templates', static_folder="static",url_prefix="/calendars")



@blueprint.route('/', methods=['GET'])
@login_required
def calendars():
	return render_template('rescallist.html')

@blueprint.route('/<string:resource>', methods=['GET'])
@login_required
def resource(resource):
	return render_template('calendar.html')

def register_pages(app):
	app.register_blueprint(blueprint)
