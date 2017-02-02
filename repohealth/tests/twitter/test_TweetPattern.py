from repohealth.twitter import TweetPattern, LotsOfForks
import repohealth.twitter


def test_all_patterns():
    assert len(list(TweetPattern.all_patterns())) > 0


def test_all_subclasses():
    # Subsubclasses should be in there!
    assert repohealth.twitter.LotsOfForks in TweetPattern.all_subclasses()


def test_repr():
    tp = TweetPattern('my pattern .*')
    assert repr(tp) == '<TweetPattern TweetPattern "my pattern .*">'


def test_re_match():
    tp = TweetPattern('my pattern .*')

    # Check there is no re cache.
    assert not hasattr(tp, 'compiled_regexp')

    r = tp.re_match('my tweet pattern shouldnt work')
    assert r is None

    # Check that the cache has worked.
    assert hasattr(tp, 'compiled_regexp')

    r = tp.re_match('my pattern actually works')
    assert r is None


def realistic_content():
    return {'test': {'name': 'test',
                     'uuid': 'unique/test',
                     'url': 'https://foobar.com/test#thing',
                     'github': {
                         'repo': {'name': 'test',
                                  'stargazers_count': 1234,
                                  'forks_count': 4321}}}}


def test_round_robin_matching():
    global_context = {'repohealth_url': 'repohealth.info'}
    content = realistic_content()
    for pattern in TweetPattern.all_patterns_all_subclasses():

        for tweeter, context in pattern.context(content):
            message = tweeter.format(context, global_context)
            assert tweeter.re_match(message)


def test_LotsOfForks():
    global_context = {'repohealth_url': 'repohealth.info'}
    content = realistic_content()
    pattern = LotsOfForks(LotsOfForks.patterns[0])

    for forks, expected in [[9, 'test now has nearly 10 forks! See the full report at https://foobar.com/test#thing'],
                                 [150, 'test now has 150 forks! See the full report at https://foobar.com/test#thing'],
                                 [1601, 'test now has over 1600 forks! See the full report at https://foobar.com/test#thing']]:
        content['test']['github']['repo']['forks_count'] = forks
        for tweeter, context in pattern.context(content):
            message = tweeter.format(context, global_context)
            assert message == expected
            assert tweeter.re_match(message)



if __name__ == '__main__':
    import pytest
    pytest.main([__file__])
