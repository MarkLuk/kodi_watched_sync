import xbmcvfs
import csv
import time
import xbmc
import io
import hashlib
import threading
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
        self.local_lock = threading.RLock()
        self.lock_token = None
        self.lock_stale_seconds = 600
        self.local_updates = {}
        self.local_updates_lock = threading.Lock()
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
        # _check_and_recover called in init, so no local lock needed yet (or we can add it to be safe)
        # But generally init is single threaded.
        if not self._acquire_lock():
            logger.warn("Could not acquire lock during database initialization/recovery check. Skipping.")
            return

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
            import traceback
            traceback.print_exc()
        finally:
            self._release_lock()

    def _acquire_lock(self, timeout=10):
        """
        Acquires an exclusive lock on the database using Directory Locking (atomic mkdir).
        1. Attempt to create lock directory `self.lock_path`.
        2. If success, write `lease` file inside.
        3. If fail (exists), check `lease` file for staleness.
        """
        import uuid
        import socket

        host = socket.gethostname()
        unique_id = str(uuid.uuid4())
        token = f"{host}:{unique_id}"

        # Lock is now a directory
        lease_file = self.lock_path + "/lease"

        start_time = time.time()

        while True:
            # Check for timeout
            if time.time() - start_time > timeout:
                logger.error(f"Timeout waiting for lock: {self.lock_path}")
                return False

            # Attempt atomic mkdir
            if xbmcvfs.mkdir(self.lock_path):
                # Success! We own the lock.
                # Write lease info
                try:
                    f = xbmcvfs.File(lease_file, 'w')
                    f.write(f"{token}:{time.time()}")
                    f.close()
                    # Verify lease ownership in case backend is not strictly atomic
                    if self._lease_matches(lease_file, token):
                        self.lock_token = token
                        return True
                    logger.warn("Lease verification failed after lock acquisition; releasing and retrying.")
                except Exception as e:
                    logger.error(f"Failed to write lease file: {e}")
                # Release directory if lease fails or verification fails
                if xbmcvfs.exists(lease_file):
                    xbmcvfs.delete(lease_file)
                xbmcvfs.rmdir(self.lock_path)
                time.sleep(0.2)
                continue
            else:
                # Lock held. Check for stale lock via lease file.
                try:
                    if xbmcvfs.exists(lease_file):
                        f_lock = xbmcvfs.File(lease_file)
                        lock_content = f_lock.read()
                        f_lock.close()

                        _token_part, ts_part = lock_content.rsplit(':', 1)
                        lock_start = float(ts_part)
                        if time.time() - lock_start > self.lock_stale_seconds:
                            logger.warn(
                                f"Found stale lock (Age: {time.time() - lock_start}s). "
                                "Attempting cleanup."
                            )
                            xbmcvfs.delete(lease_file)
                            xbmcvfs.rmdir(self.lock_path)
                            continue
                except Exception as e:
                     logger.debug(f"Could not check stale lock: {e}")

                time.sleep(0.2)
                continue

    def _release_lock(self):
        """
        Releases the exclusive lock by removing the lease file and lock directory.
        """
        lease_file = self.lock_path + "/lease"
        try:
            if xbmcvfs.exists(lease_file) and self.lock_token:
                if self._lease_matches(lease_file, self.lock_token):
                    xbmcvfs.delete(lease_file)
                else:
                    logger.warn("Lease token mismatch on release; leaving lock in place.")
                    return
            if xbmcvfs.exists(self.lock_path):
                xbmcvfs.rmdir(self.lock_path)
        except Exception as e:
            logger.error(f"Failed to release lock: {e}")
        finally:
            self.lock_token = None

    def _lease_matches(self, lease_file, token):
        """
        Ensures the lease file belongs to this process before releasing.
        """
        try:
            f_lock = xbmcvfs.File(lease_file)
            lock_content = f_lock.read()
            f_lock.close()
            return lock_content.startswith(f"{token}:")
        except Exception as e:
            logger.debug(f"Could not read lease file for verification: {e}")
            return False

    def read_database(self):
        """
        Reads the database and returns a dictionary.
        Key: filepath
        Value: dict(watched, resume_time, last_updated)
        """
        with self.local_lock:
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
            # Debug: Check for shrinkage
            current_lines = 0
            if xbmcvfs.exists(self.db_path):
                f_sz = xbmcvfs.File(self.db_path)
                old_content = f_sz.read()
                f_sz.close()

                if isinstance(old_content, bytes):
                    old_content = old_content.decode('utf-8')

                current_lines = len(old_content.strip().splitlines())

            new_lines = len(content.strip().splitlines())

            logger.info(f"Writing database. Old lines: {current_lines}, New lines: {new_lines}")

            if current_lines > 0 and new_lines < current_lines:
                logger.error(f"DATABASE SHRINK DETECTED! {current_lines} lines -> {new_lines} lines")
                import traceback
                logger.error("Stack Trace:\n" + "".join(traceback.format_stack()))
        except Exception as e_debug:
            logger.warn(f"Error in debug check: {e_debug}")

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
        with self.local_lock:
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
                                # Debounce check: only update if changed significantly
                                try:
                                    old_watched = row['watched'] == 'True'
                                    old_resume = float(row.get('resume_time', 0))
                                    diff = abs(old_resume - resume_time)
                                    # If watched status same AND resume time diff < 5 secs, skip
                                    if old_watched == watched and diff < 5.0:
                                        logger.debug(f"Skipping update for {filepath}: No significant change (Diff: {diff}s)")
                                        # Since we are inside the try block, returning here will trigger finally -> release_lock
                                        return
                                except Exception as parse_e:
                                    logger.warn(f"Error checking debounce: {parse_e}")

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
                self._record_local_update(filepath)

            except Exception as e:
                logger.error(f"Error updating item: {e}")
            finally:
                self._release_lock()

    def update_items(self, items):
        """
        Bulk update items.
        items: dict of filepath -> { 'watched': bool, 'resume_time': float }
        """
        with self.local_lock:
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
                self._record_local_updates(items.keys())

            except Exception as e:
                logger.error(f"Error updating items: {e}")
            finally:
                self._release_lock()
                 # Better to keep this class simple IO.
