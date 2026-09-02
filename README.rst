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

The two meet through the ``--porcelain`` argument and ``xargs`` command:
*nblint* arguments can be passed to *nbsync* via the command line.


---------------
Values on stdin
---------------

Where ``xargs`` waits for the whole list before it starts, a ``-``
argument reads the values from stdin and acts on each line as it
arrives. One ``-`` for every argument that comes from there, and a
line holds that many values:

.. code-block:: console

    $ journalctl -fu isc-dhcp-server -n0 -ocat --grep ^DHCPACK |
        ipgrep --line-buffered 10.20.30.0/24 |
        awk '{print $5, $3 "/24"}' |
        nbsync --batch --keep-going set-interface-ip-by-mac - - \
            --vrf=MGMT --status=dhcp --single --force

Every lease is recorded as it is handed out. The options are the same
for each one; only the MAC and the IP arrive on the line.

Reading stdin takes it away from the confirmation, which would have to
read it too, so ``--batch`` is required. And an item that fails -- a
MAC that NetBox has never heard of, say -- would otherwise stop the
feed, which is what ``--keep-going`` is for.
