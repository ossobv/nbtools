import json
from urllib.parse import urlparse


class NetboxRecorder:
    API_URL_REPLACEMENT = 'https://netbox.example.com/api'

    @classmethod
    def from_patched_nbapi(cls, nbapi):
        recorder = cls(nbapi)
        cls.patch_pynetbox(nbapi, recorder)
        return recorder

    @staticmethod
    def patch_pynetbox(api_instance, recorder):
        original_request = api_instance.http_session.request

        def hooked_request(method, url, **kwargs):
            return recorder.callback(
                original_request, method, url, **kwargs)

        api_instance.http_session.request = hooked_request

    def __init__(self, nbapi):
        assert not self.API_URL_REPLACEMENT.endswith('/')
        self._api_base_url = nbapi.base_url.rstrip('/')
        self._api_base_url_len = len(self._api_base_url)

        self._history = []

    def callback(self, original_request, method, url, **kwargs):
        # Execute real request.
        response = original_request(method, url, **kwargs)

        # Parse values and format for our testcases.
        parsed = urlparse(url)
        path = parsed.path
        qs = parsed.query
        assert not qs and 'params' in kwargs, (url, kwargs)

        entry = {
            'method': method.upper(),
            'path': path,
            'params': kwargs['params'],
            'data': kwargs['json'],
            'status': response.status_code,
            'response': response.json() if response.text else None,
        }

        self._history.append(entry)
        return response

    def redacted(self, data):
        if data in (None, True, False):
            return data
        if isinstance(data, (float, int)):
            return data
        if isinstance(data, str):
            if data.startswith(self._api_base_url):
                return (
                    self.API_URL_REPLACEMENT + data[self._api_base_url_len:])
            return data
        if isinstance(data, dict):
            return dict(
                (self.redacted(key), self.redacted(value))
                for key, value in data.items())
        if isinstance(data, (list, set, tuple)):
            return [
                self.redacted(value) for value in data]
        raise NotImplementedError(f'{type(data)}: {data}')

    def save(self, filename):
        history = self.redacted(self._history)

        with open(filename, 'w') as fp:
            json.dump(history, fp, indent=2)
            fp.write('\n')
