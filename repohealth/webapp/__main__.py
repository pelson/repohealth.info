from concurrent.futures import ProcessPoolExecutor
import os

import requests
import tornado.autoreload
import tornado.ioloop
import tornado.web
import tornado.httpserver
from tornado.log import enable_pretty_logging

from repohealth.webapp.handlers import (
    MainHandler, APIDataAvailableHandler,
    APIDataHandler, RepoReport, Status, Error404)
from repohealth.auth.github import (
    GithubAuthHandler, GithubAuthLogout)


def routes():
    return [
        tornado.web.URLSpec(r'/oauth', GithubAuthHandler, name='auth_github'),
        tornado.web.URLSpec(r'/?', MainHandler, name='main'),
        (r'/static/(.*)', tornado.web.StaticFileHandler),
        (r'/api/request/(.*)', APIDataAvailableHandler),
        (r'/api/data/([\w\-]+)/([\w\-]+)', APIDataHandler),
        tornado.web.URLSpec(r'/report/([\w\-]+)/([\w\-]+)', RepoReport),
        (r'/logout', GithubAuthLogout),
        (r'/status', Status),
        ]


def make_app(**kwargs):
    app = tornado.web.Application(
        routes(),
        login_url='/oauth', xsrf_cookies=True,
        template_path='templates',
        static_path='static',
        **kwargs)
    return app


def main():
    # Our datastore is simply a dictionary of {Repo UUID: Future objects}
    datastore = {}

    DEBUG = bool(os.environ.get('DEBUG', False))
    BASE_URL = 'https://repohealth.info' if not DEBUG else None

    app = make_app(github_client_id=os.environ['CLIENT_ID'],
                   github_client_secret=os.environ['CLIENT_SECRET'],
                   cookie_secret=os.environ['COOKIE_SECRET'],
                   github_scope=['user:email'],
                   autoreload=DEBUG, debug=DEBUG,
                   default_handler_class=Error404,
                   fq_base_uri=BASE_URL,
                   datastore=datastore)

    http_server = tornado.httpserver.HTTPServer(app, xheaders=True)
    port = int(os.environ.get("PORT", 8888))

    # https://devcenter.heroku.com/articles/optimizing-dyno-usage#python
    n_processes = int(os.environ.get("WEB_CONCURRENCY", 1))

    if n_processes == 1 or DEBUG:
        http_server.listen(port)
    else:
        # http://www.tornadoweb.org/en/stable/guide/running.html#processes-and-ports
        http_server.bind(port)
        http_server.start(n_processes)

    executor = ProcessPoolExecutor()
    app.settings['executor'] = executor

    if DEBUG:
        tornado.autoreload.add_reload_hook(executor.shutdown)

    def keep_alive(*args):
        # Keeps the heroku process from idling by fetching the logo
        # every 4 minutes.
        requests.get('http://repohealth.info/static/img/heart.png')

    tornado.ioloop.PeriodicCallback(keep_alive, 4 * 60 * 1000).start()

    enable_pretty_logging()
    tornado.ioloop.IOLoop.instance().start()


if __name__ == '__main__':
    main()
