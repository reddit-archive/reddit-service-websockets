import logging
import urlparse

import geventwebsocket
import geventwebsocket.handler

from baseplate.crypto import MessageSigner, SignatureError


LOG = logging.getLogger(__name__)


class WebSocketHandler(geventwebsocket.handler.WebSocketHandler):
    def upgrade_connection(self):
        app = self.application

        try:
            namespace = self.environ["PATH_INFO"]
            query_string = self.environ["QUERY_STRING"]
            params = urlparse.parse_qs(query_string, strict_parsing=True)
            signature = params["m"][0]
            app.signer.validate_signature(namespace, signature)
        except (KeyError, IndexError, ValueError, SignatureError):
            app.metrics.counter("conn.rejected.bad_namespace").increment()
            self.start_response("403 Forbidden", [])
            return ["Forbidden"]

        self.environ["signature_validated"] = True
        return super(WebSocketHandler, self).upgrade_connection()


class SocketServer(object):
    def __init__(self, metrics, dispatcher, mac_secret, ping_interval):
        self.metrics = metrics
        self.dispatcher = dispatcher
        self.signer = MessageSigner(mac_secret)
        self.ping_interval = ping_interval

    def __call__(self, environ, start_response):
        websocket = environ.get("wsgi.websocket")
        if not websocket:
            self.metrics.counter("conn.rejected.not_websocket").increment()
            start_response("400 Bad Request", [])
            return ["you are not a websocket"]

        # ensure the application was properly configured to use the custom
        # handler subclass which validates namespace signatures
        assert environ["signature_validated"]

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
