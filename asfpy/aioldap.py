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

"""Asynchronous LDAP client."""
#
# TYPICAL USAGE:
#
# ### TBD. look at code for now.
#

import asyncio
import logging
import concurrent.futures
import threading

import bonsai

LOGGER = logging.getLogger(__name__)


class ASF_LDAPConnection:
    def __init__(self, executor, loop, conn):
        # Shared Executor across 1 or more threads.
        self.executor = executor

        # bonsai.LDAPConnection ties itself to a loop. Thus, whatever
        # loop is used to create the connection must also be used to
        # perform its operations. Remember our loop.
        self.loop = loop

        # The underlying LDAP connection, tied to this thread/loop.
        self.conn = conn

    def close(self):
        self.conn.close()
        self.conn = None  # ensure self is unusable

    async def search(self, base, attrs, loop=None):
        if loop is None:
            loop = asyncio.get_running_loop()

        def run_search():
            # This synchronous function is now running within a thread
            # of the Executor. Use some async to run the LDAP search.
            return self.loop.run_until_complete(
                self.conn.search(base,
                                 bonsai.LDAPSearchScope.SUBTREE,
                                 attrlist=attrs))

        # Wait within the caller's loop for the result.
        return await loop.run_in_executor(self.executor, run_search)

    ### TBD ASF-specific custom methods? or use app-specific subclasses?


class ASF_LDAPClient:

    CONNECTION_CLASS = ASF_LDAPConnection

    def __init__(self, uri, binddn, bindpw):
        self.client = bonsai.LDAPClient(uri)
        self.client.set_credentials("SIMPLE", binddn, bindpw)
        self.client.set_cert_policy("allow")  # TODO: Load our cert(?)

        ### thread-local storage wasn't working. Use a nuke.
        self.loops = { }

        def new_loop():
            t = threading.current_thread()
            print('NEW-THREAD:', t)

            # Construct an event loop for each thread in the Executor.
            self.loops[t] = asyncio.new_event_loop()

        self.executor = concurrent.futures.ThreadPoolExecutor(
            thread_name_prefix='aioldap', initializer=new_loop)

    def connect(self, loop=None):
        if loop is None:
            loop = asyncio.get_running_loop()

        # Hack around GnuTLS bug with async.
        # See: https://github.com/noirello/bonsai/issues/25
        #
        # In an executor thread, we'll perform the synchronous connection,
        # so that the event loop will not be blocked.
        #
        # TLOOP was been created when the thread started, and holds
        # the event loop for all operations on this thread.
        def blocking_connect():
            tloop = self.loops[threading.current_thread()]
            async def do_connect():
                ### for testing: pretend this connection blocks
                #import time; time.sleep(8)

                # Tell bonsai to connect synchronously.
                bonsai.set_connect_async(False)
                try:
                    return await self.client.connect(is_async=True)
                finally:
                    # Make sure this always gets reset.
                    bonsai.set_connect_async(True)

            conn = tloop.run_until_complete(do_connect())
            return self.CONNECTION_CLASS(self.executor, tloop, conn)

        future = loop.run_in_executor(self.executor, blocking_connect)
        #print('CONN-FUTURE:', future)
        return ConnectContextManager(future)

# For debugging, we want the ASF_ prefix, but callers can skip it.
LDAPClient = ASF_LDAPClient


class ConnectContextManager:
    def __init__(self, future):
        self.future = future

    async def __aenter__(self):
        self.conn = await self.future
        return self.conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.conn.close()


def test_conns(client):
    # Run three tasks in parallel: heartbeat, connA, connB. The latter
    # two will open, run a couple LDAP queries, then close. Then re-open.
    # These will run in one event loop (the LDAPClient has some private
    # loops; no peeking).
    #
    # Should see: smooth heartbeat, even when an artifical delay is
    # introduced to the connect() process.

    # Some random services to read
    SERVICE_BASE = 'cn=%s,ou=groups,ou=services,dc=apache,dc=org'
    SERVICES = [ 'board', 'infrastructure-root', 'asf-secretary', ]

    # Start hanging tasks off this.
    loop = asyncio.new_event_loop()

    t0 = loop.time()
    def ts():
        return f'[{loop.time() - t0 :.2f}]'

    async def heartbeat():
        while True:
            print(f'{ts()} heartbeat')
            await asyncio.sleep(2)

    import random
    async def conn_usage(name):
        while True:
            # Stagger the connections
            await asyncio.sleep(random.randint(0, 3))
            async with client.connect() as conn:
                for _ in range(5):
                    s = random.choice(SERVICES)
                    rv = await conn.search(SERVICE_BASE % (s,), ['owner',])
                    print(f'{ts()} CONN[{name}]: RV=', rv)
                    await asyncio.sleep(random.randint(1, 3))

    loop.create_task(heartbeat())
    loop.create_task(conn_usage('A'))
    loop.create_task(conn_usage('B'))

    loop.run_forever()


if __name__ == '__main__':
    import os, getpass
    dn = 'uid=%s,ou=people,dc=apache,dc=org' % ('gstein',)
    p = os.environ.get('AIOLDAP_PASSWORD') or getpass.getpass()
    c = ASF_LDAPClient('ldaps://ldap-us.apache.org:636', dn, p)
    test_conns(c)
