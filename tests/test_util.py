from nbtools.util import natsort_key


def test_natsort_key():
    assert natsort_key('swp34.1234') == ('swp', 34, '.', 1234)
