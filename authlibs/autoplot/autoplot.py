# vim:shiftwidth=2


from ..templateCommon import  *
from authlibs.comments import comments
from datetime import datetime
from authlibs import ago

import crunchauto

blueprint = Blueprint("autoplot", __name__, template_folder='templates', static_folder="static",url_prefix="/autoplot")



@blueprint.route('/', methods=['GET','POST'])
@roles_required(['Admin','Finance','Autoplot'])
@login_required
def autoplot():
    """(Controller) Display Nodes and controls"""
    defdate = datetime.now().strftime("%Y-%m-%d")
    if 'Process' in request.form and 'datepicker' in request.form:
        (errors,warnings,debug,data,billables) = crunchauto.crunch_calendar(rundate=request.form['datepicker'])
        if (len(errors) == 0) and len(billables) ==1:
            mem = Member.query.filter(func.lower(Member.member)==func.lower(billables[0]['member'].replace("@makeitlabs.com",''))).one_or_none()
            if mem:
                print billables[0]['member']
                print mem.stripe_name
                sub = Subscription.query.filter(Subscription.member_id == mem.id).one_or_none()
                if sub:
                    print sub.subid
                    data['Stripe ID']=sub.subid
                    data['Plan']=sub.plan
                    data['Active']=sub.active
                    if not data['Active']:
                        errors.append("Membership Inactive")
                    if data['Plan'] != "pro":
                        errors.append("Not a pro member")
                else:
                    errors.append("Subscription Not Found")
            else:
                errors.append("Member not found")
        # If we found an error  in membership or subscriptionm chekcs
        if len(errors) > 0:
            data['Decision']='error'

        if data['Decision'] == 'bill':
            pass
            # Check log
            #run billing code
            # log even
            #
        return render_template('autoplot.html',defdate=defdate,errors=errors,warnings=warnings,debug=debug,data=data,billables=billables)

    # Default
    return render_template('autoplot.html',data=None,defdate=defdate)

def cli_autoplot(cmd,**kwargs):
    print "AUTOPLOT"
    (errors,warnings,debug,data,billables) = crunchauto.crunch_calendar()
    print "**ERRORS"
    print errors
    print "**WARNINGS"
    print warnings
    print "**DEBUG"
    print debug
    print "**DATA"
    print data
    print "**BILLABLES"
    print billables

    price = current_app.config['globalConfig'].Config.get("autoplot","stripe_item")
    crunchauto.do_payment('cus_J1MAqeEKC1dLfT',price,'autoplot-2021-wk07-test',"Autoplot TEST 2021 Week 7",test=True)

def register_pages(app):
	app.register_blueprint(blueprint)

0
