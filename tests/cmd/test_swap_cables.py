from nbtools.cmd.swap_cables import SwapCableCommand
from nbtools.command import ProcessMode

from ..nbtest import get_test_api, nb_responses_load


@nb_responses_load('test_swap_cables_0.json', caller=__file__)
def test_swap_cables_0():
    source_dev_name = 'switch3.dostno.systems'
    source_iface_name = 'swp52'
    target_dev_name = 'switch3.dostno.systems'
    target_iface_name = 'swp53'

    swap_cables = SwapCableCommand(get_test_api())
    swap_cables.set_a_interface(source_dev_name, source_iface_name)
    swap_cables.set_b_interface(target_dev_name, target_iface_name)
    swap_cables.run(ProcessMode.YES)
