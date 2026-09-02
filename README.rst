nbtools
=======

Collection of ``nblint`` and ``nbsync`` tools to operate on *NetBox* --
the networking source of truth.

This project is very alpha.


-----------------
Setup and example
-----------------

.. code-block:: console

    $ make setup

    $ . .venv/bin/activate

    $ nbsync
    usage: nbsync [-h] [-c INIFILE] [--debug] [--record RECORD] {...}

    $ nbsync swap-cables switch1:swp4 switch2:swp4
    (should unplug the cable from switch1 swp4 and plug it into switch2 swp4)


----------------
nblint vs nbsync
----------------

The nbtools suite contains two commands: nblint and nbsync. *nblint*
should be able to work with readonly tokens and is focused on *finding*
things. *nbsync* needs write tokens, and is used for deliberate changes.

The two meet through the ``--porcelain`` argument and ``xargs`` (or stdin).
*nblint* arguments can be passed to *nbsync* via the command line.

.. code-block:: console

    $ nblint --porcelain empty-prefixes
    10.1.3.0/24@vrf-red
    10.1.4.0/24@

    $ nblint --porcelain empty-prefixes | xargs nbsync delete-prefix
    -------------
    delete-prefix
    -------------
    - vrf-red del prefix 10.1.3.0/24
    - global del prefix 10.1.4.0/24
    Type 'yes' to continue:

Each value is one token, so ``xargs`` hands one argument per finding.
Where a prefix alone would be ambiguous -- NetBox allows the same one
in several VRFs -- the value carries the VRF after an ``@``, empty for
the global table.

*nbsync* re-checks before it writes: ``delete-prefix`` refuses a prefix
that has gained contents since the listing was made.

Where ``xargs`` waits for the whole list before it starts, a ``-``
argument streams it -- each line acted on as it arrives:

.. code-block:: console

    $ nblint --porcelain empty-prefixes | nbsync --batch delete-prefix -


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


--------
Examples
--------

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
