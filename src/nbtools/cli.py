"""
The argparse surface both tools share: help layout and tab completion.
"""
from argparse import HelpFormatter, _SubParsersAction
from textwrap import fill


# The subcommand that prints a completion script. It is not a lint or a
# sync command -- it reads no config and talks to no NetBox -- so it
# sits beside COMMANDS rather than in it.
COMPLETION = 'completion'
COMPLETION_SHELLS = ('bash',)


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
    "Add a subparser per command class, and the completion command"
    subparsers = parser.add_subparsers(
        dest='command', metavar='COMMAND', help=help)

    for cmdcls in commands:
        cmdcls.add_arguments(subparsers.add_parser(
            cmdcls.name, help=cmdcls.summary(), description=cmdcls.help,
            formatter_class=ParagraphHelpFormatter))

    prog = parser.prog
    completion = subparsers.add_parser(
        COMPLETION, help='Print the tab completion script for a shell.',
        description=(
            f'Print the tab completion script for a shell. It completes '
            f'the COMMAND names of {prog}; options are not completed.\n'
            f'\n'
            f'To load it into the running shell:\n'
            f'\n'
            f'  source <({prog} {COMPLETION} bash)\n'
            f'\n'
            f'Or add that line to ~/.bashrc.'),
        formatter_class=ParagraphHelpFormatter)
    completion.add_argument('shell', choices=COMPLETION_SHELLS)

    return subparsers


def completion_script(parser, shell):
    "The completion script for this parser in that shell"
    assert shell in COMPLETION_SHELLS, shell
    return bash_completion(parser)


def bash_completion(parser):
    """
    A bash script completing the COMMAND names of this parser

    The global options go before the COMMAND, so the script skips
    over them -- and over the value of those that take one, which is
    why it needs to know which ones do. Once a COMMAND is on the line
    there is nothing left for it to offer, bar the shell after
    'completion', and bash falls back to completing file names.

    Bash splits '--config=x.ini' into '--config', '=' and 'x.ini'
    (COMP_WORDBREAKS holds '='); the '=' is skipped with the option.
    """
    commands = []
    valued = []
    for action in parser._actions:
        if isinstance(action, _SubParsersAction):
            commands.extend(action.choices)
        elif action.option_strings and action.nargs != 0:
            valued.extend(action.option_strings)

    func = '_' + parser.prog.replace('-', '_')

    return f'''\
# bash completion for {parser.prog}; load with:
#   source <({parser.prog} {COMPLETION} bash)
{func}() {{
    local i
    for ((i = 1; i < COMP_CWORD; i++)); do
        case ${{COMP_WORDS[i]}} in
        {'|'.join(valued)})
            ((i++))
            [[ ${{COMP_WORDS[i]}} == = ]] && ((i++))
            ;;
        -*)
            ;;
        {COMPLETION})
            ((i == COMP_CWORD - 1)) || return 0
            COMPREPLY=($(compgen -W '{' '.join(COMPLETION_SHELLS)}' \\
                -- "${{COMP_WORDS[COMP_CWORD]}}"))
            return 0
            ;;
        *)
            return 0
            ;;
        esac
    done

    # Past it: the word being completed is the value of an option.
    ((i == COMP_CWORD)) || return 0

    case ${{COMP_WORDS[COMP_CWORD]}} in
    -*)
        return 0
        ;;
    esac

    COMPREPLY=($(compgen -W '{' '.join(commands)}' \\
        -- "${{COMP_WORDS[COMP_CWORD]}}"))
}}
complete -o default -F {func} {parser.prog}
'''
