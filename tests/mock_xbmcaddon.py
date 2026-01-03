class Addon:
    _settings = {}

    def __init__(self, id=None):
        pass

    def getSetting(self, id):
        return self._settings.get(id, "")

    def setSetting(self, id, value):
        self._settings[id] = value
