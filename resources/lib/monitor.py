import xbmc
import json
import os

class WatchedSyncMonitor(xbmc.Monitor):
    def __init__(self, db_manager):
        xbmc.Monitor.__init__(self)
        self.db_manager = db_manager

    def onNotification(self, sender, method, data):
        # Listen for VideoLibrary.OnUpdate to capture watched/resume changes
        if method == "VideoLibrary.OnUpdate":
            try:
                data_json = json.loads(data)
                if 'item' in data_json:
                    item = data_json['item']
                    item_type = item.get('type')
                    item_id = item.get('id')

                    if item_type in ['movie', 'episode'] and item_id:
                        self._process_library_update(item_type, item_id)
            except Exception as e:
                xbmc.log(f"[WatchedSync] Error processing notification: {e}", xbmc.LOGERROR)

    def _process_library_update(self, item_type, item_id):
        # Use JSON-RPC to get full details (file path, playcount, resume)
        json_cmd = {
            "jsonrpc": "2.0",
            "method": f"VideoLibrary.Get{item_type.capitalize()}Details",
            "params": {
                f"{item_type}id": item_id,
                "properties": ["file", "playcount", "resume"]
            },
            "id": 1
        }

        response = xbmc.executeJSONRPC(json.dumps(json_cmd))
        try:
            resp_obj = json.loads(response)
            if 'result' in resp_obj and f'{item_type}details' in resp_obj['result']:
                details = resp_obj['result'][f'{item_type}details']
                filepath = details.get('file')
                playcount = details.get('playcount', 0)
                resume = details.get('resume', {})
                resume_time = resume.get('position', 0.0)

                watched = playcount > 0

                # Check for settings? We should only sync if db_path is set.
                # But db_manager handles the check.

                xbmc.log(f"[WatchedSync] Detected update for {filepath}: Watched={watched}, Resume={resume_time}", xbmc.LOGDEBUG)
                self.db_manager.update_item(filepath, watched, resume_time)

        except Exception as e:
            xbmc.log(f"[WatchedSync] Error parsing JSON RPC response: {e}", xbmc.LOGERROR)
