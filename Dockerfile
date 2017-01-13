# Dockerfile for standalone service container
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
        python-fbthrift \
        python-gevent \
        python-pyramid \
        python-gevent-websocket \
        rabbitmq-server \
        python-haigha \
        python-setuptools

EXPOSE 9090
ADD . /opt/ws
WORKDIR /opt/ws

# AMQP Setup
RUN ulimit -n 1024

CMD (rabbitmq-server &) && python setup.py develop && python setup.py build && baseplate-serve2 --debug --bind 0.0.0.0:9090 --reload example.ini
