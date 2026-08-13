from re import compile as re_compile


def natsort_key(name: str) -> tuple[str | int]:
    return tuple(
        (int(i) if i.isdigit() else i)
        for i in natsort_key.re.split(name)
        if i)
natsort_key.re = re_compile(r'(\d+)')  # noqa


def quoted_name(name) -> str:
    """
    Single-quote a name if it needs it, doubling quotes like SQL does

    NetBox device names are free-form, so this is a real one:

        FREE (was-planned: node3.zl.backend1.prod.juno.cloud)

    Unquoted, the "device:interface rest of the line" output cannot be
    read: the device name runs into the rest of the sentence. So a name
    holding a space gets quoted, and an embedded quote is doubled:

        Bob's spare (old)  ->  'Bob''s spare (old)'
    """
    name = str(name)
    if ' ' in name or "'" in name:
        return "'{}'".format(name.replace("'", "''"))

    return name
