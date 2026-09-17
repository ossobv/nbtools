"""
The argparse surface both tools share.
"""
from argparse import HelpFormatter
from textwrap import fill


class ParagraphHelpFormatter(HelpFormatter):
    """
    Wrap descriptions and epilogs a paragraph at a time

    argparse joins a description into one paragraph, which turns a
    few sentences into a wall and an example pipeline into mush. Here
    a blank line separates paragraphs, each wrapped on its own, and a
    paragraph whose every line is indented is printed as written:

        help = (
            'Set the type of interfaces.\\n'
            '\\n'
            'Example:\\n'
            '\\n'
            '  nblint --porcelain interface-types --limit=bridge |\\n'
            '    nbsync --batch set-interface-type bridge -')

    Argument help is left alone: it is short, and argparse indents it.
    """
    def _fill_text(self, text, width, indent):
        paragraphs = []
        for paragraph in text.strip('\n').split('\n\n'):
            lines = paragraph.split('\n')
            if all(line.startswith(' ') for line in lines):
                paragraphs.append('\n'.join(
                    indent + line for line in lines))
            else:
                paragraphs.append(fill(
                    ' '.join(paragraph.split()), width,
                    initial_indent=indent, subsequent_indent=indent,
                    break_on_hyphens=False, break_long_words=False))

        return '\n\n'.join(paragraphs)


def add_commands(parser, commands, help):
    "Add a subparser per command class"
    subparsers = parser.add_subparsers(
        dest='command', metavar='COMMAND', help=help)

    for cmdcls in commands:
        cmdcls.add_arguments(subparsers.add_parser(
            cmdcls.name, help=cmdcls.summary(), description=cmdcls.help,
            formatter_class=ParagraphHelpFormatter))

    return subparsers
