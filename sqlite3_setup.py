import sqlite3

connection = sqlite3.connect("database.sqlite")
cursor = connection.cursor()

sql = """
CREATE TABLE presences (
id TEXT PRIMARY KEY,
time TEXT DEFAULT '01.01.1970 00:00:00'
)
"""
cursor.execute(sql)

sql = """
CREATE TABLE stats (
guild TEXT NOT NULL,
id TEXT NOT NULL,
messages INTEGER DEFAULT 0,
reactions INTEGER DEFAULT 0,
PRIMARY KEY (guild, id)
)
"""
cursor.execute(sql)

cursor.close()
connection.close()
