# vim:shiftwidth=2:expandtab

from ..templateCommon import *

blueprint = Blueprint("printerstatus", __name__, template_folder='templates', static_folder="static", url_prefix="/printerstatus")

@blueprint.route('/', methods=['GET'])
@login_required
def status():
    # Mock data representing 4 printers with various states
    printers = [
        {
            'name': 'Prusa i3 MK3S+ #1',
            'status': 'running', # green
            'progress': 68,
            'time_remaining': '1h 45m',
            'filename': 'benchy_0.2mm_pla.gcode',
            'error': None
        },
        {
            'name': 'Prusa i3 MK3S+ #2',
            'status': 'idle', # red
            'progress': 0,
            'time_remaining': None,
            'filename': None,
            'error': None
        },
        {
            'name': 'Bambu Lab X1C #1',
            'status': 'running', # green
            'progress': 92,
            'time_remaining': '12m',
            'filename': 'housing_lid_petg.gcode',
            'error': None
        },
        {
            'name': 'Formlabs Form 3',
            'status': 'error', # black
            'progress': 0,
            'time_remaining': None,
            'filename': 'resin_vat_bracket.stl',
            'error': 'Resin level low or cartridge missing'
        }
    ]
    return render_template('printerstatus.html', printers=printers)

def register_pages(app):
    app.register_blueprint(blueprint)
