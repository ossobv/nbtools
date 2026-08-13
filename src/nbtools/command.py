import sys

from enum import Enum


ProcessMode = Enum('ProcessMode', [('INTERACTIVE', -1), ('NO', 0), ('YES', 1)])


class Command:
    """
    Base for the subcommands of both nbsync and nblint.

    A subclass owns its own CLI surface: 'name' and 'help' describe the
    subparser, add_arguments() populates it and from_args() builds an
    instance from the parsed arguments. That keeps the argument
    definition next to the code that consumes it.

    What each tool then does with a command is the whole of the
    difference between them: see SyncCommand and LintCommand below.
    """
    name = None     # e.g. 'clone-interface'
    help = None     # subparser help text

    @classmethod
    def add_arguments(cls, parser):
        "Add this command's arguments to its (sub)parser, if it has any"

    @classmethod
    def from_args(cls, nbapi, args):
        "Build a configured command from parsed arguments"
        raise NotImplementedError

    def __init__(self, nbapi):
        self.nbapi = nbapi
        self._verbose = True

    def print(self, *args, **kwargs):
        "Print the payload: the thing the command was run to produce"
        print(*args, **kwargs)

    def verbose(self, *args, **kwargs):
        "Print decoration: banners and notices, never the payload"
        if self._verbose:
            print(*args, **kwargs)

    def print_banner(self):
        rule = '-' * len(self.name)
        self.verbose(rule)
        self.verbose(self.name)
        self.verbose(rule)


class SyncCommand(Command):
    """
    A subcommand of nbsync, which changes NetBox.

    plan() does the work of figuring out *what* to change and returns
    the FutureWork items; run() below owns the listing, the
    confirmation and the execution, so no subcommand repeats it.
    """
    def set_quiet(self):
        self._verbose = False

    def run(self, process_mode: ProcessMode):
        self.process_mode = process_mode

        work_to_do = self.plan()

        # Anything to do?
        if not work_to_do:
            self.verbose('Nothing to do')
            return

        # There is work.
        self.print_banner()
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


class LintCommand(Command):
    """
    A subcommand of nblint, which only reports.

    find() returns the findings and run() prints them. A lint command
    never changes anything -- that is what nbsync is for -- so there is
    no plan, no confirmation and no work list here.
    """
    @classmethod
    def from_args(cls, nbapi, args):
        return cls(nbapi)

    def __init__(self, nbapi):
        super().__init__(nbapi)
        self._porcelain = False

    def set_porcelain(self):
        "Print findings for a pipe rather than for a person"
        self._porcelain = True
        self._verbose = False

    def run(self) -> int:
        "Report the findings, return how many there were"
        findings = self.find()

        # Silence is the good case, and it keeps a run over several
        # commands readable.
        if not findings:
            return 0

        if self._porcelain:
            for finding in findings:
                self.print(finding.porcelain())
            return len(findings)

        self.print_banner()
        for finding in findings:
            self.print('-', finding)

        return len(findings)

    def find(self) -> list:
        """
        Return the findings

        Each finding renders one human-readable line through str(), and
        one machine-readable value through porcelain() -- the thing an
        nbsync command would take as an argument.
        """
        raise NotImplementedError
