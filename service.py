import xbmc
import xbmcaddon
import time
import json
from resources.lib.database import DatabaseManager
from resources.lib.monitor import WatchedSyncMonitor

class SyncService:
    def __init__(self):
        self.addon = xbmcaddon.Addon()
        self.db_path = ""
        self.sync_interval = 15
        self.monitor = None
        self.db_manager = None
        self._reload_settings()

    def _reload_settings(self):
        self.db_path = self.addon.getSetting("db_path")
        try:
            self.sync_interval = int(self.addon.getSetting("sync_interval"))
        except:
            self.sync_interval = 15

        if self.db_path:
            self.db_manager = DatabaseManager(self.db_path)
            # Re-create monitor only if needed, but monitor takes db_manager ref
            if not self.monitor:
                self.monitor = WatchedSyncMonitor(self.db_manager)
            else:
                self.monitor.db_manager = self.db_manager

    def run(self):
        if self.addon.getSetting("sync_on_startup") == "true":
            xbmc.log("[WatchedSync] Startup sync initiated.", xbmc.LOGINFO)
            self.perform_sync()

        last_sync = time.time()

        while not self.monitor.abortRequested():
            # Check for settings change? Monitor.onSettingsChanged is better but polling is simple for now.
            # Actually, let's just create a quick check or rely on next loop.

            now = time.time()
            if (now - last_sync) > (self.sync_interval * 60) and self.sync_interval > 0:
                xbmc.log("[WatchedSync] Periodic sync initiated.", xbmc.LOGINFO)
                self.perform_sync()
                last_sync = time.time()

            if self.monitor.waitForAbort(10):
                break

    def perform_sync(self):
        if not self.db_manager:
            return

        remote_data = self.db_manager.read_database()
        if not remote_data:
            return

        # Get Local Movies
        self._sync_media_type("movie", remote_data)
        # Get Local Episodes
        self._sync_media_type("episode", remote_data)

    def _sync_media_type(self, media_type, remote_data):
        json_cmd = {
            "jsonrpc": "2.0",
            "method": f"VideoLibrary.Get{media_type.capitalize()}s",  # Movies or Episodes
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
                        self._apply_update_if_needed(media_type, item, remote_item)
        except Exception as e:
            xbmc.log(f"[WatchedSync] Error syncing {media_type}s: {e}", xbmc.LOGERROR)

    def _apply_update_if_needed(self, media_type, local_item, remote_item):
        local_watched = local_item.get('playcount', 0) > 0
        local_resume = local_item.get('resume', {}).get('position', 0.0)

        remote_watched = remote_item['watched']
        remote_resume = remote_item['resume_time']

        needs_update = False
        updates = {}

        # Logic: If remote is different, apply remote.
        # Note: Floating point comparison for resume time might need epsilon.

        if local_watched != remote_watched:
            updates['playcount'] = 1 if remote_watched else 0
            needs_update = True

        if abs(local_resume - remote_resume) > 1.0: # 1 second tolerance
            updates['resume'] = {'position': remote_resume}
            needs_update = True

        if needs_update:
            xbmc.log(f"[WatchedSync] Updating {local_item['file']} to Watched={remote_watched}, Resume={remote_resume}", xbmc.LOGINFO)
            self._set_item_details(media_type, local_item[f'{media_type}id'], updates)

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

if __name__ == '__main__':
    service = SyncService()
    service.run()
