from repohealth.twitter import RegexpFormatter


def test_custom_key_type():
    f = RegexpFormatter()
    r = f.format('{test} the {contents}', special={'contents': '0-9+'})
    assert r == '(.*?) the (0-9+)'


def test_return_fields():
    f = RegexpFormatter()
    f.format('{The} keys {from this} format {string} are '
             '{0} attain{able} {from this} object')
    expected = ['The', 'from this', 'string', '0', 'able', 'from this']
    assert f.fields == expected


if __name__ == '__main__':
    import pytest
    pytest.main([__file__])
