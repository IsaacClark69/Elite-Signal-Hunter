import sqlite3
import numpy as np
import io
import json

DATABASE_FILE = "signal_hunter.db"

def init_db():
    """Initializes the database and creates tables if they don't exist."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    # Create Profiles table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS profiles (
        name TEXT PRIMARY KEY,
        type TEXT NOT NULL,
        data BLOB NOT NULL
    )
    """)
    
    # Create Snapshots table for metadata logging
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS snapshots (
        snapshot_id TEXT PRIMARY KEY,
        timestamp_utc TEXT NOT NULL,
        directory TEXT NOT NULL,
        metadata_json TEXT NOT NULL
    )
    """)
    
    conn.commit()
    conn.close()

def _adapt_array(arr):
    """Converts numpy array to a binary format for SQLite."""
    out = io.BytesIO()
    np.save(out, arr)
    out.seek(0)
    return sqlite3.Binary(out.read())

def _convert_array(text):
    """Converts binary format from SQLite back to a numpy array."""
    out = io.BytesIO(text)
    out.seek(0)
    return np.load(out)

# Register the numpy array adapter and converter
sqlite3.register_adapter(np.ndarray, _adapt_array)
sqlite3.register_converter("array", _convert_array)

def save_profile_to_db(name, profile_type, data):
    """Saves a signal profile to the database."""
    conn = sqlite3.connect(DATABASE_FILE, detect_types=sqlite3.PARSE_DECLTYPES)
    cursor = conn.cursor()
    cursor.execute("REPLACE INTO profiles (name, type, data) VALUES (?, ?, ?)", (name, profile_type, data))
    conn.commit()
    conn.close()

def load_profiles_from_db():
    """Loads all profiles from the database."""
    profiles = {}
    conn = sqlite3.connect(DATABASE_FILE, detect_types=sqlite3.PARSE_DECLTYPES)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT name, data FROM profiles")
        rows = cursor.fetchall()
        for row in rows:
            profiles[row[0]] = row[1]
    except sqlite3.OperationalError:
        # Table probably doesn't exist yet, return empty dict
        pass
    finally:
        conn.close()
    return profiles

def delete_profile_from_db(name):
    """Deletes a profile from the database."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM profiles WHERE name = ?", (name,))
    conn.commit()
    conn.close()

def log_snapshot_to_db(snapshot_id, timestamp, directory, metadata):
    """Logs snapshot metadata to the database."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    metadata_str = json.dumps(metadata)
    cursor.execute("REPLACE INTO snapshots (snapshot_id, timestamp_utc, directory, metadata_json) VALUES (?, ?, ?, ?)",
                   (snapshot_id, timestamp, directory, metadata_str))
    conn.commit()
    conn.close()

def get_all_snapshots():
    """Retrieves all snapshots from the database."""
    snapshots = []
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT snapshot_id, timestamp_utc, directory, metadata_json FROM snapshots ORDER BY timestamp_utc DESC")
        rows = cursor.fetchall()
        for row in rows:
            snapshots.append({
                "id": row[0],
                "timestamp": row[1],
                "directory": row[2],
                "metadata": json.loads(row[3])
            })
    except sqlite3.OperationalError:
        # Table probably doesn't exist yet, return empty list
        pass
    finally:
        conn.close()
    return snapshots
