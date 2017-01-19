"""
Compute the data that is used for producing the health report.

"""
import datetime
import os
import json
import shutil

from functools import partial

import tornado.ioloop

import git
from github import Github

import repohealth.git
import repohealth.github.stargazers
import repohealth.github.issues
import repohealth.github.emojis


CACHE_GH = os.path.join('ephemeral_storage', '{}.github.json')
CACHE_COMMITS = os.path.join('ephemeral_storage', '{}.commits.json')
CACHE_CLONE = os.path.join('ephemeral_storage', '{}')
STATUS_FILE = os.path.join('ephemeral_storage', '{}.status.json')


def clear_cache(uuid):
    print("Spoiling the cache for {}".format(uuid))
    if os.path.exists(CACHE_GH.format(uuid)):
        os.remove(CACHE_GH.format(uuid))
    if os.path.exists(CACHE_COMMITS.format(uuid)):
        os.remove(CACHE_COMMITS.format(uuid))
    if os.path.exists(CACHE_CLONE.format(uuid)):
        shutil.rmtree(CACHE_CLONE.format(uuid))


def repo_data(uuid, token):
    def update_status(message=None, clear=False):
        status_file = STATUS_FILE.format(uuid)

        if not os.path.exists(status_file) or clear:
            status = []
        else:
            with open(status_file, 'r') as fh:
                status = json.load(fh)

            # Log the last status item as complete.
            now = datetime.datetime.utcnow()
            status[-1]['end'] = now.strftime('%Y-%m-%dT%H:%M:%SZ')

        # Allow for the option of not adding a status message so that we can
        # call this function to close off the previous message once it is
        # complete.
        if message is not None:
            now = datetime.datetime.utcnow()
            status.append(dict(start=now.strftime('%Y-%m-%dT%H:%M:%SZ'),
                               status=message))

        # TODO: Use a lock to avoid race conditions on read/write of status.
        with open(status_file, 'w') as fh:
            json.dump(status, fh)

    cache = CACHE_GH.format(uuid)
    dirname = os.path.dirname(cache)
    # Ensure the storage location exists.
    if not os.path.exists(dirname):
        os.makedirs(dirname)

    update_status('Initial validation of repo', clear=True)
    g = Github(token)
    repo = g.get_repo(uuid)

    # Check that this is actually a valid repository. If not, return a known
    # status so that our report can deal with it with more grace than simply
    # catching the exception.
    try:
        repo.raw_data
    except Exception:
        report = {'status': 404,
                  'message': 'Repository "{}" not found.'.format(uuid)}
        return report

    if os.path.exists(cache):
        update_status('Load GitHub API data from ephemeral cache')
        with open(cache, 'r') as fh:
            report = json.load(fh)
    else:
        report = {}

        loop = tornado.ioloop.IOLoop()

        update_status('Fetching GitHub API data')
        report['repo'] = repo.raw_data

        update_status('Fetching GitHub issues data')

        issues_fn = partial(repohealth.github.issues.repo_issues, repo, token)
        issues = loop.run_sync(issues_fn)
        user_keys = ['login', 'id']
        issue_keys = ['number', 'comments', 'created_at', 'state', 'closed_at']

        def handle_issue(issue):
            return dict(**{'user/{}'.format(key): issue['user'][key]
                           for key in user_keys},
                        **{key: issue[key] for key in issue_keys})
        report['issues'] = [handle_issue(issue) for issue in issues]

        update_status('Fetching GitHub stargazer data')
        stargazers_fn = partial(repohealth.github.stargazers.repo_stargazers,
                                repo, token)
        stargazers = loop.run_sync(stargazers_fn)

        star_keys = ['starred_at']

        def handle_star(star):
            return dict(**{'user/{}'.format(key): star['user'][key]
                           for key in user_keys},
                        **{key: star[key] for key in star_keys})

        report['stargazers'] = [handle_star(stargazer)
                                for stargazer in stargazers
                                if isinstance(stargazer, dict)]

        with open(cache, 'w') as fh:
            json.dump(report, fh)

    cache = CACHE_COMMITS.format(uuid)
    if not os.path.exists(cache):
        clone_target = CACHE_CLONE.format(uuid)
        if os.path.exists(clone_target):
            update_status('Fetching remotes from cached clone')
            repo = git.Repo(clone_target)
            for remote in repo.remotes:
                remote.fetch()
        else:
            update_status('Cloning repo')
            repo = git.Repo.clone_from(repo.clone_url, clone_target)

        update_status('Analysing commits')
        repo_data = repohealth.git.commits(repo)
        with open(cache, 'w') as fh:
            json.dump(repo_data, fh)
    else:
        update_status('Load commit from ephemeral cache')
        with open(cache, 'r') as fh:
            repo_data = json.load(fh)

    # Round off the status so that the last task has an end time.
    update_status()

    repo_data['github'] = report
    return repo_data
