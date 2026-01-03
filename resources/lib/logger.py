import xbmc

PREFIX = "[WatchedSync]"

def debug(msg):
    xbmc.log(f"{PREFIX} {msg}", xbmc.LOGDEBUG)

def info(msg):
    xbmc.log(f"{PREFIX} {msg}", xbmc.LOGINFO)

def warn(msg):
    xbmc.log(f"{PREFIX} {msg}", xbmc.LOGWARNING)

def error(msg):
    xbmc.log(f"{PREFIX} {msg}", xbmc.LOGERROR)
