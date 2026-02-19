import json
from pathlib import Path

import pynetbox
import responses
from responses.matchers import query_param_matcher

from nbtools.cmd.clone_if import CloneInterfaceCommand
from nbtools.command import ProcessMode


BASE_URL = 'https://netbox.example.com'
TOKEN = 'dummy-token'


def nb_responses_add(filename):
    path = Path(__file__).parent / filename
    with open(path) as fp:
        req_resp_history = json.load(fp)

    for entry in req_resp_history:
        # Callback to manually check request data. If we used a matcher for
        # this, we would simply "not find" the correct API call. Now we _do_
        # find it, and can check if anything is wrong.
        def request_callback(request, entry=entry):
            if request.body:
                actual_data = json.loads(request.body)
            else:
                actual_data = None
            expected_data = entry['data']
            # Raises a standard AssertionError with diff when running under
            # pytest.
            assert actual_data == expected_data, (
                f'{entry["method"]} data mismatch at {request.url}')

            return (
                entry['status'],                # status
                {},                             # headers
                json.dumps(entry['response']),  # response
            )

        method = getattr(responses, entry['method'])
        url = f'{BASE_URL}{entry["path"]}'

        request_matchers = []
        if entry['params']:
            request_matchers.append(query_param_matcher(entry['params']))

        responses.add_callback(
            method=method, url=url, callback=request_callback,
            content_type='application/json', match=request_matchers)


@responses.activate
def test_clone_iface_0():
    nb_responses_add('test_clone_if.0.json')

    source_dev_name = 'switch2.dostno.systems'
    source_iface_name = 'swp53s2'
    target_dev_name = 'switch3.dostno.systems'
    target_iface_name = 'swp56s2'

    nbapi = pynetbox.api(BASE_URL, token=TOKEN)

    clone_iface = CloneInterfaceCommand(nbapi)
    clone_iface.set_source_interface(source_dev_name, source_iface_name)
    clone_iface.set_target_interface(target_dev_name, target_iface_name)
    clone_iface.run(ProcessMode.YES)
