import sqlite3

conn = sqlite3.connect("users.db")
c = conn.cursor()

c.execute("ALTER TABLE users ADD COLUMN username TEXT")

conn.commit()
conn.close()

print("username column added")
