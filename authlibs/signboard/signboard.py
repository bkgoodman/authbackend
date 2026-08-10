#vim:shiftwidth=2:expandtab

from ..templateCommon import  *

from authlibs.comments import comments
from authlibs import accesslib
from flask import make_response, current_app
import datetime
import hashlib
import binascii
import json
import requests
import icalendar
import pytz
from dateutil import tz
import recurring_ical_events
from google import genai

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



# Show LIVE signboard
@blueprint.route('/_signboard')
def signboard():
    return do_signboard()

# Show DEBUG signboard
@blueprint.route('/_signboard_debug')
def signboard_debug():
    return do_signboard(debug=True)

def utctolocal(dt, endofdate=False):
    """Convert UTC datetime to local timezone"""
    to_zone = tz.gettz('America/New_York')
    
    # If it's already a datetime (likely UTC from iCal)
    if isinstance(dt, datetime.datetime):
        if dt.tzinfo is None: # Handle naive
            dt = dt.replace(tzinfo=tz.gettz('UTC'))
        return dt.astimezone(to_zone)
    
    # If it's just a date (All-day event)
    if isinstance(dt, datetime.date):
        if endofdate:
            return datetime.datetime.combine(dt, datetime.time(23, 59, 59, tzinfo=to_zone))
        else:
            return datetime.datetime.combine(dt, datetime.time(0, 0, 0, tzinfo=to_zone))
    return dt

def get_calendar_events(days=14):
    """Get events from Google Calendar"""
    # Calendar URLs from pubcal.py
    PUBLIC_URL="https://calendar.google.com/calendar/ical/makeitlabs.com_mpfejifn6j4f5klmu1oubknb34%40group.calendar.google.com/private-01f894c0d4256616b9da5022bfeede0c/basic.ics"
    
    events = []
    try:
        g = requests.get(PUBLIC_URL)
        cal = icalendar.Calendar.from_ical(g.text)
        g.close()

        now = datetime.datetime.now().replace(tzinfo=tz.gettz('America/New York'))
        cutoff = now + datetime.timedelta(days=days)

        # Use recurring_ical_events to expand recurring events
        recurring_events = recurring_ical_events.of(cal).between(now, cutoff)

        for component in recurring_events:
            calstart = utctolocal(component['DTSTART'].dt)
            calend = utctolocal(component.get('DTEND', component['DTSTART']).dt, endofdate=True)

            # Format date string
            diff_days = (calstart.date() - now.date()).days
            if diff_days == 0:
                daystr = "Today"
            elif diff_days == 1:
                daystr = "Tomorrow"
            elif 1 < diff_days < 7:
                daystr = calstart.strftime("%a")
            else:
                daystr = calstart.strftime("%b %d")

            shortstart = calstart.strftime("%-I:%M %p")
            shortend = calend.strftime("%-I:%M %p")
            when = f"{daystr} {shortstart} - {shortend}"

            summary = str(component.get('SUMMARY', 'Event'))
            
            # Get description if available
            description = ""
            if 'DESCRIPTION' in component:
                description = str(component['DESCRIPTION'])
                # Clean up description - remove HTML tags and limit length
                import re
                description = re.sub(r'<[^>]+>', '', description)  # Remove HTML
                description = description.replace('\n', ' ').strip()  # Replace newlines
                if len(description) > 200:
                    description = description[:200] + "..."
            
            # Determine location/device based on summary like original pubcal.py
            device = ""
            summary_lower = summary.lower()
            if 'mopa' in summary_lower and 'epilog' in summary_lower:
                device = "Laser Room"
            elif 'mopa' in summary_lower:
                device = "Laser Room"
            elif 'epilog' in summary_lower:
                device = "Laser Room"
            elif 'shopbot' in summary_lower:
                device = "Machine Shop"
            elif 'jetlathe' in summary_lower:
                device = "Machine Shop"
            elif 'prototrak' in summary_lower:
                device = "Machine Shop"
            elif 'bridgeport' in summary_lower:
                device = "Machine Shop"
            elif 'auto' in summary_lower:
                device = "Auto Area"
            elif 'tormach' in summary_lower:
                device = "Machine Shop"

            events.append({
                'what': summary,
                'when': when,
                'where': device,
                'detail': description if description else "",
                'source': 'calendar',
                'priority': 2  # 2 = Neutral priority, compete normally
            })
    except Exception as e:
        print(f"Error getting calendar events: {e}")
    
    return events

def get_eventbrite_events(days=14):
    """Get events from Eventbrite API"""
    events = []
    try:
        # Get API credentials from config
        org_id = current_app.config['globalConfig'].Config.get('Eventbrite', 'org_id', fallback='')
        token = current_app.config['globalConfig'].Config.get('Eventbrite', 'token', fallback='')
        
        if not org_id or not token:
            return events
            
        window = datetime.datetime.now() + datetime.timedelta(days=days)
        r = requests.get(f"https://www.eventbriteapi.com/v3/organizations/{org_id}/events/?status=live&expand=ticket_availability&token={token}")
        
        if r.status_code >= 200 and r.status_code <= 299:
            j = r.json()
            for x in j['events']:
                n = x['name']['text']
                desc = x['description']['text'].replace("\"","'")[:200]  # Truncate
                url = x['url']
                t = x['start']['local']
                d = datetime.datetime.strptime(t, "%Y-%m-%dT%H:%M:%S")
                if d < window:
                    ds = d.strftime("%A, %B %d, %I:%M %p")
                    events.append({
                        'what': n,
                        'when': ds,
                        'detail': desc,
                        'url': url,
                        'source': 'eventbrite',
                        'priority': 2  # 2 = Neutral priority, compete normally
                    })
    except Exception as e:
        print(f"Error getting Eventbrite events: {e}")
    
    return events

# Worker for live of debug signboards
def do_signboard(debug=False):
    # Get local database signs
    local_signs = _get_signs()
    primary = []
    secondary = []
    
    now = datetime.datetime.now()
    for s in local_signs:
        if s.start < now < s.end:
            match s.priority:
                case 0:  # Always
                    primary.append(s)
                case 1:  # If nothing else
                    secondary.append(s)
                case 2:  # Debug/Test only
                    if debug:
                        primary.append(s)
        elif now > s.end and s.retain == 0:
            db.session.delete(s)
    
    db.session.commit()
    
    # Convert local signs to dict format
    local_events = []
    for sign in primary:
        local_events.append({
            'what': sign.s_what or '',
            'when': sign.s_when or '',
            'where': sign.s_where or '',
            'detail': sign.s_desc or '',
            'url': sign.s_qr or '',
            'source': 'local',
            'priority': sign.priority  # 0 = Always display
        })
    
    # Also include secondary local events with priority info
    for sign in secondary:
        local_events.append({
            'what': sign.s_what or '',
            'when': sign.s_when or '',
            'where': sign.s_where or '',
            'detail': sign.s_desc or '',
            'url': sign.s_qr or '',
            'source': 'local',
            'priority': sign.priority  # 1 = Only if nothing else
        })
    
    # Get external events
    calendar_events = get_calendar_events()
    eventbrite_events = get_eventbrite_events()
    
    # Combine all events
    all_events = local_events + calendar_events + eventbrite_events
    
    # Use AI to merge and prioritize all events
    try:
        go = ai_curate_events(all_events, debug)
    except Exception as e:
        print(f"AI curation failed: {e}")
        # Fallback: if we have priority 0 events, use them
        if primary:
            go = primary
        # Otherwise use secondary local events or default
        elif secondary:
            go = secondary
        else:
            go = [{'s_what': "Welcome to MakeIt Labs!"}]
    
    html = render_template('welcome.html', signs=go)
    return html

@blueprint.route('/events_text')
def events_text():
    """Return a simple text list of events for the upcoming week"""
    cal_events = get_calendar_events(days=7)
    eb_events = get_eventbrite_events(days=7)
    
    all_events = cal_events + eb_events
    
    lines = []
    lines.append("EVENTS FOR THIS WEEK:")
    lines.append("=====================")
    
    for e in all_events:
        title = e.get('what', '').strip()
        when = e.get('when', '').strip()
        detail = e.get('detail', '').strip()
        
        lines.append(f"Title: {title}")
        if detail:
            # Truncate to first line
            lines.append(f"Detail: {detail.split(chr(10))[0]}")
        lines.append(f"When: {when}")
        lines.append("")
        
    response = make_response("\n".join(lines))
    response.mimetype = 'text/plain'
    return response

def ai_curate_events(all_events, debug=False):
    """Use Google AI to curate and prioritize events"""
    if not all_events:
        return [{'s_what': "Welcome to MakeIt Labs!"}]
    
    # Get Google AI API key
    api_key = current_app.config['globalConfig'].Config.get('GoogleAI', 'token', fallback='')
    if not api_key:
        # Sort events before fallback selection
        def event_sort_key(event):
            priority = event.get('priority', 2)
            when_str = event.get('when', '').lower()
            today_boost = 0 if 'today' in when_str else 1
            return (priority, today_boost)
        
        sorted_events = sorted(all_events, key=event_sort_key)
        # Fallback to first 3 events (now properly sorted)
        return [dict_to_sign(event) for event in sorted_events[:3]]
    
    client = genai.Client(api_key=api_key)
    
    # Sort events by priority and importance before limiting
    # Priority 0 first, then by today's events, then by time proximity
    def event_sort_key(event):
        priority = event.get('priority', 2)
        # Lower priority number = higher importance
        priority_score = priority
        
        # Boost for today's events
        when_str = event.get('when', '').lower()
        today_boost = 0 if 'today' in when_str else 1
        
        return (priority_score, today_boost)
    
    sorted_events = sorted(all_events, key=event_sort_key)
    
    # Prepare event data for AI
    events_text = ""
    for i, event in enumerate(sorted_events[:15], 1):  # Increased limit to 15 after sorting
        events_text += f"\nEvent {i}:\n"
        events_text += f"  What: {event.get('what', 'N/A')}\n"
        events_text += f"  When: {event.get('when', 'N/A')}\n"
        events_text += f"  Where: {event.get('where', 'N/A')}\n"
        events_text += f"  Detail: {event.get('detail', 'N/A')}\n"
        events_text += f"  Source: {event.get('source', 'N/A')}\n"
        events_text += f"  QR_Code: {event.get('url', '')}\n"
        events_text += f"  Priority: {event.get('priority', 2)} (0=Always display, 1=Only if nothing else, 2=Normal)\n"
    
    system = """
You are creating content for a front-lobby signboard at MakeIt Labs. Your task is to select and format the most important events to display.

IMPORTANT: This data is compiled from MULTIPLE SOURCES (local database, Google Calendar, Eventbrite). The same event may appear multiple times from different sources. You MUST identify and merge duplicate events before selecting.

DUPLICATE DETECTION:
- Events with similar titles/times are likely the same event
- When merging, prefer the source with more complete information
- Combine details from all sources when beneficial
- Count duplicates as ONE event, not multiple

SELECTION PROCESS (follow this order):
1. First, identify and merge any duplicate events across sources
2. Check if there are any Priority 0 events. If there are 3 or fewer, you MUST include all of them.
3. If there are more than 3 Priority 0 events, select the 3 most important Priority 0 events.
4. If you have fewer than 3 events after step 2, fill remaining slots with Priority 2 events (external calendar/Eventbrite) based on:
   - Events happening TODAY get highest preference
   - Public events, classes, and important announcements
   - Relevance and timing
5. ONLY use Priority 1 events if you have no Priority 0 or Priority 2 events available.

ADDITIONAL RULES:
- Select MAXIMUM 3 events total
- Filter out individual reservations - focus on public events
- If a title is long, create a short title and put details in the description
- If a good "where"/location is not specify - try to use following rules which match an eveent like:
   - Pottery -> "Pottery Studio (Basement)"
   - Woodworking -> "Wood Shop"
   - Laser -> "Laser Room"
   - Member's Nite/Open House -> "Cleanspace Meeting Area"
   - Automotive -> "Auto Area"
   - Welding -> "Welding Area"
   - Board Meetings -> "Conference Room"
   - Textiles/Sewing/Fabric -> "Textiles Studio"
- Important to SUMMARIZE an event "detail" as best for  a short lobby signboard (No Google meet links or URLS, etc)!!
- Omitt events that already happened
- Make "what" short by minimizing or removing redundant and obvious info.  We are at "MakeIt Labs" - we don't need language that says that

RESPONSE FORMAT:
Return ONLY a JSON array with exactly 3 objects. Do not user or enclose in markdown. Each object must have these fields:
- s_what: Short title (required)
- s_when: Time/date (required)
- s_where: Location (OMMIT IF EMPTY! Do not put "TBD" or any placeholders!)
- s_desc: Description (omit if not needed)- SUMMARIZE for a lobby-sign! No URLS or links or phone numbers, just short text!!
- s_qr: URL (omit if no URL)

Example:
[{"s_what": "Intro to Woodworking", "s_when": "Today 6:00 PM", "s_where": "Wood Shop", "s_desc": "Learn basic woodworking techniques"}]
"""
    
    prompt = f"Current datetime is {str(datetime.datetime.now())}. Here are the available events:\n{events_text}\n\nSelect and format the best 3 events for display."
    
    response = client.models.generate_content(
        model="gemini-3.5-flash",
        config=genai.types.GenerateContentConfig(
            system_instruction=system),
        contents=prompt
    )
    
    #print (f"Prompt: {prompt}\n")
    try:
        # Clean AI response - strip markdown code blocks if present
        response_text = response.text.strip()
        #print (f"Respomnse: {response_text}\n")
        
        # Check if response is wrapped in markdown code blocks
        if response_text.startswith('```json'):
            # Remove ```json at start and ``` at end
            response_text = response_text[7:]  # Remove ```json
            if response_text.endswith('```'):
                response_text = response_text[:-3]  # Remove ```
            response_text = response_text.strip()
        elif response_text.startswith('```'):
            # Remove generic code block
            response_text = response_text[3:]  # Remove ```
            if response_text.endswith('```'):
                response_text = response_text[:-3]  # Remove ```
            response_text = response_text.strip()
        
        # Parse AI response as JSON
        curated_events = json.loads(response_text)
        # Ensure we have exactly 3 events
        return curated_events[:3] if len(curated_events) >= 3 else curated_events
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}")
        print(f"Raw AI response: {response.text}")
        # Fallback: return first 3 events (already sorted above)
        print ("ERROR: Lobby sign bad JSON!\n")
        return [dict_to_sign(event) for event in sorted_events[:3]]

def dict_to_sign(event_dict):
    """Convert event dict to Sign-like object"""
    class SignDict:
        def __init__(self, d):
            self.s_what = d.get('what', '')
            self.s_when = d.get('when', '')
            self.s_where = d.get('where', '')
            self.s_desc = d.get('detail', '')
            self.s_qr = d.get('url', '')
    
    return SignDict(event_dict)

def _get_signs():
    return  Sign.query.all()

def register_pages(app):
	app.register_blueprint(blueprint)
