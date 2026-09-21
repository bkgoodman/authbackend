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

    events = Event.query.order_by(Event.name).all()
    return render_template('class_admin.html', events=events)

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
    
    from .eventbrite import get_event_capacities
    capacities = get_event_capacities()
    
    return render_template('my_classes.html', upcoming_dates=upcoming_dates, capacities=capacities)

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

@classes_bp.route('/api/send_notices')
@login_required
def send_notices():
    if not current_user.privs('Classes') and not current_user.privs('Admin'):
        return jsonify({"status": "error", "message": "Unauthorized"}), 403
    from .eventbrite import notify_instructors
    notify_instructors()
    return jsonify({"status": "ok", "message": "Notices sent"})

def register_pages(app):
    app.register_blueprint(classes_bp, url_prefix='/classes')
