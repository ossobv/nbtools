import sys

from enum import Enum


ProcessMode = Enum('ProcessMode', [('INTERACTIVE', -1), ('NO', 0), ('YES', 1)])


class SyncCommand:
    """
    Base for all nbsync subcommands.

    A subclass owns its own CLI surface: 'name' and 'help' describe the
    subparser, add_arguments() populates it and from_args() builds an
    instance from the parsed arguments. That keeps the argument
    definition next to the code that consumes it.

    plan() does the work of figuring out *what* to change and returns
    the FutureWork items; run() below owns the listing, the
    confirmation and the execution, so no subcommand repeats it.
    """
    name = None     # e.g. 'clone-interface'
    help = None     # subparser help text

    @classmethod
    def add_arguments(cls, parser):
        "Add this command's arguments to its (sub)parser"
        raise NotImplementedError

    @classmethod
    def from_args(cls, nbapi, args):
        "Build a configured command from parsed arguments"
        raise NotImplementedError

    def __init__(self, nbapi):
        self.nbapi = nbapi
        self._verbose = True

    def set_quiet(self):
        self._verbose = False

    def verbose(self, *args, **kwargs):
        if self._verbose:
            print(*args, **kwargs)

    def print(self, *args, **kwargs):
        print(*args, **kwargs)

    def run(self, process_mode: ProcessMode):
        self.process_mode = process_mode

        work_to_do = self.plan()

        # Anything to do?
        if not work_to_do:
            self.verbose('Nothing to do')
            return

        # There is work.
        rule = '-' * len(self.name)
        self.verbose(rule)
        self.verbose(self.name)
        self.verbose(rule)
        for work in work_to_do:
            self.print('-', work)

        self.confirm_or_die()

        for work in work_to_do:
            work.do(self.nbapi)

    def confirm_or_die(self):
        "Depending on the process_mode, continue, ask or die"
        if self.process_mode == ProcessMode.INTERACTIVE:
            while True:
                print("Type 'yes' to continue: ", end='', file=sys.stderr)
                try:
                    yesno = input().strip()
                except KeyboardInterrupt:
                    print('', file=sys.stderr)
                    print('Aborted by user request', file=sys.stderr)
                    sys.exit(1)
                if yesno.strip() == 'yes':
                    break

        elif self.process_mode == ProcessMode.YES:
            pass

        elif self.process_mode == ProcessMode.NO:
            print('Aborted', file=sys.stderr)
            sys.exit(3)

        else:
            raise NotImplementedError(self.process_mode)

    def plan(self) -> list:
        "Return the FutureWork items this command wants to perform"
        raise NotImplementedError
