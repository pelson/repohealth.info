import datetime
import logging
import os
import json
import traceback

from github import Github
import jinja2
import tornado.autoreload
import tornado.ioloop
import tornado.web
import tornado.httpserver
from tornado.escape import json_encode

from repohealth.auth.github import (
        BaseHandler as OAuthBase)
import repohealth.notebook
import repohealth.generate
import repohealth.github.emojis


def repo_uuid(org_or_user, repo_name):
    return '{}/{}'.format(org_or_user, repo_name).lower()


class BaseHandler(OAuthBase):
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

    def _handle_request_exception(self, e):
        tb = traceback.format_exc()
        logging.error(tb)
        self.set_status(500)
        self.finish(self.render('error.html', traceback=tb))


class Error404(BaseHandler):
    def prepare(self):
        self.set_status(404)
        msg = ("This page doesn't exist... well, it does, it's just there "
               "is nothing to see here.")
        self.finish(self.render('error.html', error=msg))


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
    def report_not_ready(self, uuid, token):
        self.set_status(202)
        self.finish(self.render('report.pending.html',
                                token=token, repo_slug=uuid))

    @tornado.web.authenticated
    @tornado.gen.coroutine
    def get(self, org_user, repo_name):
        uuid = repo_uuid(org_user, repo_name)
        user = self.get_current_user()
        token = user['access_token']

        format = self.get_argument('format', 'html')
        if format not in ['notebook', 'html']:
            self.set_status(400)
            return self.finish(self.render(
                'error.html', repo_slug=uuid,
                error=("Invalid format specified. Please choose "
                       "either 'notebook' or 'html'."),))

        datastore = self.settings['datastore']

        if not repohealth.generate.cache_available(uuid):
            # Do what we do with the data handler (return 202 until we
            # are ready)
            return self.report_not_ready(uuid, token)
        else:
            # Secret-sauce to spoil the cache.
            if self.get_argument('cache', '') == 'spoil':
                if uuid in datastore:
                    datastore.pop(uuid)
                repohealth.generate.clear_cache(uuid)
                return self.redirect(self.request.uri.split('?')[0])
            data_fn = tornado.gen.coroutine(repohealth.generate.repo_data)
            payload = yield data_fn(uuid, token)

            if payload.get('status', 200) != 200:
                code = getattr(payload, 'status', 500)
                self.set_status(code)

                if 'traceback' in payload:
                    logging.error(payload['traceback'])
                    self.finish(self.render(
                        'error.html', error=payload['message'],
                        traceback=payload['traceback'],
                        repo_slug=uuid))
                    return
                else:
                    # A more refined message, rather than the full traceback
                    # form.
                    return self.finish(self.render(
                        'error.html', error=payload["message"],
                        repo_slug=uuid))

            viz_fn = tornado.gen.coroutine(repohealth.generate.visualisations)
            visualisations = yield viz_fn(payload)

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
                                cached_jobs=repohealth.generate.in_cache(),
                                user=user, gh=gh))


class APIDataAvailableHandler(BaseHandler):
    known_uuid = []
    known_tokens = []

    def _handle_request_exception(self, e):
        tb = traceback.format_exc()
        logging.error(tb)
        self.set_header('Content-Type', 'application/json')
        self.set_status(500)
        self.finish({'status': 500, 'message': str(tb), 'traceback': tb})

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

        status = repohealth.generate.job_status(uuid)

        if repohealth.generate.cache_available(uuid):
            return {'status': 200, 'message': "ready",
                    'status_info': status}

        if uuid not in datastore:
            future = executor.submit(repohealth.generate.prepare_repo_data,
                                     uuid, token)
            future._start_time = datetime.datetime.utcnow()
            datastore[uuid] = future
            future.add_done_callback(lambda future: datastore.pop(uuid))

            # The status code should be set to "Submitted, and processing"
            self.set_status(202)
            response = {'status': 202,
                        'message': 'Job submitted and is processing.',
                        'status_info': []}
            return response
        else:
            future = datastore[uuid]
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
        uuid = repo_uuid(org_user, repo_name)
        token = self.get_current_user()['access_token']
        self.resp(uuid, token)

    def post(self, org_user, repo_name):
        uuid = repo_uuid(org_user, repo_name)
        token = self.get_argument('token', None)
        self.resp(uuid, token)

    def resp(self, uuid, token):
        self.set_header('Content-Type', 'application/json')
        response = self.availablitiy(uuid, token)
        if response['status'] != 200:
            self.set_status(response['status'])
            self.finish(json_encode(response))
        else:
            result = repohealth.generate.repo_data(uuid, token)
            # Just because we have the result, doesn't mean it wasn't
            # an exception...
            if result.get('status', 200) != 200:
                self.set_status(result['status'])
                logging.error(result)
                return self.finish(json_encode(result))
            else:
                self.finish(json_encode(
                    {'status': 200,
                     'content': result}))


class MainHandler(BaseHandler):
    def get(self):
        self.finish(self.render("index.html"))

    def post(self):
        slug = self.get_argument('slug', None)
        if slug is None or slug.count('/') != 1:
            self.set_status(400)
            msg = 'Please enter a valid GitHub repository.'
            self.finish(self.render('index.html', input_error=msg,
                                    repo_slug=slug))
        else:
            self.redirect('/report/{}'.format(slug))
