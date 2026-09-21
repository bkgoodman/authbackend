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
        has_more = True
        while has_more and url:
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

            dates_has_more = True
            while dates_has_more and dates_url:
                dates_r = requests.get(dates_url)
                if dates_r.status_code == 200:
                    dates_data = dates_r.json()
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
                    
                    # Pagination for series dates
                    d_pagination = dates_data.get('pagination', {})
                    dates_has_more = d_pagination.get('has_more', False)
                    if dates_has_more:
                        page = d_pagination.get('page_number', 1)
                        if e.get('is_series'):
                            dates_url = f"https://www.eventbriteapi.com/v3/series/{eventbrite_id}/events/?token={token}&page={page+1}"
                        else:
                            dates_has_more = False # Single events don't paginate
                else:
                    dates_has_more = False

            # Pagination for main events loop
            pagination = j.get('pagination', {})
            has_more = pagination.get('has_more', False)
            if has_more:
                page = pagination.get('page_number', 1)
                url = f"https://www.eventbriteapi.com/v3/organizations/{org_id}/events/?status=live&token={token}&page={page+1}"

    except Exception as ex:
        return False, str(ex)
    
    return True, "Synced successfully"

def get_event_capacities():
    """
    Returns a dictionary of EventDate eventbrite_ids to their ticket availability status
    {
       '1234567': {'is_sold_out': True, 'capacity': 10, 'sold': 10}
    }
    """
    org_id, token = get_eventbrite_creds()
    if not org_id or not token:
        return {}
        
    capacities = {}
    url = f"https://www.eventbriteapi.com/v3/organizations/{org_id}/events/?status=live&expand=ticket_availability&token={token}"
    
    try:
        has_more = True
        while has_more and url:
            r = requests.get(url)
            if r.status_code != 200:
                break
                
            j = r.json()
            for e in j.get('events', []):
                # For non-series events, the ticket_availability is on the event itself
                ta = e.get('ticket_availability', {})
                capacities[e['id']] = {
                    'is_sold_out': ta.get('is_sold_out', False),
                    'capacity': ta.get('maximum_quantity', 0),
                    'sold': ta.get('quantity_sold', 0)
                }
                
                # If series, we must paginate through its instances to get their individual capacities
                if e.get('is_series'):
                    dates_url = f"https://www.eventbriteapi.com/v3/series/{e['id']}/events/?expand=ticket_availability&status=live&token={token}"
                    dates_has_more = True
                    while dates_has_more and dates_url:
                        dates_r = requests.get(dates_url)
                        if dates_r.status_code == 200:
                            dates_data = dates_r.json()
                            for inst in dates_data.get('events', []):
                                i_ta = inst.get('ticket_availability', {})
                                capacities[inst['id']] = {
                                    'is_sold_out': i_ta.get('is_sold_out', False),
                                    'capacity': i_ta.get('maximum_quantity', 0),
                                    'sold': i_ta.get('quantity_sold', 0)
                                }
                            d_pag = dates_data.get('pagination', {})
                            if d_pag.get('has_more'):
                                dates_url = f"https://www.eventbriteapi.com/v3/series/{e['id']}/events/?expand=ticket_availability&status=live&token={token}&page={d_pag.get('page_number', 1)+1}"
                            else:
                                dates_has_more = False
                        else:
                            dates_has_more = False

            pagination = j.get('pagination', {})
            has_more = pagination.get('has_more', False)
            if has_more:
                page = pagination.get('page_number', 1)
                url = f"https://www.eventbriteapi.com/v3/organizations/{org_id}/events/?status=live&expand=ticket_availability&token={token}&page={page+1}"
    except Exception as ex:
        print(f"Error fetching capacities: {ex}")
        
    return capacities

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
