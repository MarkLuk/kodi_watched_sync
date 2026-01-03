import xbmcvfs
import csv
import time
import xbmc
import io
import hashlib
from datetime import datetime
import resources.lib.logger as logger

class DatabaseManager:
    def __init__(self, db_path):
        """
        Initialize the DatabaseManager with the path to the CSV file.
        """
        self.db_path = db_path
        self.lock_path = db_path + ".lock"
        self.backup_path = db_path + ".bak"
        self.md5_path = db_path + ".md5"
        self.backup_md5_path = self.md5_path + ".bak"
        self._check_and_recover()

    def _calculate_checksum(self, content):
        """
        Calculates MD5 checksum of the content.
        """
        if isinstance(content, str):
            content = content.encode('utf-8')
        return hashlib.md5(content).hexdigest()

    def _check_and_recover(self):
        """
        Checks if the main database file is valid.
        Valid means:
        1. File exists and size > 0.
        2. Checksum matches (if .md5 file exists).

        If invalid, attempts to recover from backup (verifying backup integrity first).
        """
        try:
            db_valid = False

            # 1. Check existence and size
            if xbmcvfs.exists(self.db_path):
                f = xbmcvfs.File(self.db_path)
                size = f.size()
                content = f.read()
                f.close()
                if size > 0:
                    # 2. Check checksum
                    if xbmcvfs.exists(self.md5_path):
                        f_md5 = xbmcvfs.File(self.md5_path)
                        stored_md5 = f_md5.read().strip()
                        f_md5.close()

                        calc_md5 = self._calculate_checksum(content)
                        if calc_md5 == stored_md5:
                            db_valid = True
                        else:
                            logger.error(f"Database checksum mismatch! Calculated: {calc_md5}, Stored: {stored_md5}")
                    else:
                        # If no MD5 file, assume valid if size > 0 (legacy support or first run)
                        logger.warn("No checksum file found. Assuming database is valid.")
                        db_valid = True

            if not db_valid:
                logger.warn(f"Main database invalid. Attempting to recover from backup: {self.backup_path}")
                if xbmcvfs.exists(self.backup_path):
                    # Validate backup before restoring
                    backup_valid = False
                    f_bak = xbmcvfs.File(self.backup_path)
                    backup_content = f_bak.read()
                    f_bak.close()

                    if xbmcvfs.exists(self.backup_md5_path):
                        f_bak_md5 = xbmcvfs.File(self.backup_md5_path)
                        stored_bak_md5 = f_bak_md5.read().strip()
                        f_bak_md5.close()

                        calc_bak_md5 = self._calculate_checksum(backup_content)
                        if calc_bak_md5 == stored_bak_md5:
                            backup_valid = True
                        else:
                            logger.error("Backup checksum mismatch! Cannot recover from corrupt backup.")
                    else:
                        # If backup exists but no checksum, assume it's valid?
                        # User wants verify on recovery. If missing, we can't strict verify, but maybe it's better than nothing.
                        # Proceed with caution if size > 0.
                        if len(backup_content) > 0:
                            logger.warn("Backup exists but no checksum found. Restoring anyway.")
                            backup_valid = True
                        else:
                            logger.error("Backup is empty.")

                    if backup_valid:
                        success = xbmcvfs.copy(self.backup_path, self.db_path)
                        if success:
                            # Also restore the MD5 file
                            if xbmcvfs.exists(self.backup_md5_path):
                                xbmcvfs.copy(self.backup_md5_path, self.md5_path)
                            else:
                                # Re-calculate new MD5 for the restored DB
                                new_md5 = self._calculate_checksum(backup_content)
                                f_md5 = xbmcvfs.File(self.md5_path, 'w')
                                f_md5.write(new_md5)
                                f_md5.close()

                            logger.info("Database successfully recovered from backup.")
                        else:
                            logger.error("Failed to recover database from backup.")
                else:
                    logger.warn("No backup found. Starting fresh.")
        except Exception as e:
            logger.error(f"Error during database recovery check: {e}")
            traceback.print_exc()

    def _acquire_lock(self, timeout=10):
        """
        Acquires an exclusive lock on the database using a .lock file.
        Waits up to 'timeout' seconds.
        """
        start_time = time.time()
        while xbmcvfs.exists(self.lock_path):
            if time.time() - start_time > timeout:
                logger.error(f"Timeout waiting for lock: {self.lock_path}")
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
        """
        Releases the exclusive lock by deleting the .lock file.
        """
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
            logger.error(f"Failed to acquire lock: {self.lock_path}")
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

    def _write_file_safely(self, content):
        """
        Writes content to the database safely:
        1. Write to .tmp file
        2. Calculate checksum and write to .md5.tmp
        3. Backup existing .csv to .bak AND .md5 to .md5.bak
        4. Rename .tmp to .csv and .md5.tmp to .md5
        """
        temp_path = self.db_path + ".tmp"
        temp_md5_path = self.md5_path + ".tmp"

        try:
            # 1. Write to temp
            f = xbmcvfs.File(temp_path, 'w')
            f.write(content)
            f.close()

            # 2. Write MD5 temp
            checksum = self._calculate_checksum(content)
            f_md5 = xbmcvfs.File(temp_md5_path, 'w')
            f_md5.write(checksum)
            f_md5.close()

            # 3. Backup existing (if it exists)
            if xbmcvfs.exists(self.db_path):
                if xbmcvfs.exists(self.backup_path):
                    xbmcvfs.delete(self.backup_path)
                xbmcvfs.copy(self.db_path, self.backup_path)

                # Backup MD5 if it exists
                if xbmcvfs.exists(self.md5_path):
                    if xbmcvfs.exists(self.backup_md5_path):
                         xbmcvfs.delete(self.backup_md5_path)
                    xbmcvfs.copy(self.md5_path, self.backup_md5_path)

            # 4. Rename temp to main
            if xbmcvfs.exists(self.db_path):
                xbmcvfs.delete(self.db_path)

            success = xbmcvfs.rename(temp_path, self.db_path)
            if not success:
                logger.error("Failed to rename temp file to database file.")
                return

            if xbmcvfs.exists(self.md5_path):
                xbmcvfs.delete(self.md5_path)
            xbmcvfs.rename(temp_md5_path, self.md5_path)

        except Exception as e:
            logger.error(f"Error during safe write: {e}")
            # Try to clean up temp
            if xbmcvfs.exists(temp_path): xbmcvfs.delete(temp_path)
            if xbmcvfs.exists(temp_md5_path): xbmcvfs.delete(temp_md5_path)

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

            # Write safely
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

            self._write_file_safely(output.getvalue())

        except Exception as e:
            logger.error(f"Error updating item: {e}")
        finally:
            self._release_lock()

    def update_items(self, items):
        """
        Bulk update items.
        items: dict of filepath -> { 'watched': bool, 'resume_time': float }
        """
        if not self.db_path:
            return

        if not self._acquire_lock():
            logger.error(f"Failed to acquire lock: {self.lock_path}")
            return

        try:
            current_data = {}
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
                        current_data[row['filepath']] = row

            now_str = str(time.time())

            # Update with new items
            for filepath, data in items.items():
                row = {
                    'filepath': filepath,
                    'watched': str(data['watched']),
                    'resume_time': str(data['resume_time']),
                    'last_updated': now_str
                }
                current_data[filepath] = row

            # Write safely
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            for row in current_data.values():
                writer.writerow(row)

            self._write_file_safely(output.getvalue())

        except Exception as e:
            logger.error(f"Error updating items: {e}")
        finally:
            self._release_lock()
             # Better to keep this class simple IO.
