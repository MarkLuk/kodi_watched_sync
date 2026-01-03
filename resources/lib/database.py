import xbmcvfs
import csv
import time
import xbmc
import io
from datetime import datetime
import resources.lib.logger as logger

class DatabaseManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self.lock_path = db_path + ".lock"

    def _acquire_lock(self, timeout=10):
        start_time = time.time()
        while xbmcvfs.exists(self.lock_path):
            if time.time() - start_time > timeout:
                logger.warn(f"Timeout waiting for lock: {self.lock_path}")
                return False
            time.sleep(0.5)

        try:
            f = xbmcvfs.File(self.lock_path, 'w')
            f.write(str(time.time()))
            f.close()
            return True
        except Exception as e:
            logger.error(f"Failed to acquire lock: {e}")
            return False

    def _release_lock(self):
        try:
            if xbmcvfs.exists(self.lock_path):
                xbmcvfs.delete(self.lock_path)
        except Exception as e:
            logger.error(f"Failed to release lock: {e}")

    def read_database(self):
        """
        Reads the database and returns a dictionary.
        Key: filepath
        Value: dict(watched, resume_time, last_updated)
        """
        data = {}
        if not self.db_path or not xbmcvfs.exists(self.db_path):
            return data

        if not self._acquire_lock():
            return data

        try:
            # Read all content to memory to use standard CSV module
            f = xbmcvfs.File(self.db_path)
            content = f.read()
            f.close()

            # xbmcvfs.File.read() returns string (if text) or bytes.
            # Usually strict bytes in newer Py, but Kodi python API is sometimes strings.
            # Assuming string for simplicity or decode. Python 3 strings are unicode.
            # If content is bytes, decode it.
            if isinstance(content, bytes):
                content = content.decode('utf-8')

            with io.StringIO(content) as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    data[row['filepath']] = {
                        'watched': row['watched'] == 'True',
                        'resume_time': float(row['resume_time']),
                        'last_updated': float(row['last_updated'])
                    }
        except Exception as e:
            logger.error(f"Error reading database: {e}")
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
            if xbmcvfs.exists(self.db_path):
                f = xbmcvfs.File(self.db_path)
                content = f.read()
                f.close()

                if isinstance(content, bytes):
                    content = content.decode('utf-8')

                with io.StringIO(content) as csvfile:
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
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

            f = xbmcvfs.File(self.db_path, 'w')
            f.write(output.getvalue())
            f.close()

        except Exception as e:
            logger.error(f"Error updating item: {e}")
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
