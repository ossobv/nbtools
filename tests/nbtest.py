import json
from functools import wraps
from pathlib import Path

import pynetbox
import responses
from responses.matchers import query_param_matcher


BASE_URL = 'https://netbox.example.com'
TOKEN = 'dummy-token'


def get_test_api():
    return pynetbox.api(BASE_URL, token=TOKEN)


def nb_responses_load(filename, /, caller=None):
    def actual_decorator(func):
        @wraps(func)
        @responses.activate
        def with_nb_responses(*args, **kwargs):
            nb_responses_add(Path(caller or __file__).parent / filename)
            return func(*args, **kwargs)
        return with_nb_responses
    return actual_decorator


def nb_responses_add(filename):
    with open(filename) as fp:
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

            status = entry['status']
            headers = {}
            response = ''
            if entry['response']:
                response = json.dumps(entry['response'])

            return (status, headers, response)

        method = getattr(responses, entry['method'])
        url = f'{BASE_URL}{entry["path"]}'

        request_matchers = []
        if entry['params']:
            request_matchers.append(query_param_matcher(entry['params']))

        responses.add_callback(
            method=method, url=url, callback=request_callback,
            content_type='application/json', match=request_matchers)
