import sqlite3
conn = sqlite3.connect('database.db')
c = conn.cursor()
c.execute("ALTER TABLE visitors ADD COLUMN photo TEXT DEFAULT 'default.png'")
conn.commit()
conn.close()