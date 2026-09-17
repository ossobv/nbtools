nbtools
=======

Collection of ``nblint`` and ``nbsync`` tools to operate on *NetBox* —
the networking source of truth.

``nblint`` has these *linting* commands:

=======================  ===================================================================================
Check                    Description
=======================  ===================================================================================
unassigned-ips           Find IP addresses that sit on no interface.
empty-prefixes           Find prefixes that hold nothing: no address and no smaller prefix inside them.
duplicate-prefixes       Find prefixes that exist in more than one VRF.
duplicate-ips            Find IP addresses that exist in more than one VRF.
unparented-ips           Find IP addresses that no prefix of a sensible size covers.
duplicate-macs           Find MAC addresses that exist more than once.
device-bmcs              Find machines whose management controller cannot be reached.
subinterface-parents     Find numeric subinterfaces whose parent is not the interface their name names.
subinterface-labels      Find numeric subinterfaces whose label does not spell out their VRF.
interface-types          Find interfaces whose name says what type they are, but whose type does not.
unpaired-interface-tags  Find interfaces carrying a link tag that the far end of their cable does not.
interface-vlans          Find tagged interfaces whose 802.1Q mode and VLANs do not agree.
unattached-cables        Find physical cables that do not have both ends attached.
unattached-interfaces    Find interfaces that no cable is plugged into; the other half of unattached-cables.
discovered-items         List the devices and virtual machines that auto-discovery filed under "Discovery".
tenant-names             Find tenants and tenant-groups whose name is not slug-style.
=======================  ===================================================================================

*If you run nblint without a command, it will run all of them.*

``nbsync`` has these *update* commands:

=======================  =========================================================
Command                  Description
=======================  =========================================================
clone-interface          Clone interface with subinterfaces from source to target.
migrate-gateway          Migrate a VM by moving the connected gateway IPs.
migrate-interface        Migrate properties of an interface from source to target.
set-interface-ip         Set IP on an interface.
set-interface-ip-by-mac  Set IP on the interface holding a MAC address.
set-interface-type       Set the type of interfaces, e.g. to bridge.
unset-interface-mac      Remove MAC addresses from an interface.
zap-interface            Zap (clean/wipe) properties from an interface.
swap-cables              Swap two connected cables.
=======================  =========================================================

*Running an nbsync WITHOUT --batch is safe: it does nothing until you
accept the change.*

Exit codes: 0 clean, 1 nblint finding, 2 startup/usage error, 3 NetBox/state error.


--------
Examples
--------

For example, you can find empty prefixes in NetBox using ``nblint``:

.. code-block:: console

    $ nblint empty-prefixes
    --------------
    empty-prefixes
    --------------
    - 10.7.7.0/24 #133 status=active vrf=DOSTNO_DAN
    - 10.103.0.0/24 #1 status=active vrf=MGMT

Or cables that are only partially attached:

.. code-block:: console

    $ nblint unattached-cables
    -----------------
    unattached-cables
    -----------------
    - cable #227 status=connected a=<none> b=switch2:swp54s2

And you use one of the ``nbsync`` commands to perform actions that
require lots of manual clicking in the *NetBox* web interface.

For instance, if you've noticed you got two cables mixed up:

.. code-block:: console

    $ nbsync -C dostno swap-cables pve3:enmlx0 pve3:enmlx1
    -----------
    swap-cables
    -----------
    - pve3:enmlx0 cable #187 set b_terminations=[]
    - pve3:enmlx1 cable #182 set b_terminations=[{'object_type': 'dcim.interface', 'object_id': 177}]
    - pve3:enmlx0 cable #187 set b_terminations=[{'object_type': 'dcim.interface', 'object_id': 178}]
    Type 'yes' to continue: yes


-------
Install
-------

.. code-block:: console

    $ pipx install git+https://github.com/ossobv/nbtools.git@main

    $ cat >~/.config/nbtools.ini <<EOF
    [mynetbox]
    api_url = https://netbox.example.com/api
    api_token = 17801aeb9ce93006bea477e41e70ad5d53219919
    EOF

    $ source <(nblint completion bash)

    $ source <(nbsync completion bash)

    $ nblint --help
    ...


-----------------
nblint vs nbsync?
-----------------

The nbtools suite contains two commands: nblint and nbsync. *nblint*
should be able to work with readonly tokens and is focused on *finding*
things. *nbsync* needs write tokens, and is used for deliberate changes.

The two meet through the ``--porcelain`` argument and ``xargs`` (or stdin).
*nblint* arguments can be passed to *nbsync* via the command line.


------------------
Arguments or stdin
------------------

Assume there is an application that dumps MAC and IP combinations, that
can be tailed/followed:

.. code-block:: console

    $ feed-mac-and-ips
    11:22:33:44:55:66 10.20.30.4/24
    77:88:99:aa:bb:cc 10.20.30.17/24
    ...

You could use this, as individual calls:

.. code-block:: console

    $ feed-mac-and-ips | while read mac ip; do
        nbsync --batch set-interface-ip-by-mac $mac $ip
      done

Or, you could pass them through stdin:

.. code-block:: console

    $ feed-mac-and-ips |
        nbsync --batch --keep-going set-interface-ip-by-mac - -

That way, we only need to start nbsync once. The drawback of
``--keep-going`` is that you don't get a clean exit code when there are
issues with the input or NetBox, but sometimes that isn't a problem.


-----------
Development
-----------

See the ``Makefile`` for basic dev setup.


------------
DHCP example
------------

**Automatic updates from ISC dhcpd to NetBox:**

.. code-block:: inifile

    [Unit]
    Description=Write dhcp ACKs to netbox
    Requires=isc-dhcp-server.service
    After=isc-dhcp-server.service
    ConditionPathExists=/etc/default/isc-dhcp-server-to-netbox
    StartLimitIntervalSec=900
    StartLimitBurst=90

    [Service]
    EnvironmentFile=/etc/default/isc-dhcp-server-to-netbox
    ExecStartPre=/bin/test -n "${DHCP_RANGE}"
    ExecStartPre=/bin/test -n "${DHCP_VRF}"
    ExecStart=/bin/sh -c 'journalctl -f -u isc-dhcp-server.service -n 0 -o cat --grep ^DHCPACK | ipgrep --line-buffered "${DHCP_RANGE}" | sed --unbuffered -Ee "s@^DHCPACK on ([^ ]*) to ([^ ]*) .*@\\2 \\1/24@" | nbsync --batch set-interface-ip-by-mac - - --vrf="${DHCP_VRF}" --status=dhcp --single --force'
    SyslogIdentifier=isc-dhcp-server-to-netbox
    Restart=on-failure
    RestartSec=10

    [Install]
    WantedBy=multi-user.target
