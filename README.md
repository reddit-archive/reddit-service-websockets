reddit-service-websockets
=========================

Websockets for reddit.

This service is primarily aimed at broadcasting messages to clients. It can
also optionally report to the backend when clients connect or disconnect. All
communication with other backend services is mediated by an AMQP broker
(RabbitMQ).

### Usage

Applications using this service are in charge of managing authorization. The
service validates that incoming requests were authorized by the main
application using a message authentication code. The path portion of a
websocket request indicates which message "namespace" the socket will receive.

Messages are sent to the service via an AMQP [fan out
exchange](http://www.rabbitmq.com/tutorials/amqp-concepts.html#exchanges).
Each worker process binds to the exchange and will receive all messages sent to
it. Messages are dispatched to appropriate websocket clients by mapping the
message's routing key to the socket namespace specified in the websocket
request.

If configured to do so, the service will also insert connect/disconnect
messages onto a topic exchange in AMQP.

### Further reading

This service is used and written for reddit.com's socket needs. Client and
server code examples can be found in the monolith's repos:

* [r2/r2/lib/websockets.py](https://github.com/reddit/reddit/blob/master/r2/r2/lib/websockets.py)
* [r2/r2/public/static/js/websocket.js](https://github.com/reddit/reddit/blob/master/r2/r2/public/static/js/websocket.js)
