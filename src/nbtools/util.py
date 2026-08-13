from re import compile as re_compile


def natsort_key(name: str) -> tuple[str | int]:
    return tuple(
        (int(i) if i.isdigit() else i)
        for i in natsort_key.re.split(name)
        if i)
natsort_key.re = re_compile(r'(\d+)')  # noqa
