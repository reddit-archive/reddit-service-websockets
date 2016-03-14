import logging
import socket

import gevent
import haigha.connection


EXCHANGE = "sutro"
LOG = logging.getLogger(__name__)


class MessageSource(object):
    """An AMQP based message source.

    This will monitor a fanout exchange on AMQP and signal on receipt of any
    messages.

    """

    def __init__(self, host, port, vhost, username, password, message_handler):
        self.host = host
        self.port = port
        self.vhost = vhost
        self.username = username
        self.password = password
        self.message_handler = message_handler

    def connect(self):
        self.connection = haigha.connection.Connection(
            host=self.host,
            port=self.port,
            vhost=self.vhost,
            user=self.username,
            password=self.password,
            transport="gevent",
            logger=LOG,
            close_cb=self._on_close,
        )

        self.channel = self.connection.channel()
        self.channel.exchange.declare(exchange=EXCHANGE, type="fanout")
        self.channel.queue.declare(
            exclusive=True,
            auto_delete=True,
            durable=False,
            cb=self._on_queue_created,
        )

    @property
    def connected(self):
        return bool(self.connection)

    def _on_queue_created(self, queue_name, *ignored):
        self.channel.queue.bind(queue=queue_name, exchange=EXCHANGE)
        self.channel.basic.consume(
            queue=queue_name,
            consumer=self._on_message,
        )

    def _on_message(self, message):
        decoded = message.body.decode("utf-8")
        namespace = message.delivery_info["routing_key"]
        self.message_handler(namespace=namespace, message=decoded)

    def _on_close(self):
        LOG.warning("lost connection")
        self.connection = None
        self.channel = None

    def pump_messages(self):
        while True:
            try:
                self.connect()
                LOG.info("connected")

                while self.connected:
                    LOG.debug("pumping")
                    self.connection.read_frames()
                    gevent.sleep()
            except socket.error as exception:
                LOG.warning("connection failed: %s", exception)
                gevent.sleep(1)
