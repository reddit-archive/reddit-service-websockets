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
    },

    "web": {
        "allowed_origins": config.TupleOf(config.String),
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
        message_handler=dispatcher.on_message_received,
    )

    app = SocketServer(
        metrics=metrics_client,
        dispatcher=dispatcher,
        allowed_origins=cfg.web.allowed_origins,
        mac_secret=cfg.web.mac_secret,
        ping_interval=cfg.web.ping_interval,
    )

    gevent.spawn(source.pump_messages)

    return app
