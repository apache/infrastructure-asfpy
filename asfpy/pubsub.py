#!/usr/bin/env python
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

import requests
import requests.exceptions
import json
import time
import sys


class Listener:
    """ Generic listener for pubsubs. Grabs each payload and runs process() on them. """

    def __init__(self, url):
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
    # For example:
    # $ python3 pubsub.py http://pubsub.apache.org:2069/git
    def print_payload(payload):
        print('RECEIVED:', payload)
    listen_forever(print_payload, sys.argv[1], debug=True, raw=True)
