import logging
import urlparse

import gevent
import geventwebsocket
import geventwebsocket.handler
from geventwebsocket.websocket import WebSocket

from baseplate.crypto import MessageSigner, SignatureError

from .patched_websocket import read_frame as patched_read_frame
from .patched_websocket import send_raw_frame


LOG = logging.getLogger(__name__)


WebSocket.read_frame = patched_read_frame


class WebSocketHandler(geventwebsocket.handler.WebSocketHandler):
    def read_request(self, raw_requestline):
        retval = super(WebSocketHandler, self).read_request(raw_requestline)

        # if the client address doesn't exist, we're probably bound to a
        # unix socket and someone else (e.g. nginx) will be forwarding the
        # client's real address.
        if not self.client_address:
            try:
                self.client_address = (
                    self.headers["x-forwarded-for"],
                    int(self.headers["x-forwarded-port"]),
                )
            except KeyError:
                pass

        return retval

    def log_request(self):
        # geventwebsocket logs every request at INFO level. that's annoying.
        pass

    def upgrade_connection(self):
        """Validate authorization to attach to a namespace before connecting.

        We hook into the geventwebsocket stuff here to ensure that the
        authorization is valid before we return a `101 Switching Protocols`
        rather than connecting then disconnecting the user.

        """
        if not self.client_address:
            # we can't do websockets if we don't have a valid client_address
            # because geventwebsocket uses that to keep connection objects.
            # if this error is happening, you probably need to update your proxy
            raise Exception("no client address. check x-forwarded-{for,port}")

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

        # Check if compression is supported.  The RFC explanation for the
        # variations on what is accepted here is convoluted, so we'll just
        # stick with the happy case:
        #
        #    https://tools.ietf.org/html/rfc6455#page-48
        #
        # Worst case scenario, we fall back to not compressing.
        extensions = self.environ.get('HTTP_SEC_WEBSOCKET_EXTENSIONS')
        extensions = {extension.split(";")[0].strip()
                      for extension in extensions.split(",")}
        self.environ["supports_compression"] = \
            "permessage-deflate" in extensions

        return super(WebSocketHandler, self).upgrade_connection()

    def start_response(self, status, headers, exc_info=None):
        if self.environ["supports_compression"]:

            # {client,server}_no_context_takeover prevents compression context
            # from being used across frames.  This is necessary so that we
            # don't have to maintain a separate compressor for every connection
            # that's made, which would be a large memory footprint.  This also
            # lets us compress a message once and send to all clients, saving
            # on CPU electrons.
            headers.append(("Sec-WebSocket-Extensions",
                            "permessage-deflate; server_no_context_takeover; "
                            "client_no_context_takeover"))
            self.application.metrics.counter(
                "compression.permessage-deflate").increment()
        else:
            self.application.metrics.counter("compression.none").increment()

        return super(WebSocketHandler, self).start_response(
            status, headers, exc_info=exc_info)


class SocketServer(object):
    def __init__(self, metrics, dispatcher, mac_secret, ping_interval):
        self.metrics = metrics
        self.dispatcher = dispatcher
        self.signer = MessageSigner(mac_secret)
        self.ping_interval = ping_interval
        self.status_publisher = None

    def __call__(self, environ, start_response):
        path_info = environ["PATH_INFO"]
        if path_info == "/health":
            start_response("200 OK", [
                ("Content-Type", "application/json"),
            ])
            return ['{"status": "OK"}']

        websocket = environ.get("wsgi.websocket")
        if not websocket:
            self.metrics.counter("conn.rejected.not_websocket").increment()
            start_response("400 Bad Request", [])
            return ["you are not a websocket"]

        # ensure the application was properly configured to use the custom
        # handler subclass which validates namespace signatures
        assert environ["signature_validated"]

        namespace = environ["PATH_INFO"]

        dispatcher = gevent.spawn(
            self._pump_dispatcher, namespace, websocket,
            supports_compression=environ["supports_compression"])

        try:
            self.metrics.counter("conn.connected").increment()
            self._send_message("connect", {"namespace": namespace})
            while True:
                message = websocket.receive()
                LOG.debug('message received: %r', message)
                if message is None:
                    break
        except geventwebsocket.WebSocketError as e:
            LOG.debug("socket failed: %r", e)
        finally:
            self.metrics.counter("conn.lost").increment()
            self._send_message("disconnect", {"namespace": namespace})
            dispatcher.kill()

    def _send_message(self, key, value):
        if self.status_publisher:
            self.status_publisher("websocket.%s" % key, value)

    def _pump_dispatcher(self, namespace, websocket, supports_compression):
        for msg in self.dispatcher.listen(namespace, max_timeout=self.ping_interval):
            if msg is not None:
                if supports_compression and msg.compressed is not None:
                    send_raw_frame(websocket, msg.compressed)
                else:
                    websocket.send(msg.raw)
            else:
                websocket.send_frame("", websocket.OPCODE_PING)
