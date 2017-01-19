from concurrent.futures import ProcessPoolExecutor
from collections import OrderedDict
import datetime
import os
import json
import traceback

from github import Github
import jinja2
import plotly.graph_objs as go
import plotly.offline.offline as pl_offline
import requests
import tornado.autoreload
import tornado.ioloop
import tornado.web
import tornado.httpserver
from tornado.escape import json_encode

from repohealth.auth.github import (
        BaseHandler as OAuthBase, GithubAuthHandler, GithubAuthLogout)
import repohealth.notebook
import repohealth.generate
import repohealth.github.emojis
from repohealth.analysis import PLOTLY_PLOTS


class BaseHandler(OAuthBase):
    def prepare(self):
        # Redirect to https in production.
        url = self.request.full_url()
        if self.request.protocol == "http" and 'localhost' not in url:
            self.redirect("https://%s".format(url[len("http://"):]),
                          permanent=True)
        super(OAuthBase, self).prepare()

    def render_template(self, template_name, **kwargs):
        template_dirs = self.settings["template_path"]
        env = jinja2.Environment(loader=jinja2.FileSystemLoader(template_dirs))
        env.filters['gh_emoji'] = repohealth.github.emojis.to_html
        template = env.get_template(template_name)
        content = template.render(kwargs)
        return content

    def render(self, template_name, **kwargs):
        """
        This is for making some extra context variables available to
        the template.

        """
        kwargs.update({
            'settings': self.settings,
            'STATIC_URL': self.settings.get('static_url_prefix', '/static/'),
            'request': self.request,
            'xsrf_token': self.xsrf_token,
            'xsrf_form_html': self.xsrf_form_html,
            'authenticated': self.get_current_user() is not None,
            'user': self.get_current_user(),
            'handler': self
        })
        content = self.render_template(template_name, **kwargs)
        self.write(content)


class Error404(BaseHandler):
    def prepare(self):
        self.set_status(404)
        self.finish(self.render('404.html'))


def pretty_timedelta(datetime, from_date):
    diff = from_date - datetime
    s = diff.seconds
    if diff.days > 7 or diff.days < 0:
        return datetime.strftime('%d %b %y')
    elif diff.days == 1:
        return '1 day ago'
    elif diff.days > 1:
        return '{} days ago'.format(diff.days)
    elif s <= 1:
        return 'just now'
    elif s < 120:
        return '{} seconds ago'.format(s)
    elif s < 3600:
        return '{} minutes ago'.format(s//60)
    elif s < 7200:
        return '1 hour ago'
    else:
        return '{} hours ago'.format(s//3600)


class RepoReport(BaseHandler):
    def report_not_ready(self, uuid):
        user = self.get_current_user()
        token = user['access_token']
        self.finish(self.render('report.pending.html',
                                token=token, repo_slug=uuid))

    @tornado.web.authenticated
    def get(self, org_user, repo_name):
        uuid = '{}/{}'.format(org_user, repo_name)
        format = self.get_argument('format', 'html')
        if format not in ['notebook', 'html']:
            self.set_status(400)
            return self.finish(self.render(
                'error.html', repo_slug=uuid,
                error=("Invalid format specified. Please choose "
                       "either 'notebook' or 'html'."),))
        datastore = self.settings['datastore']
        if uuid not in datastore:
            # Do what we do with the data handler (return 202 until we
            # are ready)
            return self.report_not_ready(uuid)
        else:
            future = datastore[uuid]
            if not future.done():
                # Do what we do with the data handler (return 202 until we
                # are ready)
                return self.report_not_ready(uuid)
            else:
                # Secret-sauce to spoil the cache.
                if self.get_argument('cache', '') == 'spoil':
                    repohealth.generate.clear_cache(uuid)
                    datastore.pop(uuid)
                    return self.redirect(self.request.uri.split('?')[0])
                try:
                    payload = datastore[uuid].result()
                except (KeyboardInterrupt, SystemExit):
                    raise
                except Exception as err:
                    print(traceback.format_exc())
                    self.set_status(500)
                    self.finish(self.render(
                        'error.html', error=str(err),
                        traceback=traceback.format_exc(),
                        repo_slug=uuid))
                    return

                if payload.get('status', 200) != 200:
                    self.set_status(payload['status'])
                    # A more refined message, rather than the full traceback
                    # form.
                    return self.finish(self.render(
                        'error.html', error=payload["message"]))

                def html(fig):
                    config = dict(showLink=False, displaylogo=False)
                    plot_html, plotdivid, w, h = pl_offline._plot_html(
                        fig, config, validate=True,
                        default_width='100%', default_height='100%',
                        global_requirejs=False)

                    script_split = plot_html.find('<script ')
                    plot_content = {'div': plot_html[:script_split],
                                    'script': plot_html[script_split:],
                                    'id': plotdivid}
                    return plot_content

                visualisations = OrderedDict()

                for key, title, mod in PLOTLY_PLOTS:
                    prep_fn_name = '{}_prep'.format(key)
                    viz_fn_name = '{}_viz'.format(key)
                    prepare = getattr(mod, prep_fn_name)
                    viz = getattr(mod, viz_fn_name)

                    data = prepare(payload)
                    fig = viz(data)

                    if not isinstance(fig, go.Figure):
                        fig = go.Figure(fig)
                    fig.layout.margin = go.Margin(t=0, b=40, l=40, r=20, pad=1)
                    fig.layout.legend = dict(x=0.1, y=1)
                    visualisation = html(fig)
                    del fig

                    with open(mod.__file__, 'r') as fh:
                        mod_source = fh.readlines()
                    code = ''.join(
                             mod_source +
                             ["\n\n",
                              "{} = {}(payload)\n".format(key, prep_fn_name),
                              "iplot({}({}))\n".format(viz_fn_name, key),
                              ])

                    visualisation['code'] = code
                    visualisation['title'] = title

                    visualisations[key] = visualisation

                if format == 'notebook':
                    content = repohealth.notebook.notebook(uuid, payload,
                                                           visualisations)
                    fname = "health_{}.ipynb".format(uuid.replace('/', '_'))

                    self.set_header("Content-Type", 'application/x-ipynb+json')
                    self.set_header("Content-Disposition",
                                    'attachment; filename="{}'.format(fname))
                    return self.finish(content)
                else:
                    self.finish(self.render('report.html', payload=payload,
                                            viz=visualisations,
                                            repo_slug=uuid))


class Status(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        user = self.get_current_user()
        gh = Github(user['access_token'])
        self.finish(self.render('status.html',
                                futures=self.settings['datastore'],
                                user=user, gh=gh))


class APIDataAvailableHandler(BaseHandler):
    known_uuid = []
    known_tokens = []

    def check_xsrf_cookie(self, *args, **kwargs):
        # We don't want xsrf checking for this API - the user can come from
        # anywhere, provided they give us a token.
        pass

    # No authentication needed - pass the github token as TOKEN.
    def post(self, uuid):
        self.set_header('Content-Type', 'application/json')
        token = self.get_argument('token', None)
        response = self.availablitiy(uuid, token)
        self.set_status(response['status'])
        self.finish(json_encode(response))

    def availablitiy(self, uuid, token):
        """
        Return a status payload to confirm whether or not the data exists
        ({'status': 200, ...} for yes)

        """
        if token is None:
            response = {'status': 401, 'message': 'Token is not defined'}
            return response

        datastore = self.settings['datastore']
        executor = self.settings['executor']

        if uuid not in datastore:
            future = executor.submit(repohealth.generate.repo_data,
                                     uuid, token)
            future._start_time = datetime.datetime.utcnow()
            datastore[uuid] = future

            # The status code should be set to "Submitted, and processing"
            self.set_status(202)
            response = {'status': 202,
                        'message': 'Job submitted and is processing.',
                        'status_info': []}
            return response
        else:
            future = datastore[uuid]

            status_file = repohealth.generate.STATUS_FILE.format(uuid)
            if not os.path.exists(status_file):
                status = {}
            else:
                with open(status_file, 'r') as fh:
                    status = json.load(fh)

            if future.done():
                return {'status': 200, 'message': "ready",
                        'status_info': status}
            else:
                since = pretty_timedelta(future._start_time,
                                         datetime.datetime.utcnow())
                message = ('Job started {} and is still running.'
                           ''.format(since))
                response = {'status': 202, 'message': message,
                            'status_info': status}
                return response


class APIDataHandler(APIDataAvailableHandler):
    @tornado.web.authenticated
    def get(self, org_user, repo_name):
        uuid = '{}/{}'.format(org_user, repo_name)
        token = self.get_current_user()['access_token']
        self.resp(uuid, token)

    def post(self, org_user, repo_name):
        uuid = '{}/{}'.format(org_user, repo_name)
        token = self.get_argument('token', None)
        self.resp(uuid, token)

    def resp(self, uuid, token):
        self.set_header('Content-Type', 'application/json')
        response = self.availablitiy(uuid, token)

        if response['status'] != 200:
            self.set_status(response['status'])
            self.finish(json_encode(response))
        else:
            future = self.settings['datastore'][uuid]
            # Just because we have the result, doesn't mean it wasn't
            # an exception...
            try:
                self.finish(json_encode({'status': 200,
                                         'content': future.result()}))
            except Exception as err:
                print(traceback.format_exc())
                response = {'status': 500, 'message': str(err),
                            'traceback': traceback.format_exc()}
                return response


class MainHandler(BaseHandler):
    def get(self):
        self.render("index.html")

    def post(self):
        slug = self.get_argument('slug', None)
        if slug is None or slug.count('/') != 1:
            self.set_status(400)
            msg = 'Please enter a valid GitHub repository.'
            self.finish(self.render('index.html', input_error=msg,
                                    repo_slug=slug))
        else:
            self.redirect('/report/{}'.format(slug))


def make_app(**kwargs):
    app = tornado.web.Application([
        tornado.web.URLSpec(r'/oauth', GithubAuthHandler, name='auth_github'),
        tornado.web.URLSpec(r'/', MainHandler, name='main'),
        (r'/static/(.*)', tornado.web.StaticFileHandler),
        (r'/api/request/(.*)', APIDataAvailableHandler),
        (r'/api/data/([\w\-]+)/([\w\-]+)', APIDataHandler),
        tornado.web.URLSpec(r'/report/([\w\-]+)/([\w\-]+)', RepoReport),
        (r'/logout', GithubAuthLogout),
        (r'/status', Status),
        ],
        login_url='/oauth', xsrf_cookies=True,
        template_path='templates',
        static_path='static',
        **kwargs)
    return app


if __name__ == '__main__':
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
        requests.get('https://repohealth.info/static/img/heart.png')

    tornado.ioloop.PeriodicCallback(keep_alive, 4 * 60 * 1000).start()

    tornado.ioloop.IOLoop.instance().start()
