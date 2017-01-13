# Dockerfile for a test-running environment
FROM ubuntu:trusty

ENV DEBIAN_FRONTEND noninteractive

RUN apt-get update && \
    apt-get install -y software-properties-common && \
    add-apt-repository -y ppa:reddit/ppa

RUN apt-get update && \
    apt-get install -y \
        python \
        python-baseplate \
        python-cassandra \
        python-coverage \
        python-fbthrift \
        python-gevent \
        python-nose \
        python-mock \
        python-webtest \
        python-pyramid \
        python-gevent-websocket \
        python-haigha \
        python-setuptools

ADD . /opt/ws
WORKDIR /opt/ws

CMD nosetests
