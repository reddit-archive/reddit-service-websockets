from setuptools import setup

setup(
    name="reddit_service_websockets",
    version="0.1",
    packages=[
        "reddit_service_websockets"
    ],
    install_requires=[
        "gevent",
        "gevent-websocket",
        "haigha",
        "baseplate",
    ],
)
