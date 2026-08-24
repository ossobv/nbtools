from nbtools.synccmd.migr_if import MigrateInterfaceCommand
from nbtools.types import DevIface

from ..nbtest import get_test_api, nb_responses_load


SRC = 'switch2.dostno.systems'
TGT = 'switch3.dostno.systems'


@nb_responses_load('test_migr_if.0.json', caller=__file__)
def test_migr_iface_0():
    """
    Plan the move, check the listing, then carry it out

    Planned and executed in one pass, because the recorded fixture is
    a history: it answers each call once, in the order it was taped.
    Asserting on the plan first is what checks the listing; running it
    afterwards is what checks the request bodies.
    """
    migr_iface = MigrateInterfaceCommand(get_test_api())
    migr_iface.set_source_interface(DevIface(f'{SRC}:swp53s0'))
    migr_iface.set_target_interface(DevIface(f'{TGT}:swp51'))
    migr_iface.set_quiet()

    work_to_do = migr_iface.plan()

    assert [str(work) for work in work_to_do] == [
        f"{SRC}:swp53s0 cable #137 set a_terminations="
        f"[{{'object_type': 'dcim.interface', 'object_id': 473}}]",
        f'{TGT} set int swp51 description= mode=None tags=[] '
        f'type=25gbase-x-sfp28',

        f'{TGT} add int swp51.50 vrf DOSTNO_PUBLIC',
        f'{SRC}:swp53s0.50 del ip 1234:8080:666:2::/127',
        f'{TGT}:swp51.50 add ip 1234:8080:666:2::/127',
        f'{SRC} del int swp53s0.50',

        f'{TGT} add int swp51.55 vrf DOSTNO_SWIFT',
        f'{SRC}:swp53s0.55 del ip 10.123.5.44/31',
        f'{TGT}:swp51.55 add ip 10.123.5.44/31',
        f'{SRC}:swp53s0.55 del ip 10.123.5.48/31',
        f'{TGT}:swp51.55 add ip 10.123.5.48/31',
        f'{SRC} del int swp53s0.55',

        # No IPs on these, only the subinterface moves.
        f'{TGT} add int swp51.66 vrf DOSTNO_SABER',
        f'{SRC} del int swp53s0.66',
        f'{TGT} add int swp51.94 vrf DOSTNO_RIM',
        f'{SRC} del int swp53s0.94',
        f'{TGT} add int swp51.623 vrf DOSTNO_EDEAN',
        f'{SRC} del int swp53s0.623',

        f'{TGT} add int swp51.666 vrf DOSTNO',
        f'{SRC}:swp53s0.666 del ip 10.123.2.0/31',
        f'{TGT}:swp51.666 add ip 10.123.2.0/31',
        f'{SRC}:swp53s0.666 del ip 10.123.2.20/31',
        f'{TGT}:swp51.666 add ip 10.123.2.20/31',
        f'{SRC}:swp53s0.666 del ip 10.123.20.10/31',
        f'{TGT}:swp51.666 add ip 10.123.20.10/31',
        f'{SRC}:swp53s0.666 del ip 10.123.20.13/31',
        f'{TGT}:swp51.666 add ip 10.123.20.13/31',
        f'{SRC}:swp53s0.666 del ip 10.123.20.40/31',
        f'{TGT}:swp51.666 add ip 10.123.20.40/31',
        f'{SRC} del int swp53s0.666',
    ]

    for work in work_to_do:
        work.do(migr_iface.nbapi)
