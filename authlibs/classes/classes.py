from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, jsonify
from flask_user import current_user, login_required
from authlibs.db_models import db, Event, EventDate, EventInstructor, Member
from authlibs import utilities
import datetime
from . import classes_bp

@classes_bp.route('/admin', methods=['GET', 'POST'])
@login_required
def admin():
    if not current_user.privs('Classes') and not current_user.privs('Admin'):
        flash("You are not authorized to view the Class Administration page.", "danger")
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        action = request.form.get('action')
        event_id = request.form.get('event_id')
        member_id = request.form.get('member_id')
        
        if action == 'assign':
            if not EventInstructor.query.filter_by(event_id=event_id, member_id=member_id).first():
                ei = EventInstructor(event_id=event_id, member_id=member_id)
                db.session.add(ei)
                db.session.commit()
                flash("Instructor assigned", "success")
        elif action == 'unassign':
            ei = EventInstructor.query.filter_by(event_id=event_id, member_id=member_id).first()
            if ei:
                db.session.delete(ei)
                db.session.commit()
                flash("Instructor unassigned", "success")
        return redirect(url_for('classes.admin'))

    from .eventbrite import get_event_capacities
    capacities = get_event_capacities()
    
    events = Event.query.order_by(Event.name).all()
    
    # Calculate event warnings
    now = datetime.datetime.now()
    event_warnings = {}
    for ev in events:
        upcoming_dates = [ed for ed in ev.dates if ed.time_start >= now]
        if not upcoming_dates:
            event_warnings[ev.id] = {"text": "No upcoming classes scheduled.", "level": "warning"}
        else:
            all_full = True
            next_avail = None
            for ed in upcoming_dates:
                cap_info = capacities.get(ed.eventbrite_id, {})
                # If we don't have capacity info or it's sold out, consider full
                is_full = cap_info.get('is_sold_out', False)
                if not is_full:
                    all_full = False
                    if not next_avail or ed.time_start < next_avail.time_start:
                        next_avail = ed
            
            if all_full:
                event_warnings[ev.id] = {"text": "ALL classes are FULL (Need to add more on calendar)", "level": "danger"}
            elif next_avail:
                event_warnings[ev.id] = {"text": f"Next available slot is in {next_avail.time_start.strftime('%B')}", "level": "success"}

    return render_template('class_admin.html', events=events, capacities=capacities, event_warnings=event_warnings)

@classes_bp.route('/my_classes')
@login_required
def my_classes():
    instructor_links = EventInstructor.query.filter_by(member_id=current_user.id).all()
    event_ids = [ei.event_id for ei in instructor_links]
    
    now = datetime.datetime.now()
    upcoming_dates = EventDate.query.filter(
        EventDate.event_id.in_(event_ids),
        EventDate.time_start >= now
    ).order_by(EventDate.time_start).all() if event_ids else []
    
    return render_template('my_classes.html', upcoming_dates=upcoming_dates)

@classes_bp.route('/event/<eventbrite_id>/attendees')
@login_required
def get_event_attendees(eventbrite_id):
    from .eventbrite import get_attendees
    attendees = get_attendees(eventbrite_id)
    return jsonify({"attendees": attendees})

@classes_bp.route('/api/cron_sync')
def cron_sync():
    from .eventbrite import sync_events, notify_instructors
    success, msg = sync_events()
    if success:
        notify_instructors()
        return jsonify({"status": "ok", "message": "Synced and notifications sent"})
    else:
        return jsonify({"status": "error", "message": msg}), 500

def register_pages(app):
    app.register_blueprint(classes_bp, url_prefix='/classes')
