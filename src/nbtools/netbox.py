"""
Talking to NetBox: the connection, and the reads everything shares.

connect() is where both tools get their nbapi, and it is the only
place that knows the session is allowed to try a read again. The rest
of the module is the lookups the commands have in common.
"""
import logging

from collections import namedtuple
from contextlib import contextmanager

import pynetbox
import requests

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .exceptions import ApiError, NotFound
from .types import DevIface
from .util import natsort_key


log = logging.getLogger(__name__)

# How often a read is tried again, and how long it may take. pynetbox
# passes no timeout at all, and requests has no session-wide default,
# so without the second one a connection that hangs instead of
# answering hangs forever -- and then no retry ever fires, because
# nothing ever fails.
DEFAULT_RETRIES = 3
DEFAULT_TIMEOUT = (5, 60)       # (connect, read), in seconds

# The statuses worth a second try. 408 is the one seen here daily, 429
# is the rate limiter asking politely, and 502/503/504 are the proxy
# in front of NetBox. Not 500: that is NetBox raising on this
# particular request, and it will raise again.
RETRY_STATUSES = (408, 429, 502, 503, 504)

# Spelled out, because urllib3's default is the *idempotent* methods,
# which is not the same question as the safe ones: it includes PUT and
# DELETE. nbsync writes with POST, PATCH and DELETE, and a DELETE that
# timed out at the proxy may well have landed -- replaying it would
# delete whatever holds that id by then.
RETRY_METHODS = frozenset({'GET', 'HEAD', 'OPTIONS'})

# Sleeps of about 0s, 1s and 2s, jittered. The jitter is for cron:
# a batch of runs that all back off by the same amount reconverges on
# the server that was already too busy.
BACKOFF_FACTOR = 0.5
BACKOFF_MAX = 10
BACKOFF_JITTER = 0.5


class LoggingRetry(Retry):
    """
    A urllib3.util.Retry that says it retried.

    A NetBox needing three tries for every call is a fault report, not
    a detail, and both tools configure logging at INFO, so a WARNING
    lands in cron mail without --debug.

    (Only the answered-with-a-status half is logged here. When urllib3
    retries a broken connection or a timeout it warns about that
    itself.)
    """
    def increment(self, method=None, url=None, response=None, **kwargs):
        retry = super().increment(
            method=method, url=url, response=response, **kwargs)

        if response is not None:
            log.warning(
                'retrying %s %s after HTTP %s (%s left)',
                method, url, response.status, retry.total)

        return retry


class TimeoutAdapter(HTTPAdapter):
    """
    An adapter that supplies the timeout requests would not.

    Session.send() always passes a timeout, so this fills in the
    default rather than overriding what a caller asked for.
    """
    def __init__(self, *args, timeout=None, **kwargs):
        self._timeout = timeout
        super().__init__(*args, **kwargs)

    def send(self, request, **kwargs):
        if kwargs.get('timeout') is None:
            kwargs['timeout'] = self._timeout

        return super().send(request, **kwargs)


def _retrying_adapter(retries=None, timeout=None):
    "The adapter connect() mounts; see the constants above for why"
    if retries is None:
        retries = DEFAULT_RETRIES
    if timeout is None:
        timeout = DEFAULT_TIMEOUT

    retry = LoggingRetry(
        total=retries, connect=retries, read=retries, status=retries,
        status_forcelist=RETRY_STATUSES, allowed_methods=RETRY_METHODS,
        backoff_factor=BACKOFF_FACTOR, backoff_max=BACKOFF_MAX,
        backoff_jitter=BACKOFF_JITTER, respect_retry_after_header=True,
        # Hand the last response back rather than raising RetryError,
        # so a run that is out of tries fails the way it always did:
        # with the pynetbox RequestError naming the status.
        raise_on_status=False)

    return TimeoutAdapter(max_retries=retry, timeout=timeout)


def _mount_retries(nbapi, retries=None, timeout=None):
    """
    Give an existing pynetbox api the retrying session

    Mounted on the session pynetbox made rather than replacing it,
    which leaves alone whatever pynetbox keeps on there itself.
    """
    adapter = _retrying_adapter(retries=retries, timeout=timeout)
    nbapi.http_session.mount('http://', adapter)
    nbapi.http_session.mount('https://', adapter)

    return nbapi


def connect(config):
    """
    The nbapi both tools run on: reads retried, writes never

    Retrying reads is safe because of how a command is built. A sync
    command reads everything in plan() and writes nothing until run()
    has the finished list, so a read that has to be repeated cannot
    double a change -- there is not one yet. A lint command only ever
    reads. What must not be repeated is the writing half, and
    RETRY_METHODS is what keeps it out.
    """
    nbapi = pynetbox.api(config.api_url_base, token=config.api_token)

    return _mount_retries(
        nbapi, retries=config.api_retries, timeout=config.api_timeout)


@contextmanager
def translated_errors():
    """
    Report a NetBox that failed to answer like any other failure

    pynetbox raises RequestError for a status it did not want, and
    requests raises its own for a connection that never got that far.
    Neither is a StateError, so without this both tools answer a 408
    with a traceback where everything else gets one line.
    """
    try:
        yield
    except pynetbox.RequestError as e:
        raise ApiError.from_request_error(e) from e
    except requests.RequestException as e:
        raise ApiError(f'{type(e).__name__}: {e}') from e


# The interface we were asked about, plus its subinterfaces. Shared by
# every command that operates on an interface and its children.
InterfaceTree = namedtuple(
    'InterfaceTree', 'dev if_name if_parent if_children')


def get_device(nbapi, name):
    "Get the device by name"
    device = nbapi.dcim.devices.get(name=name)
    if not device:
        raise NotFound(name)

    return device


def get_interfaces_by_name(nbapi, device, name, with_subinterfaces=True):
    "Get swp34 or swp34 and swp34.12, swp34.13, swp34.14 with vlan"
    parent_iface = nbapi.dcim.interfaces.get(device_id=device.id, name=name)
    if not parent_iface:
        raise NotFound(name)

    interfaces = [parent_iface]

    if with_subinterfaces:
        # Technically. we should just need this loop.
        by_id = set(nbapi.dcim.interfaces.filter(
            device_id=device.id,
            parent_id=parent_iface.id))

        # But, because we're not 100% confident that everything is
        # properly set, we'll check by name too.
        by_name = set(nbapi.dcim.interfaces.filter(
            device_id=device.id,
            name__isw=f'{name}.'))

        # Check that ifaces by name and by id are the same.
        by_id_tst = {(iface.name, iface.id) for iface in by_id}
        by_name_tst = {(iface.name, iface.id) for iface in by_name}
        by_id_excess = (by_id_tst - by_name_tst)
        by_name_excess = (by_name_tst - by_id_tst)
        assert not by_id_excess, by_id_excess
        assert not by_name_excess, by_name_excess

        interfaces.extend(sorted(by_id, key=(
            lambda x: natsort_key(x.name))))

    return interfaces


def check_child_interface_names(ifaces, ifacename) -> None:
    "The children of swp34 are expected to be named swp34.something"
    startswith = f'{ifacename}.'
    for iface in ifaces:
        if not iface.name.startswith(startswith):
            raise NotImplementedError(
                f'expected "{iface}" to start with "{startswith}"')


def get_interface_tree(
        nbapi, devif: DevIface, with_subinterfaces=True,
        raise_as=NotFound) -> InterfaceTree:
    """
    Look up a DevIface and its subinterfaces as an InterfaceTree.

    Pass raise_as to label which side of the operation went missing,
    e.g. raise_as=UnrecognisedItemOnSource.
    """
    try:
        device = get_device(nbapi, devif.device)
        ifaces = get_interfaces_by_name(
            nbapi, device, devif.interface,
            with_subinterfaces=with_subinterfaces)
    except NotFound as e:
        raise raise_as(devif) from e

    parent_iface = ifaces.pop(0)
    check_child_interface_names(ifaces, devif.interface)

    return InterfaceTree(
        dev=device,
        if_name=devif.interface,
        if_parent=parent_iface,
        if_children=ifaces,
    )


def get_mac_addresses(nbapi, mac):
    """
    Get every record NetBox holds for this exact MAC address

    Filtering happens twice on purpose. pynetbox turns a q= into a
    freeform search, which also returns neighbours, so the exact match
    is redone here rather than trusted to the server.
    """
    wanted = str(mac).lower()

    return [
        rec for rec in nbapi.dcim.mac_addresses.filter(q=wanted)
        if str(rec.mac_address).lower() == wanted]


def get_ip_addresses(nbapi, iface):
    "Get the IPs assigned to this interface"
    # NOTE: hardware only. For a VM this would be vminterface_id. The
    # old code asserted on iface.__class__.__module__ to catch that,
    # which only ever documented the missing feature.
    return list(nbapi.ipam.ip_addresses.filter(interface_id=iface.id))


def get_interface_by_id(nbapi, iface_id):
    """
    Get a whole dcim.interface by id

    The interface nested in an IP address record is the brief one: id,
    name, device and no more. Ask for VRF or parent and you get an
    AttributeError, so anything that starts from an IP has to fetch the
    interface itself.
    """
    iface = nbapi.dcim.interfaces.get(iface_id)
    if not iface:
        raise NotFound(iface_id)

    return iface


def get_ip_addresses_by_address(nbapi, address):
    """
    Get every record NetBox holds for this exact address

    As in get_mac_addresses(), the match is redone here: the
    server-side filter is trusted to narrow the set down, not to be
    exact about it.
    """
    wanted = str(address)

    return [
        rec for rec in nbapi.ipam.ip_addresses.filter(address=wanted)
        if str(rec.address) == wanted]


def get_vm(nbapi, name):
    "Get the virtual machine by name"
    vm = nbapi.virtualization.virtual_machines.get(name=name)
    if not vm:
        raise NotFound(name)

    return vm


def get_vm_interfaces(nbapi, vm):
    "Get the interfaces of a virtual machine, in natural name order"
    return sorted(
        nbapi.virtualization.interfaces.filter(virtual_machine_id=vm.id),
        key=(lambda x: natsort_key(x.name)))


def get_vm_ip_addresses(nbapi, vmiface):
    """
    Get the IPs assigned to this VM interface

    The hardware twin of this is get_ip_addresses() above. They are two
    functions rather than one that guesses, because a dcim.interface id
    and a virtualization.vminterface id come from different tables: an
    id alone does not say which kind it is, so the caller has to.
    """
    return list(nbapi.ipam.ip_addresses.filter(vminterface_id=vmiface.id))
