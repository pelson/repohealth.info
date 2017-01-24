"""
Compute the data that is used for producing the health report.

"""
from collections import OrderedDict
import datetime
from functools import partial
import glob
import json
import os
import logging
import shutil
import traceback

import fasteners
import tornado.ioloop

import git
from github import Github
import plotly.graph_objs as go
import plotly.offline.offline as pl_offline

import repohealth
import repohealth.git
import repohealth.github.stargazers
import repohealth.github.issues
import repohealth.github.emojis
from repohealth.analysis import PLOTLY_PLOTS


CACHE_ROOT = os.path.join(os.path.abspath(os.path.dirname(os.path.dirname(repohealth.__file__))),
                          'ephemeral_storage')


CACHE_EXCEPTION = os.path.join(CACHE_ROOT, '{}.exception.json')
CACHE_GH = os.path.join(CACHE_ROOT, '{}.github.json')
CACHE_COMMITS = os.path.join(CACHE_ROOT, '{}.commits.json')
CACHE_CLONE = os.path.join(CACHE_ROOT, '{}')
CACHE_PLOTS = os.path.join(CACHE_ROOT, '{}.plots.json')
STATUS_FILE = os.path.join(CACHE_ROOT, '{}.status.json')
STATUS_LOCK_FILE = os.path.join(CACHE_ROOT, '{}.status.lock.json')


def clear_cache(uuid):
    logging.info("Spoiling the cache for {}".format(uuid))
    if os.path.exists(CACHE_EXCEPTION.format(uuid)):
        os.remove(CACHE_EXCEPTION.format(uuid))
    if os.path.exists(CACHE_GH.format(uuid)):
        os.remove(CACHE_GH.format(uuid))
    if os.path.exists(CACHE_COMMITS.format(uuid)):
        os.remove(CACHE_COMMITS.format(uuid))
    if os.path.exists(CACHE_CLONE.format(uuid)):
        shutil.rmtree(CACHE_CLONE.format(uuid))


from contextlib import contextmanager


@contextmanager
def no_raise(uuid):
    cache_file = CACHE_EXCEPTION.format(uuid)
    try:
        yield
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as err:
        result = {'status': getattr(err, 'code', 500),
                  'message': str(err),
                  'traceback': traceback.format_exc()}
        with open(cache_file, 'w') as fh:
            json.dump(result, fh)
        return result


def cache_available(uuid):
    avail = ((os.path.exists(CACHE_GH.format(uuid)) and
              os.path.exists(CACHE_COMMITS.format(uuid))) or
             os.path.exists(CACHE_EXCEPTION.format(uuid)))
    return avail


def in_cache():
    """
    Return all of the uuids of packages with sucessful & valid caches.

    """
    patterns = [CACHE_GH.format('*/*'), CACHE_COMMITS.format('*/*')]

    gh = sorted(glob.glob(patterns[0]))
    cm = sorted(glob.glob(patterns[1]))

    # One particularly sneaky (and unpleasant) way of getting the uuid from the
    # filename is to inject something that shouldn't be there, and then
    # figure out the indices that we need to pick off...
    split_char = '&/&/&/&'
    gh_pick = CACHE_GH.format(split_char).split(split_char)
    gh = [path[len(gh_pick[0]) : -len(gh_pick[1])] for path in gh]
    cm_pick = CACHE_COMMITS.format(split_char).split(split_char)
    cm = [path[len(gh_pick[0]) : -len(cm_pick[1])] for path in cm]
  
    available = set(gh) & set(cm)
    return sorted(available)


def job_status(uuid):
    status_file = STATUS_FILE.format(uuid)
    if not os.path.exists(status_file):
        status = {}
    else:
        with fasteners.InterProcessLock(STATUS_LOCK_FILE.format(uuid)):
            with open(status_file, 'r') as fh:
                status = json.load(fh)
    return status


def prepare_repo_data(uuid, token):
    # A function that doesn't give you the data, it just makes
    # sure it is all available in the cache.
    result = repo_data(uuid, token)
    status = result.get('status', 200)
    return status


def repo_data(uuid, token):
    def update_status(message=None, clear=False, update=False):
        status_file = STATUS_FILE.format(uuid)
        status_lock = fasteners.InterProcessLock(STATUS_LOCK_FILE.format(uuid))

        with status_lock:
            if not os.path.exists(status_file) or clear:
                status = []
            else:
                with open(status_file, 'r') as fh:
                    status = json.load(fh)

            if status and not update:
                # Log the last status item as complete.
                now = datetime.datetime.utcnow()
                status[-1]['end'] = now.strftime('%Y-%m-%dT%H:%M:%SZ')

            # Allow for the option of not adding a status message so that we can
            # call this function to close off the previous message once it is
            # complete.
            if message is not None:
                if update:
                    status[-1]['status'] = message
                else:
                    now = datetime.datetime.utcnow()
                    status.append(dict(start=now.strftime('%Y-%m-%dT%H:%M:%SZ'),
                                       status=message))

            with open(status_file, 'w') as fh:
                json.dump(status, fh)

    cache_file = CACHE_EXCEPTION.format(uuid)
    if os.path.exists(cache_file):
        with open(cache_file, 'r') as fh:
            result = json.load(fh)
            return result

    with no_raise(uuid):
        cache = CACHE_GH.format(uuid)
        dirname = os.path.dirname(cache)
        # Ensure the storage location exists.
        if not os.path.exists(dirname):
            os.makedirs(dirname)

        if os.path.exists(cache):
            update_status('Load GitHub API data from ephemeral cache', clear=True)
            with open(cache, 'r') as fh:
                report = json.load(fh)
            # We don't stop here - there is more to the report to add...
        else:
            update_status('Initial validation of repo', clear=True)
            g = Github(token)
            gh_repo = g.get_repo(uuid)

            # Check that this is actually a valid repository. If not, return a known
            # status so that our report can deal with it with more grace than simply
            # catching the exception.
            try:
                gh_repo.raw_data
            except Exception:
                report = {'status': 404,
                          'message': 'Repository "{}" not found.'.format(uuid)}
                with open(CACHE_EXCEPTION.format(uuid), 'w') as fh:
                    json.dump(report, fh)
                return report

            report = {}

            loop = tornado.ioloop.IOLoop()

            update_status('Fetching GitHub API data')
            report['repo'] = gh_repo.raw_data

            update_status('Fetching GitHub issues data')

            issues_fn = partial(repohealth.github.issues.repo_issues, gh_repo, token)
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
                                    gh_repo, token)
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
            clone_exists = os.path.exists(clone_target)

            if clone_exists:
                # For local dev, we just fetch anything that already sits in the ephemeral cache.
                update_status('Fetching remotes from cached clone')
                repo = git.Repo(clone_target)
                for remote in repo.remotes:
                    remote.fetch()
            else:
                update_status('Cloning repo')

                class Progress(git.remote.RemoteProgress):
                    def update(self, op_code, cur_count, max_count=None, message=''):
                        if message:
                            update_status('Cloning repo: {}'.format(message), update=True)

                repo = git.Repo.clone_from(report['repo']['clone_url'], clone_target,
                                           progress=Progress())

            update_status('Analysing commits')
            repo_data = repohealth.git.commits(repo)
            with open(cache, 'w') as fh:
                json.dump(repo_data, fh)

            if not clone_exists:
                # This was ours to clone, so nuke it now.
                shutil.rmtree(clone_target)

        else:
            update_status('Load commit from ephemeral cache')
            with open(cache, 'r') as fh:
                repo_data = json.load(fh)

        # Round off the status so that the last task has an end time.
        update_status()

        repo_data['github'] = report
        return repo_data


def visualisations(payload):
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

        try:
            data = prepare(payload)
            fig = viz(data)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as err:
            logging.exception('A problem with one of the plotly '
                              'plots occured.')
            logging.exception(traceback.format_exc())
            continue

        if not isinstance(fig, go.Figure):
            fig = go.Figure(fig)
        fig.layout.margin = go.Margin(t=4, b=40, l=40, r=20, pad=1)
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
    return visualisations
