from collections import namedtuple
import posixpath
import random
from zlib import (
    compressobj,
    DEFLATED,
    MAX_WBITS,
)

import gevent
import gevent.queue

from .patched_websocket import make_compressed_frame


# See http://www.zlib.net/manual.html#Advanced for details:
#
#     "windowBits can also be -8..-15 for raw deflate"
#
# Also see http://stackoverflow.com/a/22311297/720638
#
# We use a single global compressor to save on memory overhead, at the expense
# of compression efficiency (since we cannot maintain a per-connection context
# window).

COMPRESSOR = compressobj(7, DEFLATED, -MAX_WBITS)


# We don't bother compressing if the message would already fit into a single
# packet (i.e. if the length of the message including IP and TCP headers is
# less than the Maximum Transmission Unit).
#
# According to this, the MTU of a packet includes IP and TCP but not ethernet
# headers:
#
#     http://stackoverflow.com/a/9151421/720638
#
# 1500 - common MTU size
# 60 - TCP max header size
# 60 - IP max header size
MIN_COMPRESS_SIZE = 1500 - 60 - 60


Message = namedtuple('Message', ['compressed', 'raw'])


def _walk_namespace_hierarchy(namespace):
    assert namespace.startswith("/")

    yield namespace
    while namespace != "/":
        namespace = posixpath.dirname(namespace)
        yield namespace


class MessageDispatcher(object):
    def __init__(self, metrics):
        self.consumers = {}
        self.metrics = metrics

    def on_message_received(self, namespace, message):
        consumers = self.consumers.get(namespace, [])

        # Compress the message
        if len(message) >= MIN_COMPRESS_SIZE:
            compressed = make_compressed_frame(message, COMPRESSOR)
        else:
            compressed = None
        message = Message(compressed=compressed, raw=message)

        with self.metrics.timer("dispatch"):
            for consumer in consumers:
                consumer.put(message)

    def listen(self, namespace, max_timeout):
        """Register to listen to a namespace and yield messages as they arrive.

        If no messages arrive within `max_timeout` seconds, this will yield a
        `None` to allow clients to do periodic actions like send PINGs.

        This will run forever and yield items as an iterable. Use it in a loop
        and break out of it when you want to deregister.

        """
        queue = gevent.queue.Queue()

        namespace = namespace.rstrip("/")
        for ns in _walk_namespace_hierarchy(namespace):
            self.consumers.setdefault(ns, []).append(queue)

        try:
            while True:
                # jitter the timeout a bit to ensure we don't herd
                timeout = max_timeout - random.uniform(0, max_timeout / 2)

                try:
                    yield queue.get(block=True, timeout=timeout)
                except gevent.queue.Empty:
                    yield None

                # ensure we're not starving others by spinning
                gevent.sleep()
        finally:
            for ns in _walk_namespace_hierarchy(namespace):
                self.consumers[ns].remove(queue)
                if not self.consumers[ns]:
                    del self.consumers[ns]
