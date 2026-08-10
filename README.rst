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
