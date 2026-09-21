import requests
import datetime
from dateutil import tz
from flask import current_app
from authlibs.db_models import db, Event, EventDate, EventInstructor
from authlibs.google_admin import genericEmailSender

def get_eventbrite_creds():
    org_id = current_app.config['globalConfig'].Config.get('Eventbrite', 'org_id', fallback='')
    token = current_app.config['globalConfig'].Config.get('Eventbrite', 'token', fallback='')
    return org_id, token

def sync_events():
    org_id, token = get_eventbrite_creds()
    if not org_id or not token:
        return False, "Missing Eventbrite configuration"
    
    # Fetch live events
    url = f"https://www.eventbriteapi.com/v3/organizations/{org_id}/events/?status=live&token={token}"
    try:
        r = requests.get(url)
        if r.status_code != 200:
            return False, f"Error fetching events: {r.status_code} {r.text}"
        
        j = r.json()
        ny_tz = tz.gettz('America/New_York')
        
        for e in j.get('events', []):
            eventbrite_id = e['id']
            name = e.get('name', {}).get('text', 'Unknown')
            description = e.get('description', {}).get('text', '')[:2000] if e.get('description') else ''
            url = e.get('url', '')
            status = e.get('status', 'live')
            
            event = Event.query.filter_by(eventbrite_id=eventbrite_id).first()
            if not event:
                event = Event(eventbrite_id=eventbrite_id, name=name, description=description, url=url, status=status)
                db.session.add(event)
                db.session.commit()
            else:
                event.name = name
                event.description = description
                event.url = url
                event.status = status
                db.session.commit()

            # Now fetch dates
            dates_url = None
            if e.get('is_series'):
                dates_url = f"https://www.eventbriteapi.com/v3/series/{eventbrite_id}/events/?token={token}"
            else:
                dates_url = f"https://www.eventbriteapi.com/v3/events/{eventbrite_id}/?token={token}"

            if dates_url:
                dates_r = requests.get(dates_url)
                if dates_r.status_code == 200:
                    dates_data = dates_r.json()
                    # If it's a single event, wrap it in a list to use same loop
                    instances = dates_data.get('events', [dates_data]) if 'events' in dates_data else [dates_data]
                    
                    for instance in instances:
                        inst_id = instance['id']
                        time_start_str = instance.get('start', {}).get('local')
                        time_end_str = instance.get('end', {}).get('local')
                        
                        if time_start_str and time_end_str:
                            time_start = datetime.datetime.strptime(time_start_str, "%Y-%m-%dT%H:%M:%S")
                            time_end = datetime.datetime.strptime(time_end_str, "%Y-%m-%dT%H:%M:%S")
                            
                            ed = EventDate.query.filter_by(eventbrite_id=inst_id).first()
                            if not ed:
                                ed = EventDate(event_id=event.id, eventbrite_id=inst_id, time_start=time_start, time_end=time_end)
                                db.session.add(ed)
                            else:
                                ed.time_start = time_start
                                ed.time_end = time_end
                                ed.event_id = event.id
                    db.session.commit()
    except Exception as ex:
        return False, str(ex)
    
    return True, "Synced successfully"

def get_attendees(eventbrite_id):
    org_id, token = get_eventbrite_creds()
    if not token:
        return []
    
    url = f"https://www.eventbriteapi.com/v3/events/{eventbrite_id}/attendees/?token={token}"
    attendees = []
    try:
        r = requests.get(url)
        if r.status_code == 200:
            data = r.json()
            for a in data.get('attendees', []):
                profile = a.get('profile', {})
                attendees.append({
                    'name': profile.get('name', 'Unknown'),
                    'email': profile.get('email', 'Unknown')
                })
    except Exception as e:
        print(f"Error fetching attendees: {e}")
    return attendees

def notify_instructors():
    # Find all EventDates starting in the next 48 hours
    now = datetime.datetime.now()
    cutoff = now + datetime.timedelta(hours=48)
    
    upcoming_dates = EventDate.query.filter(EventDate.time_start > now, EventDate.time_start <= cutoff).all()
    
    for ed in upcoming_dates:
        event = ed.event
        instructors = event.instructors.all()
        if not instructors:
            continue
            
        attendees = get_attendees(ed.eventbrite_id)
        
        for instructor in instructors:
            member = instructor.member
            
            # Send email
            subject = f"Upcoming Class: {event.name} TOMORROW"
            body = f"Hello {member.firstname},\n\n"
            body += f"You are scheduled to instruct the following class within the next two days:\n"
            body += f"Class: {event.name}\n"
            body += f"Date/Time: {ed.time_start.strftime('%Y-%m-%d %I:%M %p')}\n\n"
            
            if attendees:
                body += f"Registered Students ({len(attendees)}):\n"
                for a in attendees:
                    body += f"- {a['name']} ({a['email']})\n"
            else:
                body += "No students registered yet.\n"
                
            body += "\nThank you!\nMakeIt Labs Automation"
            
            try:
                genericEmailSender("info@makeitlabs.com", member.email, subject, body)
            except Exception as e:
                print(f"Error sending email to {member.email}: {e}")
