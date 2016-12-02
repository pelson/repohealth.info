import datetime
import os
import json
import tornado.ioloop
import tornado.web
import time

from github_oauth import BaseHandler, GithubAuthHandler


class GistLister(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        self.finish(str(self.get_current_user()))


class Logout(BaseHandler):
    def get(self):
        self.clear_cookie("user")
        #self.redirect('/')
        self.finish('Done')


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

    target = os.path.join('ephemeral_storage', uuid)
    if os.path.exists(target):
        repo = git.Repo(target)
        for remote in repo.remotes:
            remote.fetch()
    else:
        repo = git.Repo.clone_from(repo.clone_url, target)     
    import git_analysis

    repo_data = git_analysis.contributors(repo)
    computed = {'contributors': repo_data}
    return {'computed': computed, 'github': report}
    

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

                self.finish(template.render(payload=payload))


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


def make_app(**kwargs):
    app = tornado.web.Application([
        tornado.web.URLSpec(r'/oauth', GithubAuthHandler, name='auth_github'),
        tornado.web.URLSpec(r'/', GistLister, name='main'),
        tornado.web.URLSpec(r'/data/(.*)', DataAvailableHandler, name='data'),
        tornado.web.URLSpec(r'/report/(.*)', RepoReport),
        (r'/logout', Logout),
        ], login_url='/oauth', xsrf_cookies=True, **kwargs)
    return app


if __name__ == '__main__':
    datastore = {}
    with ProcessPoolExecutor() as executor:
        app = make_app(github_client_id=os.environ['CLIENT_ID'],
                       github_client_secret=os.environ['CLIENT_SECRET'],
                       cookie_secret=os.environ['COOKIE_SECRET'],
                       github_scope=['repo', 'user:email'],
                       #               autoreload=True, debug=True,
                       # xheaders MUST be set on heroku, as x-forward-proto is used to forward http -> https
                       xheaders=True,
                       executor=executor, datastore=datastore)
        app.listen(os.environ.get('PORT', 8888))
        tornado.ioloop.IOLoop.current().start()
