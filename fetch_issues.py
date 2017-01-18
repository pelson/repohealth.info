import logging
import json
import time
import github as gh
from tornado.httpclient import AsyncHTTPClient
import requests

from urllib.parse import urlparse, parse_qs
from tornado.gen import coroutine


def parse_link(link_header):
    l0, l1 = link_header.split(',')
    next_url = l0.strip()[1:-len('>; rel="next"')]
    last_url = l1.strip()[1:-len('>; rel="last"')]
    return next_url, last_url


def handle_response(issues, response):
    content = json.loads(response.body.decode('utf-8'))
    issues.extend(content)


@coroutine
def repo_issues(repo, token):
    issues_url = repo.issues_url.format(**{'/number': ''})
    page_size = 100

    headers = {'User-Agent': 'tornado'}
    headers['Authorization'] = 'token {}'.format(token)

    # Be good citizens and allow a maximum of 40 concurrent requests.
    client = AsyncHTTPClient(max_clients=40)
    url = issues_url + "?per_page={}&page={}&state=all".format(page_size, 1)
    response = yield client.fetch(url, headers=headers)

    issues = []
    handle_response(issues, response)
    
    next_url, last_url = parse_link(response.headers['Link'])
    qs = parse_qs(urlparse(last_url).query)
    last_page = int(qs['page'][0])

    from functools import partial
    get_issues = partial(handle_response, issues)
    futures = []
    for page in range(2, last_page + 1):
        url = issues_url + "?per_page={}&page={}&state=all".format(page_size, page)
        f = client.fetch(url, headers=headers, callback=get_issues)
        futures.append(f)

    for future in futures:
        yield future
    return issues


if __name__ == '__main__':
    token = '...'

    g = gh.Github(token)
    r = g.get_repo('d3/d3')
#    r = g.get_repo('dask/dask')

    from tornado.ioloop import IOLoop
    from functools import partial

    issues_fn = partial(repo_issues, r, token) 
    issues = IOLoop.instance().run_sync(issues_fn)

