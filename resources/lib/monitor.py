import xbmc
import json
import os
import threading
import resources.lib.logger as logger

class WatchedSyncMonitor(xbmc.Monitor):
    def __init__(self, db_manager):
        """
        Initialize the monitor with a reference to the database manager.
        """
        xbmc.Monitor.__init__(self)
        self.db_manager = db_manager
        self.batch_queue = {}
        self.batch_timer = None
        self.is_scanning = False
        self.queue_lock = threading.Lock()

    def onNotification(self, sender, method, data):
        """
        Callback for Kodi notifications.
        Listens for 'VideoLibrary.OnUpdate' to capture watched status or resume point changes.
        Also tracks scan status to prevent overwrites.
        """
        if method == "VideoLibrary.OnScanStarted":
            self.is_scanning = True
            logger.info("Scan started. Monitoring suspended for new items.")
        elif method == "VideoLibrary.OnScanFinished":
            self.is_scanning = False
            logger.info("Scan finished. Monitoring resumed.")

        # Listen for VideoLibrary.OnUpdate to capture watched/resume changes
        if method == "VideoLibrary.OnUpdate":
            if self.is_scanning:
                logger.debug("Ignoring update during scan.")
                return

            try:
                data_json = json.loads(data)
                if 'item' in data_json:
                    item = data_json['item']
                    item_type = item.get('type')
                    item_id = item.get('id')

                    if item_type in ['movie', 'episode', 'musicvideo'] and item_id:
                        self._process_library_update(item_type, item_id)
            except Exception as e:
                logger.error(f"Error processing notification: {e}")

    def _flush_queue(self):
        """
        Flushes the batch queue to the database.
        """
        with self.queue_lock:
            items_to_sync = self.batch_queue.copy()
            self.batch_queue.clear()
            self.batch_timer = None

        if items_to_sync:
            logger.info(f"Flushing batch queue with {len(items_to_sync)} items.")
            self.db_manager.update_items(items_to_sync)

    def _process_library_update(self, item_type, item_id):
        """
        Fetches details for the updated item and queues it for update.
        """
        # Determine correct RPC method name
        # Movie -> GetMovieDetails, Episode -> GetEpisodeDetails, musicvideo -> GetMusicVideoDetails
        method_type = item_type.capitalize()
        if item_type == 'musicvideo':
             method_type = 'MusicVideo'

        # Use JSON-RPC to get full details (file path, playcount, resume)
        json_cmd = {
            "jsonrpc": "2.0",
            "method": f"VideoLibrary.Get{method_type}Details",
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

                logger.debug(f"Queuing update for {filepath}: Watched={watched}, Resume={resume_time}")

                with self.queue_lock:
                    self.batch_queue[filepath] = {'watched': watched, 'resume_time': resume_time}
                    if not self.batch_timer:
                        # 5 second buffer
                        self.batch_timer = threading.Timer(5.0, self._flush_queue)
                        self.batch_timer.start()

        except Exception as e:
            logger.error(f"Error parsing JSON RPC response: {e}")
