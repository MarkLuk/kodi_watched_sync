import sys
import os
import time
import json
import threading

# Add tests directory to sys.path
sys.path.append(os.path.join(os.getcwd(), 'tests'))

# Mock modules
import mock_xbmc as xbmc
import mock_xbmcaddon as xbmcaddon
import mock_xbmcvfs as xbmcvfs
import mock_xbmcgui as xbmcgui

# Inject mocks
sys.modules['xbmc'] = xbmc
sys.modules['xbmcaddon'] = xbmcaddon
sys.modules['xbmcvfs'] = xbmcvfs
sys.modules['xbmcgui'] = xbmcgui

sys.path.append(os.getcwd())

from resources.lib.database_csv import DatabaseManager
from resources.lib.monitor import WatchedSyncMonitor
from resources.lib.sync import SyncManager

def test_race_condition():
    print("Testing Race Condition...")
    db_path = os.path.join(os.getcwd(), "tests", "race_test.csv")
    if os.path.exists(db_path): os.remove(db_path)

    # 1. Setup: DB has item as UNWATCHED
    with open(db_path, 'w') as f:
        f.write("filepath,watched,resume_time,last_updated\n")
        f.write("path/to/movie.mkv,False,0.0,0.0\n")

    db_manager = DatabaseManager(db_path)
    monitor = WatchedSyncMonitor(db_manager)
    # Note: In real app, Service creates SyncManager and passes db_manager.
    # We will need to patch SyncManager to use monitor if we implement that.
    sync_manager = SyncManager(db_manager)

    # Mock Import RPC to return UNWATCHED (from DB) but we want to simulate
    # that local Kodi has it UNWATCHED currently (so import would not change anything normally),
    # BUT we are about to mark it WATCHED via user action.

    # Actually, the race is:
    # 1. User marks Watched -> Monitor queues it.
    # 2. Sync Service runs BEFORE queue flush.
    # 3. DB has Unwatched.
    # 4. Sync Service sees DB Unwatched.

    # If local Kodi is ALREADY Watched (because user just did it), Sync sees Local=Watched, Remote=Unwatched.
    # Sync Logic: "If local != remote -> Updates."
    # Since Remote is Unwatched, it will overwrite Local to Unwatched.

    # We need to simulate that "Local is Watched" for the SyncManager.

    def mock_rpc(cmd):
        cmd_json = json.loads(cmd)
        if "GetMovies" in cmd_json['method']:
            # SyncManager calls this to see local state.
            # Local state IS Watched (user just did it).
            return json.dumps({
                "result": {
                    "movies": [
                        {"movieid": 1, "file": "path/to/movie.mkv", "playcount": 1, "resume": {"position": 0.0}}
                    ]
                }
            })
        if "GetMovieDetails" in cmd_json['method']:
             # Monitor calls this to get details for the update
             return json.dumps({
                 "result": {
                     "moviedetails": {
                         "file": "path/to/movie.mkv",
                         "playcount": 1,
                         "resume": {"position": 0.0}
                     }
                 }
             })

        # Capture SetMovieDetails - this is the "Overwrite"
        if "SetMovieDetails" in cmd_json['method']:
             print(f"  [!] SetMovieDetails called! Overwriting to: {cmd_json['params']}")

        return "{}"

    xbmc.executeJSONRPC = mock_rpc

    # 1. User Action: Mark Watched
    print("  User marks item as Watched...")
    monitor.onNotification("sender", "VideoLibrary.OnUpdate", json.dumps({"item": {"type": "movie", "id": 1}}))

    # Verify it's in queue
    with monitor.queue_lock:
        in_queue = "path/to/movie.mkv" in monitor.batch_queue
        print(f"  Item in pending queue: {in_queue}")

    if not in_queue:
        print("  [ERROR] Item failed to enter queue. Test invalid.")
        return

    # 2. Sync Runs (while item is in queue)
    print("  Sync Service runs...")

    # Inject monitor into sync_manager if/when we implement the fix
    if hasattr(sync_manager, 'monitor'):
        print("  (Injecting monitor into sync_manager for fix verification)")
        sync_manager.monitor = monitor
    else:
        # Manually verify if we can set it, or just run it.
        # For REPRODUCTION (before fix), sync_manager doesn't know about monitor.
        pass

    # We also want to test the Service level debounce.
    # But let's test SyncManager skipping first.
    sync_manager.sync_remote_to_local()

    # 3. Verify
    # If overwrite happened, we would have seen "SetMovieDetails" print and potentially "Importing..." log.

    print("Test finished.")

if __name__ == "__main__":
    test_race_condition()
