from nbtools.synccmd.clone_if import CloneInterfaceCommand
from nbtools.command import ProcessMode
from nbtools.types import DevIface

from ..nbtest import get_test_api, nb_responses_load


@nb_responses_load('test_clone_if.0.json', caller=__file__)
def test_clone_iface_0():
    source = DevIface('switch2.dostno.systems:swp53s2')
    target = DevIface('switch3.dostno.systems:swp56s2')

    clone_iface = CloneInterfaceCommand(get_test_api())
    clone_iface.set_source_interface(source)
    clone_iface.set_target_interface(target)
    clone_iface.set_quiet()
    clone_iface.run(ProcessMode.YES)
