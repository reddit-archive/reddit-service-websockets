import gevent

from baseplate import config, make_metrics_client

from .dispatcher import MessageDispatcher
from .socketserver import SocketServer
from .source import MessageSource


CONFIG_SPEC = {
    "amqp": {
        "endpoint": config.Endpoint,
        "vhost": config.String,
        "username": config.String,
        "password": config.String,

        "exchange": {
            "broadcast": config.String,
            "status": config.String,
        },

        "send_status_messages": config.Boolean,
    },

    "web": {
        "mac_secret": config.Base64,
        "ping_interval": config.Integer,
    },
}


def make_app(raw_config):
    cfg = config.parse_config(raw_config, CONFIG_SPEC)

    metrics_client = make_metrics_client(raw_config)

    dispatcher = MessageDispatcher(metrics=metrics_client)

    source = MessageSource(
        config=cfg.amqp,
    )

    app = SocketServer(
        metrics=metrics_client,
        dispatcher=dispatcher,
        mac_secret=cfg.web.mac_secret,
        ping_interval=cfg.web.ping_interval,
    )

    source.message_handler = dispatcher.on_message_received
    app.status_publisher = source.send_message

    gevent.spawn(source.pump_messages)

    return app
