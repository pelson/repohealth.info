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
        # Use tornado's async http client to fetch the token URL, and execute
        # the given callback
        http.fetch(self._oauth_request_token_url(**args),
                   functools.partial(self._on_access_token, callback))

    def _on_access_token(self, future, response):
        args = parse_qs(response.body)
        print('Code', response.code, response.body)
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
            if not set(user['scope'].split(',')).issuperset(set(self.settings['github_scope'])):
                # We need to get a new authentication.
                self.clear_cookie("user")
                user = None
            
            if float(user.get('version', 0)) < GithubAuthHandler.cookie_version:
                self.clear_cookie("user")
                user = None
        return user

    def fq_reverse_url(self, name, *args):
        return "{0}://{1}{2}".format(self.request.protocol,
                                     self.request.host,
                                     self.reverse_url(name, *args))


class GithubAuthLogout(BaseHandler):
    def get(self):
        next_uri = self.get_argument('next', self.reverse_url('main'),
                                     strip=True)
        self.clear_cookie("user")
        self.redirect(next_uri)


class GithubAuthHandler(BaseHandler):
    # Keep track of the version of the authentication cookie. If we make any changes
    # then increment this to invalidate and re-authenticate.
    cookie_version = 1.3

    @tornado.gen.coroutine
    def get(self):
        next_uri = self.get_argument('next', self.fq_reverse_url('main'), strip=True)
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
        current_user = self.get_current_user()
        if current_user and float(current_user.get('version', 0)) >= self.cookie_version:
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
            self.redirect(next_uri)
            return

        else:
            # We have no authorization code yet, so redirect to GitHub and come back here when we do.
            yield self.authorize_redirect(
                redirect_uri=auth_uri,
                client_id=self.settings['github_client_id'],
                client_secret=self.settings['github_client_secret'],
                scope=self.settings['github_scope'])


    def _on_auth(self, response_json):
        if not response_json:
            self.clear_cookie("user")
            raise tornado.web.HTTPError(500, "Github auth failed")

        if 'error' in response_json:
            self.clear_cookie("user")
            raise tornado.web.HTTPError(500, "Github auth failed")

        user = response_json

        from github import Github
        gh = Github(user.get('access_token', 'not a valid token'))
        auth_user = gh.get_user()
        user['login'] = auth_user.login
        user['avatar_url'] = auth_user.avatar_url
        user['html_url'] = auth_user.html_url
        user['version'] = self.cookie_version

        user = tornado.escape.json_encode(user)
        self.set_secure_cookie("user", user, expires_days=5)


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
    app = make_app(cookie_secret=os.environ('COOKIE_SECRET'),
                   github_client_id=os.environ['CLIENT_ID'],
                   github_client_secret=os.environ['CLIENT_SECRET'],
                   debug=True,
                   github_scope=['repo'],
                   autoreload=True)
    app.listen(8888)
    tornado.ioloop.IOLoop.current().start()
