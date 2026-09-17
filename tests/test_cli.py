"""
The shared CLI surface.
"""
from nbtools.cli import ParagraphHelpFormatter


def fill(text, width=40, indent=''):
    return ParagraphHelpFormatter('prog')._fill_text(text, width, indent)


def test_paragraphs_are_wrapped_apart():
    text = (
        'One two three four five six seven eight nine ten.\n'
        '\n'
        'Eleven.')

    assert fill(text, width=20) == (
        'One two three four\n'
        'five six seven eight\n'
        'nine ten.\n'
        '\n'
        'Eleven.')


def test_an_indented_paragraph_is_kept_as_written():
    text = (
        'Example:\n'
        '\n'
        '  nblint --porcelain interface-types --limit=bridge |\n'
        '    nbsync --batch set-interface-type bridge -\n'
        '\n'
        'Done.')

    assert fill(text, width=20, indent='  ') == (
        '  Example:\n'
        '\n'
        '    nblint --porcelain interface-types --limit=bridge |\n'
        '      nbsync --batch set-interface-type bridge -\n'
        '\n'
        '  Done.')


def test_a_hyphenated_word_is_not_split():
    assert fill('aaaa unattached-cables', width=20) == (
        'aaaa\nunattached-cables')
