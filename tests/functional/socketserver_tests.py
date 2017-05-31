import unittest

from baseplate.secrets import SecretsStore
import webtest
from mock import Mock, patch

import reddit_service_websockets as ws
from reddit_service_websockets.socketserver import SocketServer

NOT_WEBSOCKET_RESP_BODY = 'you are not a websocket'

class WebsocketServiceTests(unittest.TestCase):
    def setUp(self):
        secrets = SecretsStore("example_secrets.json")
        self.app = SocketServer(
            metrics=Mock(),
            dispatcher=Mock(),
            secrets=secrets,
            error_reporter=None,
            ping_interval=1,
            admin_auth='test-auth',
            conn_shed_rate=5,
        )
        self.test_app = webtest.TestApp(self.app)

    def test_health(self):
        resp = self.test_app.get('/health')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.body, '{"status": "OK", "connections": 0}')

    def test_quiesce_fails_get(self):
        resp = self.test_app.get('/quiesce',
                                 expect_errors=True,
                                 headers={})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.body, NOT_WEBSOCKET_RESP_BODY)

    def test_quiesce_unauthorized(self):
        resp = self.test_app.post('/quiesce',
                                  expect_errors=True,
                                  headers={})
        self.assertEqual(resp.status_code, 401)

    def test_quiesce_authorized(self):
        auth_header = {
            'Authorization': 'Basic ' + self.app.admin_auth
        }
        resp = self.test_app.post('/quiesce',
                                  headers=auth_header)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(self.app.quiesced)

    def test_already_quiesced_app(self):
        self.app.quiesced = True
        resp = self.test_app.post('/quiesce',
                                  expect_errors=True,
                                  headers={})
        self.assertEqual(resp.status_code, 410)
        self.assertEqual(resp.body, '{"status": "quiesced", "connections": 0}')

    def test_quiesced_returns_conn_count(self):
        self.app.quiesced = True
        self.app.connections = set([Mock(), Mock()])
        resp = self.test_app.get('/health',
                                 expect_errors=True,
                                 headers={})
        self.assertEqual(resp.status_code, 410)
        self.assertEqual(resp.body, '{"status": "quiesced", "connections": 2}')
        # Remove a connection and check for updated count in response
        self.app.connections.pop()
        resp = self.test_app.get('/health',
                                 expect_errors=True,
                                 headers={})
        self.assertEqual(resp.status_code, 410)
        self.assertEqual(resp.body, '{"status": "quiesced", "connections": 1}')

