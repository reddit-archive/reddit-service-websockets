import json
import logging
import socket

import gevent
import haigha.channel_pool
import haigha.connection


LOG = logging.getLogger(__name__)


class MessageSource(object):
    """An AMQP based message source.

    This will monitor a fanout exchange on AMQP and signal on receipt of any
    messages, as well as allow messages to be sent to a topic exchange on
    status changes within the system.

    """

    def __init__(self, config):
        assert config.endpoint.family == socket.AF_INET

        self.host = config.endpoint.address.host
        self.port = config.endpoint.address.port
        self.vhost = config.vhost
        self.username = config.username
        self.password = config.password
        self.broadcast_exchange = config.exchange.broadcast
        self.status_exchange = config.exchange.status
        self.send_status_messages = config.send_status_messages
        self.message_handler = None

        self.channel = None
        self.publish_channel = None

    def _connect(self):
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

        self.publisher = haigha.channel_pool.ChannelPool(self.connection)

        self.channel = self.connection.channel()
        self.channel.exchange.declare(exchange=self.broadcast_exchange, type="fanout")
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
        self.channel.queue.bind(queue=queue_name, exchange=self.broadcast_exchange)
        self.channel.basic.consume(
            queue=queue_name,
            consumer=self._on_message,
        )

    def _on_message(self, message):
        if self.message_handler:
            decoded = message.body.decode("utf-8")
            namespace = message.delivery_info["routing_key"]
            self.message_handler(namespace=namespace, message=decoded)

    def _on_close(self):
        LOG.warning("lost connection")
        self.connection = None
        self.channel = None
        self.publisher = None

    def send_message(self, key, payload):
        """Publish a status update to the status exchange."""
        if self.send_status_messages and self.publisher:
            serialized_payload = json.dumps(payload).encode("utf-8")
            message = haigha.message.Message(serialized_payload)
            self.publisher.publish(message, self.status_exchange, routing_key=key)

    def pump_messages(self):
        """Maintain a connection to the broker and handle incoming frames.

        This will never return, so it should be run from a separate greenlet.

        """
        while True:
            try:
                self._connect()
                LOG.info("connected")

                while self.connected:
                    LOG.debug("pumping")
                    self.connection.read_frames()
                    gevent.sleep()
            except socket.error as exception:
                LOG.warning("connection failed: %s", exception)
                gevent.sleep(1)
