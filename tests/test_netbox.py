"""
The connection: retried reads, unrepeated writes, readable failures.

NetBox here answers 408 often enough that a daily run of
set-interface-ip-by-mac died on one of its four GETs. netbox.connect()
mounts a session that tries a read again, and these tests pin the
three properties that make that safe to do: a read comes back, a write
is never repeated, and a run that is out of tries fails the way it
always did.

responses emulates urllib3's retry loop off the adapter's max_retries,
and does not sleep while doing it, so this needs no server and takes
no time.
"""
import json
import logging

from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

import pynetbox
import pytest
import requests
import responses

from responses.registries import OrderedRegistry

from nbtools.exceptions import ApiError
from nbtools.netbox import (
    DEFAULT_RETRIES, DEFAULT_TIMEOUT, RETRY_METHODS, RETRY_STATUSES,
    _mount_retries, _retrying_adapter, translated_errors)

from .nbtest import BASE_URL, TOKEN


IP_URL = f'{BASE_URL}/api/ipam/ip-addresses/'

# What the failing GET in that log asked for.
ONE_IP = {
    'count': 1, 'next': None, 'previous': None,
    'results': [{'id': 900, 'address': '10.101.13.247/24'}]}

TIMED_OUT = {'detail': 'Request Timeout'}


def an_api(retries=None, timeout=None):
    "A pynetbox api with the retrying adapter on it, as connect() makes"
    return _mount_retries(
        pynetbox.api(BASE_URL, token=TOKEN),
        retries=retries, timeout=timeout)


def a_read(api):
    "The read that dies daily: the IPs already on this interface"
    return list(api.ipam.ip_addresses.filter(interface_id=5206))


@responses.activate(registry=OrderedRegistry)
def test_read_survives_a_408():
    responses.get(IP_URL, json=TIMED_OUT, status=408)
    responses.get(IP_URL, json=TIMED_OUT, status=408)
    responses.get(IP_URL, json=ONE_IP, status=200)

    found = a_read(an_api())

    assert [str(ip) for ip in found] == ['10.101.13.247/24']
    assert len(responses.calls) == 3


@responses.activate(registry=OrderedRegistry)
def test_read_out_of_tries_fails_as_it_always_did():
    """
    The error the operator already knows, not a new one

    raise_on_status=False is what keeps this a pynetbox RequestError
    naming the 408 rather than a urllib3 RetryError naming nothing.
    """
    for _ in range(DEFAULT_RETRIES + 2):
        responses.get(IP_URL, json=TIMED_OUT, status=408)

    with pytest.raises(pynetbox.RequestError) as caught:
        a_read(an_api())

    assert '408' in str(caught.value)
    assert len(responses.calls) == DEFAULT_RETRIES + 1


@responses.activate(registry=OrderedRegistry)
def test_a_write_is_never_repeated():
    """
    The reason RETRY_METHODS is spelled out

    A POST that timed out at the proxy may well have landed. urllib3's
    default method list would repeat a PUT or a DELETE for the same
    reason it repeats a GET; this one does not.
    """
    responses.post(IP_URL, json=TIMED_OUT, status=408)

    with pytest.raises(pynetbox.RequestError):
        an_api().ipam.ip_addresses.create(address='10.101.13.247/24')

    assert len(responses.calls) == 1


@responses.activate(registry=OrderedRegistry)
def test_a_500_is_not_retried():
    "NetBox raising on this request will raise on it again"
    responses.get(IP_URL, json={'detail': 'oops'}, status=500)

    with pytest.raises(pynetbox.RequestError):
        a_read(an_api())

    assert len(responses.calls) == 1
    assert 500 not in RETRY_STATUSES


@responses.activate(registry=OrderedRegistry)
def test_retries_can_be_turned_off():
    "api_retries = 0 in the INI, for when the retrying is in the way"
    responses.get(IP_URL, json=TIMED_OUT, status=408)

    with pytest.raises(pynetbox.RequestError):
        a_read(an_api(retries=0))

    assert len(responses.calls) == 1


@responses.activate(registry=OrderedRegistry)
def test_a_retry_is_logged(caplog):
    "A NetBox that needs two tries per call is a fault report"
    responses.get(IP_URL, json=TIMED_OUT, status=408)
    responses.get(IP_URL, json=ONE_IP, status=200)

    with caplog.at_level(logging.WARNING, logger='nbtools.netbox'):
        a_read(an_api())

    assert len(caplog.records) == 1
    assert 'retrying GET' in caplog.text
    assert 'HTTP 408' in caplog.text


def test_the_methods_are_the_safe_ones_only():
    "Not urllib3's default, which is the idempotent ones"
    assert RETRY_METHODS == frozenset({'GET', 'HEAD', 'OPTIONS'})


class Sent(Exception):
    "Raised in place of actually sending, carrying what was passed"

    def __init__(self, kwargs):
        self.kwargs = kwargs
        super().__init__(kwargs)


@pytest.fixture
def sent(monkeypatch):
    "Catch the kwargs the adapter hands to requests"
    def do_not_send(self, request, **kwargs):
        raise Sent(kwargs)

    monkeypatch.setattr(
        requests.adapters.HTTPAdapter, 'send', do_not_send)


def send_through(adapter, **kwargs):
    "Send a prepared request and return the kwargs that came out"
    prepared = requests.Request('GET', IP_URL).prepare()
    with pytest.raises(Sent) as caught:
        adapter.send(prepared, **kwargs)

    return caught.value.kwargs


def test_the_timeout_pynetbox_does_not_pass(sent):
    """
    Without this a hung connection hangs forever

    pynetbox passes no timeout and requests has no session-wide
    default, so nothing would ever fail -- and a retry only helps
    something that fails.
    """
    assert send_through(
        _retrying_adapter(), timeout=None)['timeout'] == DEFAULT_TIMEOUT
    assert send_through(
        _retrying_adapter(timeout=(1, 2)),
        timeout=None)['timeout'] == (1, 2)


def test_an_asked_for_timeout_wins(sent):
    "It fills the default in; it does not override a caller"
    assert send_through(
        _retrying_adapter(), timeout=7)['timeout'] == 7


@responses.activate(registry=OrderedRegistry)
def test_a_failure_to_answer_reads_like_any_other(caplog):
    """
    A 408 prints one line, where it used to print a traceback

    RequestError is not a StateError, so neither main() caught it.
    """
    for _ in range(DEFAULT_RETRIES + 1):
        responses.get(IP_URL, json=TIMED_OUT, status=408)

    with pytest.raises(ApiError) as caught:
        with translated_errors():
            a_read(an_api())

    assert str(caught.value) == (
        f'GET {IP_URL}?interface_id=5206&limit=0: 408 Request Timeout')


@responses.activate
def test_a_connection_that_never_got_there_too():
    "requests raises its own for those, and it is the same failure"
    responses.get(IP_URL, body=requests.ConnectionError('no route'))

    with pytest.raises(ApiError) as caught:
        with translated_errors():
            a_read(an_api())

    assert 'no route' in str(caught.value)


def test_what_it_leaves_alone():
    "A state error travels the same path and must not be rewritten"
    with pytest.raises(ValueError, match='not mine'):
        with translated_errors():
            raise ValueError('not mine')


class Flaky(BaseHTTPRequestHandler):
    """
    A NetBox that times out once and then answers.

    Everything above goes through responses, which emulates the retry
    loop rather than running it. This one is here so that the policy
    is proved against the real urllib3 at least once.
    """
    served = 0

    def do_GET(self):
        type(self).served += 1
        if type(self).served == 1:
            body, status = TIMED_OUT, 408
        else:
            body, status = ONE_IP, 200

        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        "Quiet: the test says what happened, not the server"


@pytest.fixture
def flaky_netbox():
    "The address of a NetBox that 408s the first read"
    Flaky.served = 0
    server = HTTPServer(('127.0.0.1', 0), Flaky)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield 'http://{}:{}'.format(*server.server_address)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_against_a_real_socket(flaky_netbox):
    """
    The same thing again, over TCP

    One retry only: urllib3 sleeps nothing before the first one, so
    this costs no time.
    """
    api = _mount_retries(
        pynetbox.api(flaky_netbox, token=TOKEN), retries=1, timeout=(5, 5))

    found = a_read(api)

    assert [str(ip) for ip in found] == ['10.101.13.247/24']
    assert Flaky.served == 2
