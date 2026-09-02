from collections import namedtuple
from logging import getLogger

from .util import quoted_name

log = getLogger(__name__)


def find_elem(items, matchfunc):
    "Return the matching item or None, asserts that there is 0 or 1 result"
    candidates = [item for item in items if matchfunc(item)]
    assert len(candidates) in (0, 1), candidates
    return (candidates[0] if candidates else None)


class named_anon(namedtuple('named_anon', 'name parent')):
    def __str__(self):
        return quoted_name(self.name)


class named_id(namedtuple('named_id', 'name id parent')):
    def __str__(self):
        # return f'{self.name}(#{self.id})'
        return quoted_name(self.name)


class named_lambda(namedtuple('named_lambda', 'placeholder_name func parent')):
    def __call__(self, *args, **kwargs):
        return self.func(*args, **kwargs)

    def __str__(self):
        return self.placeholder_name


class FutureWork:
    def do(self, nbapi):
        self._resolve(nbapi)
        self._do(nbapi)

    def _resolve(self, nbapi):
        for key, value in list(self.values.items()):
            if callable(value):
                self.values[key] = value(nbapi)

            # Translate all named items to ids.
            if isinstance(value, named_id):
                self.values[key] = value.id

    def _do(self, nbapi):
        raise NotImplementedError


class DummyWork(FutureWork):
    def __init__(self, name_id: named_id):
        assert isinstance(name_id, named_id), name_id
        self.name_id = name_id
        self.values = {}

    def _do(self, nbapi):
        pass


class FutureCreate(FutureWork):
    def __init__(self, name_id: named_anon, values: dict):
        assert isinstance(name_id, named_anon), name_id
        self.name_id = name_id
        self.values = values


class FutureDelete(FutureWork):
    def __init__(self, name_id: named_id):
        assert isinstance(name_id, named_id), name_id
        self.name_id = name_id
        self.values = {}


class FutureModify(FutureWork):
    def __init__(self, name_id: named_id, values: dict):
        assert isinstance(name_id, named_id), name_id
        self.name_id = name_id
        self.values = values


class ModifyCable(FutureModify):
    def __str__(self):
        kvs = ' '.join(f'{k}={v}' for k, v in self.values.items())
        return (
            f'{self.name_id.parent.parent}:{self.name_id.parent} '
            f'cable {self.name_id} set {kvs}')

    def _do(self, nbapi):
        updates = [self.values.copy()]
        updates[0]['id'] = self.name_id.id
        log.debug('nbapi.dcim.cables.update %r', updates)
        nbapi.dcim.cables.update(updates)


# class SwapCables(FutureWork):
#     """We need to combine two modifies here, because it's an atomic swap."""
#     def __str__(self):
#         return '\n'.join(str(future) for future in self.futures)
#
#     def __init__(self, name, id1, values1, id2, values2):
#         super().__init__()
#         # Alas, we cannot do atomic swap:
#         # ['Duplicate termination found for dcim.interface 7366: cable 1784']
#         # https://github.com/netbox-community/netbox/issues/4890
#         self.futures = [
#             ModifyCable(name, id1, {list(values1.keys())[0]: []}),
#             ModifyCable(name, id2, values2),
#             ModifyCable(name, id1, values1),
#         ]
#
#     def _resolve(self, nbapi):
#         for future in self.futures:
#             future._resolve(nbapi)
#
#     def _do(self, nbapi):
#         updates = []
#         for future in self.futures:
#             updates.append(future.values.copy())
#             updates[-1]['id'] = future.id
#
#         # Alas, no atomic stuff here. Do the updates one at at time.
#         for update in updates:
#             log.debug('nbapi.dcim.cables.update %r', [update])
#             nbapi.dcim.cables.update([update])


class CreateInterface(FutureCreate):
    def __str__(self):
        v = self.values
        return (
            f'{self.name_id.parent} '
            f'add int {self.name_id} vrf {v["vrf"]}')

    def _do(self, nbapi):
        log.debug('nbapi.dcim.interfaces.create %r', self.values)
        nbapi.dcim.interfaces.create(self.values)


class DeleteInterface(FutureDelete):
    def __str__(self):
        return f'{self.name_id.parent} del int {self.name_id}'

    def _do(self, nbapi):
        deletes = [self.name_id.id]
        log.debug('nbapi.dcim.interfaces.delete %r', deletes)
        nbapi.dcim.interfaces.delete(deletes)


class ModifyInterface(FutureModify):
    def __str__(self):
        kvs = ' '.join(f'{k}={v}' for k, v in self.values.items())
        return f'{self.name_id.parent} set int {self.name_id} {kvs}'

    def _do(self, nbapi):
        updates = [self.values.copy()]
        updates[0]['id'] = self.name_id.id
        log.debug('nbapi.dcim.interfaces.update %r', updates)
        nbapi.dcim.interfaces.update(updates)


class AssignIPAddress(FutureCreate):
    def __str__(self):
        v = self.values
        # XXX: we want to see "dev ... " here too
        # and rename Assign to Create?
        return (
            f'{self.name_id.parent.parent}:{self.name_id.parent} '
            f'add ip {self.name_id} vrf {v["vrf"]}')

    def _do(self, nbapi):
        # TODO: Move these to a check _before_ work.
        assert 'assigned_object_id' in self.values, self.values
        assert 'assigned_object_type' in self.values, self.values
        log.debug('nbapi.ipam.ip_addresses.create %r', self.values)
        nbapi.ipam.ip_addresses.create(self.values)


class DummyUnassignIPAddress(DummyWork):
    def __str__(self):
        return (
            f'{self.name_id.parent.parent}:{self.name_id.parent} '
            f'del ip {self.name_id}')


class ReassignIPAddress(FutureModify):
    def __str__(self):
        # The vrf is optional: an IP that only changes owner keeps the
        # one it is routed in, and then there is nothing to say about
        # it. Pair this with a DummyUnassignIPAddress so the listing
        # shows where the IP leaves as well as where it lands.
        vrf = (f' vrf {self.values["vrf"]}' if 'vrf' in self.values else '')
        return (
            f'{self.name_id.parent.parent}:{self.name_id.parent} '
            f'add ip {self.name_id}{vrf}')

    def _do(self, nbapi):
        # TODO: Move these to a check _before_ work.
        assert 'assigned_object_id' in self.values, self.values
        assert 'assigned_object_type' in self.values, self.values
        updates = [self.values.copy()]
        updates[0]['id'] = self.name_id.id
        log.debug('nbapi.ipam.ip_addresses.update %r', updates)
        nbapi.ipam.ip_addresses.update(updates)


class DeleteMacAddress(FutureDelete):
    def __str__(self):
        return (
            f'{self.name_id.parent.parent}:{self.name_id.parent} '
            f'del mac {self.name_id}')

    def _do(self, nbapi):
        deletes = [self.name_id.id]
        log.debug('nbapi.dcim.mac_addresses.delete %r', deletes)
        nbapi.dcim.mac_addresses.delete(deletes)


class DeleteIPAddress(FutureDelete):
    def __str__(self):
        return (
            f'{self.name_id.parent.parent}:{self.name_id.parent} '
            f'del ip {self.name_id}')

    def _do(self, nbapi):
        deletes = [self.name_id.id]
        log.debug('nbapi.ipam.ip_addresses.delete %r', deletes)
        nbapi.ipam.ip_addresses.delete(deletes)


class DeletePrefix(FutureDelete):
    def __str__(self):
        return f'{self.name_id.parent} del prefix {self.name_id}'

    def _do(self, nbapi):
        deletes = [self.name_id.id]
        log.debug('nbapi.ipam.prefixes.delete %r', deletes)
        nbapi.ipam.prefixes.delete(deletes)


class ModifyIPAddress(FutureModify):
    def __str__(self):
        kvs = ' '.join(f'{k}={v}' for k, v in self.values.items())
        return (
            f'{self.name_id.parent.parent}:{self.name_id.parent} '
            f'set ip {self.name_id} {kvs}')

    def _do(self, nbapi):
        updates = [self.values.copy()]
        updates[0]['id'] = self.name_id.id
        log.debug('nbapi.ipam.ip_addresses.update %r', updates)
        nbapi.ipam.ip_addresses.update(updates)
