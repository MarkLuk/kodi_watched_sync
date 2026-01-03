class Addon:
    def __init__(self, id=None):
        self.settings = {}

    def getSetting(self, id):
        return self.settings.get(id, "")

    def setSetting(self, id, value):
        self.settings[id] = value
