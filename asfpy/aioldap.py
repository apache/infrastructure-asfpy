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

# Map the various bonsai exceptions into our namespace.
from bonsai import errors

# Re-map the LDAPSearchScope constants to our namespace.
# These can now be used as (eg.) asfpy.aioldap.SCOPE.SUBTREE
from bonsai import LDAPSearchScope as SCOPE


LOGGER = logging.getLogger(__name__)


class ASF_LDAPConnection:
    def __init__(self, client, executor):
        # NOTE: must be instantiated within one of the EXECUTOR threads.

        # Shared Executor holding one or more threads.
        self.executor = executor

        # bonsai.LDAPConnection ties itself to a loop. Thus, whatever
        # loop is used to create the connection must also be used to
        # perform its operations. We will construct that loop here,
        # and use it for all bonsai actions. It does not have any
        # thread affinity, until it is running. Thus, we can use this
        # loop within any thread of the Executor.
        self.loop = asyncio.new_event_loop()

        # Hack around GnuTLS bug with async.
        # See: https://github.com/noirello/bonsai/issues/25
        # and: https://github.com/noirello/bonsai/issues/69
        #
        # In THIS executor thread, we'll perform the synchronous
        # connection, so that the main thread's event loop will
        # not be blocked.
        async def do_connect():
            ### for testing: pretend this connection blocks
            #import time; time.sleep(5)

            # Tell bonsai to connect synchronously.
            bonsai.set_connect_async(False)
            try:
                # Ties to self.loop (the running loop now).
                return await client.connect(is_async=True)
            finally:
                # Make sure this always gets reset.
                bonsai.set_connect_async(True)

        # The underlying LDAP connection, tied to our loop.
        self.conn = self.loop.run_until_complete(do_connect())

    def close(self):
        self.conn.close()
        self.conn = None  # ensure self is unusable

    async def use_loop(self, loop, method, *args, **kw):
        "Running in LOOP, run/wait for METHOD with *ARGS and **KW."
        if loop is None:
            loop = asyncio.get_running_loop()

        def call_method():
            # This synchronous function is now running within a thread
            # of the Executor. Use some async to run the LDAP connection's
            # method within our loop.
            return self.loop.run_until_complete(method(*args, **kw))

        # Wait within the caller's loop for the result.
        return await loop.run_in_executor(self.executor, call_method)

    async def search(self, base, attrs, scope=SCOPE.SUBTREE, loop=None):
        return await self.use_loop(loop,
                                   self.conn.search,
                                   base,
                                   scope,
                                   attrlist=attrs)

    async def whoami(self, loop=None):
        return await self.use_loop(loop, self.conn.whoami)

    ### TBD ASF-specific custom methods? or use app-specific subclasses?


class ASF_LDAPClient:

    CONNECTION_CLASS = ASF_LDAPConnection

    def __init__(self, uri, binddn, bindpw):
        self.client = bonsai.LDAPClient(uri)
        self.client.set_credentials("SIMPLE", binddn, bindpw)
        self.client.set_cert_policy("allow")  # TODO: Load our cert(?)

        self.executor = concurrent.futures.ThreadPoolExecutor(
            thread_name_prefix='aioldap')

    def connect(self, loop=None):
        if loop is None:
            loop = asyncio.get_running_loop()

        # Run (blocking) in an executor thread.
        def blocking_connect():
            return self.CONNECTION_CLASS(self.client, self.executor)

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

    async def print_me():
        async with client.connect() as conn:
            print('ME:', await conn.whoami())

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
                    rv = await conn.search(SERVICE_BASE % (s,), ['owner', 'member',])
                    print(f'{ts()} CONN[{name}]: RV=', rv)
                    await asyncio.sleep(random.randint(1, 3))
                # between reconnections
                await asyncio.sleep(random.randint(0, 5))

    loop.create_task(print_me())
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
