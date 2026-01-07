import xbmc
import xbmcaddon
import time
import resources.lib.logger as logger
from resources.lib.storage import get_db_manager
from resources.lib.monitor import WatchedSyncMonitor
from resources.lib.sync import SyncManager

class SyncService:
    """
    Main service class that runs in the background.
    Handles startup sync and periodic synchronization of watched status.
    """
    def __init__(self):
        self.addon = xbmcaddon.Addon()
        self.sync_interval = 15
        self.monitor = None
        self.db_manager = None
        self.sync_manager = None
        self._reload_settings()

    def _reload_settings(self):
        """
        Loads configuration from addon settings.
        Initializes DatabaseManager, Monitor, and SyncManager based on configured DB path.
        """
        try:
            self.sync_interval = int(self.addon.getSetting("sync_interval"))
        except:
            self.sync_interval = 15

        self.db_manager = get_db_manager(self.addon)
        if self.db_manager:
            self.sync_manager = SyncManager(self.db_manager)
            # Re-create monitor only if needed, but monitor takes db_manager ref
            if not self.monitor:
                self.monitor = WatchedSyncMonitor(self.db_manager)
            else:
                self.monitor.db_manager = self.db_manager

            # Link monitor to sync_manager
            self.sync_manager.monitor = self.monitor
        else:
            self.sync_manager = None

    def run(self):
        """
        Main service loop.
        Executes startup sync if enabled, then waits for abort while checking for periodic sync triggers.
        """
        if self.addon.getSetting("enable_service") != "true":
            pass
        else:
            if self.addon.getSetting("sync_on_startup") == "true":
                logger.info("Startup sync initiated.")
                self.perform_sync()

        last_sync = time.time()

        while not self.monitor.abortRequested():
            if self.addon.getSetting("enable_service") != "true":
                self.monitor.waitForAbort(5)
                continue

            # Reload sync interval dynamically
            try:
                self.sync_interval = int(self.addon.getSetting("sync_interval"))
            except:
                self.sync_interval = 15

            now = time.time()
            if (now - last_sync) > (self.sync_interval * 60) and self.sync_interval > 0:
                logger.info("Periodic sync initiated.")
                self.perform_sync()
                last_sync = time.time()

            if self.monitor.waitForAbort(10):
                break

    def perform_sync(self):
        """
        Initiates a synchronization (Import) from the remote DB to the local library.
        """
        if not self.sync_manager:
            if not self.db_manager:
                 logger.error("Cannot sync: Database not configured.")
            return

        # Debounce: If there are pending updates, wait until they are flushed.
        # This prevents the sync from reading old local state while the monitor is about to write new state.
        if self.monitor:
            retries = 0
            while self.monitor.has_pending_updates() and retries < 10:
                logger.info("Sync delayed due to pending updates...")
                time.sleep(5.0)
                retries += 1

        # Service always performs Import (Remote to Local)
        self.sync_manager.sync_remote_to_local()

if __name__ == '__main__':
    service = SyncService()
    service.run()
