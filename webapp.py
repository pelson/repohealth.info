import datetime
import os
import json
import time

from github_oauth import BaseHandler as OAuthBase, GithubAuthHandler
import tornado.autoreload
import tornado.ioloop
import tornado.web

from jinja2 import Environment, FileSystemLoader 


class BaseHandler(OAuthBase):
    def render_template(self, template_name, **kwargs):
        template_dirs = self.settings["template_path"]
        env = Environment(loader=FileSystemLoader(template_dirs))
        template = env.get_template(template_name)
        content = template.render(kwargs)
        return content


    def render(self, template_name, **kwargs):
        """
        This is for making some extra context variables available to
        the template
        """
        kwargs.update({
            'settings': self.settings,
            'STATIC_URL': self.settings.get('static_url_prefix', '/static/'),
            'request': self.request,
            'xsrf_token': self.xsrf_token,
            'xsrf_form_html': self.xsrf_form_html,
            'authenticated': self.get_current_user() is not None,
            'handler': self
        })
        content = self.render_template(template_name, **kwargs)

        self.write(content)


class Logout(BaseHandler):
    def get(self):
        self.clear_cookie("user")
        self.redirect(self.reverse_url('main'))


def fetch_repo_data(uuid, token):
    from github import Github
    import git 

    cache = os.path.join('ephemeral_storage', uuid + '.json')
    dirname = os.path.dirname(cache)
    # Ensure the storage location exists.
    if not os.path.exists(dirname):
        os.makedirs(dirname)

    if os.path.exists(cache):
        with open(cache, 'r') as fh:
            report = json.load(fh)
    else:
        g = Github(token)
        requests = 0

        repo = g.get_repo(uuid)
        requests += 1

        report = {}

        report['repo'] = repo.raw_data

        issues = repo.get_issues(state='all', since=datetime.datetime.now() - datetime.timedelta(days=30))
        
        limit = 5
        issues_raw = [issue.raw_data for issue, _ in zip(issues, range(limit))]
        report['issues'] = issues_raw

        requests += 1

        with open(cache, 'w') as fh:
            json.dump(report, fh)

    cache = os.path.join('ephemeral_storage', uuid + '_computed.json')
    if not os.path.exists(cache):
        target = os.path.join('ephemeral_storage', uuid)
        if os.path.exists(target):
            repo = git.Repo(target)
            for remote in repo.remotes:
                remote.fetch()
        else:
            repo = git.Repo.clone_from(repo.clone_url, target)     
        import git_analysis

        repo_data = git_analysis.commits(repo)
        with open(cache, 'w') as fh:
            json.dump(repo_data, fh)
    else:
        with open(cache, 'r') as fh:
            repo_data = json.load(fh)

    repo_data['github'] = report
    return repo_data
 

from concurrent.futures import ProcessPoolExecutor

class RepoReport(BaseHandler):
    @tornado.web.authenticated
    def get(self, uuid):
        datastore = self.settings['datastore']
        if uuid not in datastore:
            # Do what we do with the data handler (return 202 until we are ready)
            return DataAvailableHandler.get(self, uuid)
        else:
            future = datastore[uuid]
            if not future.done():
                # Do what we do with the data handler (return 202 until we are ready)
                return DataAvailableHandler.get(self, uuid)
            else:
                import jinja2
                env = jinja2.Environment(loader=jinja2.FileSystemLoader('./'))
                template = env.get_template('report.html')
    
                #repo = git.Repo('ephemeral_storage/SciTools/iris')
                #repo_data = git_analysis.contributors(repo)
                #computed = {'contributors': repo_data} 
                payload = datastore[uuid].result()
                #self.finish(template.render(payload=payload))

                import plotly
                import plotly.plotly as py
                import plotly.graph_objs as go
                import plotly.offline.offline as pl_offline

                
                def html(fig):
                    config = dict(showLink=False, displaylogo=False)
                    plot_html, plotdivid, width, height = pl_offline._plot_html(
                        fig, config, validate=True,
                        default_width='100%', default_height='100%', global_requirejs=False)

                    script_split = plot_html.find('<script ')
                    plot_content = {'div': plot_html[:script_split],
                                    'script': plot_html[script_split:],
                                    'id': plotdivid}
                    return plot_content

                payload['viz'] = {}
                import pandas as pd
                commits = pd.DataFrame.from_dict(payload['commits'])
                first_commits = commits.drop_duplicates(subset='email')


                trace0 = go.Scatter(
                    x=first_commits['date'],
                    y=[i + 1 for i in range(len(first_commits['date']))],
                    text=first_commits['name'],
                )
                fig = go.Figure(data=[trace0])
                payload['viz']['new_contributors'] = html(fig)

                
                trace0 = go.Scatter(
                    x=commits['date'],
                    y=[i + 1 for i in range(len(commits['date']))]
                )
                fig = go.Figure(data=[trace0])
                payload['viz']['commits'] = html(fig)


                add = sub = go.Scatter(
                    x=commits['date'],
                    y=commits['insertions'].cumsum(),
                    text=commits['sha'],
                )
                sub = go.Scatter(
                    x=commits['date'],
                    y=commits['deletions'].cumsum(),
                )
                fig = go.Figure(data=[add, sub])
                payload['viz']['add_sub'] = html(fig)

                self.finish(self.render('report.html', payload=payload))


class DataAvailableHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self, uuid):
        from tornado.escape import json_encode

        self.set_header('Content-Type', 'application/json')

        datastore = self.settings['datastore']
        executor = self.settings['executor']
        # TODO: Validation of uuid.

        if uuid not in datastore:
            user = self.get_current_user()
            token = user['access_token']
            future = executor.submit(fetch_repo_data, uuid, token)
            future._start_time = datetime.datetime.now()
            datastore[uuid] = future

            # The status code should be set to "Submitted, and processing"
            self.set_status(202)
            response = {'status': 202, 'message': 'Job submitted and is processing.'}
            self.finish(json_encode(response))
        else:
            future = datastore[uuid]
            if future.done():
                # TODO: Result could be the raising of an exception...
                self.finish(json_encode(future.result()))
            else:
                self.set_status(202)
                response = {'status': 202,
                            'message': ('Job is still running ({}).'
                                        ''.format(datetime.datetime.now() - future._start_time)),
                            }
                self.finish(json_encode(response))


class MainHandler(BaseHandler):
    def get(self):
        self.render("index.html")


def make_app(**kwargs):
    app = tornado.web.Application([
        tornado.web.URLSpec(r'/oauth', GithubAuthHandler, name='auth_github'),
        tornado.web.URLSpec(r'/', MainHandler, name='main'),
        (r'/static/(.*)', tornado.web.StaticFileHandler),
        tornado.web.URLSpec(r'/data/(.*)', DataAvailableHandler, name='data'),
        tornado.web.URLSpec(r'/report/(.*)', RepoReport),
        (r'/logout', Logout),
        ],
        login_url='/oauth', xsrf_cookies=True,
        template_path='templates',
        static_path='static',
        **kwargs)
    return app


if __name__ == '__main__':
    # Our datastore is simply a dictionary of {Repo UUID: Future objects}
    datastore = {}

    app = make_app(github_client_id=os.environ['CLIENT_ID'],
                   github_client_secret=os.environ['CLIENT_SECRET'],
                   cookie_secret=os.environ['COOKIE_SECRET'],
                   github_scope=['repo', 'user:email'],
                   autoreload=True, debug=True,
                   datastore=datastore)
    app.listen(os.environ.get('PORT', 8888))

    executor = ProcessPoolExecutor()
    app.settings['executor'] = executor

    tornado.autoreload.add_reload_hook(executor.shutdown)
    tornado.ioloop.IOLoop.current().start()
