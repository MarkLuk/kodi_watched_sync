# Watched Sync

**Watched Sync** is a Kodi addon designed to synchronize watched status and resume points between multiple Kodi instances using either a central CSV file or a MariaDB backend.

## How it Works

The addon operates in two ways:
1.  **Automatic (Background Service)**: It runs in the background to periodically import watched statuses from a central database to your local library. It also monitors your local library for changes (e.g., when you finish a movie or stop an episode) and automatically updates the central database.
2.  **Manual (Script)**: You can manually trigger an "Import" (Sync to Library) or "Export" (Sync to DB) via the addon executable.

## Database
You can choose a "low-tech" CSV approach on a shared storage like NAS/SMB or a MariaDB backend for stronger concurrency.

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
3.  **Storage Backend**: Choose `CSV` or `MariaDB`.
    1.  If using **CSV**, set **Database Folder** to a shared folder where `watched_status.csv` will be stored (e.g., `smb://nas/share/kodi_sync/`).
    2.  If using **MariaDB**, fill in host, port, database, user, password, and table name.
4.  **Sync Interval (mins)**: Set how often (in minutes) the addon should check the central database for updates from other devices. Default is 15 minutes.
5.  **Sync on Startup**: Enable this to force a sync check every time Kodi starts.

### MariaDB Setup

#### MariaDB container install (Docker)

Use command line
```bash
docker run -d --name watched-sync-mariadb \
  -e MARIADB_ROOT_PASSWORD=your_root_password \
  -e MARIADB_DATABASE=watched_sync \
  -e MARIADB_USER=kodi \
  -e MARIADB_PASSWORD=password \
  -p 3306:3306 \
  --restart unless-stopped \
  mariadb:lts
```
or docker compose
```yaml
services:
  watched-sync-mariadb:
    image: mariadb:lts
    container_name: watched-sync-mariadb
    environment:
      - MARIADB_ROOT_PASSWORD=your_root_password
      - MARIADB_DATABASE=watched_sync
      - MARIADB_USER=kodi
      - MARIADB_PASSWORD=password
    ports:
      - "3306:3306"
    restart: unless-stopped
```

#### MariaDB database and user setup

Login to the container and enter the MariaDB password (set by `MARIADB_ROOT_PASSWORD`)
```bash
docker exec -it watched-sync-mariadb mariadb -u root -p
```

Create a database and user:

```sql
CREATE DATABASE watched_sync;
CREATE USER 'kodi'@'%' IDENTIFIED BY 'watched_sync_password';
GRANT ALL PRIVILEGES ON watched_sync.* TO 'kodi'@'%';
FLUSH PRIVILEGES;
```

Explanation:
- `CREATE DATABASE watched_sync;` creates a database named `watched_sync` to store watched status and resume points information.
- `CREATE USER 'kodi'@'%' IDENTIFIED BY 'watched_sync_password';` creates a user named `kodi` with a password `watched_sync_password` that can connect from any host (`%`).
- `GRANT ALL PRIVILEGES ON watched_sync.* TO 'kodi'@'%';` grants the user `kodi` full access to the `watched_sync` database.
- `FLUSH PRIVILEGES;` reloads permissions so the changes take effect immediately.

#### Add-on configuration

If you used the Docker example above:
- Host: your NAS IP or hostname
- Port: `3306`
- Database: `watched_sync`
- User: `kodi`
- Password: `watched_sync_password`
- Table: `watched_status`

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
