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
            return
        writer.write(b'HTTP/1.1 200 OK\r\n'
                     b'Content-Type: application/vnd.pypubsub-stream\r\n'
                     b'\r\n'
                     b'{"n": 1}\n')
        await writer.drain()
        writer.close()

    async def run():
        server = await asyncio.start_server(handle, '127.0.0.1', 0)
        port = server.sockets[0].getsockname()[1]
        try:
            return await _collect(f'http://127.0.0.1:{port}/', 1)
        finally:
            server.close()
            await server.wait_closed()

    assert _run(run()) == [{'n': 1}]
