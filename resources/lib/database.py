import os
import csv
import time
import xbmc
from datetime import datetime

class DatabaseManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self.lock_path = db_path + ".lock"

    def _acquire_lock(self, timeout=10):
        start_time = time.time()
        while os.path.exists(self.lock_path):
            if time.time() - start_time > timeout:
                xbmc.log(f"[WatchedSync] Timeout waiting for lock: {self.lock_path}", xbmc.LOGWARNING)
                return False
            time.sleep(0.5)

        try:
            with open(self.lock_path, 'w') as f:
                f.write(str(time.time()))
            return True
        except Exception as e:
            xbmc.log(f"[WatchedSync] Failed to acquire lock: {e}", xbmc.LOGERROR)
            return False

    def _release_lock(self):
        try:
            if os.path.exists(self.lock_path):
                os.remove(self.lock_path)
        except Exception as e:
            xbmc.log(f"[WatchedSync] Failed to release lock: {e}", xbmc.LOGERROR)

    def read_database(self):
        """
        Reads the database and returns a dictionary.
        Key: filepath
        Value: dict(watched, resume_time, last_updated)
        """
        data = {}
        if not self.db_path or not os.path.exists(self.db_path):
            return data

        if not self._acquire_lock():
            return data

        try:
            with open(self.db_path, mode='r', newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    data[row['filepath']] = {
                        'watched': row['watched'] == 'True',
                        'resume_time': float(row['resume_time']),
                        'last_updated': float(row['last_updated'])
                    }
        except Exception as e:
            xbmc.log(f"[WatchedSync] Error reading database: {e}", xbmc.LOGERROR)
        finally:
            self._release_lock()

        return data

    def update_item(self, filepath, watched, resume_time):
        """
        Updates a single item in the database.
        """
        if not self.db_path:
            return

        if not self._acquire_lock():
            return

        try:
            # Read all existing data first (to preserve other entries)
            # Note: Optimized approach would be to read without lock first,
            # but to ensure consistency we read with lock held or we trust read_database logic if we separate it.
            # But here we are already holding the lock.

            rows = []
            file_exists = False
            fieldnames = ['filepath', 'watched', 'resume_time', 'last_updated']

            # Read existing
            if os.path.exists(self.db_path):
                with open(self.db_path, mode='r', newline='', encoding='utf-8') as csvfile:
                    reader = csv.DictReader(csvfile)
                    for row in reader:
                        if row['filepath'] == filepath:
                            row['watched'] = str(watched)
                            row['resume_time'] = str(resume_time)
                            row['last_updated'] = str(time.time())
                            file_exists = True
                        rows.append(row)

            if not file_exists:
                rows.append({
                    'filepath': filepath,
                    'watched': str(watched),
                    'resume_time': str(resume_time),
                    'last_updated': str(time.time())
                })

            # Write back
            with open(self.db_path, mode='w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

        except Exception as e:
            xbmc.log(f"[WatchedSync] Error updating item: {e}", xbmc.LOGERROR)
        finally:
            self._release_lock()

    def sync_local_to_remote_bulk(self, local_status_map):
        """
        Updates the remote DB with multiple items if they are newer.
        This is a bit complex. For now, let's just stick to "update_item" for individual events.
        For bulk sync (startup), we might want to read remote, compare with local, and update whichever is newer.

        Actually, let's implement a method that takes a dict of local state,
        reads remote, merges them (taking newest), writes back to remote, and returns the changes for local.
        """
        pass # To be implemented in service logic or here?
             # Better to keep this class simple IO.
