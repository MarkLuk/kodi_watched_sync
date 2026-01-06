import resources.lib.logger as logger
from resources.lib.database_csv import DatabaseManager

try:
    from resources.lib.database_mariadb import MariaDBManager
except Exception as e:
    MariaDBManager = None
    _MARIADB_IMPORT_ERROR = e


def _build_csv_path(db_folder):
    if not db_folder:
        return ""
    if db_folder.endswith("/") or db_folder.endswith("\\"):
        return db_folder + "watched_status.csv"
    return db_folder + "/" + "watched_status.csv"


def get_db_manager(addon):
    backend = addon.getSetting("storage_backend")
    try:
        backend = int(backend)
    except Exception:
        backend = 0

    if backend == 1:
        if not MariaDBManager:
            logger.error(f"MariaDB backend unavailable: {_MARIADB_IMPORT_ERROR}")
            return None

        host = addon.getSetting("mariadb_host")
        port_str = addon.getSetting("mariadb_port")
        database = addon.getSetting("mariadb_database")
        user = addon.getSetting("mariadb_user")
        password = addon.getSetting("mariadb_password")
        table = addon.getSetting("mariadb_table") or "watched_status"

        if not host or not database or not user:
            logger.error("MariaDB settings incomplete. Please configure host, database, and user.")
            return None

        try:
            port = int(port_str)
        except Exception:
            port = 3306

        try:
            return MariaDBManager(
                host=host,
                port=port,
                database=database,
                user=user,
                password=password,
                table=table,
            )
        except Exception as e:
            logger.error(f"Failed to initialize MariaDB backend: {e}")
            return None

    db_folder = addon.getSetting("db_folder")
    db_path = _build_csv_path(db_folder)
    if not db_path:
        logger.error("CSV database folder not configured.")
        return None
    return DatabaseManager(db_path)
