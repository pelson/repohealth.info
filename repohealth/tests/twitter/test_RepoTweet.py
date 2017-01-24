from repohealth.twitter import RepoTweet


def report_contents():
    return {'foobar': {'name': 'foobar',
                       'url': 'https://blahblah/foo',
                       'uuid': 'org/foobar'},
            'wibble': {'name': 'wibble',
                       'url': 'ftp://noteventherightname',
                       'uuid': 'something generic with a space'}}


def test_drop_content_name():
    tp = RepoTweet('my pattern {name}')

    content = report_contents()
    tp.drop_content('my pattern foobar', content)
    assert list(content.keys()) == ['wibble']

    content = report_contents()
    tp.drop_content('my pattern wibble', content)
    assert list(content.keys()) == ['foobar']


def test_drop_content_uuid():
    tp = RepoTweet('my pattern {uuid}')

    content = report_contents()
    tp.drop_content('my pattern org/foobar', content)
    assert list(content.keys()) == ['wibble']

    content = report_contents()
    tp.drop_content('my pattern something generic with a space', content)
    assert list(content.keys()) == ['foobar']


def test_drop_content_url():
    tp = RepoTweet('my pattern {url}')

    content = report_contents()
    tp.drop_content('my pattern ftp://noteventherightname', content)
    assert list(content.keys()) == ['foobar']


def test_drop_content_multiple():
    tp = RepoTweet('my pattern {name} {uuid}')

    content = report_contents()
    tp.drop_content('my pattern foobar something generic with a space', content)
    # Only the first should be dropped (foobar).
    assert list(content.keys()) == ['wibble']



if __name__ == '__main__':
    import pytest, sys
    pytest.main(sys.argv)
