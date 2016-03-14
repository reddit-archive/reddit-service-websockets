import gevent

from baseplate import config

from .dispatcher import MessageDispatcher
from .socketserver import SocketServer
from .source import MessageSource
from .stats import StatsClient, StatsCollector


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

    "stats": {
        "host": config.String,
        "port": config.Integer,
    },
}


def make_app(raw_config):
    cfg = config.parse_config(raw_config, CONFIG_SPEC)

    stats = StatsClient(cfg.stats.host, cfg.stats.port)

    dispatcher = MessageDispatcher(
        stats=stats,
    )

    source = MessageSource(
        config=cfg.amqp,
        message_handler=dispatcher.on_message_received,
    )

    app = SocketServer(
        stats=stats,
        dispatcher=dispatcher,
        allowed_origins=cfg.web.allowed_origins,
        mac_secret=cfg.web.mac_secret,
        ping_interval=cfg.web.ping_interval,
    )

    collector = StatsCollector(
        stats=stats,
        dispatcher=dispatcher,
    )

    gevent.spawn(source.pump_messages)
    gevent.spawn(collector.collect_and_report_periodically)

    return app
