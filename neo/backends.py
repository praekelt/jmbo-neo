from foundry.backends import MultiBackend


class NeoBackendBase(object):

    def authenticate(self, username=None, password=None):
        user = super(NeoBackendBase, self).authenticate(username=username, password=password)
        if user is not None:
            user.raw_password = password
        return user


class NeoMultiBackend(NeoBackendBase, MultiBackend):
    pass
