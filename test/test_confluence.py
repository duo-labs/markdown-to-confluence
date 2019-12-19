import unittest
import json
import logging

from confluence import Confluence, DEFAULT_LABEL_PREFIX

logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO)


class MockResponse():
    def __init__(self, *args, is_json=True, response=None, status=None):
        self.is_json = is_json
        self._json = response

        if self.is_json:
            self.text = json.dumps(response)
        else:
            self.text = response
        self.status_code = status

    @property
    def ok(self):
        return self.status_code >= 200 and self.status_code <= 400

    def json(self):
        if self.is_json:
            return self._json
        return None


class MockConfluenceClient():
    def __init__(self, *args, **kwargs):
        self.auth = None
        self.is_json = kwargs.get('is_json', True)
        self.response = kwargs.get('response', {})
        self.status = kwargs.get('status', {})
        self.requests = []

    def request(self, *args, **kwargs):
        self.requests.append(kwargs)
        return MockResponse(is_json=self.is_json,
                            response=self.response,
                            status=self.status)


class TestConfluence(unittest.TestCase):
    def setUp(self):
        self.space = 'SPACE'
        self.slug = "example-page"
        self.api = Confluence(api_url='https://wiki.example.com/rest/api',
                              username='foo',
                              password='bar')

    def testPostExists(self):
        response = {
            "results": [
                {
                    "id": "1234567",
                    "type": "page",
                    "status": "current",
                    "title": "Example Page",
                    "restrictions": {},
                },
            ],
            "start":
            0,
            "limit":
            25,
            "size":
            1
        }
        client = MockConfluenceClient(response=response,
                                      status=200,
                                      is_json=True)
        self.api._session = client
        got = self.api.exists(slug=self.slug)
        self.assertTrue(got)

    def testPostDoesntExist(self):
        response = {
            "results": [],
            "start": 0,
            "limit": 25,
            "size": 0,
        }
        client = MockConfluenceClient(response=response,
                                      status=200,
                                      is_json=True)
        self.api._session = client
        got = self.api.exists(slug=self.slug)
        self.assertFalse(got)

    def testLabelCreation(self):
        slug = 'example-post'
        tags = ['knowledge', 'testing']
        expected = [{
            'prefix': DEFAULT_LABEL_PREFIX,
            'name': slug
        }, {
            'prefix': DEFAULT_LABEL_PREFIX,
            'name': 'knowledge'
        }, {
            'prefix': DEFAULT_LABEL_PREFIX,
            'name': 'testing'
        }]
        client = MockConfluenceClient(response={}, status=200, is_json=True)
        self.api._session = client
        self.api.create_labels(page_id='12345', slug=slug, tags=tags)
        sent = self.api._session.requests[0]
        self.assertEqual(len(sent['json']), len(expected))
        for label in expected:
            self.assertIn(label, sent['json'])

    def testGetAuthor(self):
        userKey = '1234567890'
        expected = {
            "type": "known",
            "username": "foo",
            "userKey": userKey,
            "profilePicture": {
                "path": "/download/attachments/123456/user-avatar",
                "width": 48,
                "height": 48,
                "isDefault": False
            },
            "displayName": "Foo Bar"
        }
        client = MockConfluenceClient(response=expected,
                                      status=200,
                                      is_json=True)
        self.api._session = client
        got = self.api.get_author('foo')
        self.assertEqual(got['userKey'], userKey)


if __name__ == '__main__':
    unittest.main()