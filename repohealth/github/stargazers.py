import collections
import json
import logging
import traceback
from urllib.parse import urlparse, parse_qs

import github as gh
from tornado.httpclient import AsyncHTTPClient
import tornado.gen


def parse_link(link_header):
    l0, l1 = link_header.split(',')
    next_url = l0.strip()[1:-len('>; rel="next"')]
    last_url = l1.strip()[1:-len('>; rel="last"')]
    return next_url, last_url


def handle_response(container, response):
    content = json.loads(response.body.decode('utf-8'))
    if content:
        for record in content:
            # Sometimes we were seeing spurious "documentation_url" responses
            # that hadn't been well handled. These came particularly from the
            # d3/d3 stars request.
            if isinstance(record, dict):
                container.append(record)


@tornado.gen.coroutine
def repo_stargazers(repo, token):
    count = repo.stargazers_count
    stargazers_url = repo.stargazers_url

    page_size = 100

    headers = {'User-Agent': 'tornado'}
    if token:
        headers['Authorization'] = 'token {}'.format(token)
    headers['Accept'] = 'application/vnd.github.v3.star+json'

    url = stargazers_url + "?per_page={}&page={}".format(page_size, 1)

    # Be good citizens and allow a maximum of 40 concurrent requests.
    client = AsyncHTTPClient(max_clients=40)
    response = yield client.fetch(url, headers=headers)

    stargazers = []
    handle_response(stargazers, response)

    if 'Link' not in response.headers:
        return stargazers

    next_url, last_url = parse_link(response.headers['Link'])
    qs = parse_qs(urlparse(last_url).query)
    last_page = int(qs['page'][0])

    from functools import partial
    get_stargazers = partial(handle_response, stargazers)
    futures = []
    for page in range(2, last_page + 1):
        url = stargazers_url + "?per_page={}&page={}".format(page_size, page)
        f = client.fetch(url, headers=headers, callback=get_stargazers)
        f.url = url
        futures.append(f)

    error_count = 0

    while futures:
        waited = False
        for future in futures[:]:
            future = futures.pop(0)
            try:
                yield future
            except tornado.httpclient.HTTPError as err:
                # Try again, but give it a little while...
                url = future.url
                if error_count < 5:
                    f = client.fetch(future.url, headers=headers,
                                     callback=get_stargazers)
                    f.url = future.url
                    futures.append(f)
                else:
                    if not waited:
                        # Give Github some time to get over our request
                        # before we retry.
                        logging.exception("Sleeping attempt {} to rectify "
                                          "fetch error.".format(error_count))
                        yield tornado.gen.sleep(15)
                        error_count += 1
                        waited = True

                    logging.exception('A problem with {} occured after {} '
                                      'attempts. Skipping'
                                      ''.format(url, error_count))
                    logging.exception(traceback.format_exc())

    if len(stargazers) != count:
        logging.warning('The number of expected stargazers ({}) did not '
                        'match the number we recieved ({}).'
                        ''.format(count, len(stargazers)))
    return stargazers


if __name__ == '__main__':
    token = '...'
    token = None

    g = gh.Github(token)
    r = g.get_repo('d3/d3')
    # r = g.get_repo('dask/dask')
    r = g.get_repo('scitools/iris')

    from tornado.ioloop import IOLoop
    from functools import partial

    stargazers_fn = partial(repo_stargazers, r, token)
    stargazers = IOLoop.instance().run_sync(stargazers_fn)
    stargazers = IOLoop.instance().run_sync(stargazers_fn)

    print(len(stargazers))
    print(stargazers[50])
