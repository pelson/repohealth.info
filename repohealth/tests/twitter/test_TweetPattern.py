from repohealth.twitter import TweetPattern
import repohealth.twitter


def test_all_patterns():
    assert isinstance(TweetPattern.all_patterns(), list)
    assert len(TweetPattern.all_patterns()) > 0


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
    content = realistic_content()
    for pattern in TweetPattern.all_patterns():

        for tweeter, context in pattern.context(content):
            message = tweeter.format(context)
            assert tweeter.re_match(message)



if __name__ == '__main__':
    import pytest
    pytest.main([__file__])
