import os
from flask import Flask, redirect, render_template, request, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import sqlite3
from datetime import datetime
from init_db import init_db
from dotenv import load_dotenv
from groq import Groq

# Load.env file for API key
load_dotenv() 

# Database path fix
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'database.db')

init_db()

app = Flask(__name__)
app.secret_key = "hostel-visitor-2026"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def home():
    conn = get_db()
    visitors = conn.execute("SELECT * FROM visitors ORDER BY id DESC").fetchall()
    rooms = conn.execute("SELECT DISTINCT room_number FROM visitors ORDER BY room_number").fetchall()
    conn.close()

    total_count = len(visitors)
    inside_count = sum(1 for v in visitors if v['status'] == 'Inside')
    checkout_count = total_count - inside_count

    return render_template('home.html',
                         visitors=visitors,
                         total_count=total_count,
                         inside_count=inside_count,
                         checkout_count=checkout_count,
                         rooms=rooms)

@app.route('/records')
def records():
    room = request.args.get('room')
    status = request.args.get('status')
    q = request.args.get('q')

    conn = get_db()
    query = "SELECT * FROM visitors WHERE 1=1"
    params = []

    if room:
        query += " AND room_number =?"
        params.append(room)
    if status:
        query += " AND status =?"
        params.append(status)
    if q:
        query += " AND visitor_name LIKE?"
        params.append(f"%{q}%")

    query += " ORDER BY id DESC"
    visitors = conn.execute(query, params).fetchall()
    conn.close()
    return render_template('records.html', visitors=visitors)

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

    prompt = f"""
    Visitor name: {visitor['visitor_name']}
    Visiting Student: {visitor['student_name']}
    Room No: {visitor['room_number']}
    Purpose: {visitor['purpose']}
    In Time: {visitor['in_time']}
    Out Time: {out_time}
    Status: {status}

    Based on this, give 1 practical security tip for the hostel guard.
    Keep it simple, encouraging, and not more than 2 lines.
    """

    try:
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}]
        )
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
        student_name = request.form['student_name']
        room_number = request.form['room_number']
        purpose = request.form['purpose']

        if not visitor_name or not student_name or not room_number or not purpose:
            flash('Please complete all fields', 'danger')
            return render_template('add_visitor.html')

        in_time = datetime.now().strftime('%d-%m-%Y %I:%M %p')

        conn = get_db()
        conn.execute("""
            INSERT INTO visitors (visitor_name, student_name, room_number, purpose, in_time, status)
            VALUES (?,?,?,?,?,?)
        """, (visitor_name, student_name, room_number, purpose, in_time, 'Inside'))
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
        student_name = request.form['student_name']
        room_number = request.form['room_number']
        purpose = request.form['purpose']

        conn.execute("""
            UPDATE visitors
            SET visitor_name=?, student_name=?, room_number=?, purpose=?
            WHERE id=?
        """, (visitor_name, student_name, room_number, purpose, id))
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
    out_time = datetime.now().strftime('%d-%m-%Y %I:%M %p')

    cursor = conn.execute("""
        UPDATE visitors
        SET status = 'Left', out_time =?
        WHERE id =? AND status = 'Inside'
    """, (out_time, id))

    conn.commit()

    if cursor.rowcount == 0:
        flash('Visitor not found or already checked out', 'danger')
    else:
        flash('Visitor checked out successfully', 'success')

    conn.close()
    return redirect(url_for('records'))

@app.route('/filter')
def filter_page():
    room = request.args.get('room')
    purpose = request.args.get('purpose')
    status = request.args.get('status')

    conn = get_db()
    query = "SELECT * FROM visitors WHERE 1=1"
    params = []

    if room:
        query += ' AND room_number =?'
        params.append(room)
    if purpose:
        query += ' AND purpose =?'
        params.append(purpose)
    if status:
        query += ' AND status =?'
        params.append(status)

    query += ' ORDER BY in_time DESC'
    visitors = conn.execute(query, params).fetchall()

    rooms = conn.execute('SELECT DISTINCT room_number FROM visitors ORDER BY room_number').fetchall()
    purposes = conn.execute('SELECT DISTINCT purpose FROM visitors ORDER BY purpose').fetchall()

    conn.close()

    return render_template(
        'filter.html',
        visitors=visitors,
        rooms=rooms,
        purposes=purposes,
        selected_room=room,
        selected_purpose=purpose,
        selected_status=status
    )

@app.route('/search')
def search():
    q = request.args.get('q', '')
    conn = get_db()
    if q:
        search_term = f'%{q}%'
        visitors = conn.execute("""
            SELECT * FROM visitors
            WHERE visitor_name LIKE? OR room_number LIKE? OR purpose LIKE? OR student_name LIKE?
            ORDER BY id DESC
        """, (search_term, search_term, search_term, search_term)).fetchall()
    else:
        visitors = conn.execute("SELECT * FROM visitors ORDER BY id DESC").fetchall()
    conn.close()
    return render_template('records.html', visitors=visitors)

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