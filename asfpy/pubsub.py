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

""" PyPubSub listener class. """
#
# TYPICAL USAGE:
#
#   async for payload in listen(PUBSUB_URL):
#
# This will produce a series of payloads, forever.
#
# NOTE: this listener is intended for pypubsub, which terminates
#   payloads with a newline. The old svnpubsub used NUL characters,
#   so this client will not work with that server.
#

import requests
import requests.exceptions
import json
import time
import sys
import asyncio
import logging
import warnings

import aiohttp


LOGGER = logging.getLogger(__name__)

# The server sends keepalives every 5 seconds, so we should see
# activity well within this timeout period.
DEFAULT_INACTIVITY_TIMEOUT = 11
### for debug:
#DEFAULT_INACTIVITY_TIMEOUT = 4.5


async def listen(pubsub_url, username=None, password=None, timeout=None):

    if username:
        auth = aiohttp.BasicAuth(username, password)
    else:
        auth = None

    if timeout is None:
        timeout = DEFAULT_INACTIVITY_TIMEOUT
    ct = aiohttp.ClientTimeout(sock_read=timeout)

    async with aiohttp.ClientSession(auth=auth, timeout=ct) as session:

        # Retry immediately, and then back it off.
        delay = 0.0

        ### tbd: look at event loop, to see if it has been halted
        while True:
            LOGGER.debug('Opening new connection...')
            try:
                async for payload in _process_connection(session, pubsub_url):
                    if not payload:
                        pass  ### tbd?: event loop killed or hit EOF

                    # We got a payload, so reset the DELAY.
                    delay = 0.0

                    yield payload

            except (ConnectionRefusedError,
                    aiohttp.ClientConnectorError,
                    aiohttp.ServerTimeoutError,
                    aiohttp.ClientPayloadError,
                    ) as e:
                LOGGER.error(f'Connection failed ({type(e).__name__}: {e})'
                             f', reconnecting in {delay} seconds')
                await asyncio.sleep(delay)

                # Back off on the delay. Step it up from 0s, doubling each
                # time, and top out at 30s retry. Steps: 0, 2, 6, 14, 30.
                delay = min(30.0, (delay + 1.0) * 2)


async def _process_connection(session, pubsub_url):
    # Connect to pubsub and listen for payloads.
    async with session.get(pubsub_url) as conn:

        #print('LIMITS:', conn.content.get_read_buffer_limits())

        while True:

            # The pubsub server defines stream payloads as:
            #    ENCODED_JSON(payload)+"\n"
            #
            # Due to the encoding, bare newlines will not occur
            # within the encoded part. Thus, we can read content
            # until we find a newline.
            #
            # Note: this newline is in RAW, but the json loader
            # ignores it.
            try:
                raw = await conn.content.readuntil(b'\n')
            except ValueError as e:
                LOGGER.error(f'Saw "{e}"; re-raising as ClientPayloadError to close/reconnect')
                raise aiohttp.ClientPayloadError(f're-raised from ValueError in readuntil()')

            if not raw:
                # We just hit EOF.
                yield None

            yield json.loads(raw)


def test_listening():
    logging.basicConfig(level=logging.DEBUG)

    import time
    start = time.time()
    count = 0

    # We'll say "now" is when we believe the connection to be alive.
    last_traffic = time.time()

    async def report_stats():
        while True:
            # NOTE: do not set this lower than 60, or at startup,
            # DURATION will be zero, creating a div-by-zero error.
            await asyncio.sleep(70)

            duration = int((time.time() - start) / 60)
            alive_since = int(time.time() - last_traffic)
            print(f'[{duration}m] {count} events.  {count/duration:.1f}/min'
                  f'  traffic: {alive_since}s ago')

    async def print_events():
        async for payload in listen('https://pubsub.apache.org:2070/'):
            nonlocal last_traffic
            last_traffic = time.time()

            if 'stillalive' not in payload:
                print(f'PAYLOAD: [{payload.get("pubsub_path", "none")}]'
                      f'  KEYS: {sorted(payload.keys())}')
                nonlocal count
                count += 1

    async def run_test():
        await asyncio.gather(report_stats(), print_events())

    asyncio.run(run_test())


class Listener:
    """ Generic listener for pubsubs. Grabs each payload and runs process() on them. """

    def __init__(self, url):
        warnings.warn('use listen_forever() instead', DeprecationWarning)
        self.url = url
        self.connection = None

    def attach(self, func, **kwargs):
        raw = kwargs.get('raw', False)
        debug = kwargs.get('debug', False)
        since = kwargs.get('since', -1)
        auth = kwargs.get('auth', None)
        listen_forever(func, self.url, auth, raw, since, debug)


def listen_forever(func, url, auth=None, raw=False, since=-1, debug=False):
    """Listen on URL forever, calling FUNC for each payload.

    ### more docco about FUNC calling, AUTH, RAW, SINCE, DEBUG
    """
    warnings.warn('use listen() instead', DeprecationWarning)

    while True:
        if debug:
            message("[INFO] Subscribing to stream at %s\n", url, fp=sys.stdout)
        connection = None
        while not connection:
            try:
                headers = {
                    'User-Agent': 'python/asfpy'
                }
                if since != -1:
                    headers['X-Fetch-Since'] = str(since)
                connection = requests.get(url, headers=headers, auth=auth, timeout=30, stream=True)
                if debug:
                    message("[INFO] Subscribed, reading stream\n", fp=sys.stdout)
            except requests.exceptions.RequestException:
                message("[WARNING] Could not connect to pubsub service at %s,"
                        " retrying in 10s...\n", url, sleep=10)
                continue
            if not connection:
                if debug:
                    message("[WARNING] %s did not respond with a streamable connection,"
                            " reconnecting in 10 seconds\n", url, sleep=10)
        try:
            body = ""
            for chunk in connection.iter_content(chunk_size=None):
                body += chunk.decode('utf-8', errors='ignore')
                # pypubsub/gitpubsub payloads end in \n, svnpubsub payloads end in \0:
                if body[-1] in ["\n", "\x00"]:
                    try:
                        payload = json.loads(body.rstrip("\r\n\x00"))
                    except ValueError as detail:
                        if debug:
                            message("[WARNING] Bad JSON or something: %s\n", detail)
                        # No payload. Circle back around for another.
                        payload = None
                    if not raw and isinstance(payload, dict):
                        payload = payload.get('payload')
                    if payload:
                        # Since we have a valid payload, we do not want to repeat it.
                        # Thus, set `since` to -1 now, so as to not have an x-fetch-since
                        # header on the next retry in case this connection fails at some point.
                        since = -1
                        func(payload)
                    body = ""
        except requests.exceptions.RequestException:
            if debug:
                message("[WARNING] Disconnected from %s, reconnecting\n", url, sleep=2)
                continue
        if debug:
            message("Connection to %s was closed, reconnecting in 10 seconds\n", url, sleep=10)


def message(fmt, *args, sleep=None, fp=sys.stderr):
    fp.write(fmt % args)
    fp.flush()
    if sleep:
        time.sleep(sleep)


if __name__ == '__main__':
    ### pass PUBSUB_URL ?
    test_listening()
