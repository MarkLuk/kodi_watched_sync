# Watched Sync

**Watched Sync** is a Kodi addon designed to synchronize watched status and resume points between multiple Kodi instances using a simple, central CSV file.

## How it Works

The addon operates in two ways:
1.  **Automatic (Background Service)**: It runs in the background to periodically import watched statuses from a central CSV file to your local library. It also monitors your local library for changes (e.g., when you finish a movie or stop an episode) and automatically updates the central CSV file.
2.  **Manual (Script)**: You can manually trigger an "Import" (Sync to Library) or "Export" (Sync to DB) via the addon executable.

This "low-tech" CSV approach allows you to host the database file on any shared storage (NAS, SMB share, Dropbox folder, etc.) without needing a complex SQL server setup.

## Features

-   **Watched Status Sync**: Synchronizes watched/unwatched status for Movies, Episodes, and Music Videos.
-   **Resume Points**: Synchronizes resume timestamps, allowing you to stop on one device and resume on another.
-   **Automatic Background Sync**: Periodically pulls updates from other devices.
-   **Real-time Updates**: Pushes changes to the central database immediately when you stop playback or mark an item as watched.
-   **Manual Controls**: Force an import or export when needed.
-   **Cross-Platform**: Works on any platform Kodi supports (Windows, Linux, Android, etc.), as long as they can access the shared folder.

## Installation

1.  Download the latest release zip file.
2.  Open Kodi and go to **Add-ons** > **Install from zip file**.
3.  Select the downloaded zip file to install.

## Configuration

After installation, you **must** configure the addon for it to work.

1.  Go to **Add-ons** > **My add-ons** > **Services** > **Watched Sync**.
2.  Select **Configure**.
3.  **Database Folder**: Browse to a valid folder where the `watched_status.csv` file will be stored. This folder must be accessible and writable by all your Kodi instances (e.g., `smb://nas/share/kodi_sync/`).
4.  **Sync Interval (mins)**: Set how often (in minutes) the addon should check the central database for updates from other devices. Default is 15 minutes.
5.  **Sync on Startup**: Enable this to force a sync check every time Kodi starts.

## Usage

**Automatic Usage**:
Once configured, simply use Kodi as normal.
-   When you watch something, it will be marked in the central file.
-   Other devices will pick up this change on their next startup or periodic sync.

**Manual Usage**:
If you want to force a sync immediately:
1.  Go to **Add-ons** > **Program add-ons** (or just **Add-ons**).
2.  Select **Watched Sync**.
3.  A dialog will appear asking you to select an operation:
    -   **Import from DB**: Pulls the latest statuses from the CSV file into your local library.
    -   **Export to DB**: Pushes your current local library statuses to the CSV file (useful for the initial setup).
