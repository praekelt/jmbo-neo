from foundry.backends import MultiBackend

from neo.api import authenticate as authenticate_neo


class NeoBackend(MultiBackend):
    
    def authenticate(self, username=None, password=None):
        return authenticate_neo(username, password)
