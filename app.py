import os
import csv
import math
import pytz
from io import StringIO
from flask import Flask, redirect, render_template, request, url_for, flash, session, make_response
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
from datetime import datetime, timedelta
from init_db import init_db
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'database.db')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

init_db()

app = Flask(__name__)
app.secret_key = "hostel-visitor-2026"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def calculate_time_spent(in_time_str, out_time_str):
    try:
        fmt = '%d-%m-%Y %I:%M %p'
        in_dt = datetime.strptime(in_time_str, fmt)
        out_dt = datetime.strptime(out_time_str, fmt)
        diff = out_dt - in_dt
        hours, remainder = divmod(diff.seconds, 3600)
        minutes = remainder // 60
        if hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"
    except:
        return "N/A"

def get_day_count(conn, day_date):
    day_str = day_date.strftime('%d-%m-%Y')
    cursor = conn.execute("SELECT COUNT(*) FROM visitors WHERE in_time LIKE?", (f'{day_str}%',))
    return cursor.fetchone()[0]

@app.route('/')
def home():
    conn = get_db()
    visitors = conn.execute("SELECT * FROM visitors ORDER BY id DESC LIMIT 5").fetchall()
    total_count = conn.execute("SELECT COUNT(*) FROM visitors").fetchone()[0]
    inside_count = conn.execute("SELECT COUNT(*) FROM visitors WHERE status = 'Inside'").fetchone()[0]
    checkout_count = total_count - inside_count
    rooms = conn.execute("SELECT DISTINCT room_number FROM visitors ORDER BY room_number").fetchall()

    labels = []
    data = []
    for i in range(6, -1, -1):
        day = datetime.now() - timedelta(days=i)
        labels.append(day.strftime("%a"))
        data.append(get_day_count(conn, day))

    conn.close()
    return render_template('home.html', visitors=visitors, total_count=total_count,
                           inside_count=inside_count, checkout_count=checkout_count,
                           rooms=rooms, labels=labels, data=data)

@app.route('/dashboard')
def dashboard():
    conn = get_db()
    total_count = conn.execute("SELECT COUNT(*) FROM visitors").fetchone()[0]
    inside_count = conn.execute("SELECT COUNT(*) FROM visitors WHERE status = 'Inside'").fetchone()[0]
    checkout_count = total_count - inside_count

    labels = []
    data = []
    for i in range(29, -1, -1):
        day = datetime.now() - timedelta(days=i)
        labels.append(day.strftime("%d %b"))
        data.append(get_day_count(conn, day))

    top_rooms = conn.execute("SELECT room_number, COUNT(*) as c FROM visitors GROUP BY room_number ORDER BY c DESC LIMIT 5").fetchall()

    # NEW: PURPOSE DATA FOR PIE CHART
    purpose_data = conn.execute('''
        SELECT purpose, COUNT(*) as count
        FROM visitors
        GROUP BY purpose
        ORDER BY count DESC
    ''').fetchall()

    purpose_labels = [row['purpose'] for row in purpose_data]
    purpose_counts = [row['count'] for row in purpose_data]

    conn.close()

    return render_template('dashboard.html',
                           total_count=total_count,
                           inside_count=inside_count,
                           checkout_count=checkout_count,
                           labels=labels, data=data,
                           top_rooms=top_rooms,
                           purpose_labels=purpose_labels,
                           purpose_counts=purpose_counts)

@app.route('/records')
def records():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page
    room = request.args.get('room')
    status = request.args.get('status')
    q = request.args.get('q')
    conn = get_db()
    query = "SELECT * FROM visitors WHERE 1=1"
    count_query = "SELECT COUNT(*) FROM visitors WHERE 1=1"
    params = []
    count_params = []
    if room:
        query += " AND room_number =?"
        count_query += " AND room_number =?"
        params.append(room)
        count_params.append(room)
    if status:
        query += " AND status =?"
        count_query += " AND status =?"
        params.append(status)
        count_params.append(status)
    if q:
        query += " AND visitor_name LIKE?"
        count_query += " AND visitor_name LIKE?"
        params.append(f"%{q}%")
        count_params.append(f"%{q}%")
    query += " ORDER BY id DESC LIMIT? OFFSET?"
    params.extend([per_page, offset])
    visitors = conn.execute(query, params).fetchall()
    total = conn.execute(count_query, count_params).fetchone()[0]
    inside_count = conn.execute("SELECT COUNT(*) FROM visitors WHERE status = 'Inside'").fetchone()[0]
    checkout_count = total - inside_count
    rooms = conn.execute("SELECT DISTINCT room_number FROM visitors ORDER BY room_number").fetchall()
    conn.close()
    total_pages = math.ceil(total / per_page) if total > 0 else 1
    return render_template('records.html', visitors=visitors, page=page, total_pages=total_pages, room=room, status=status, q=q, total_count=total, inside_count=inside_count, checkout_count=checkout_count, rooms=rooms)

@app.route('/export_csv')
def export_csv():
    if session.get('role')!= 'admin':
        flash('Only admin can export data', 'danger')
        return redirect(url_for('home'))
    conn = get_db()
    visitors = conn.execute("SELECT * FROM visitors ORDER BY id DESC").fetchall()
    conn.close()
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['ID', 'Visitor Name', 'Contact No', 'Student Name', 'Room No', 'Purpose', 'In Time', 'Out Time', 'Time Spent', 'Status', 'Photo'])
    for v in visitors:
        cw.writerow([v['id'], v['visitor_name'], v['contact_no'], v['student_name'], v['room_number'], v['purpose'], v['in_time'], v['out_time'], v['time_spent'], v['status'], v['photo']])
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=visitor_report.csv"
    output.headers["Content-type"] = "text/csv"
    return output

@app.route('/details/<int:id>')
def details(id):
    conn = get_db()
    visitor = conn.execute('SELECT * FROM visitors WHERE id =?', (id,)).fetchone()
    conn.close()
    if visitor is None:
        flash('Visitor not found', 'danger')
        return redirect(url_for('records'))
    return render_template('details.html', visitor=visitor)

@app.route("/visitor/<int:id>/tip")
def get_visitor_tip(id):
    conn = get_db()
    visitor = conn.execute('SELECT * FROM visitors WHERE id =?', (id,)).fetchone()
    conn.close()
    if visitor is None:
        flash('Visitor not found', 'danger')
        return redirect(url_for('records'))
    out_time = visitor['out_time'] if visitor['out_time'] else "Not checked out yet"
    status = visitor['status']
    prompt = f"""Visitor name: {visitor['visitor_name']}
    Contact: {visitor['contact_no']}
    Visiting Student: {visitor['student_name']}
    Room No: {visitor['room_number']}
    Purpose: {visitor['purpose']}
    In Time: {visitor['in_time']}
    Out Time: {out_time}
    Time Spent: {visitor['time_spent']}
    Status: {status}
    Based on this, give 1 practical security tip for the hostel guard. Keep it simple, encouraging, and not more than 2 lines."""
    try:
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        response = client.chat.completions.create(model="llama-3.1-8b-instant", messages=[{"role": "user", "content": prompt}])
        tip = response.choices[0].message.content
    except Exception as e:
        tip = "AI tip service is currently unavailable. Please check your GROQ_API_KEY."
    return render_template("details.html", visitor=visitor, tip=tip)

@app.route('/add_visitor', methods=['GET', 'POST'])
def add_visitor():
    if session.get('role')!= 'admin':
        flash('You do not have permission to add visitors', 'danger')
        return redirect(url_for('home'))
    if request.method == 'POST':
        visitor_name = request.form['visitor_name']
        contact_no = request.form['contact_no']
        student_name = request.form['student_name']
        room_number = request.form['room_number']
        purpose = request.form['purpose']
        file = request.files.get('photo')
        photo_filename = 'default.png'
        if file and file.filename and allowed_file(file.filename):
            photo_filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], photo_filename))
        if not visitor_name or not contact_no or not student_name or not room_number or not purpose:
            flash('Please complete all fields', 'danger')
            return render_template('add_visitor.html')
        in_time = datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%d-%m-%Y %I:%M %p')
        conn = get_db()
        conn.execute("""INSERT INTO visitors (visitor_name, contact_no, student_name, room_number, purpose, in_time, status, photo) VALUES (?,?,?,?,?,?,?,?)""", (visitor_name, contact_no, student_name, room_number, purpose, in_time, 'Inside', photo_filename))
        conn.commit()
        conn.close()
        flash(f'Visitor {visitor_name} added successfully', 'success')
        return redirect(url_for('records'))
    return render_template('add_visitor.html')

@app.route('/edit_visitor/<int:id>', methods=['GET', 'POST'])
def edit_visitor(id):
    if session.get('role')!= 'admin':
        flash('You do not have permission to edit visitors', 'danger')
        return redirect(url_for('home'))
    conn = get_db()
    visitor = conn.execute('SELECT * FROM visitors WHERE id =?', (id,)).fetchone()
    if visitor is None:
        conn.close()
        flash('Visitor not found', 'danger')
        return redirect(url_for('records'))
    if request.method == 'POST':
        visitor_name = request.form['visitor_name']
        contact_no = request.form['contact_no']
        student_name = request.form['student_name']
        room_number = request.form['room_number']
        purpose = request.form['purpose']
        photo_filename = visitor['photo']
        file = request.files.get('photo')
        if file and file.filename and allowed_file(file.filename):
            photo_filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], photo_filename))
        conn.execute("""UPDATE visitors SET visitor_name=?, contact_no=?, student_name=?, room_number=?, purpose=?, photo=? WHERE id=?""",
                     (visitor_name, contact_no, student_name, room_number, purpose, photo_filename, id))
        conn.commit()
        conn.close()
        flash('Visitor updated successfully', 'success')
        return redirect(url_for('records'))
    conn.close()
    return render_template('edit_visitor.html', visitor=visitor)

@app.route('/delete_visitor/<int:id>', methods=['POST'])
def delete_visitor(id):
    if session.get('role')!= 'admin':
        flash('You do not have permission to delete visitors', 'danger')
        return redirect(url_for('home'))
    conn = get_db()
    conn.execute('DELETE FROM visitors WHERE id =?', (id,))
    conn.commit()
    conn.close()
    flash('Visitor deleted successfully', 'success')
    return redirect(url_for('records'))

@app.route('/checkout_visitor/<int:id>', methods=['POST'])
def checkout_visitor(id):
    conn = get_db()
    visitor = conn.execute('SELECT * FROM visitors WHERE id =? AND status = "Inside"', (id,)).fetchone()
    if visitor:
        out_time = datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%d-%m-%Y %I:%M %p')
        time_spent = calculate_time_spent(visitor['in_time'], out_time)
        conn.execute("""UPDATE visitors SET status = 'Left', out_time =?, time_spent =? WHERE id =?""", (out_time, time_spent, id))
        conn.commit()
        flash(f'Visitor checked out. Time Spent: {time_spent}', 'success')
    else:
        flash('Visitor not found or already checked out', 'danger')
    conn.close()
    return redirect(url_for('records'))

@app.route('/pass/<int:id>')
def print_pass(id):
    if session.get('role')!= 'admin':
        flash('Only admin can print passes', 'danger')
        return redirect(url_for('login'))
    conn = get_db()
    visitor = conn.execute('SELECT * FROM visitors WHERE id =?', (id,)).fetchone()
    conn.close()
    if visitor is None:
        flash('Visitor not found', 'danger')
        return redirect(url_for('records'))
    return render_template('pass.html', v=visitor)

@app.route('/filter')
def filter_page():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page
    room = request.args.get('room', '')
    purpose = request.args.get('purpose', '')
    status = request.args.get('status', '')
    conn = get_db()
    query = "SELECT * FROM visitors WHERE 1=1"
    count_query = "SELECT COUNT(*) FROM visitors WHERE 1=1"
    params = []
    count_params = []
    if room:
        query += " AND room_number =?"
        count_query += " AND room_number =?"
        params.append(room)
        count_params.append(room)
    if purpose:
        query += " AND purpose =?"
        count_query += " AND purpose =?"
        params.append(purpose)
        count_params.append(purpose)
    if status:
        query += " AND status =?"
        count_query += " AND status =?"
        params.append(status)
        count_params.append(status)
    query += " ORDER BY in_time DESC LIMIT? OFFSET?"
    params.extend([per_page, offset])
    visitors = conn.execute(query, params).fetchall()
    total = conn.execute(count_query, count_params).fetchone()[0]
    total_pages = math.ceil(total / per_page) if total > 0 else 1
    rooms = conn.execute('SELECT DISTINCT room_number FROM visitors ORDER BY room_number').fetchall()
    purposes = conn.execute('SELECT DISTINCT purpose FROM visitors ORDER BY purpose').fetchall()
    conn.close()
    return render_template('filter.html', visitors=visitors, rooms=rooms, purposes=purposes,
                           selected_room=room, selected_purpose=purpose, selected_status=status,
                           page=page, total_pages=total_pages)

@app.route('/search')
def search():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page
    q = request.args.get('q', '')
    conn = get_db()
    if q:
        search_term = f'%{q}%'
        query = "SELECT * FROM visitors WHERE visitor_name LIKE? OR contact_no LIKE? OR room_number LIKE? OR purpose LIKE? OR student_name LIKE? ORDER BY id DESC LIMIT? OFFSET?"
        count_query = "SELECT COUNT(*) FROM visitors WHERE visitor_name LIKE? OR contact_no LIKE? OR room_number LIKE? OR purpose LIKE? OR student_name LIKE?"
        params = [search_term, search_term, search_term, search_term, search_term, per_page, offset]
        count_params = [search_term, search_term, search_term, search_term, search_term]
    else:
        query = "SELECT * FROM visitors ORDER BY id DESC LIMIT? OFFSET?"
        count_query = "SELECT COUNT(*) FROM visitors"
        params = [per_page, offset]
        count_params = []
    visitors = conn.execute(query, params).fetchall()
    total = conn.execute(count_query, count_params).fetchone()[0]
    total_pages = math.ceil(total / per_page) if total > 0 else 1
    inside_count = conn.execute("SELECT COUNT(*) FROM visitors WHERE status = 'Inside'").fetchone()[0]
    checkout_count = total - inside_count
    rooms = conn.execute("SELECT DISTINCT room_number FROM visitors ORDER by room_number").fetchall()
    conn.close()
    return render_template('records.html', visitors=visitors, page=page, total_pages=total_pages, q=q, room=None, status=None, total_count=total, inside_count=inside_count, checkout_count=checkout_count, rooms=rooms)

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        if not username or not password:
            flash('Username and password required', 'danger')
            return render_template('register.html')
        conn = get_db()
        existing = conn.execute('SELECT * FROM users WHERE username =?', (username,)).fetchone()
        if existing:
            flash('Username already exists!', 'danger')
            conn.close()
            return render_template('register.html')
        hashed = generate_password_hash(password)
        conn.execute('INSERT INTO users (username, password, role) VALUES (?,?,?)', (username, hashed, 'user'))
        conn.commit()
        conn.close()
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    return render_template("register.html")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE username =?', (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user['password'], password):
            session['username'] = username
            session['role'] = user['role']
            flash(f'Welcome {username}!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Invalid username or password', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('role', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

@app.context_processor
def inject_user():
    return dict(current_user=session.get('username'))

if __name__ == '__main__':
    app.run(debug=True)