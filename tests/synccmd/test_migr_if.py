from nbtools.synccmd.migr_if import MigrateInterfaceCommand
from nbtools.command import ProcessMode
from nbtools.types import DevIface

from ..nbtest import get_test_api, nb_responses_load


@nb_responses_load('test_migr_if.0.json', caller=__file__)
def test_migr_iface_0():
    source = DevIface('switch2.dostno.systems:swp53s0')
    target = DevIface('switch3.dostno.systems:swp51')

    migr_iface = MigrateInterfaceCommand(get_test_api())
    migr_iface.set_source_interface(source)
    migr_iface.set_target_interface(target)
    migr_iface.set_quiet()
    migr_iface.run(ProcessMode.YES)
