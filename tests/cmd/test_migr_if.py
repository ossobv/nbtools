from nbtools.cmd.migr_if import MigrateInterfaceCommand
from nbtools.command import ProcessMode

from ..nbtest import get_test_api, nb_responses_load


@nb_responses_load('test_migr_if.0.json', caller=__file__)
def test_migr_iface_0():
    source_dev_name = 'switch2.dostno.systems'
    source_iface_name = 'swp53s0'
    target_dev_name = 'switch3.dostno.systems'
    target_iface_name = 'swp51'

    migr_iface = MigrateInterfaceCommand(get_test_api())
    migr_iface.set_source_interface(source_dev_name, source_iface_name)
    migr_iface.set_target_interface(target_dev_name, target_iface_name)
    migr_iface.set_quiet()
    migr_iface.run(ProcessMode.YES)
