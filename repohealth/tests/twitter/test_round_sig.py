from repohealth.twitter import round_sig


def test_small():
    assert round_sig(0.0012345, 2) == 0.0012


def test_medium():
    assert round_sig(12.345, 3) == 12.3


def test_large():
    assert round_sig(12345, 4) == 12340



if __name__ == '__main__':
    import pytest, sys
    pytest.main(sys.argv)
