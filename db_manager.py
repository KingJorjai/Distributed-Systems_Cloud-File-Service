import hashlib
import sqlite3
import threading
import os

def calculate_hash_file(ruta_fichero):
    if not os.path.exists(ruta_fichero):
        return None
    
    sha256 = hashlib.sha256()
    with open(ruta_fichero, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256.update(byte_block)
    return sha256.hexdigest()

class ServerDB:
    def __init__(self, db_path="server_sync.db"):
        self.db_path = db_path
        self.lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        with self.lock:
            with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS server_sync (
                        cliente_id TEXT,
                        fichero TEXT,
                        rev INTEGER,
                        hash TEXT,
                        PRIMARY KEY (cliente_id, fichero)
                    )
                """)
                conn.commit()

    def get_file_info(self, cliente_id, fichero):
        with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT rev, hash FROM server_sync 
                WHERE cliente_id=? AND fichero=?
            """, (cliente_id, fichero))
            return cursor.fetchone()

    def update_file_info(self, cliente_id, fichero, rev, hash_val):
        with self.lock:
            with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO server_sync (cliente_id, fichero, rev, hash)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(cliente_id, fichero) DO UPDATE SET
                        rev=excluded.rev,
                        hash=excluded.hash
                """, (cliente_id, fichero, rev, hash_val))
                conn.commit()
                
    def delete_file(self, cliente_id, fichero):
        with self.lock:
            with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM server_sync WHERE cliente_id=? AND fichero=?", (cliente_id, fichero))
                conn.commit()

class ClientDB:
    def __init__(self, db_path="client_sync.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS local_sync (
                    fichero TEXT PRIMARY KEY,
                    rev INTEGER,
                    hash TEXT
                )
            """)
            conn.commit()

    def get_file_info(self, fichero):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT rev, hash FROM local_sync WHERE fichero=?", (fichero,))
            return cursor.fetchone()

    def update_file_info(self, fichero, rev, hash_val):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO local_sync (fichero, rev, hash)
                VALUES (?, ?, ?)
                ON CONFLICT(fichero) DO UPDATE SET
                    rev=excluded.rev,
                    hash=excluded.hash
            """, (fichero, rev, hash_val))
            conn.commit()