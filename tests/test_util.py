from nbtools.util import natsort_key, quoted_name


# A real NetBox device name, shortened.
SPACED_DEV = 'FREE (was-planned: node3.example.com)'


def test_natsort_key():
    assert natsort_key('swp34.1234') == ('swp', 34, '.', 1234)


def test_quoted_name_leaves_plain_name_alone():
    assert quoted_name('node3.example.com') == 'node3.example.com'


def test_quoted_name_quotes_name_with_space():
    assert quoted_name(SPACED_DEV) == f"'{SPACED_DEV}'"


def test_quoted_name_doubles_embedded_quote():
    assert quoted_name("Bob's spare (old)") == "'Bob''s spare (old)'"


def test_quoted_name_quotes_on_a_quote_alone():
    "Else a leading quote reads as the start of a quoted name"
    assert quoted_name("'weird") == "'''weird'"


def test_quoted_name_leaves_backslash_alone():
    "Only the quote is special; a backslash needs no second rule"
    assert quoted_name('c:\\some path') == "'c:\\some path'"
