#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""How listen() behaves when a connection ends.

Each test runs a pubsub-shaped server that ends the connection in one
particular way, and asks whether listen() comes back for the next one.
"""

import asyncio
import json

from aiohttp import web

import asfpy.pubsub


async def _start_server(handler):
    """Serve HANDLER on a port of its own. Returns the runner and its url."""
    app = web.Application()
    app.router.add_get('/', handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0)
    await site.start()
    port = runner.addresses[0][1]
    return runner, f'http://127.0.0.1:{port}/'


async def _stream_one_payload(request, payload):
    """Write PAYLOAD to REQUEST as pubsub does, then hang up."""
    resp = web.StreamResponse()
    resp.enable_chunked_encoding()
    await resp.prepare(request)
    await resp.write(json.dumps(payload).encode('utf-8') + b'\n')
    await resp.write_eof()
    return resp


async def _collect(url, count):
    """Read COUNT payloads from listen(URL) and stop."""
    payloads = []
    events = asfpy.pubsub.listen(url)
    try:
        async for payload in events:
            payloads.append(payload)
            if len(payloads) == count:
                break
    finally:
        await events.aclose()
    return payloads


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, timeout=30))


def test_reconnects_when_the_server_hangs_up():
    """A server that ends the stream between payloads is reconnected to."""
    seen = []

    async def handler(request):
        seen.append(len(seen))
        return await _stream_one_payload(request, {'n': seen[-1]})

    async def run():
        runner, url = await _start_server(handler)
        try:
            return await _collect(url, 3)
        finally:
            await runner.cleanup()

    assert _run(run()) == [{'n': 0}, {'n': 1}, {'n': 2}]


def test_reconnects_after_a_partial_payload():
    """A server that dies mid-payload is reconnected to, and the
    half-written payload is not passed on as if it were whole."""
    connections = []

    async def handler(request):
        connections.append(None)
        if len(connections) == 1:
            resp = web.StreamResponse()
            resp.enable_chunked_encoding()
            await resp.prepare(request)
            await resp.write(b'{"n": 0, "truncated": tr')
            await resp.write_eof()
            return resp
        return await _stream_one_payload(request, {'n': 1})

    async def run():
        runner, url = await _start_server(handler)
        try:
            return await _collect(url, 1)
        finally:
            await runner.cleanup()

    assert _run(run()) == [{'n': 1}]


def test_reconnects_when_the_server_says_no():
    """An error response is not read as if it were a payload."""
    connections = []

    async def handler(request):
        connections.append(None)
        if len(connections) == 1:
            return web.Response(status=503, text='gateway is having a moment\n')
        return await _stream_one_payload(request, {'n': 1})

    async def run():
        runner, url = await _start_server(handler)
        try:
            return await _collect(url, 1)
        finally:
            await runner.cleanup()

    assert _run(run()) == [{'n': 1}]


def test_reconnects_when_the_server_answers_not_200():
    """A 2xx that is not 200 has a body too, and raise_for_status() lets
    it through: it must not be read as if it were a payload."""
    connections = []

    async def handler(request):
        connections.append(None)
        if len(connections) == 1:
            return web.Response(status=201, text='{"created": true}\n')
        return await _stream_one_payload(request, {'n': 1})

    async def run():
        runner, url = await _start_server(handler)
        try:
            return await _collect(url, 1)
        finally:
            await runner.cleanup()

    assert _run(run()) == [{'n': 1}]
    assert len(connections) == 2


def test_reconnects_when_the_server_hangs_up_before_answering():
    """A server that takes the request and then drops the connection is
    reconnected to. aiohttp retries an idempotent request once by itself,
    so this has to happen twice before listen() is the one to handle it."""
    connections = []

    async def handle(reader, writer):
        connections.append(None)
        await reader.readuntil(b'\r\n\r\n')
        if len(connections) <= 2:
            # Take the request, then hang up without answering it.
            writer.close()
            await writer.wait_closed()
            return
        writer.write(b'HTTP/1.1 200 OK\r\n'
                     b'Content-Type: application/vnd.pypubsub-stream\r\n'
                     b'\r\n'
                     b'{"n": 1}\n')
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    async def run():
        server = await asyncio.start_server(handle, '127.0.0.1', 0)
        port = server.sockets[0].getsockname()[1]
        try:
            return await _collect(f'http://127.0.0.1:{port}/', 1)
        finally:
            server.close()
            await server.wait_closed()

    assert _run(run()) == [{'n': 1}]


def test_reconnects_when_a_payload_line_exceeds_the_read_buffer():
    """A payload line longer than the read buffer makes readuntil() raise
    LineTooLong, which is neither a ValueError nor a connection error, so
    without a catch it takes listen() down instead of reconnecting."""
    connections = []

    async def handler(request):
        connections.append(None)
        if len(connections) == 1:
            resp = web.StreamResponse()
            resp.enable_chunked_encoding()
            await resp.prepare(request)
            # A single line past the stream's limit. aiohttp sizes it as a
            # multiple of the read buffer, so be safely past any multiple.
            await resp.write(b'{"blob": "'
                             + b'x' * (3 * asfpy.pubsub.DEFAULT_READ_BUFFER_SIZE)
                             + b'"}\n')
            await resp.write_eof()
            return resp
        return await _stream_one_payload(request, {'n': 1})

    async def run():
        runner, url = await _start_server(handler)
        try:
            return await _collect(url, 1)
        finally:
            await runner.cleanup()

    assert _run(run()) == [{'n': 1}]
    assert len(connections) == 2


# The header the server reads, spelled out rather than taken from the module,
# so that a test failure means the wire is wrong and not merely the name.
CURSOR_HEADER = 'X-Fetch-Since-Cursor'


def test_reconnect_asks_for_what_it_missed():
    """A reconnect names the last payload seen, so the server can replay
    whatever it published while nobody was listening."""
    asked = []

    async def handler(request):
        asked.append(request.headers.get(CURSOR_HEADER))
        if len(asked) == 1:
            return await _stream_one_payload(request, {'n': 0, 'pubsub_cursor': 'first'})
        # What the server replays for anyone resuming from 'first'.
        return await _stream_one_payload(request, {'n': 1, 'pubsub_cursor': 'second'})

    async def run():
        runner, url = await _start_server(handler)
        try:
            return await _collect(url, 2)
        finally:
            await runner.cleanup()

    payloads = _run(run())
    assert [p['n'] for p in payloads] == [0, 1]
    assert asked == [None, 'first']


def test_a_keepalive_does_not_move_the_cursor():
    """Keepalives carry no cursor; resuming from one would skip events."""
    asked = []

    async def handler(request):
        asked.append(request.headers.get(CURSOR_HEADER))
        resp = web.StreamResponse()
        resp.enable_chunked_encoding()
        await resp.prepare(request)
        if len(asked) == 1:
            await resp.write(json.dumps({'n': 0, 'pubsub_cursor': 'first'}).encode() + b'\n')
            await resp.write(json.dumps({'stillalive': 1}).encode() + b'\n')
        else:
            await resp.write(json.dumps({'n': 1, 'pubsub_cursor': 'second'}).encode() + b'\n')
        await resp.write_eof()
        return resp

    async def run():
        runner, url = await _start_server(handler)
        try:
            return await _collect(url, 3)
        finally:
            await runner.cleanup()

    payloads = _run(run())
    assert payloads == [{'n': 0, 'pubsub_cursor': 'first'},
                        {'stillalive': 1},
                        {'n': 1, 'pubsub_cursor': 'second'}]
    assert asked == [None, 'first']


async def _listen_for(url, seconds):
    """Read listen(URL) for SECONDS, discarding what it yields, and stop."""
    events = asfpy.pubsub.listen(url)

    async def drain():
        async for _ in events:
            pass

    try:
        await asyncio.wait_for(drain(), timeout=seconds)
    except asyncio.TimeoutError:
        pass
    finally:
        await events.aclose()


def test_a_server_that_keeps_hanging_up_is_backed_off_from():
    """A payload does not show a connection was healthy: a server that sends
    one keepalive and hangs up sends one every time, and must not be
    reconnected to as fast as it can answer."""
    connections = []

    async def handler(request):
        connections.append(None)
        return await _stream_one_payload(request, {'stillalive': 1})

    async def run():
        runner, url = await _start_server(handler)
        try:
            await _listen_for(url, 1.5)
        finally:
            await runner.cleanup()

    _run(run())
    # No wait before the second connection, two seconds before the third.
    assert len(connections) == 2


def test_a_connection_that_held_starts_the_backoff_over(monkeypatch):
    """Once a connection has stayed up, whatever ended it was not the server
    refusing to stay up, and the next one is opened straight away."""
    monkeypatch.setattr(asfpy.pubsub, 'HEALTHY_CONNECTION_SECONDS', 0.3)
    opened = []
    held_until = []

    async def handler(request):
        loop = asyncio.get_running_loop()
        opened.append(loop.time())
        if len(opened) < 3:
            return await _stream_one_payload(request, {'stillalive': 1})
        resp = web.StreamResponse()
        resp.enable_chunked_encoding()
        await resp.prepare(request)
        if len(opened) == 3:
            for _ in range(5):
                await resp.write(json.dumps({'stillalive': 1}).encode() + b'\n')
                await asyncio.sleep(0.1)
            held_until.append(loop.time())
        await resp.write_eof()
        return resp

    async def run():
        runner, url = await _start_server(handler)
        try:
            # 0s and 2s of backoff, then the third connection holds for 0.5s.
            await _listen_for(url, 4)
        finally:
            await runner.cleanup()

    _run(run())
    assert len(opened) >= 4
    # Continuing the backoff would have waited 6s here.
    assert opened[3] - held_until[0] < 1.0
