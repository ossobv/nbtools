from nbtools.cmd.clone_if import CloneInterfaceCommand
from nbtools.command import ProcessMode

from ..nbtest import get_test_api, nb_responses_load


@nb_responses_load('test_clone_if.0.json', caller=__file__)
def test_clone_iface_0():
    source_dev_name = 'switch2.dostno.systems'
    source_iface_name = 'swp53s2'
    target_dev_name = 'switch3.dostno.systems'
    target_iface_name = 'swp56s2'

    clone_iface = CloneInterfaceCommand(get_test_api())
    clone_iface.set_source_interface(source_dev_name, source_iface_name)
    clone_iface.set_target_interface(target_dev_name, target_iface_name)
    clone_iface.set_quiet()
    clone_iface.run(ProcessMode.YES)
