import xbmc
import json
import resources.lib.logger as logger

class SyncManager:
    def __init__(self, db_manager):
        self.db_manager = db_manager

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

    def sync_local_to_remote(self):
        """
        Reads local Kodi library and updates the DB (Export).
        """
        if not self.db_manager:
            return

        # Export Movies
        self._export_media_type("movie")
        # Export Episodes
        self._export_media_type("episode")

    def _import_media_type(self, media_type, remote_data):
        json_cmd = {
            "jsonrpc": "2.0",
            "method": f"VideoLibrary.Get{media_type.capitalize()}s",
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
            logger.info(f"Importing {local_item['file']} to Watched={remote_watched}, Resume={remote_resume}")
            self._set_item_details(media_type, local_item[f'{media_type}id'], updates)

    def _export_media_type(self, media_type):
        json_cmd = {
            "jsonrpc": "2.0",
            "method": f"VideoLibrary.Get{media_type.capitalize()}s",
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

                    # We blindly update the DB with local state for all items
                    # Optimization: Could read DB first and check if update is needed,
                    # but database.py handles updates safely.
                    # Actually, calling update_item for every single item might be slow due to locking overhead per call.
                    # But for now, let's keep it simple.

                    self.db_manager.update_item(filepath, watched, resume_time)

        except Exception as e:
            logger.error(f"Error exporting {media_type}s: {e}")

    def _set_item_details(self, media_type, item_id, updates):
        json_cmd = {
            "jsonrpc": "2.0",
            "method": f"VideoLibrary.Set{media_type.capitalize()}Details",
            "params": {
                f"{media_type}id": item_id,
                **updates
            },
            "id": 1
        }
        xbmc.executeJSONRPC(json.dumps(json_cmd))
