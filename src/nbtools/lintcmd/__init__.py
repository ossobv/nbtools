# The subcommands nblint offers, in --help order. Registration is kept
# explicit on purpose: no import scanning, so the list stays greppable.
COMMANDS = ()

COMMANDS_BY_NAME = {cmdcls.name: cmdcls for cmdcls in COMMANDS}
