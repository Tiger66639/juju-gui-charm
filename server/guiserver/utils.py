# This file is part of the Juju GUI, which lets users view and manage Juju
# environments within a graphical interface (https://launchpad.net/juju-gui).
# Copyright (C) 2013 Canonical Ltd.
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU Affero General Public License version 3, as published by
# the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranties of MERCHANTABILITY,
# SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Juju GUI server utility functions and classes."""

import collections
import functools
import logging
import re
import urlparse
import weakref

from tornado import (
    escape,
    httpclient,
)


def add_future(io_loop, future, callback, *args):
    """Schedule a callback on the IO loop when the given Future is finished.

    The callback will receive the given optional args and the completed Future.
    """
    partial_callback = functools.partial(callback, *args)
    io_loop.add_future(future, partial_callback)


def clone_request(request, url, validate_cert=True):
    """Create and return an httpclient.HTTPRequest from the given request.

    The passed url is used for the new request. The given request object is
    usually an instance of tornado.httpserver.HTTPRequest.
    """
    return httpclient.HTTPRequest(
        url, body=request.body or None, headers=request.headers,
        method=request.method, validate_cert=validate_cert)


def get_headers(request, websocket_url):
    """Return additional headers to be included in the client connection.

    Specifically this function includes in the returned dict the Origin
    header, taken from the provided browser request. If the origin is not found
    the HTTP(S) equivalent of the provided websocket address is returned.
    """
    origin = request.headers.get('Origin')
    if origin is None:
        origin = ws_to_http(websocket_url)
    return {'Origin': origin}


def get_juju_api_url(path, source_template, target_template, default):
    """Return the Juju WebSocket API fully qualified URL.

    Receives the current WebSocket handler path and the templates used by the
    Juju GUI. For instance, path is a string representing the path used by the
    client to connect to the GUI server (like "/ws/api/1.2.3.4/17070/uuid").
    The source template specifies where in the path relevant information can be
    found: for instance "/api/$server/$port/$uuid". The target template maps
    parsed values to the real Juju WebSocket URL.
    If a URL cannot be inferred as described, return the given default.
    """
    pattern = source_template.replace(
        '$server', '(?P<server>.*)').replace(
        '$port', '(?P<port>\d+)').replace(
        '$uuid', '(?P<uuid>.*)')
    match = re.search(pattern, path)
    if match is None:
        # The path is empty: probably an old Juju version is being used.
        return default
    return target_template.format(**match.groupdict())


def join_url(base_url, path, query):
    """Create and return an URL string joining the given parts.

    The base_url argument is any URL, and can include the path part but not the
    query string. The path argument is any path to be added to the URL, or an
    empty string. The query argument is the URL query string, e.g. "arg=value".
    """
    query = '?{}'.format(query) if query else ''
    return '{}/{}{}'.format(base_url.rstrip('/'), path.lstrip('/'), query)


def json_decode_dict(message):
    """Decode the given JSON message, returning a Python dict.

    If the message is not a valid JSON string, or if the resulting object is
    not a dict-like object, log a warning and return None.
    """
    try:
        data = escape.json_decode(message)
    except ValueError:
        msg = 'JSON decoder: message is not valid JSON: {!r}'.format(message)
        logging.warning(msg)
        return None
    if not isinstance(data, collections.Mapping):
        msg = 'JSON decoder: message is not a dict: {!r}'.format(message)
        logging.warning(msg)
        return None
    return data


def request_summary(request):
    """Return a string representing a summary for the given request."""
    return '{} {} ({})'.format(request.method, request.uri, request.remote_ip)


def wrap_write_message(handler):
    """Wrap the write_message() method of the given handler.

    The resulting function uses a weak reference to the handler, in order to
    avoid calling the wrapped method if the handler (a WebSocket connection)
    has been closed or garbage collected.

    If the handler is still there, and the connection is still established,
    JSON encode the received data before propagating it.
    """
    handler_ref = weakref.ref(handler)

    def wrapped(data):
        handler = handler_ref()
        if (handler is None) or (not handler.connected):
            return logging.warning(
                'discarding message (closed connection): {!r}'.format(data))
        message = escape.json_encode(data)
        handler.write_message(message)

    return wrapped


def ws_to_http(url):
    """Return the HTTP(S) equivalent of the provided ws/wss URL."""
    parts = urlparse.urlsplit(url)
    scheme = {'ws': 'http', 'wss': 'https'}[parts.scheme]
    return '{}://{}{}'.format(scheme, parts.netloc, parts.path)
