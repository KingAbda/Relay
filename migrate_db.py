import sys, os
sys.path.insert(0, os.path.dirname(__file__))
os.environ['RELAY_SECRET_KEY'] = 'temp'

# Direct SQLite hack - add missing columns
import sqlite3
paths = [
    r'C:\Users\ATouray\relay-local\app\instance\relay.db',
    r'C:\Users\ATouray\relay-local\instance\relay.db'
]
for path in paths:
    if os.path.exists(path):
        try:
            conn = sqlite3.connect(path)
            c = conn.cursor()
            # Check which columns exist
            c.execute("PRAGMA table_info(users)")
            cols = [row[1] for row in c.fetchall()]
            if 'is_member' not in cols:
                c.execute("ALTER TABLE users ADD COLUMN is_member BOOLEAN DEFAULT 0")
                print(f"Added is_member to {path}")
            if 'member_since' not in cols:
                c.execute("ALTER TABLE users ADD COLUMN member_since DATETIME")
                print(f"Added member_since to {path}")
            c.execute("PRAGMA table_info(user_skills)")
            cols = [row[1] for row in c.fetchall()]
            if 'credit_cost' not in cols:
                c.execute("ALTER TABLE user_skills ADD COLUMN credit_cost INTEGER DEFAULT 1")
                print(f"Added credit_cost to {path}")
            c.execute("PRAGMA table_info(sessions)")
            cols = [row[1] for row in c.fetchall()]
            if 'amount_charged' not in cols:
                c.execute("ALTER TABLE sessions ADD COLUMN amount_charged FLOAT DEFAULT 0.0")
                print(f"Added amount_charged to {path}")
            if 'user_id_index' not in [row[1] for row in c.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()]:
                c.execute("CREATE INDEX IF NOT EXISTS ix_credit_transactions_user_id ON credit_transactions(user_id)")
            conn.commit()
            conn.close()
            print(f"Migration complete for {path}")
        except Exception as e:
            print(f"Error on {path}: {e}")
