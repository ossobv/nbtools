import sys

from enum import Enum

from .exceptions import InvalidInput, StateError


ProcessMode = Enum('ProcessMode', [('INTERACTIVE', -1), ('NO', 0), ('YES', 1)])

# The argument that means "this value is on stdin" rather than being a
# value itself. One spelling for every command, so that a reader who
# has seen it once knows it everywhere.
STDIN_ARG = '-'


def stdin_or(type_func):
    """
    Wrap an argparse type so that '-' comes through untouched

    argparse applies type= to every value, and '-' is not one:

        parser.add_argument('ip', type=stdin_or(IPv4AddrWithMask), ...)

    SyncCommand.set_input_rows() takes it from there.
    """
    def parse(text):
        if text == STDIN_ARG:
            return STDIN_ARG

        return type_func(text)

    parse.__name__ = '{}_or_stdin'.format(
        getattr(type_func, '__name__', 'value'))

    return parse


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

    A command that works through a list of input values -- an item per
    interface, per prefix, per line -- takes them through set_input()
    and implements plan_one() instead of plan(). run() then knows the
    items apart, which is what lets the values arrive on stdin and be
    acted on as they land: see set_input_rows() and _run_streaming().
    """
    def __init__(self, nbapi):
        super().__init__(nbapi)
        # The input rows, one per item to plan; None for a command
        # that plans no items but overrides plan() outright, and None
        # too when they are coming off stdin -- _run_streaming() then
        # reads them a line at a time and this never holds them all.
        self._input = None
        # How a line of stdin becomes a row: (row_type, slots,
        # dashes), set by set_input_rows() when an argument was '-'.
        self._row_slots = None
        # Set once this command's input is coming off stdin.
        self._stdin_is_input = False
        # Set to carry on past an item that fails; see run().
        self._keep_going = False

    def set_quiet(self):
        self._verbose = False

    def set_keep_going(self):
        """
        Report an item that fails and go on to the next one

        Only the streaming path has items to go on to, and only there
        is stopping the wrong answer: the input is a feed somebody
        left running, and an item NetBox cannot place -- a MAC it has
        never heard of -- is an ordinary event in it, not a reason to
        stop reading. The batch path plans everything before it
        writes, so a failure there still costs nothing and still
        stops.
        """
        self._keep_going = True

    def set_input(self, values):
        "The values to plan an item apiece from; see plan_one()"
        # Stored as handed over, not materialised: set_input_rows()
        # may have given us a stream that run() is to pull lazily.
        self._input = values

    def set_input_rows(self, row_type, slots):
        """
        Take the input as rows of values, a '-' argument off stdin

        slots is one (value, type_func) pair per argument the command
        takes, in the order they are typed, each value being what
        argparse parsed -- or STDIN_ARG for an argument given as '-'.
        With no '-' among them the input is the single row typed.

        With a '-' it is a row per line of stdin, and the line is
        split into as many fields as there are dashes. So a command
        taking two arguments is fed by two-field lines:

            nbsync --batch set-interface-ip-by-mac - - --vrf=MGMT
            11:22:33:44:55:66 10.20.30.4/24

        The fields fill the dashes left to right. Split from the
        right, so that the leftmost takes any extra whitespace and a
        value holding spaces still arrives whole -- device names are
        free-form and do hold them.

        Lazy in the stdin half: the rows stay an iterator and run()
        pulls them one at a time. That is what stdin is *for* here --
        work keeps going out while the input is still coming, so a
        long list from a pipe starts changing NetBox at once instead
        of after its last line. "| xargs -L1 COMMAND" is the other
        pipeline and needs none of this; it just waits.

        Blank lines are dropped. Reading and parsing are kept apart
        -- see _parse_row() -- so a line nobody can read costs one
        item rather than the rest of the input.

        Reading stdin also rules out the confirmation, which would
        have to read it too, so --batch becomes mandatory. That is
        enforced by confirm_or_die() rather than checked here, and so
        holds for a command that never considered it.
        """
        dashes = [
            index for index, (value, _) in enumerate(slots)
            if value == STDIN_ARG]

        if not dashes:
            self.set_input([row_type(*(value for value, _ in slots))])
            return

        self._stdin_is_input = True
        self._row_slots = (row_type, slots, dashes)

    @staticmethod
    def _stdin_lines():
        "The non-blank lines of stdin, stripped, as they arrive"
        for line in sys.stdin:
            line = line.strip()
            if line:
                yield line

    def _parse_row(self, line):
        """
        One row from one line of stdin, or raise InvalidInput

        A line that does not hold the fields the dashes asked for is
        refused, as is a field its type_func will not take -- the
        rejection argparse does for the values that arrive as
        arguments, in the place where there is no argparse to do it.

        Called from _run_streaming() inside the guard around the
        item, and not from the loop that reads the lines: an iterator
        that raises is finished, and the input has to outlive a bad
        line in it.
        """
        row_type, slots, dashes = self._row_slots

        fields = line.rsplit(None, len(dashes) - 1)
        if len(fields) != len(dashes):
            raise InvalidInput(
                f'{line!r}: wanted {len(dashes)} values, found '
                f'{len(fields)}')

        values = [value for value, _ in slots]
        for index, field in zip(dashes, fields):
            try:
                values[index] = slots[index][1](field)
            except ValueError as e:
                raise InvalidInput(f'{line!r}: {e}') from e

        return row_type(*values)

    def run(self, process_mode: ProcessMode) -> int:
        "See _run_streaming(); returns how many items failed"
        self.process_mode = process_mode

        if self._stdin_is_input:
            return self._run_streaming()

        work_to_do = self.plan()

        # Anything to do?
        if not work_to_do:
            self.verbose('Nothing to do')
            return 0

        # There is work.
        self.print_banner()
        for work in work_to_do:
            self.print('-', work)

        self.confirm_or_die()

        for work in work_to_do:
            work.do(self.nbapi)

        return 0

    def _run_streaming(self):
        """
        Plan, list and do each item as it arrives, not in one go

        Returns how many items failed, which is none unless
        set_keep_going() said to carry on past them.

        The trade-off the caller chose by piping: an error partway
        along leaves the earlier items done, where the batch path
        above plans everything first and so fails having changed
        nothing. Under --keep-going that goes for the failed item
        too: it is reported where it stopped, and what it had already
        written stays written.
        """
        # No listing to confirm yet -- and none is coming, since
        # streaming requires --batch. This is only the guard.
        self.confirm_or_die()
        self.prepare()

        banner_shown = False
        seen = failed = 0

        for line in self._stdin_lines():
            seen += 1
            try:
                # Parsed in here, not in the loop above: a line
                # nobody can read is this item's failure.
                for work in self.plan_one(self._parse_row(line)):
                    if not banner_shown:
                        self.print_banner()
                        banner_shown = True

                    # Flushed, because the far end of the pipe is a
                    # log somebody tails: a line an hour late is no
                    # report.
                    self.print('-', work, flush=True)
                    work.do(self.nbapi)
            except StateError as e:
                if not self._keep_going:
                    raise

                failed += 1
                print(f'{line}: {e.description}: {e}', file=sys.stderr)

        if failed:
            print(f'Failed on {failed} of {seen} items', file=sys.stderr)
        elif not banner_shown:
            self.verbose('Nothing to do')

        return failed

    def confirm_or_die(self):
        "Depending on the process_mode, continue, ask or die"
        if self.process_mode == ProcessMode.INTERACTIVE:
            # An answer read off stdin would just be an input line.
            if self._stdin_is_input:
                print(
                    'stdin holds the input, so the answer cannot come '
                    'from there: use --batch', file=sys.stderr)
                sys.exit(3)

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

    def prepare(self):
        """
        Read whatever every item is going to need, once

        Called before the first plan_one(), by both paths through
        run(). A lookup that does not depend on the item belongs
        here: on a stream the items keep coming, and one left in
        plan_one() is another API call for every line.
        """

    def plan_one(self, value) -> list:
        """
        Return the FutureWork items for one input value

        A command with input values implements this instead of
        plan(); run() calls it an item at a time when the values are
        streaming in off stdin, and plan() below joins them up when
        they are not.
        """
        raise NotImplementedError

    def plan(self) -> list:
        """
        Return the FutureWork items this command wants to perform

        A command either overrides this, or takes input values and
        implements plan_one().
        """
        if self._input is None:
            raise NotImplementedError(
                'a sync command implements plan(), or takes input '
                'values and implements plan_one()')

        self.prepare()

        return [
            work for value in self._input for work in self.plan_one(value)]


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
