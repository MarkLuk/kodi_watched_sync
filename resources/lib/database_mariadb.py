import os
import sys
import time
import threading
import hashlib
import resources.lib.logger as logger

_VENDOR_PATH = os.path.join(os.path.dirname(__file__), "vendor")
if _VENDOR_PATH not in sys.path:
    sys.path.insert(0, _VENDOR_PATH)

try:
    import pymysql
except Exception as import_error:
    pymysql = None
    _IMPORT_ERROR = import_error


class MariaDBManager:
    def __init__(self, host, port, database, user, password, table="watched_status", connect_timeout=5):
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.table = self._sanitize_table_name(table)
        self.connect_timeout = connect_timeout
        self.local_lock = threading.RLock()
        self.local_updates = {}
        self.local_updates_lock = threading.Lock()

        if not pymysql:
            raise RuntimeError(f"PyMySQL not available: {_IMPORT_ERROR}")

        self._ensure_schema()

    def _sanitize_table_name(self, name):
        if not name:
            return "watched_status"
        safe = "".join(ch for ch in name if ch.isalnum() or ch == "_")
        if not safe:
            return "watched_status"
        if safe != name:
            logger.warn(f"Adjusted MariaDB table name from '{name}' to '{safe}'")
        return safe

    def _connect(self):
        return pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database,
            charset="utf8mb4",
            autocommit=True,
            connect_timeout=self.connect_timeout,
        )

    def _filepath_hash(self, filepath):
        if isinstance(filepath, str):
            filepath = filepath.encode("utf-8")
        return hashlib.md5(filepath).digest()

    def _ensure_schema(self):
        query = (
            f"CREATE TABLE IF NOT EXISTS `{self.table}` ("
            "filepath_hash BINARY(16) PRIMARY KEY,"
            "filepath TEXT NOT NULL,"
            "watched TINYINT(1) NOT NULL,"
            "resume_time DOUBLE NOT NULL,"
            "last_updated DOUBLE NOT NULL"
            ") CHARACTER SET utf8mb4"
        )
        try:
            conn = self._connect()
            try:
                with conn.cursor() as cur:
                    cur.execute(query)
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Failed to initialize MariaDB schema: {e}")
            raise

    def recently_updated(self, filepath, window_seconds):
        """
        Returns True if the local item was updated recently.
        """
        now = time.time()
        with self.local_updates_lock:
            ts = self.local_updates.get(filepath)
            if ts is None:
                return False
            if now - ts > window_seconds:
                self.local_updates.pop(filepath, None)
                return False
            return True

    def _record_local_update(self, filepath):
        with self.local_updates_lock:
            self.local_updates[filepath] = time.time()

    def _record_local_updates(self, items):
        with self.local_updates_lock:
            now = time.time()
            for filepath in items:
                self.local_updates[filepath] = now

    def read_database(self):
        with self.local_lock:
            data = {}
            try:
                conn = self._connect()
                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            f"SELECT filepath, watched, resume_time, last_updated FROM `{self.table}`"
                        )
                        for filepath, watched, resume_time, last_updated in cur.fetchall():
                            data[filepath] = {
                                "watched": bool(watched),
                                "resume_time": float(resume_time),
                                "last_updated": float(last_updated),
                            }
                finally:
                    conn.close()
            except Exception as e:
                logger.error(f"Error reading MariaDB: {e}")
            return data

    def update_item(self, filepath, watched, resume_time):
        with self.local_lock:
            try:
                conn = self._connect()
                try:
                    with conn.cursor() as cur:
                        now = time.time()
                        filepath_hash = self._filepath_hash(filepath)
                        cur.execute(
                            f"INSERT INTO `{self.table}` "
                            "(filepath_hash, filepath, watched, resume_time, last_updated) "
                            "VALUES (%s, %s, %s, %s, %s) "
                            "ON DUPLICATE KEY UPDATE "
                            "filepath=VALUES(filepath), watched=VALUES(watched), "
                            "resume_time=VALUES(resume_time), last_updated=VALUES(last_updated)",
                            (filepath_hash, filepath, int(watched), float(resume_time), now),
                        )
                    self._record_local_update(filepath)
                finally:
                    conn.close()
            except Exception as e:
                logger.error(f"Error updating MariaDB item: {e}")

    def update_items(self, items):
        with self.local_lock:
            if not items:
                return
            try:
                rows = []
                now = time.time()
                for filepath, data in items.items():
                    rows.append(
                        (
                            self._filepath_hash(filepath),
                            filepath,
                            int(data["watched"]),
                            float(data["resume_time"]),
                            now,
                        )
                    )

                conn = self._connect()
                try:
                    with conn.cursor() as cur:
                        cur.executemany(
                            f"INSERT INTO `{self.table}` "
                            "(filepath_hash, filepath, watched, resume_time, last_updated) "
                            "VALUES (%s, %s, %s, %s, %s) "
                            "ON DUPLICATE KEY UPDATE "
                            "filepath=VALUES(filepath), watched=VALUES(watched), "
                            "resume_time=VALUES(resume_time), last_updated=VALUES(last_updated)",
                            rows,
                        )
                    self._record_local_updates(items.keys())
                finally:
                    conn.close()
            except Exception as e:
                logger.error(f"Error updating MariaDB items: {e}")
