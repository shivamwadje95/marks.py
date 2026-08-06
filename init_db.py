import os
import sqlite3
from werkzeug.security import generate_password_hash

def init_db():
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DB_PATH = os.path.join(BASE_DIR, "database.db")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""CREATE TABLE IF NOT EXISTS visitors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    visitor_name TEXT NOT NULL,
    contact_no TEXT,
    student_name TEXT NOT NULL,
    room_number TEXT NOT NULL,
    visit_date TEXT,
    purpose TEXT NOT NULL,
    in_time TEXT NOT NULL,
    out_time TEXT,
    time_spent TEXT,
    status TEXT DEFAULT "Inside",
    photo TEXT DEFAULT "default.png"
    )""")

    cursor.execute("""CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    role TEXT DEFAULT "user"
    )""")

    # new column added to visitors table
    try: cursor.execute("ALTER TABLE visitors ADD COLUMN contact_no TEXT")
    except: pass
    try: cursor.execute("ALTER TABLE visitors ADD COLUMN time_spent TEXT")
    except: pass

    # Default admin user
    cursor.execute("SELECT * FROM users WHERE username = 'admin'")
    if not cursor.fetchone():
        hashed_pw = generate_password_hash("admin123")
        cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", ("admin", hashed_pw, "admin"))

    conn.commit()
    conn.close()
    print("Database Initialized!")

if __name__ == "__main__":
    init_db()