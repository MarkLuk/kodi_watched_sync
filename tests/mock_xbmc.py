
import logging

LOGDEBUG = 0
LOGINFO = 1
LOGWARNING = 2
LOGERROR = 3

def log(msg, level=LOGDEBUG):
    print(f"[XBMC Log] {msg}")

def executeJSONRPC(json_cmd):
    # This will be mocked in the test script dynamically if needed,
    # or we can implement basic responses here.
    return "{}"

class Monitor:
    def __init__(self):
        self.abort = False

    def waitForAbort(self, timeout):
        return self.abort

    def abortRequested(self):
        return self.abort

    def onNotification(self, sender, method, data):
        pass

    def onSettingsChanged(self):
        pass
