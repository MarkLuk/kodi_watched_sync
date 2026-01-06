import xbmc
import json
import resources.lib.logger as logger

class SyncManager:
    def __init__(self, db_manager):
        """
        Initialize the SyncManager with a reference to the database manager.
        """
        self.db_manager = db_manager
        self.import_guard_seconds = 15

    def sync_remote_to_local(self):
        """
        Reads the DB and updates local Kodi library (Import).
        """
        if not self.db_manager:
            return

        remote_data = self.db_manager.read_database()
        if not remote_data:
            return

        # Sync Movies
        self._import_media_type("movie", remote_data)
        # Sync Episodes
        self._import_media_type("episode", remote_data)
        # Sync Music Videos
        self._import_media_type("musicvideo", remote_data)

    def sync_local_to_remote(self):
        """
        Reads local Kodi library and updates the DB (Export).
        """
        if not self.db_manager:
            return

        remote_data = self.db_manager.read_database()

        updates = {}
        # Export Movies
        self._collect_media_type("movie", updates, remote_data)
        # Export Episodes
        self._collect_media_type("episode", updates, remote_data)
        # Export Music Videos
        self._collect_media_type("musicvideo", updates, remote_data)

        if updates:
            logger.info(f"Exporting {len(updates)} items to database")
            self.db_manager.update_items(updates)
            logger.info("Export completed")

    def _import_media_type(self, media_type, remote_data):
        """
        Fetches local library items of a specific type and imports watched status/resume points
        from the remote data if corrections are needed.
        """
        method_type = media_type.capitalize()
        if media_type == 'musicvideo': method_type = 'MusicVideo'

        json_cmd = {
            "jsonrpc": "2.0",
            "method": f"VideoLibrary.Get{method_type}s",
            "params": {
                "properties": ["file", "playcount", "resume"]
            },
            "id": 1
        }

        response = xbmc.executeJSONRPC(json.dumps(json_cmd))
        try:
            resp_obj = json.loads(response)
            if 'result' in resp_obj and f'{media_type}s' in resp_obj['result']:
                items = resp_obj['result'][f'{media_type}s']
                for item in items:
                    filepath = item['file']
                    if filepath in remote_data:
                        remote_item = remote_data[filepath]
                        self._apply_import_if_needed(media_type, item, remote_item)
        except Exception as e:
            logger.error(f"Error importing {media_type}s: {e}")

    def _apply_import_if_needed(self, media_type, local_item, remote_item):
        """
        Compares local item state with remote item state and applies updates to the local library
        if differences exceed thresholds (different watched status or >1s resume diff).
        """
        local_watched = local_item.get('playcount', 0) > 0
        local_resume = local_item.get('resume', {}).get('position', 0.0)

        remote_watched = remote_item['watched']
        remote_resume = remote_item['resume_time']

        needs_update = False
        updates = {}

        if local_watched != remote_watched:
            updates['playcount'] = 1 if remote_watched else 0
            needs_update = True

        if abs(local_resume - remote_resume) > 1.0:
            updates['resume'] = {'position': remote_resume}
            needs_update = True

        if needs_update:
            if hasattr(self.db_manager, "recently_updated"):
                filepath = local_item.get("file")
                if filepath and self.db_manager.recently_updated(filepath, self.import_guard_seconds):
                    logger.info(f"Skipping import for {filepath}: recent local update.")
                    return
            logger.info(f"Importing {local_item['file']} to Watched={remote_watched}, Resume={remote_resume}")
            self._set_item_details(media_type, local_item[f'{media_type}id'], updates)

    def _collect_media_type(self, media_type, updates, remote_data):
        """
        Fetches local library items of a specific type and adds them to the updates dictionary
        to be used for bulk database export.
        """
        method_type = media_type.capitalize()
        if media_type == 'musicvideo': method_type = 'MusicVideo'

        json_cmd = {
            "jsonrpc": "2.0",
            "method": f"VideoLibrary.Get{method_type}s",
            "params": {
                "properties": ["file", "playcount", "resume"]
            },
            "id": 1
        }

        response = xbmc.executeJSONRPC(json.dumps(json_cmd))
        try:
            resp_obj = json.loads(response)
            if 'result' in resp_obj and f'{media_type}s' in resp_obj['result']:
                items = resp_obj['result'][f'{media_type}s']
                for item in items:
                    filepath = item['file']
                    playcount = item.get('playcount', 0)
                    resume = item.get('resume', {})
                    resume_time = resume.get('position', 0.0)
                    watched = playcount > 0

                    # Check if update is needed
                    should_update = True
                    if filepath in remote_data:
                        remote_item = remote_data[filepath]
                        remote_watched = remote_item['watched']
                        remote_resume = remote_item['resume_time']

                        # Logic: Update if watched status changed OR resume time changed significantly (>5s?)
                        # Use 1s to be consistent with import logic, or maybe slightly looser for export to avoid flutter
                        # existing debounce in database_csv.py is 5.0s, let's use 1.0s here to catch small changes but match import.

                        watched_changed = (watched != remote_watched)
                        resume_changed = (abs(resume_time - remote_resume) > 1.0)

                        if not watched_changed and not resume_changed:
                            should_update = False

                    if should_update:
                        updates[filepath] = {
                            'watched': watched,
                            'resume_time': resume_time
                        }
        except Exception as e:
            logger.error(f"Error exporting {media_type}s: {e}")

    def _set_item_details(self, media_type, item_id, updates):
        """
        Updates the properties of a specific library item via JSON-RPC.
        """
        method_type = media_type.capitalize()
        if media_type == 'musicvideo': method_type = 'MusicVideo'

        json_cmd = {
            "jsonrpc": "2.0",
            "method": f"VideoLibrary.Set{method_type}Details",
            "params": {
                f"{media_type}id": item_id,
                **updates
            },
            "id": 1
        }
        xbmc.executeJSONRPC(json.dumps(json_cmd))
