from nbtools.synccmd.swap_cables import SwapCableCommand
from nbtools.command import ProcessMode
from nbtools.types import DevIface

from ..nbtest import get_test_api, nb_responses_load


@nb_responses_load('test_swap_cables.0.json', caller=__file__)
def test_swap_cables_0():
    source = DevIface('switch3.dostno.systems:swp52')
    target = DevIface('switch3.dostno.systems:swp53')

    swap_cables = SwapCableCommand(get_test_api())
    swap_cables.set_a_interface(source)
    swap_cables.set_b_interface(target)
    swap_cables.set_quiet()
    swap_cables.run(ProcessMode.YES)
