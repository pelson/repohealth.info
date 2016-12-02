import codecs
import functools
import logging
import re
try:
    from urllib.parse import parse_qs
except ImportError:
    from urlparse import parse_qs

import tornado.auth
import tornado.ioloop
import tornado.gen
import tornado.web
import tornado.escape


class GitHubMixin(tornado.auth.OAuth2Mixin):
    _OAUTH_AUTHORIZE_URL = 'https://github.com/login/oauth/authorize'
    _OAUTH_ACCESS_TOKEN_URL = 'https://github.com/login/oauth/access_token'

    @tornado.auth._auth_return_future
    def get_authenticated_user(self, redirect_uri, client_id, client_secret,
                               code, callback, extra_fields=None):
    
        http = self.get_auth_http_client()
        args = {
            "redirect_uri": redirect_uri,
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
        }
        fields = set(['id', 'name', 'first_name', 'last_name',
                      'locale', 'picture', 'link'])
        if extra_fields:
            fields.update(extra_fields)
        http.fetch(self._oauth_request_token_url(**args),
                   functools.partial(self._on_access_token, callback))

    def _on_access_token(self, future, response):
        args = parse_qs(response.body)

        if response.error or 'error' in args:
            raise ValueError(response.body)
            future.set_exception(tornado.auth.AuthError('GitHub auth error: %s' % str(response)))
            return

        # Decode the parsed query string so that we can use the result as expected.
        result = {}
        # Remove the qs list values.
        for k, v in args.items():
            result[k.decode('ascii')] = v[-1].decode('ascii')
        future.set_result(result)


class BaseHandler(tornado.web.RequestHandler, GitHubMixin):
    def get_current_user(self):
        user = self.get_secure_cookie("user")

        # At this point, user is either defined, or is None (not logged in).
        if user is not None:
            user = tornado.escape.json_decode(user)

        return user

    def fq_reverse_url(self, name, *args):
        print('WHAT WE HAVE:', self.request.uri)
        print(self.request.headers)
        return "{0}://{1}{2}".format(self.request.protocol,
                                     self.request.host,
                                     self.reverse_url(name, *args))


class GithubAuthHandler(BaseHandler):

    @tornado.gen.coroutine
    def get(self):
        next_uri = self.get_argument('next', self.fq_reverse_url('main'), strip=True)
        print('NEXT:', next_uri)
        auth_uri = tornado.httputil.url_concat(self.fq_reverse_url('auth_github'),
                                               dict(next=next_uri))

        error = self.get_argument('error', None, strip=True)
        if error:
            msg = self.get_argument('error_description', 'No error message provided', strip=True)
            self.clear()
            self.set_status(400)
            self.finish("<html><body>{}<br>{}</body></html>".format(msg, auth_uri))
            return

        # If we are already authorized, just continue on through.
        if self.get_current_user():
            self.redirect(next_uri)
            return

        code = self.get_argument('code', None)
        if code:
            # We have the code, now get a token.
            access = yield self.get_authenticated_user(
                redirect_uri=auth_uri,
                client_id=self.settings['github_client_id'],
                client_secret=self.settings['github_client_secret'],
                code=self.get_argument('code'),
                callback=self._on_auth,
                )
            print('Access:', access)
            self.redirect(next_uri)
            return

        else:
            # We have no authorization code yet, so redirect to GitHub and come back here when we do.
            yield self.authorize_redirect(
                redirect_uri=auth_uri,
                client_id=self.settings['github_client_id'],
                client_secret=self.settings['github_client_secret'],
                scope=self.settings['github_scope'])


    def _on_auth(self, user, access_token=None):
        if not user:
            raise tornado.web.HTTPError(500, "Github auth failed")
            self.clear_cookie("user")
            return

        user = tornado.escape.json_encode(user)
        if 'error' in user:
            raise ValueError(user)
            raise tornado.web.HTTPError(500, "Github auth failed")
            self.clear_cookie("user")
            return

        self.set_secure_cookie("user", user, expires_days=1)


class GistLister(BaseHandler):
    @tornado.web.authenticated
    @tornado.gen.coroutine
    def get(self):
        self.write(str(self.get_current_user()))
        self.finish('foobar')
        return
        self.github_request(
                '/gists', self._on_get_gists,
                access_token=self.current_user['access_token'])

    def _on_get_gists(self, gists):
        self.write(str(gists))


def make_app(**kwargs):
    app = tornado.web.Application([
        tornado.web.URLSpec(r'/auth', GithubAuthHandler, name='auth_github'),
        tornado.web.URLSpec(r'/', GistLister, name='main'),
        ], 
        login_url='/auth', xsrf_cookies=True, **kwargs)
    return app


if __name__ == '__main__':
    app = make_app(github_client_id='2f43c89156cbcf321139',
                   github_client_secret='36782ebeac39bb66c1548969938933884d63152f',
                   cookie_secret='a_secret_cookie_salt',
                   debug=True,
                   github_scope=['repo'],
                   autoreload=True)
    app.listen(8888)
    tornado.ioloop.IOLoop.current().start()
