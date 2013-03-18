class NeoMiddleware(object):
    '''
    This middleware needs to go after AuthenticationMiddleware and SessionMiddleware. It adds the
    user password to the user object on the request. It also processes an exception if the password
    is not in the session, requiring the user to re-authenticate.
    '''

    #def process_exception(self, request, exception):
    #    raise exception

    def process_request(self, request):
        if hasattr(request, 'user') and request.user.is_authenticated():
            pw = request.session.get('raw_password', None)
            if pw:
                request.user.raw_password = pw

        return None

    def process_response(self, request, response):
        if hasattr(request, 'user') and request.user.is_authenticated():
            if hasattr(request.user, 'old_password') or hasattr(request.user, 'forgot_password_token'):
                request.session['raw_password'] = request.user.raw_password

        return response
