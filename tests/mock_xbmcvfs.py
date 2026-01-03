import os

def exists(path):
    return os.path.exists(path)

def delete(path):
    if os.path.exists(path):
        os.remove(path)

class File:
    def __init__(self, path, mode='r'):
        self.path = path
        self.mode = mode
        self.f = None
        # xbmcvfs.File doesn't support 'with' context manager in older versions,
        # but my code does `f = File(); f.write(); f.close()`.
        # However, for local file simulation, we open eagerly.
        self.f = open(self.path, self.mode)

    def read(self):
        return self.f.read()

    def write(self, content):
        return self.f.write(content)

    def close(self):
        if self.f:
            self.f.close()
            self.f = None
