import datetime
import hashlib
import hmac
import logging
import urlparse

import geventwebsocket
import geventwebsocket.handler


LOG = logging.getLogger(__name__)


def is_subdomain(domain, base_domain):
    return domain == base_domain or domain.endswith("." + base_domain)


def is_allowed_origin(origin, whitelist):
    # if there's no whitelist, assume all is ok
    if not whitelist:
        return True

    try:
        parsed = urlparse.urlparse(origin)
    except ValueError:
        return False

    if parsed.scheme not in ("http", "https"):
        return False

    if parsed.port is not None and parsed.port not in (80, 443):
        return False

    for domain in whitelist:
        if is_subdomain(parsed.hostname, domain):
            return True
    return False


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
        origin = self.environ.get("HTTP_ORIGIN", "")
        if not is_allowed_origin(origin, self.application.allowed_origins):
            LOG.info("rejected connection from %s due to bad origin %r",
                     self.environ["REMOTE_ADDR"], origin)
            self.application.stats.count("sutro.conn.rejected.bad_origin")
            self.start_response("403 Forbidden", [])
            return ["Forbidden"]

        if not is_valid_namespace(self.environ, self.application.mac_secret):
            LOG.info("rejected connection from %s due to invalid namespace",
                     self.environ["REMOTE_ADDR"])
            self.application.stats.count("sutro.conn.rejected.bad_namespace")
            self.start_response("403 Forbidden", [])
            return ["Forbidden"]

        return super(WebSocketHandler, self).upgrade_connection()


class SocketServer(object):
    def __init__(self, stats, dispatcher, allowed_origins, mac_secret,
                 ping_interval):
        self.stats = stats
        self.dispatcher = dispatcher
        self.allowed_origins = allowed_origins
        self.mac_secret = mac_secret
        self.ping_interval = ping_interval

    def __call__(self, environ, start_response):
        websocket = environ.get("wsgi.websocket")
        if not websocket:
            self.stats.count("sutro.conn.rejected.not_websocket")
            start_response("400 Bad Request", [])
            return ["you are not a websocket"]

        namespace = environ["PATH_INFO"]
        try:
            self.stats.count("sutro.conn.connected")
            for msg in self.dispatcher.listen(namespace,
                                              max_timeout=self.ping_interval):
                if msg is not None:
                    websocket.send(msg)
                else:
                    websocket.send_frame("", websocket.OPCODE_PONG)
        except geventwebsocket.WebSocketError as e:
            LOG.debug("socket failed: %r", e)
        finally:
            self.stats.count("sutro.conn.lost")
