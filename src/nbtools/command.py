import sys

from enum import Enum


ProcessMode = Enum('ProcessMode', [('INTERACTIVE', -1), ('NO', 0), ('YES', 1)])


class Command:
    def __init__(self, nbapi):
        self.nbapi = nbapi

    def run(self, process_mode: ProcessMode):
        self.process_mode = process_mode
        self._process()

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

    def _process(self):
        raise NotImplementedError
