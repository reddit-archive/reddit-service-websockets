"""
This module patches a few core functions to add compression capabilities,
since gevent-websocket does not appear to be maintained anymore.
"""
from socket import error
from zlib import (
    decompressobj,
    MAX_WBITS,
    Z_FULL_FLUSH,
)

from geventwebsocket.exceptions import (
    ProtocolError,
    WebSocketError,
)
from geventwebsocket.websocket import (
    MSG_SOCKET_DEAD,
    Header,
    WebSocket,
)


DECOMPRESSOR = decompressobj(-MAX_WBITS)


def _encode_bytes(text):
    if isinstance(text, str):
        return text

    if not isinstance(text, unicode):
        text = unicode(text or '')

    return text.encode('utf-8')


def make_compressed_frame(message, compressor):
    """
    Make a compressed websocket frame from a message and compressor.

    Generates header and a compressed message which can then be used on any
    websocket connection where `no_context_takeover` has been negotiated.
    This prevents the need to re-compress a broadcast-style message for every
    websocket connection.

    `compressor` is a zlib compressor object.
    """
    binary = not isinstance(message, (str, unicode))
    opcode = WebSocket.OPCODE_BINARY if binary else WebSocket.OPCODE_TEXT
    if binary:
        message = str(message)
    else:
        message = _encode_bytes(message)
    message = compressor.compress(message)
    # We use Z_FULL_FLUSH (rather than Z_SYNC_FLUSH) here when
    # server_no_context_takeover has been passed, to reset the context at
    # the end of every frame.  Patches to the actual gevent-websocket
    # library should probably be able to support both.
    message += compressor.flush(Z_FULL_FLUSH)
    # See https://tools.ietf.org/html/rfc7692#page-19
    if message.endswith('\x00\x00\xff\xff'):
        message = message[:-4]

    # Generate header.  The RSV0 bit indicates the payload is compressed.
    flags = Header.RSV0_MASK
    header = Header.encode_header(
        fin=True, opcode=opcode, mask='', length=len(message), flags=flags)

    return header + message


def send_raw_frame(websocket, raw_message):
    """
    `raw_message` includes both the header and the encoded message.
    """
    try:
        websocket.raw_write(raw_message)
    except error:
        websocket.current_app.on_close(MSG_SOCKET_DEAD)
        raise WebSocketError(MSG_SOCKET_DEAD)


def read_frame(websocket):
    # Patched `read_frame` method that supports decompression

    header = Header.decode_header(websocket.stream)

    # Start patched lines
    compressed = header.flags & header.RSV0_MASK
    if compressed:
        header.flags &= ~header.RSV0_MASK
    # End patched lines

    if header.flags:
        raise ProtocolError

    if not header.length:
        return header, ''

    try:
        payload = websocket.raw_read(header.length)
    except error:
        payload = ''
    except Exception:

        # Start patched lines
        raise WebSocketError('Could not read payload')
        # End patched lines

    if len(payload) != header.length:
        raise WebSocketError('Unexpected EOF reading frame payload')

    if header.mask:
        payload = header.unmask_payload(payload)

    # Start patched lines
    if compressed:
        payload = ''.join((
            DECOMPRESSOR.decompress(payload),
            DECOMPRESSOR.decompress('\0\0\xff\xff'),
            DECOMPRESSOR.flush(),
        ))
    # End patched lines

    return header, payload
