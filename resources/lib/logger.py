import xbmc

PREFIX = "[WatchedSync]"

def debug(msg):
    """Logs a debug message with the addon prefix."""
    xbmc.log(f"{PREFIX} {msg}", xbmc.LOGDEBUG)

def info(msg):
    """Logs an info message with the addon prefix."""
    xbmc.log(f"{PREFIX} {msg}", xbmc.LOGINFO)

def warn(msg):
    """Logs a warning message with the addon prefix."""
    xbmc.log(f"{PREFIX} {msg}", xbmc.LOGWARNING)

def error(msg):
    """Logs an error message with the addon prefix."""
    xbmc.log(f"{PREFIX} {msg}", xbmc.LOGERROR)
