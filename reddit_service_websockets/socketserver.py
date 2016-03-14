import datetime
import hashlib
import hmac
import logging
import urlparse

import geventwebsocket
import geventwebsocket.handler


LOG = logging.getLogger(__name__)


def is_valid_namespace(environ, mac_secret):
    namespace = environ.get("PATH_INFO", "")
    if not namespace:
        return False

    try:
        query_string = environ["QUERY_STRING"]
        params = urlparse.parse_qs(query_string, strict_parsing=True)
        mac = params["h"][0]
        expires = params["e"][0]
        expiration_time = datetime.datetime.utcfromtimestamp(int(expires))
    except (KeyError, IndexError, ValueError):
        return

    if expiration_time < datetime.datetime.utcnow():
        return

    expected_mac = hmac.new(mac_secret, expires + namespace,
                            hashlib.sha1).hexdigest()
    if not constant_time_compare(mac, expected_mac):
        return False

    return True


def constant_time_compare(actual, expected):
    """Return whether or not two strings match.

    The time taken is dependent on the number of characters provided instead of
    the number of characters that match which makes this function resistant to
    timing attacks.

    """
    actual_len = len(actual)
    expected_len = len(expected)
    result = actual_len ^ expected_len
    if expected_len > 0:
        for i in xrange(actual_len):
            result |= ord(actual[i]) ^ ord(expected[i % expected_len])
    return result == 0


class WebSocketHandler(geventwebsocket.handler.WebSocketHandler):
    def upgrade_connection(self):
        if not is_valid_namespace(self.environ, self.application.mac_secret):
            LOG.info("rejected connection from %s due to invalid namespace",
                     self.environ["REMOTE_ADDR"])
            self.application.metrics.counter("conn.rejected.bad_namespace").increment()
            self.start_response("403 Forbidden", [])
            return ["Forbidden"]

        return super(WebSocketHandler, self).upgrade_connection()


class SocketServer(object):
    def __init__(self, metrics, dispatcher, mac_secret, ping_interval):
        self.metrics = metrics
        self.dispatcher = dispatcher
        self.mac_secret = mac_secret
        self.ping_interval = ping_interval

    def __call__(self, environ, start_response):
        websocket = environ.get("wsgi.websocket")
        if not websocket:
            self.metrics.counter("conn.rejected.not_websocket").increment()
            start_response("400 Bad Request", [])
            return ["you are not a websocket"]

        namespace = environ["PATH_INFO"]
        try:
            self.metrics.counter("conn.connected").increment()
            for msg in self.dispatcher.listen(namespace,
                                              max_timeout=self.ping_interval):
                if msg is not None:
                    websocket.send(msg)
                else:
                    websocket.send_frame("", websocket.OPCODE_PONG)
        except geventwebsocket.WebSocketError as e:
            LOG.debug("socket failed: %r", e)
        finally:
            self.metrics.counter("conn.lost").increment()
