import xbmc
import xbmcgui
import xbmcaddon
import os
import resources.lib.logger as logger
from resources.lib.database import DatabaseManager
from resources.lib.sync import SyncManager

def run():
    """
    Entry point for manual script execution.
    Displays a dialog to choose between Import (Sync to Library) and Export (Sync from Library).
    """
    addon = xbmcaddon.Addon()
    db_folder = addon.getSetting("db_folder")

    if not db_folder:
        xbmcgui.Dialog().ok("Watched Sync", "Please configure the database folder in settings first.")
        return

    # Path logic duplicated from service.py, could be centralized in a helper
    if db_folder.endswith("/") or db_folder.endswith("\\"):
        db_path = db_folder + "watched_status.csv"
    else:
        db_path = db_folder + "/" + "watched_status.csv"

    db_manager = DatabaseManager(db_path)
    sync_manager = SyncManager(db_manager)

    # options = ["Import from DB (Sync to Library)", "Export to DB (Sync from Library)"]
    # 0 = Import, 1 = Export
    ret = xbmcgui.Dialog().select("Watched Sync Operation", ["Import from DB", "Export to DB"])

    if ret == 0:
        logger.info("Manual Import started")
        xbmcgui.Dialog().notification("Watched Sync", "Importing...", xbmcgui.NOTIFICATION_INFO, 2000)
        sync_manager.sync_remote_to_local()
        xbmcgui.Dialog().notification("Watched Sync", "Import Complete", xbmcgui.NOTIFICATION_INFO, 3000)

    elif ret == 1:
        logger.info("Manual Export started")
        xbmcgui.Dialog().notification("Watched Sync", "Exporting...", xbmcgui.NOTIFICATION_INFO, 2000)
        sync_manager.sync_local_to_remote()
        xbmcgui.Dialog().notification("Watched Sync", "Export Complete", xbmcgui.NOTIFICATION_INFO, 3000)

if __name__ == '__main__':
    run()
