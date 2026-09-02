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


def one_value(value):
    """
    The row type for set_input_values(): the value, as it came

    A row of one field is that field, so a command taking a list of
    values sees the value itself in plan_one() rather than a tuple
    holding it.
    """
    return value


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

    A command that works through a list of input values takes them
    through set_input() -- or set_input_rows() / set_input_values(),
    which also let them arrive on stdin -- and implements plan_one()
    instead of plan().
    """
    def __init__(self, nbapi):
        super().__init__(nbapi)

        # The input rows, one per item to plan; None for a command
        # that plans no items but overrides plan() outright, and None
        # too when they are coming off stdin -- _run_streaming() then
        # reads them a line at a time and this never holds them all.
        self._input = None

        # The values typed beside a '-', which are items of their own
        # and go first; only set_input_values() has any, a fixed
        # row's other slots being constants rather than items.
        self._head = ()

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
        """
        The values to plan an item apiece from; see plan_one()
        """
        # Stored as handed over, not materialised: set_input_rows()
        # may have given us a stream that run() is to pull lazily.
        self._input = values

    def set_input_rows(self, row_type, slots):
        """
        Take the input as rows of values, a '-' argument off stdin

        Example:

            TargetIp = namedtuple('TargetIp', 'target ip')

            SyncCommand.set_input_rows(TargetIp, [
                (args.target, MacAddr),
                (args.ip, IPv4AddrWithMask)])

        slots is one (value, type_func) pair per argument the command
        takes, in the order they are typed, each value being what
        argparse parsed -- or STDIN_ARG for an argument given as '-'.
        With no '-' among them the input is the single row typed.

        With a '-' it is a row per line of stdin, and the line is
        split into as many fields as there are dashes. So a command
        taking two arguments is fed by two-field lines:

            $ nbsync --batch set-interface-ip-by-mac - - --vrf=MGMT
            11:22:33:44:55:66 10.20.30.4/24
            ...

        The fields fill the dashes left to right.
        """
        dashes = [
            index for index, (value, _) in enumerate(slots)
            if value == STDIN_ARG]

        if not dashes:
            self.set_input([row_type(*(value for value, _ in slots))])
            return

        self._stdin_is_input = True
        self._row_slots = (row_type, slots, dashes)

    def set_input_values(self, values, type_func):
        """
        Take the input as a list of values, a '-' among them off stdin

        The other input shape next to set_input_rows()' fixed row: a
        command taking any number of values of one kind,

            parser.add_argument(
                'prefix', type=stdin_or(VrfPrefix), nargs='+', ...)

        and fed one value -- the whole line, spaces and all -- per
        line:

            nblint --porcelain empty-prefixes \\
                | nbsync --batch delete-prefix -

        Where a row's non-dash slots are constants repeated on every
        line, a list's are items in their own right: they are planned
        and done first, in the order they were typed, and the stream
        follows. A second '-' stands for nothing, the first one having
        taken stdin.
        """
        typed = [value for value in values if value != STDIN_ARG]

        if len(typed) == len(values):
            self.set_input(typed)
            return

        self._stdin_is_input = True
        self._head = typed
        self._row_slots = (one_value, [(STDIN_ARG, type_func)], [0])

    @staticmethod
    def _stdin_lines():
        """
        The lines of stdin, stripped, as they arrive

        A blank line is no item, and is skipped rather than counted as
        one that could not be read: a generator feeding this may well
        space its output out, and that is not a fault to report.
        """
        for line in sys.stdin:
            line = line.strip()
            if line:
                yield line

    def _parse_row(self, line):
        """
        One row from one line of stdin, or raise InvalidInput

        Converts the input lines per the slots set in set_input_rows().

        A line that does not hold the fields the dashes asked for is
        refused with InvalidInput.
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

        seen = failed = 0

        # Whatever was typed beside the '-'; see set_input_values().
        for value in self._head:
            seen += 1
            failed += self._do_item(str(value), value)

        # Stream over stdin, one line at a time.
        for line in self._stdin_lines():
            seen += 1
            failed += self._do_item(line)

        if failed:
            print(f'Failed on {failed} of {seen} items', file=sys.stderr)

        return failed

    def _do_item(self, label, value=None):
        """
        Plan one item and do it; return 1 if it failed, 0 if not

        A line is parsed in here rather than by the loop that reads
        it: an iterator that raises is finished, so a line that
        cannot be read has to cost the one item and not the rest of
        the stream. Which is also why this catches where it does --
        see set_keep_going(). label is what to call the item if it
        fails, the line itself for one that came off stdin.
        """
        try:
            if value is None:
                value = self._parse_row(label)

            for work in self.plan_one(value):
                # Make sure we flush, so log readers pick this up
                # immediately.
                self.print('-', work, flush=True)
                work.do(self.nbapi)
        except StateError as e:
            if not self._keep_going:
                raise

            print(f'{label}: {e.description}: {e}', file=sys.stderr)
            return 1

        return 0

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
        pass

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
