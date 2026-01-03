import sys
import os
import time
import json
import threading

# Add tests directory to sys.path so we can import mocks
sys.path.append(os.path.join(os.getcwd(), 'tests'))

# Mock modules
import mock_xbmc as xbmc
import mock_xbmcaddon as xbmcaddon

# Inject mocks into sys.modules so the real modules use them
sys.modules['xbmc'] = xbmc
sys.modules['xbmcaddon'] = xbmcaddon

# Now import our modules
# Add parent directory to path
sys.path.append(os.getcwd())

from resources.lib.database import DatabaseManager
from resources.lib.monitor import WatchedSyncMonitor
from service import SyncService

def test_database_locking():
    print("Testing Database Locking...")
    db_path = os.path.join(os.getcwd(), "tests", "watched.csv")
    if os.path.exists(db_path): os.remove(db_path)
    if os.path.exists(db_path + ".lock"): os.remove(db_path + ".lock")

    db = DatabaseManager(db_path)

    # Test 1: Acquire lock
    assert db._acquire_lock() == True
    assert os.path.exists(db_path + ".lock")
    print("  Lock acquired.")

    # Test 2: Double acquire (simulating another process waiting)
    # Since we are in same thread, this would block if we didn't have logic,
    # but my logic checks file existence.

    # Let's use a thread to hold the lock while main thread tries to acquire

    db._release_lock()

    def hold_lock():
        db2 = DatabaseManager(db_path)
        db2._acquire_lock()
        time.sleep(2)
        db2._release_lock()

    t = threading.Thread(target=hold_lock)
    t.start()
    time.sleep(0.5) # Wait for thread to grab lock

    start = time.time()
    db._acquire_lock()
    duration = time.time() - start
    print(f"  Waited {duration:.2f}s for lock.")
    assert duration >= 1.5 # Should have waited approx 1.5s remaining
    db._release_lock()
    t.join()
    print("  Locking test passed.")

def test_manual_update():
    print("Testing Update...")
    db_path = os.path.join(os.getcwd(), "tests", "watched.csv")
    db = DatabaseManager(db_path)

    db.update_item("path/to/movie.mkv", True, 120.5)

    data = db.read_database()
    assert "path/to/movie.mkv" in data
    assert data["path/to/movie.mkv"]["watched"] == True
    assert data["path/to/movie.mkv"]["resume_time"] == 120.5
    print("  Update test passed.")

def test_monitor():
    print("Testing Monitor...")
    db_path = os.path.join(os.getcwd(), "tests", "watched.csv")
    db_manager = DatabaseManager(db_path)
    monitor = WatchedSyncMonitor(db_manager)

    # Mock executeJSONRPC to return details for a movie
    def mock_rpc(cmd):
        cmd_json = json.loads(cmd)
        if "GetMovieDetails" in cmd_json['method']:
             return json.dumps({
                 "result": {
                     "moviedetails": {
                         "file": "path/to/avatar.mkv",
                         "playcount": 1,
                         "resume": {"position": 500}
                     }
                 }
             })
        return "{}"

    xbmc.executeJSONRPC = mock_rpc

    monitor.onNotification("sender", "VideoLibrary.OnUpdate", json.dumps({"item": {"type": "movie", "id": 1}}))

    data = db_manager.read_database()
    assert "path/to/avatar.mkv" in data
    assert data["path/to/avatar.mkv"]["watched"] == True
    print("  Monitor test passed.")

def test_service_sync():
    print("Testing Service Sync...")
    service = SyncService()
    # Mocking folder selection
    db_folder = os.path.join(os.getcwd(), "tests")
    service.addon.setSetting("db_folder", db_folder)
    # We need to make sure the expected db_path in service matches what we setup
    expected_db_path = os.path.join(db_folder, "watched_status.csv")

    # Create the db file at the expected location
    if os.path.exists(expected_db_path): os.remove(expected_db_path)
    db = DatabaseManager(expected_db_path)
    db.update_item("path/to/remote_movie.mkv", True, 0.0)

    # Manually trigger reload since we set settings after init (in mock)
    service._reload_settings()

    # Mock xbmc.executeJSONRPC to:
    # 1. Return list of movies (including a local match for remote item, but different state)
    # 2. Capture SetMovieDetails calls

    rpc_calls = []

    def mock_rpc_service(cmd):
        cmd_json = json.loads(cmd)
        rpc_calls.append(cmd_json)

        if "GetMovies" in cmd_json['method']:
            return json.dumps({
                "result": {
                    "movies": [
                        {"movieid": 10, "file": "path/to/remote_movie.mkv", "playcount": 0, "resume": {"position": 0.0}}
                    ]
                }
            })
        if "GetEpisodes" in cmd_json['method']:
             return json.dumps({"result": {"episodes": []}})

        return "{}"

    xbmc.executeJSONRPC = mock_rpc_service

    service.perform_sync()

    # Verify SetMovieDetails was called for movieid 10 with playcount=1
    set_call = next((c for c in rpc_calls if "SetMovieDetails" in c['method']), None)
    assert set_call is not None
    assert set_call['params']['movieid'] == 10
    assert set_call['params']['playcount'] == 1
    print("  Service Sync test passed.")

if __name__ == "__main__":
    test_database_locking()
    test_manual_update()
    test_monitor()
    test_service_sync()
    print("ALL TESTS PASSED")
