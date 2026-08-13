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
