"""Unit tests for SocketServer."""
import unittest

import geventwebsocket.websocket
from geventwebsocket.websocket import WebSocket
from mock import (
    call,
    Mock,
    patch,
)

from reddit_service_websockets.socketserver import (
    SocketServer,
    UnauthorizedError,
)

class SocketServerTests(unittest.TestCase):

    def setUp(self):
        self.server = SocketServer(
            metrics=Mock(),
            dispatcher=Mock(),
            mac_secret='test',
            ping_interval=1,
            admin_auth='test-auth',
            conn_shed_rate=5,
        )

    def test_authorized(self):
        environ = {
            'HTTP_AUTHORIZATION': 'Basic test-auth',
        }
        self.assertTrue(self.server._authorized_to_quiesce(environ))

    def test_authorized_rejects_bad_auth(self):
        environ = {
            'HTTP_AUTHORIZATION': 'Basic bad-auth',
        }
        self.assertFalse(self.server._authorized_to_quiesce(environ))

    def test_authorized_rejects_no_auth(self):
        self.assertFalse(self.server._authorized_to_quiesce({}))

    def test_unauthorized_quiesce(self):
        environ = {
            'HTTP_AUTHORIZATION': 'Basic bad-auth',
        }
        with self.assertRaises(UnauthorizedError):
            self.server._quiesce(environ)

    def test_shed_connections(self):
        mock_conn = Mock()
        self.server._shed_connections(set([mock_conn]))
        mock_conn.send_frame.assert_called_with("", mock_conn.OPCODE_CLOSE)

    def test_shed_connections_handles_errors_gracefully(self):
        mock_bad_conn = Mock()
        mock_bad_conn.send_frame.side_effect = geventwebsocket.WebSocketError
        mock_good_conn = Mock()
        self.server._shed_connections(set([mock_bad_conn, mock_good_conn]))
        mock_good_conn.send_frame.assert_called_with("", mock_good_conn.OPCODE_CLOSE)

    def test_quiesce_sets_server_quiesced(self):
        environ = {
            'HTTP_AUTHORIZATION': 'Basic test-auth',
        }
        self.assertFalse(self.server.quiesced)
        self.server._quiesce(environ)
        self.assertTrue(self.server.quiesced)

    @patch('gevent.spawn_later')
    def test_quiesce_with_conns(self, gevent_patch):
        environ = {
            'HTTP_AUTHORIZATION': 'Basic test-auth',
        }
        mock_conn = Mock()
        self.server.connections = set([mock_conn])

        self.server._quiesce(environ)

        calls = [
            # 31 -> shed_delay_seconds + 1 second for iteration
            call(31, self.server._shed_connections, [mock_conn]),
            # 41 -> shed_delay_seconds + 1 second for iteration +
            #       termination_delay_secs
            call(41, self.server._shutdown),
        ]
        gevent_patch.assert_has_calls(calls)

