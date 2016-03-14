import gevent

from .config import parse_config, comma_delimited, base64
from .dispatcher import MessageDispatcher
from .socketserver import SocketServer
from .source import MessageSource
from .stats import StatsClient, StatsCollector


CONFIG_SPEC = {
    "amqp": {
        "host": str,
        "port": int,
        "vhost": str,
        "username": str,
        "password": str,
    },

    "web": {
        "allowed_origins": comma_delimited,
        "mac_secret": base64,
        "ping_interval": int,
    },

    "stats": {
        "host": str,
        "port": int,
    },
}


def make_app(raw_config):
    config = parse_config(raw_config, CONFIG_SPEC)

    stats = StatsClient(config["stats"]["host"], config["stats"]["port"])

    dispatcher = MessageDispatcher(
        stats=stats,
    )

    source = MessageSource(
        host=config["amqp"]["host"],
        port=config["amqp"]["port"],
        vhost=config["amqp"]["vhost"],
        username=config["amqp"]["username"],
        password=config["amqp"]["password"],
        message_handler=dispatcher.on_message_received,
    )

    app = SocketServer(
        stats=stats,
        dispatcher=dispatcher,
        allowed_origins=config["web"]["allowed_origins"],
        mac_secret=config["web"]["mac_secret"],
        ping_interval=config["web"]["ping_interval"],
    )

    collector = StatsCollector(
        stats=stats,
        dispatcher=dispatcher,
    )

    gevent.spawn(source.pump_messages)
    gevent.spawn(collector.collect_and_report_periodically)

    return app
