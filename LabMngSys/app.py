import os
import smtplib
import uuid
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime
from flask import Flask, request, jsonify, render_template, session, Response, url_for
from functools import wraps
from flask_sqlalchemy import SQLAlchemy
from itsdangerous import URLSafeTimedSerializer
from werkzeug.security import generate_password_hash, check_password_hash
from icalendar import Calendar, Event

app = Flask(__name__)

# ==========================================
# EMAIL CONFIGURATION
# ==========================================
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
# IMPORTANT: For production, set SMTP_USERNAME and SMTP_PASSWORD as environment variables.
# Example: export SMTP_USERNAME="your-email@gmail.com"
#          export SMTP_PASSWORD="your-google-app-password"
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "your-email@example.com")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD") # No default for security
# ==========================================
# DATABASE CONFIGURATION
# ==========================================
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///lab_db_v7.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'super_secret_scratch_key'

db = SQLAlchemy(app)

# ==========================================
# 1. DATABASE MODELS
# ==========================================
class User(db.Model):
    __tablename__ = 'users' 
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False) 
    is_active = db.Column(db.Boolean, default=False)
    # NOTE: Email verification disabled for local development. Uncomment for production.
    # email_verified_at = db.Column(db.DateTime, nullable=True, default=None)

class Lab(db.Model):
    __tablename__ = 'labs'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    workplaces = db.relationship('Workplace', backref='lab', lazy=True, cascade="all, delete-orphan")
    is_paused = db.Column(db.Boolean, default=False)
    pause_end_date = db.Column(db.DateTime, nullable=True)

class Workplace(db.Model):
    __tablename__ = 'workplaces'
    id = db.Column(db.Integer, primary_key=True)
    lab_id = db.Column(db.Integer, db.ForeignKey('labs.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    is_paused = db.Column(db.Boolean, default=False)
    pause_end_date = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(50), default='Active')

study_equipment_association = db.Table('study_equipment',
    db.Column('study_id', db.Integer, db.ForeignKey('studies.id'), primary_key=True),
    db.Column('equipment_id', db.Integer, db.ForeignKey('equipment.id'), primary_key=True)
)

class Study(db.Model):
    __tablename__ = 'studies'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    supervisor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    primary_lab_id = db.Column(db.Integer, db.ForeignKey('labs.id'), nullable=False)
    books_entire_lab = db.Column(db.Boolean, default=False, nullable=False)

    supervisor = db.relationship('User', backref='studies')
    primary_lab = db.relationship('Lab', backref=db.backref('studies_primary', lazy=True))

    study_workplace_association = db.Table('study_workplace',
        db.Column('study_id', db.Integer, db.ForeignKey('studies.id'), primary_key=True),
        db.Column('workplace_id', db.Integer, db.ForeignKey('workplaces.id'), primary_key=True)
    )
    workplaces = db.relationship('Workplace', secondary=study_workplace_association, lazy='subquery',
                                backref=db.backref('studies_assigned_to', lazy=True))
    dedicated_equipment = db.relationship('Equipment', secondary=study_equipment_association, lazy='subquery',
                                        backref=db.backref('studies_assigned', lazy=True))
    
class EquipmentType(db.Model):
    __tablename__ = 'equipment_types'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    items = db.relationship('Equipment', backref='type', lazy=True, cascade="all, delete-orphan")

class Equipment(db.Model):
    __tablename__ = 'equipment'
    id = db.Column(db.Integer, primary_key=True)
    type_id = db.Column(db.Integer, db.ForeignKey('equipment_types.id'), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    serial_no = db.Column(db.String(50)) 
    is_paused = db.Column(db.Boolean, default=False)
    pause_end_date = db.Column(db.DateTime, nullable=True)
    custom_attributes = db.Column(db.JSON, default={})

class Reservation(db.Model):
    __tablename__ = 'reservations'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    study_id = db.Column(db.Integer, db.ForeignKey('studies.id'), nullable=False)
    workplace_id = db.Column(db.Integer, db.ForeignKey('workplaces.id'), nullable=True)
    lab_id = db.Column(db.Integer, db.ForeignKey('labs.id'), nullable=True)
    equipment_id = db.Column(db.Integer, db.ForeignKey('equipment.id'), nullable=True)
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=False)
    booking_group = db.Column(db.String(36), nullable=True)
    status = db.Column(db.String(20), default='Pending') 
    
    user = db.relationship('User', backref=db.backref('reservations', lazy=True))
    study = db.relationship('Study', backref=db.backref('reservations', lazy=True))
    workplace = db.relationship('Workplace', backref=db.backref('reservations', lazy=True))
    lab = db.relationship('Lab', backref=db.backref('reservations', lazy=True))
    equipment = db.relationship('Equipment', backref=db.backref('linked_reservations', lazy=True))

with app.app_context():
    db.create_all()
    if not User.query.first():
        admin = User(username='admin@tu-ilmenau.de', password=generate_password_hash('pass123'), role='admin', is_active=True)
        prof = User(username='prof@tu-ilmenau.de', password=generate_password_hash('pass123'), role='professor', is_active=True)
        db.session.add_all([admin, prof])
        db.session.commit()
        
        main_lab = Lab(name="Main Campus Lab")
        db.session.add(main_lab)
        db.session.commit()
        
        wp1 = Workplace(name="Test Room 101", lab_id=main_lab.id)
        wp2 = Workplace(name="Test Room 102", lab_id=main_lab.id)
        db.session.add_all([wp1, wp2])
        db.session.commit()

        t1 = EquipmentType(name="Amplifier")
        db.session.add(t1)
        db.session.commit()

# ==========================================
# HELPER FUNCTIONS
# ==========================================
def role_required(*roles):
    """Decorator to enforce role-based access control."""
    def wrapper(fn):
        @wraps(fn)
        def decorator(*args, **kwargs):
            if 'role' not in session:
                return jsonify({"error": "Authentication required"}), 401
            if session.get('role') not in roles:
                return jsonify({"error": "Unauthorized for your role"}), 403
            return fn(*args, **kwargs)
        return decorator
    return wrapper

def generate_ical(res_list, title, description):
    cal = Calendar()
    event = Event()
    event.add('summary', title)
    event.add('dtstart', res_list[0].start_date) # Assuming all reservations in list have same start/end for consolidated email
    event.add('dtend', res_list[0].end_date)     # Assuming all reservations in list have same start/end for consolidated email
    loc = ""
    if res_list[0].workplace:
        loc = res_list[0].workplace.name
    elif res_list[0].lab:
        loc = f"Entire Lab: {res_list[0].lab.name}"
    else:
        loc = "Unknown Location" # Fallback
    event.add('location', loc)
    event.add('description', description)
    cal.add_component(event)
    return cal.to_ical()

# For production, set the TEST_RECIPIENT_EMAIL environment variable to an empty string.
# For local testing, it defaults to your personal email to intercept all outgoing mail.
TEST_RECIPIENT_EMAIL = os.environ.get("TEST_RECIPIENT_EMAIL", "")

def send_email_async(subject, recipient, body, ical_data=None):
    # Do not attempt to send email if credentials are not configured
    if not SMTP_USERNAME or not SMTP_PASSWORD or SMTP_USERNAME == "your-email@example.com":
        print("--> SKIPPING EMAIL: SMTP credentials are not configured in environment variables.")
        return

    try:
        msg = MIMEMultipart()
        msg['Subject'] = subject
        msg['From'] = SMTP_USERNAME
        msg['To'] = TEST_RECIPIENT_EMAIL if TEST_RECIPIENT_EMAIL else recipient # Redirect all to test recipient if set
        msg.attach(MIMEText(body, 'plain'))
        if ical_data:
            part = MIMEApplication(ical_data, Name="lab_booking.ics")
            part['Content-Disposition'] = 'attachment; filename="lab_booking.ics"'
            msg.attach(part)
            
        final_recipient = TEST_RECIPIENT_EMAIL if TEST_RECIPIENT_EMAIL else recipient

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.sendmail(SMTP_USERNAME, final_recipient, msg.as_string())
        server.quit()
        print(f"--> Success: Email sent to {final_recipient} (Original: {recipient})")
    except Exception as e:
        print(f"--> Warning: Email failed. {e}")

def send_email(subject, recipient, body, ical_data=None):
    threading.Thread(target=send_email_async, args=(subject, recipient, body, ical_data)).start()

def notify_admins(subject, body):
    admins = User.query.filter_by(role='admin').all()
    for admin in admins:
        send_email(subject, admin.username, body)

def notify_account_approvers(subject, body):
    """Notifies users who can approve accounts (admin, professor)."""
    users_to_notify = User.query.filter(User.role.in_(['admin', 'professor'])).all()
    for user in users_to_notify:
        send_email(subject, user.username, body)

def _check_and_unpause_resources():
    """
    Checks for any resources with an expired pause date and unpauses them.
    This is designed to be called at the beginning of key routes.
    """
    now = datetime.now()
    updated = False

    # Check Labs
    expired_labs = Lab.query.filter(Lab.is_paused == True, Lab.pause_end_date != None, Lab.pause_end_date < now).all()
    for lab in expired_labs:
        lab.is_paused = False
        lab.pause_end_date = None
        updated = True

    # Check Workplaces
    expired_wps = Workplace.query.filter(Workplace.is_paused == True, Workplace.pause_end_date != None, Workplace.pause_end_date < now).all()
    for wp in expired_wps:
        wp.is_paused = False
        wp.pause_end_date = None
        updated = True

    # Check Equipment
    expired_eq = Equipment.query.filter(Equipment.is_paused == True, Equipment.pause_end_date != None, Equipment.pause_end_date < now).all()
    for eq in expired_eq:
        eq.is_paused = False
        eq.pause_end_date = None
        updated = True
    
    if updated:
        db.session.commit()

def _handle_booking_cancellations_for_pause(resource, resource_type, pause_end_date=None):
    """
    Finds future bookings for a resource, sends cancellation emails, and marks bookings for deletion.
    DOES NOT COMMIT. The commit must be handled by the calling route function.
    """
    now = datetime.now()
    query_filter = []
    reason = ""
    
    if resource_type == 'equipment':
        query_filter = [Reservation.equipment_id == resource.id]
        reason = f"the equipment '{resource.name}' has been placed under maintenance."

    elif resource_type == 'workplace':
        query_filter = [Reservation.workplace_id == resource.id]
        reason = f"the workplace '{resource.name}' has been placed under maintenance."

    elif resource_type == 'lab':
        workplace_ids_in_lab = [wp.id for wp in resource.workplaces]
        query_filter = [db.or_(Reservation.lab_id == resource.id, Reservation.workplace_id.in_(workplace_ids_in_lab))]
        reason = f"the lab '{resource.name}' has been placed under maintenance."

    if not query_filter:
        return

    # Base query for future reservations
    base_query = Reservation.query.filter(Reservation.start_date > now, *query_filter)

    # Add end date condition if provided
    if pause_end_date:
        pause_end_dt = datetime.strptime(pause_end_date, '%Y-%m-%d')
        base_query = base_query.filter(Reservation.start_date <= pause_end_dt)

    reservations_to_cancel = base_query.all()
    
    if not reservations_to_cancel:
        return

    for res in reservations_to_cancel:
        user_to_notify = res.user
        item_str = res.equipment.name if res.equipment else "Workplace/Lab-Only"
        start_str = res.start_date.strftime('%d/%m/%Y %H:%M')
        subject = "Booking Cancellation Due to Maintenance"
        body = f"Dear {user_to_notify.username.split('@')[0]},\n\nYour booking for '{item_str}' scheduled for {start_str} has been automatically cancelled because {reason}\n\nWe apologize for any inconvenience."
        send_email(subject, user_to_notify.username, body)
        db.session.delete(res)
# ==========================================
# METADATA & AUTH ROUTES
# ==========================================
@app.route('/')
def index(): return render_template('index.html')

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    user = User.query.filter_by(username=data['username']).first()
    if user and check_password_hash(user.password, data['password']):
        if not user.is_active: return jsonify({"error": "Account pending approval."}), 403
        session['user_id'] = user.id
        session['role'] = user.role
        session['username'] = user.username
        return jsonify({"role": user.role, "user_id": user.id}), 200
    return jsonify({"error": "Invalid credentials"}), 401

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username', '').lower()
    if not username.endswith('@tu-ilmenau.de'): return jsonify({"error": "Only @tu-ilmenau.de allowed."}), 400
    if User.query.filter_by(username=username).first(): return jsonify({"error": "Email registered."}), 409
    new_user = User(username=username, password=generate_password_hash(data['password']), role=data['role'], is_active=False)
    db.session.add(new_user)
    db.session.commit()

    # Notify account approvers directly since email verification is disabled for local dev
    notify_account_approvers(
        "New Account Request", 
        f"A new user has registered and is awaiting approval:\n\nEmail: {username}\nRole: {data['role']}"
    )
    return jsonify({"message": "Registration successful! Awaiting administrator approval."}), 201

@app.route('/api/forgot_password', methods=['POST'])
def forgot_password():
    email = request.json.get('email', '').lower()
    user = User.query.filter_by(username=email).first()
    
    # Always return a success message to prevent user enumeration
    if user:
        serializer = URLSafeTimedSerializer(app.secret_key)
        token = serializer.dumps(email, salt='password-reset')
        reset_url = url_for('reset_password_page', token=token, _external=True)
        
        subject = "Password Reset Request for Lab Management System"
        body = f"You requested a password reset. Please click the link below to set a new password. This link will expire in 30 minutes.\n\n{reset_url}"
        send_email(subject, email, body)
        
    return jsonify({"message": "If an account with that email exists, a password reset link has been sent."}), 200

@app.route('/reset_password/<token>')
def reset_password_page(token):
    # This route just renders the main page. The token is passed to the template,
    # and JavaScript will handle showing the correct form.
    return render_template('index.html', reset_token=token)

@app.route('/api/reset_password', methods=['POST'])
def reset_password():
    data = request.json
    token = data.get('token')
    new_password = data.get('password')
    
    serializer = URLSafeTimedSerializer(app.secret_key)
    try:
        email = serializer.loads(token, salt='password-reset', max_age=1800) # 30 minute expiration
    except:
        return jsonify({"error": "The password reset link is invalid or has expired."}), 400

    user = User.query.filter_by(username=email).first_or_404()
    user.password = generate_password_hash(new_password)
    db.session.commit()
    
    return jsonify({"message": "Your password has been successfully reset. You can now log in."}), 200

# NOTE: Email verification route disabled for local development. Uncomment for production.
# @app.route('/verify_email/<token>')
# def verify_email(token):
#     serializer = URLSafeTimedSerializer(app.secret_key)
#     try:
#         email = serializer.loads(token, salt='email-verification', max_age=3600) # 1 hour expiration
#     except:
#         return "<h1>The verification link is invalid or has expired.</h1>"
#     user = User.query.filter_by(username=email).first_or_404()
#     if user.email_verified_at:
#         return "<h1>Account already verified. Please wait for administrator approval.</h1>"
#     else:
#         user.email_verified_at = datetime.utcnow()
#         db.session.commit()
#         notify_account_approvers("New Account Request", f"A new, email-verified user has registered and is awaiting approval:\n\nEmail: {user.username}\nRole: {user.role}")
#         return "<h1>Your email has been verified! An administrator will approve your account shortly.</h1>"

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"message": "Logged out"}), 200

@app.route('/api/metadata', methods=['GET'])
def get_metadata():
    if 'role' not in session: return jsonify({"error": "Unauthorized"}), 401
    _check_and_unpause_resources()
    
    data = {
        "labs": [{"id": l.id, "name": l.name} for l in Lab.query.all()],
        "workplaces": [{"id": w.id, "name": w.name, "lab_id": w.lab_id} for w in Workplace.query.filter_by(status='Active').all()],
        "studies": [{
            "id": s.id, 
            "name": s.name, 
            "dedicated_equipment": [{"id": eq.id, "name": eq.name} for eq in s.dedicated_equipment],
            "primary_lab_id": s.primary_lab_id,
            "books_entire_lab": s.books_entire_lab,
            "workplace_ids": [wp.id for wp in s.workplaces]
        } for s in Study.query.all()],
        # All authenticated users need to see equipment types to book them.
        "equipment_types": [{"id": t.id, "name": t.name} for t in EquipmentType.query.all()],
        "all_equipment": [],
        "supervisors": []
    }

    # Only show management-specific data (for creating/editing studies) to relevant roles
    if session['role'] in ['supervisor', 'professor', 'admin']:
        data["all_equipment"] = [{"id": eq.id, "name": eq.name} for eq in Equipment.query.order_by(Equipment.name).all()]
        valid_supervisors = User.query.filter(User.role.in_(['supervisor', 'professor', 'admin'])).all()
        data["supervisors"] = [{"id": u.id, "username": u.username} for u in valid_supervisors]
    return jsonify(data), 200

# ==========================================
# MASTER BOOKINGS LIST
# ==========================================
@app.route('/api/reservations', methods=['GET'])
def get_reservations():
    if 'role' not in session: return jsonify({"error": "Unauthorized"}), 401
    role, user_id = session['role'], session['user_id'] # Corrected logic from previous turn
    
    base_query = Reservation.query.order_by(Reservation.start_date.desc())
    if role == 'student': reservations = base_query.filter_by(user_id=user_id).all()
    elif role == 'supervisor': reservations = base_query.join(Study).filter(Study.supervisor_id == user_id).all()
    else: reservations = base_query.all()

    # Group reservations by booking_group for a consolidated view
    grouped_bookings = {}
    for r in reservations:
        group_id = r.booking_group
        if group_id not in grouped_bookings:
            grouped_bookings[group_id] = {
                "group_id": group_id,
                "user": r.user.username,
                "study": r.study.name,
                "start": r.start_date.strftime('%d/%m/%Y %H:%M'),
                "end": r.end_date.strftime('%d/%m/%Y %H:%M'),
                "status": r.status,
                "locations": set(),
                "items": set()
            }
        
        if r.workplace:
            grouped_bookings[group_id]["locations"].add(r.workplace.name)
        elif r.lab: # This implies an entire lab booking
            grouped_bookings[group_id]["locations"].add(f"Entire Lab: {r.lab.name}")
        
        if r.equipment:
            grouped_bookings[group_id]["items"].add(r.equipment.name)

    # Convert sets to lists for JSON serialization
    final_list = list(grouped_bookings.values())
    for booking in final_list:
        booking["locations"] = sorted(list(booking["locations"]))
        booking["items"] = sorted(list(booking["items"]))

    return jsonify(final_list), 200

@app.route('/api/reservations/<string:group_id>', methods=['DELETE'])
def delete_reservation(group_id):
    if 'role' not in session: return jsonify({"error": "Unauthorized"}), 401
    reservations = Reservation.query.filter_by(booking_group=group_id).all()
    if not reservations: return jsonify({"error": "Reservation group not found."}), 404
    res = reservations[0] # Use the first reservation for permission checks
    
    user_id, role = session['user_id'], session['role']

    # Students can only delete their own reservations
    if role == 'student' and res.user_id != user_id:
        return jsonify({"error": "Unauthorized. You can only cancel your own reservations."}), 403

    # Supervisors can delete their own, or any within a study they supervise
    if role == 'supervisor':
        is_own_reservation = res.user_id == user_id
        study = db.session.get(Study, res.study_id)
        is_in_supervised_study = study and study.supervisor_id == user_id
        if not is_own_reservation and not is_in_supervised_study:
            return jsonify({"error": "Unauthorized. You can only cancel your own or those in studies you supervise."}), 403
    
    # Delete all reservations in the group
    for r in reservations:
        db.session.delete(r)
    db.session.commit()
    return jsonify({"message": "Reservation cancelled/deleted!"}), 200

# ==========================================
# BOOKING ROUTES
# ==========================================
@app.route('/api/items/<int:type_id>', methods=['GET'])
def get_items(type_id):
    if 'role' not in session: return jsonify({"error": "Unauthorized"}), 401
    items = Equipment.query.filter_by(type_id=type_id).all()
    return jsonify([{"id": i.id, "name": i.name, "serial_no": i.serial_no, "is_paused": i.is_paused, "custom_attributes": i.custom_attributes} for i in items]), 200

@app.route('/api/search_available', methods=['GET'])
def search_available():
    if 'role' not in session: return jsonify({"error": "Unauthorized"}), 401
    _check_and_unpause_resources()
    try:
        additional_type_id = request.args.get('type_id')
        study_id = request.args.get('study_id')
        req_start = datetime.strptime(request.args.get('start'), '%Y-%m-%dT%H:%M')
        req_end = datetime.strptime(request.args.get('end'), '%Y-%m-%dT%H:%M')
        booking_scope = request.args.get('booking_scope') # New
        selected_workplace_ids_str = request.args.get('selected_workplace_ids') # New, comma-separated
        
        if req_end <= req_start: return jsonify({"error": "End time must be after start time."}), 400
        study = db.session.get(Study, study_id)
        if not study: return jsonify({"error": "A valid study must be selected."}), 404

        if req_start.date() < study.start_date or req_end.date() > study.end_date:
            return jsonify({"error": f"Booking dates must fall within the Study timeframe."}), 400

        # Determine target locations and check for conflicts
        target_lab = study.primary_lab
        if target_lab.is_paused:
            return jsonify({"error": f"The primary Lab '{target_lab.name}' for this study is paused."}), 409
        
        # Determine the specific workplaces/lab to check based on booking_scope
        workplace_ids_to_check = []
        lab_id_to_check = None
        error_message = "The selected location for this study is already booked during this time."

        if booking_scope == 'entire_lab':
            lab_id_to_check = target_lab.id
            workplace_ids_to_check = [wp.id for wp in target_lab.workplaces] # Check all WPs in the lab
            error_message = f"The entire Lab '{target_lab.name}' is already booked during this time."
        elif booking_scope == 'all_assigned_workplaces':
            if not study.workplaces: return jsonify({"error": "Study has no specific workplaces assigned."}), 400
            for wp in study.workplaces:
                if wp.is_paused: return jsonify({"error": f"Workplace '{wp.name}' assigned to this study is paused."}), 409
                workplace_ids_to_check.append(wp.id)
            error_message = f"One or more assigned workplaces in Lab '{target_lab.name}' are already booked during this time."
        elif booking_scope == 'individual_workplaces': # This covers both 'individual_assigned_workplaces' and 'individual_workplaces_in_lab' from the frontend perspective
            if not selected_workplace_ids_str: return jsonify({"error": "No individual workplaces selected."}), 400
            selected_wp_ids = [int(x) for x in selected_workplace_ids_str.split(',') if x]
            
            # Validate selected workplaces belong to the study's context
            valid_wps_for_study = []
            if study.books_entire_lab: # Can select any WP in the primary lab
                valid_wps_for_study = [wp.id for wp in target_lab.workplaces]
            else: # Can select only from assigned WPs
                valid_wps_for_study = [wp.id for wp in study.workplaces]
            
            if not all(wp_id in valid_wps_for_study for wp_id in selected_wp_ids):
                return jsonify({"error": "Selected workplaces are not valid for this study's configuration."}), 400

            for wp_id in selected_wp_ids:
                wp = db.session.get(Workplace, wp_id)
                if wp.is_paused: return jsonify({"error": f"Workplace '{wp.name}' is paused."}), 409
                workplace_ids_to_check.append(wp_id)
            error_message = f"One or more selected workplaces in Lab '{target_lab.name}' are already booked during this time."

        # Always check for a lab-wide booking on the parent lab, plus any specific workplaces being targeted.
        conflict_conditions = [Reservation.lab_id == target_lab.id]
        if workplace_ids_to_check:
            conflict_conditions.append(Reservation.workplace_id.in_(workplace_ids_to_check))

        overlap = Reservation.query.filter(
            db.or_(*conflict_conditions),
            Reservation.start_date < req_end,
            Reservation.end_date > req_start,
            Reservation.status == 'Approved'
        ).first()

        if overlap:
            return jsonify({"error": error_message}), 409

        # Find all busy equipment in the timeslot from Approved reservations
        overlapping_reservations = Reservation.query.filter(Reservation.start_date < req_end, Reservation.end_date > req_start, Reservation.status == 'Approved').all()
        busy_equipment_ids = {res.equipment_id for res in overlapping_reservations if res.equipment_id}

        available_items = []
        found_ids = set()

        for item in study.dedicated_equipment:
            if item.id not in busy_equipment_ids and not item.is_paused:
                available_items.append(item)
                found_ids.add(item.id)

        # 2. If user wants to search for additional types, get those too
        if additional_type_id:
            additional_items_query = Equipment.query.filter(
                Equipment.type_id == additional_type_id,
                Equipment.is_paused == False,
                Equipment.id.notin_(busy_equipment_ids),
                Equipment.id.notin_(found_ids) # Don't add duplicates
            )
            available_items.extend(additional_items_query.all())

        # 3. Handle workplace-only booking (if no dedicated eq and no additional search)
        if not study.dedicated_equipment and not additional_type_id:
            return jsonify([]), 200

        return jsonify([{"id": i.id, "name": i.name, "serial_no": i.serial_no, "custom_attributes": i.custom_attributes} for i in available_items]), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/book', methods=['POST'])
def book_item():
    if 'user_id' not in session: return jsonify({"error": "Unauthorized"}), 401
    try:
        data = request.json
        start_date = datetime.strptime(data['start_date'], '%Y-%m-%dT%H:%M')
        end_date = datetime.strptime(data['end_date'], '%Y-%m-%dT%H:%M')
        study_id = data.get('study_id')
        equipment_ids = data.get('equipment_ids', [])
        booking_scope = data.get('booking_scope') # New
        selected_workplace_ids = data.get('selected_workplace_ids', []) # New

        study = db.session.get(Study, study_id)
        if not study: return jsonify({"error": "Invalid Study ID"}), 404

        res_status = 'Pending' if session['role'] == 'student' else 'Approved'
        booking_group_id = uuid.uuid4().hex
        created_reservations = []
        base_lab_id = study.primary_lab_id

        # 1. Create reservations for the selected locations
        locations_to_book = [] # List of (workplace_id, lab_id) tuples
        if booking_scope == 'entire_lab':
            locations_to_book.append((None, base_lab_id)) # Book the lab itself
        elif booking_scope == 'all_assigned_workplaces':
            if not study.workplaces: return jsonify({"error": "Study has no specific workplaces assigned."}), 400
            for wp in study.workplaces:
                locations_to_book.append((wp.id, base_lab_id))
        elif booking_scope == 'individual_workplaces': # This covers both 'individual_assigned_workplaces' and 'individual_workplaces_in_lab' from the frontend perspective
            if not selected_workplace_ids: return jsonify({"error": "No individual workplaces selected."}), 400
            for wp_id in selected_workplace_ids:
                locations_to_book.append((wp_id, base_lab_id))
        else:
            return jsonify({"error": "Invalid booking scope provided."}), 400

        for wp_id, lab_id in locations_to_book:
            res_loc = Reservation(user_id=session['user_id'], study_id=study_id, workplace_id=wp_id, lab_id=lab_id, start_date=start_date, end_date=end_date, status=res_status, booking_group=booking_group_id)
            db.session.add(res_loc)
            created_reservations.append(res_loc)

        # 2. Create reservations for equipment (booked once per item, associated with the primary lab)
        for eq_id in equipment_ids:
            overlap = Reservation.query.filter(Reservation.equipment_id == eq_id, Reservation.start_date < end_date, Reservation.end_date > start_date, Reservation.status == 'Approved').first()
            if overlap: db.session.rollback(); return jsonify({"error": f"Equipment '{overlap.equipment.name}' is already booked in this timeslot."}), 409
            
            # If only one workplace is booked, link equipment to that workplace. Otherwise, link to lab.
            eq_workplace_id = None
            if len(locations_to_book) == 1 and locations_to_book[0][0] is not None:
                eq_workplace_id = locations_to_book[0][0]

            res_eq = Reservation(user_id=session['user_id'], study_id=study_id, equipment_id=eq_id, workplace_id=eq_workplace_id, lab_id=base_lab_id, start_date=start_date, end_date=end_date, status=res_status, booking_group=booking_group_id)
            db.session.add(res_eq)
            created_reservations.append(res_eq)
            
        db.session.commit()

        user_email = session['username']
        
        # Summarize items for email
        booked_items_summary = []
        if booking_scope == 'entire_lab': booked_items_summary.append(f"Entire Lab: {study.primary_lab.name}")
        elif booking_scope == 'all_assigned_workplaces': booked_items_summary.append(f"All Assigned Workplaces: {', '.join([db.session.get(Workplace, wp_id).name for wp_id, _ in locations_to_book])}")
        elif booking_scope == 'individual_workplaces': booked_items_summary.append(f"Selected Workplaces: {', '.join([db.session.get(Workplace, wp_id).name for wp_id, _ in locations_to_book])}")
        if equipment_ids:
            eq_names = {r.equipment.name for r in created_reservations if r.equipment}
            if eq_names: booked_items_summary.append(f"Equipment: {', '.join(eq_names)}")
        items_str = "; ".join(booked_items_summary) if booked_items_summary else "Location booking"
        target_str = study.primary_lab.name
        
        if res_status == 'Approved':
            ical = generate_ical(created_reservations, "Lab Booking Confirmed", f"Items: {items_str}")
            body = f"Your booking for {target_str} ({items_str}) from {start_date.strftime('%d/%m/%Y %H:%M')} is CONFIRMED. Invite attached."
            send_email("Lab Booking Confirmed!", user_email, body, ical)
            return jsonify({"message": "Booking successful! Consolidated email sent."}), 200
        else:
            body = f"Your request for {target_str} ({items_str}) from {start_date.strftime('%d/%m/%Y %H:%M')} is awaiting approval."
            send_email("Lab Booking Pending", user_email, body)
            # Send a single, consolidated notification to the study supervisor
            if study.supervisor:
                supervisor_body = f"A new booking request from {user_email} for study '{study.name}' is awaiting your approval.\n\nItems: {items_str}\nTimeslot: {start_date.strftime('%d/%m %H:%M')} to {end_date.strftime('%d/%m %H:%M')}"
                send_email("New Booking Request for Approval", study.supervisor.username, supervisor_body)
            return jsonify({"message": "Booking submitted for approval!"}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

# ==========================================
# ADMIN ROUTES 
# ==========================================
@app.route('/api/admin/pending_users', methods=['GET'])
@role_required('admin', 'professor')
def get_pending_users(): return jsonify([{"id": u.id, "username": u.username, "role": u.role} for u in User.query.filter(User.is_active==False).all()]), 200

@app.route('/api/admin/approve_user/<int:user_id>', methods=['POST'])
@role_required('admin', 'professor')
def approve_user(user_id):
    user = db.session.get(User, user_id)
    if user:
        data = request.get_json()
        if data and 'role' in data:
            new_role = data['role']
            # Basic validation to prevent arbitrary roles
            if new_role in ['student', 'supervisor', 'professor', 'admin']:
                user.role = new_role

        user.is_active = True
        db.session.commit()
        send_email("Account Approved", user.username, f"Your account for the Lab Management System has been approved. Your assigned role is: {user.role}.")
        return jsonify({"message": f"User approved. Role set to '{user.role}'."}), 200
    return jsonify({"error": "Not found"}), 404

@role_required('admin', 'professor', 'supervisor')
@app.route('/api/admin/pending_reservations', methods=['GET'])
def get_pending_reservations():
    role, user_id = session.get('role'), session.get('user_id')
    
    base_query = Reservation.query.filter_by(status='Pending')
    if role in ['admin', 'professor']: 
        pending_reservations = base_query.all()
    elif role == 'supervisor': 
        pending_reservations = base_query.join(Study).filter(Study.supervisor_id == user_id).all()
    else: return jsonify({"error": "Unauthorized"}), 403

    # Group reservations by booking_group
    grouped_bookings = {}
    for r in pending_reservations:
        group_id = r.booking_group
        if group_id not in grouped_bookings:
            grouped_bookings[group_id] = {
                "group_id": group_id,
                "user": r.user.username,
                "study": r.study.name,
                "target": r.workplace.name,
                "start": r.start_date.strftime('%d/%m/%Y %H:%M'),
                "end": r.end_date.strftime('%d/%m/%Y %H:%M'),
                "items": []
            }
        item_name = r.equipment.name if r.equipment else "WORKPLACE-ONLY"
        grouped_bookings[group_id]["items"].append(item_name)

    return jsonify(list(grouped_bookings.values())), 200

@role_required('admin', 'professor', 'supervisor')
@app.route('/api/admin/approve_reservation/<string:group_id>', methods=['POST'])
def approve_res(group_id):
    reservations = Reservation.query.filter_by(booking_group=group_id, status='Pending').all()
    if not reservations: return jsonify({"error": "Booking not found or already actioned."}), 404
    for res in reservations: res.status = 'Approved'
    db.session.commit()
    
    # Send one consolidated email
    rep_res = reservations[0]
    items_str = ", ".join([r.equipment.name if r.equipment else "Workplace-Only" for r in reservations])
    ical = generate_ical(reservations, "Booking Approved", f"Items: {items_str}")
    send_email("Booking APPROVED", rep_res.user.username, f"Your booking for {rep_res.workplace.name} is APPROVED.", ical)
    return jsonify({"message": "Approved!"}), 200

@role_required('admin', 'professor', 'supervisor')
@app.route('/api/admin/reject_reservation/<string:group_id>', methods=['POST'])
def reject_res(group_id):
    reservations = Reservation.query.filter_by(booking_group=group_id, status='Pending').all()
    if not reservations: return jsonify({"error": "Booking not found or already actioned."}), 404
    user_email = reservations[0].user.username
    for res in reservations: db.session.delete(res)
    db.session.commit()
    send_email("Booking DECLINED", user_email, f"Your booking request was declined.")
    return jsonify({"message": "Rejected!"}), 200

@role_required('admin', 'professor')
@app.route('/api/admin/users', methods=['GET'])
def get_all_users(): return jsonify([{"id": u.id, "username": u.username, "role": u.role, "is_active": u.is_active} for u in User.query.all()]), 200

@app.route('/api/admin/users/<int:target_user_id>', methods=['PUT', 'DELETE'])
@role_required('admin')
def manage_user(target_user_id):
    user = db.session.get(User, target_user_id)
    if request.method == 'PUT':
        user.role = request.json['role']
        db.session.commit()
        return jsonify({"message": "Updated!"}), 200
    elif request.method == 'DELETE':
        db.session.delete(user)
        db.session.commit()
        return jsonify({"message": "Deleted!"}), 200

@app.route('/api/admin/studies', methods=['GET'])
@role_required('admin', 'professor', 'supervisor')
def get_all_studies():
    studies = Study.query.order_by(Study.name).all()
    return jsonify([{
        "id": s.id, "name": s.name, 
        "supervisor": s.supervisor.username, "supervisor_id": s.supervisor_id, 
        "target_location": s.primary_lab.name + \
                           (" (Entire Lab)" if s.books_entire_lab else \
                            (f" ({', '.join([wp.name for wp in s.workplaces])})" if s.workplaces else \
                             " (No specific location assigned)")) , 
        "start_date": s.start_date.strftime('%d/%m/%Y'), 
        "end_date": s.end_date.strftime('%d/%m/%Y'),
        "dedicated_equipment": [{"id": eq.id, "name": eq.name} for eq in s.dedicated_equipment]
    } for s in studies]), 200

@app.route('/api/studies', methods=['POST'])
@role_required('admin', 'professor', 'supervisor')
def create_study():
    data = request.json
    equipment_ids = data.get('equipment_ids', [])
    sd, ed = datetime.strptime(data['start_date'], '%Y-%m-%d').date(), datetime.strptime(data['end_date'], '%Y-%m-%d').date()
    
    new_study = Study(
        name=data['name'], 
        supervisor_id=data['supervisor_id'],
        primary_lab_id=data['primary_lab_id'],
        books_entire_lab=data.get('books_entire_lab', False),
        start_date=sd,
        end_date=ed
    )

    # Check for dedicated equipment conflicts
    if equipment_ids:
        for eq_id in equipment_ids:
            equipment_name = Equipment.query.get(eq_id).name
            conflicting_studies = Study.query.filter(
                Study.dedicated_equipment.any(Equipment.id == eq_id),
                Study.start_date < ed, # Current study's end date
                Study.end_date > sd    # Current study's start date
            ).all()
            
            if conflicting_studies:
                conflict_names = ", ".join([s.name for s in conflicting_studies])
                return jsonify({"error": f"Equipment '{equipment_name}' (ID: {eq_id}) is already dedicated to other studies ({conflict_names}) for overlapping dates. Please resolve the conflict."}), 409

    if not new_study.books_entire_lab:
        if not data.get('workplace_ids'):
            return jsonify({"error": "Studies not booking entire lab must have at least one workplace assigned."}), 400
        workplaces_to_assign = Workplace.query.filter(Workplace.id.in_(data['workplace_ids'])).all()
        if not all(wp.lab_id == int(new_study.primary_lab_id) for wp in workplaces_to_assign):
            return jsonify({"error": "All selected workplaces must belong to the primary lab."}), 400
        new_study.workplaces.extend(workplaces_to_assign)
    elif new_study.books_entire_lab and data.get('workplace_ids'):
        return jsonify({"error": "Studies booking entire lab cannot have specific workplaces assigned."}), 400

    if equipment_ids:
        equipment_to_assign = Equipment.query.filter(Equipment.id.in_(equipment_ids)).all()
        new_study.dedicated_equipment.extend(equipment_to_assign)

    db.session.add(new_study)
    db.session.commit()
    if session['role'] == 'supervisor':
        notify_admins("Parallel Info: New Study Created", f"Supervisor {session['username']} created a new study: {data['name']}.")
    return jsonify({"message": "Study created!"}), 201

@app.route('/api/studies/<int:study_id>', methods=['GET'])
@role_required('admin', 'professor', 'supervisor')
def get_study_details(study_id):
    study = Study.query.get_or_404(study_id)
    return jsonify({
        "id": study.id, "name": study.name, "supervisor_id": study.supervisor_id,
        "primary_lab_id": study.primary_lab_id,
        "books_entire_lab": study.books_entire_lab,
        "workplace_ids": [wp.id for wp in study.workplaces],
        "start_date": study.start_date.isoformat(), "end_date": study.end_date.isoformat(), 
        "dedicated_equipment_ids": [eq.id for eq in study.dedicated_equipment]
    }), 200

@app.route('/api/studies/<int:study_id>', methods=['PUT', 'DELETE'])
@role_required('admin', 'professor', 'supervisor')
def manage_study(study_id):
    study = Study.query.get_or_404(study_id)

    # Supervisors can only manage their own studies
    if session['role'] == 'supervisor' and study.supervisor_id != session['user_id']:
        return jsonify({"error": "Supervisors can only manage their own studies."}), 403

    if request.method == 'PUT':
        data = request.json
        if 'name' in data: study.name = data['name']
        if 'start_date' in data: study.start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
        if 'end_date' in data: study.end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date()
        if 'supervisor_id' in data: study.supervisor_id = data['supervisor_id']
        if 'primary_lab_id' in data: study.primary_lab_id = data['primary_lab_id']
        if 'books_entire_lab' in data: study.books_entire_lab = data['books_entire_lab']
        
        # Check for dedicated equipment conflicts when updating
        if 'equipment_ids' in data:
            for eq_id in data['equipment_ids']:
                equipment_name = Equipment.query.get(eq_id).name
                conflicting_studies = Study.query.filter(
                    Study.id != study.id, # Exclude the current study being edited
                    Study.dedicated_equipment.any(Equipment.id == eq_id),
                    Study.start_date < study.end_date, # Current study's end date
                    Study.end_date > study.start_date    # Current study's start date
                ).all()
                if conflicting_studies:
                    conflict_names = ", ".join([s.name for s in conflicting_studies])
                    return jsonify({"error": f"Equipment '{equipment_name}' (ID: {eq_id}) is already dedicated to other studies ({conflict_names}) for overlapping dates. Please resolve the conflict."}), 409

        if study.books_entire_lab:
            if data.get('workplace_ids'):
                return jsonify({"error": "Studies booking entire lab cannot have specific workplaces assigned."}), 400
            study.workplaces.clear()
        else:
            if not data.get('workplace_ids'):
                return jsonify({"error": "Studies not booking entire lab must have at least one workplace assigned."}), 400
            workplaces_to_assign = Workplace.query.filter(Workplace.id.in_(data['workplace_ids'])).all()
            if not all(wp.lab_id == int(study.primary_lab_id) for wp in workplaces_to_assign):
                return jsonify({"error": "All selected workplaces must belong to the primary lab."}), 400
            
            study.workplaces.clear()
            study.workplaces.extend(workplaces_to_assign)
        
        if 'equipment_ids' in data:
            study.dedicated_equipment.clear()
            equipment_to_assign = Equipment.query.filter(Equipment.id.in_(data['equipment_ids'])).all()
            study.dedicated_equipment.extend(equipment_to_assign)

    elif request.method == 'DELETE': db.session.delete(study)
    db.session.commit()
    return jsonify({"message": "Success!"}), 200

# ==========================================
# NEW: LABS & WORKPLACES CREATION ROUTES
# ==========================================
@app.route('/api/labs', methods=['POST'])
@role_required('admin', 'professor')
def create_lab():
    data = request.json
    db.session.add(Lab(name=data['name']))
    db.session.commit()
    return jsonify({"message": "Lab created!"}), 201

@app.route('/api/admin/labs/<int:lab_id>', methods=['PUT'])
@role_required('admin', 'professor', 'supervisor')
def manage_lab(lab_id):
    lab = Lab.query.get_or_404(lab_id)
    data = request.json
    if 'is_paused' in data:
        is_pausing = data['is_paused']
        pause_end_date = data.get('pause_end_date')
        if is_pausing:
            _handle_booking_cancellations_for_pause(lab, 'lab', pause_end_date)
            lab.pause_end_date = datetime.strptime(pause_end_date, '%Y-%m-%d') if pause_end_date else None
        else:
            lab.pause_end_date = None
        lab.is_paused = is_pausing
        if session['role'] in ['supervisor', 'professor'] and is_pausing:
            notify_admins("Parallel Info: Lab Paused", f"Supervisor {session['username']} paused Lab '{lab.name}' for maintenance.")

    db.session.commit()
    return jsonify({"message": "Lab status updated!"}), 200

@app.route('/api/admin/labs', methods=['GET'])
@role_required('admin', 'professor', 'supervisor')
def get_all_labs():
    return jsonify([{"id": l.id, "name": l.name, "is_paused": l.is_paused, "pause_end_date": l.pause_end_date.strftime('%d/%m/%Y') if l.pause_end_date else None} for l in Lab.query.all()]), 200

@role_required('admin', 'professor', 'supervisor')
@app.route('/api/admin/workplaces', methods=['GET'])
def get_all_workplaces():
    return jsonify([{"id": w.id, "name": w.name, "lab_name": w.lab.name, "is_paused": w.is_paused, "linked_studies": ", ".join([s.name for s in w.studies_assigned_to])} for w in Workplace.query.all()]), 200

@app.route('/api/workplaces', methods=['POST'])
@role_required('admin', 'professor', 'supervisor')
def create_workplace():
    data = request.json
    db.session.add(Workplace(name=data['name'], lab_id=data['lab_id'], is_paused=False))
    db.session.commit()
    return jsonify({"message": "Workplace created!"}), 201

@app.route('/api/workplaces/<int:wp_id>', methods=['PUT', 'DELETE'])
@role_required('admin', 'professor', 'supervisor')
def manage_workplace(wp_id):
    wp = Workplace.query.get_or_404(wp_id)
    if request.method == 'PUT':
        is_pausing = request.json['is_paused']
        pause_end_date = request.json.get('pause_end_date')
        if is_pausing:
            _handle_booking_cancellations_for_pause(wp, 'workplace', pause_end_date)
            wp.pause_end_date = datetime.strptime(pause_end_date, '%Y-%m-%d') if pause_end_date else None
        else:
            wp.pause_end_date = None
        wp.is_paused = is_pausing
        if session['role'] in ['supervisor', 'professor'] and is_pausing:
            notify_admins("Parallel Info: Workplace Paused", f"Supervisor {session['username']} paused Workplace '{wp.name}' for maintenance.")

        db.session.commit()
        return jsonify({"message": "Workplace status updated!"}), 200
    elif request.method == 'DELETE':
        if session['role'] not in ['admin', 'professor']: return jsonify({"error": "Unauthorized"}), 403
        db.session.delete(wp)
        db.session.commit()
        return jsonify({"message": "Deleted!"}), 200

@app.route('/api/admin/equipment_types', methods=['POST'])
@role_required('admin', 'professor')
def create_eq_type():
    db.session.add(EquipmentType(name=request.json['name']))
    db.session.commit()
    return jsonify({"message": "Added!"}), 201

@app.route('/api/admin/equipment', methods=['POST'])
@role_required('admin', 'professor')
def create_equipment():
    data = request.json
    db.session.add(Equipment(type_id=data['type_id'], name=data['name'], serial_no=data.get('serial_no', ''), custom_attributes=data.get('custom_attributes', {})))
    db.session.commit()
    return jsonify({"message": "Added!"}), 201

@app.route('/api/admin/equipment/<int:eq_id>', methods=['PUT', 'DELETE'])
@role_required('admin', 'professor', 'supervisor')
def manage_equipment(eq_id):
    eq = Equipment.query.get_or_404(eq_id)
    role = session['role']

    if request.method == 'PUT':
        data = request.json
        # All authorized roles can pause/unpause equipment
        if 'is_paused' in data:
            is_pausing = data['is_paused']
            pause_end_date = data.get('pause_end_date')
            if is_pausing:
                _handle_booking_cancellations_for_pause(eq, 'equipment', pause_end_date)
                eq.pause_end_date = datetime.strptime(pause_end_date, '%Y-%m-%d') if pause_end_date else None
            else:
                eq.pause_end_date = None
            eq.is_paused = is_pausing
            if role in ['supervisor', 'professor'] and is_pausing:
                notify_admins("Parallel Info: Equipment Paused", f"Supervisor {session['username']} paused {eq.name} (ID: {eq.id}) for maintenance.")


        # Only admin/professor can edit details
        if role in ['admin', 'professor']:
            if 'name' in data: eq.name = data['name']
            if 'serial_no' in data: eq.serial_no = data['serial_no']
        # Prevent supervisor from editing details
        elif role == 'supervisor' and ('name' in data or 'serial_no' in data):
            return jsonify({"error": "Supervisors can only pause/unpause equipment."}), 403

        db.session.commit()
        return jsonify({"message": "Updated!"}), 200

    elif request.method == 'DELETE':
        if role not in ['admin', 'professor']:
            return jsonify({"error": "Only Admins and Professors can delete equipment."}), 403
        db.session.delete(eq)
        db.session.commit()
        return jsonify({"message": "Equipment deleted!"}), 200

@app.route('/api/calendar', methods=['GET'])
def get_calendar_events():
    if 'role' not in session: return jsonify({"error": "Unauthorized"}), 401
    role, user_id = session['role'], session['user_id']
    events = []
    
    # Group approved reservations by booking_group to create single calendar events
    approved_reservations = Reservation.query.filter_by(status='Approved').all()
    grouped_bookings = {}
    for r in approved_reservations:
        if r.booking_group not in grouped_bookings:
            grouped_bookings[r.booking_group] = []
        grouped_bookings[r.booking_group].append(r)

    for group_id, res_list in grouped_bookings.items():
        rep_res = res_list[0] # Representative reservation for common details
        
        locations = sorted(list(set([r.workplace.name for r in res_list if r.workplace] + [f"Entire Lab: {r.lab.name}" for r in res_list if r.lab and not r.workplace])))
        items = sorted(list(set([r.equipment.name for r in res_list if r.equipment])))
        
        props = {
            "eventType": "booking", "study": rep_res.study.name, 
            "status": rep_res.status, "start": rep_res.start_date.strftime('%d/%m/%Y %H:%M'), "end": rep_res.end_date.strftime('%d/%m/%Y %H:%M'),
            "locations": locations,
            "items": items
        }

        # Anonymize event titles for students
        is_owner = rep_res.user_id == user_id
        if role == 'student' and not is_owner:
            title = "Booked"
            props['user'] = "Another User"
        else:
            title = f"{rep_res.study.name} ({rep_res.user.username.split('@')[0]})"
            props['user'] = rep_res.user.username

        events.append({
            "id": f"booking_{group_id}", 
            "title": title, 
            "start": rep_res.start_date.isoformat(), 
            "end": rep_res.end_date.isoformat(), 
            "color": "#28a745", "textColor": "#ffffff", 
            "extendedProps": props
        })
        
    # Show study periods only to relevant management/supervisor roles
    if role in ['admin', 'professor', 'supervisor']:
        studies = Study.query.filter_by(supervisor_id=user_id).all() if role == 'supervisor' else Study.query.all()
        for s in studies:
            study_location_str = s.primary_lab.name
            if s.books_entire_lab: study_location_str += " (Entire Lab)"
            elif s.workplaces: study_location_str += f" ({', '.join([wp.name for wp in s.workplaces])})"
            
            events.append({
                "id": f"study_{s.id}", "title": f"STUDY: {s.name}", "start": s.start_date.isoformat(), "end": s.end_date.isoformat(),
                "allDay": True, "color": "#6f42c1", "textColor": "#ffffff", "extendedProps": {"eventType": "study", "supervisor": s.supervisor.username, "location": study_location_str}
            })
            
    # Maintenance blocks are now visible to all logged-in users for planning purposes
    now_date = datetime.now().date()
    
    # Add maintenance blocks for paused items
    paused_labs = Lab.query.filter_by(is_paused=True).all()
    for lab in paused_labs:
        end_date = lab.pause_end_date.isoformat() if lab.pause_end_date else None
        events.append({ "id": f"maint_lab_{lab.id}", "title": f"MAINT: {lab.name}", "start": now_date.isoformat(), "end": end_date, "allDay": True, "display": 'background', "color": "#dc3545", "extendedProps": {"eventType": "maintenance", "resourceName": lab.name, "endDate": lab.pause_end_date.strftime('%d/%m/%Y') if lab.pause_end_date else "Indefinite"} })

    paused_wps = Workplace.query.filter_by(is_paused=True).all()
    for wp in paused_wps:
        if not wp.lab.is_paused: # Avoid clutter if parent lab is already paused
            end_date = wp.pause_end_date.isoformat() if wp.pause_end_date else None
            events.append({ "id": f"maint_wp_{wp.id}", "title": f"MAINT: {wp.name}", "start": now_date.isoformat(), "end": end_date, "allDay": True, "display": 'background', "color": "#fd7e14", "extendedProps": {"eventType": "maintenance", "resourceName": wp.name, "endDate": wp.pause_end_date.strftime('%d/%m/%Y') if wp.pause_end_date else "Indefinite"} })

    paused_eq = Equipment.query.filter_by(is_paused=True).all()
    for eq in paused_eq:
        end_date = eq.pause_end_date.isoformat() if eq.pause_end_date else None
        events.append({ "id": f"maint_eq_{eq.id}", "title": f"MAINT: {eq.name}", "start": now_date.isoformat(), "end": end_date, "allDay": True, "display": 'background', "color": "#ffc107", "extendedProps": {"eventType": "maintenance", "resourceName": eq.name, "endDate": eq.pause_end_date.strftime('%d/%m/%Y') if eq.pause_end_date else "Indefinite"} })

    return jsonify(events), 200

if __name__ == '__main__':
    app.run(debug=True)