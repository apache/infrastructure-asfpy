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
import os
import ssl
import concurrent.futures

import bonsai

# TIMEOUTS
#
# Two limits apply, to two different parts of the work, because nothing
# else was found to work for both.
#
# 1. Reaching the server. While a connection is being made (the TCP
#    connection, and the TLS handshake that follows it for ldaps://),
#    bonsai waits inside libldap, holding Python's global lock. If the
#    server does not answer, EVERY thread of the process stops with it,
#    the event loop included, and the timeout that bonsai's connect()
#    takes does not end the wait. What does end it is libldap's own
#    network timeout. bonsai has no call to set that, but libldap reads
#    it from the environment, once, when it is first used in a process:
#    so it is set here, as this module is imported, unless the
#    environment already has a value. The process still stands still
#    for that long when the server does not answer: keep it short.
#
#    To use another value, set LDAPNETWORK_TIMEOUT (in seconds) in the
#    environment of the process. Note that this then applies to anything
#    in the process that uses libldap, and to the programs it starts,
#    such as ldapsearch. A value from ldap.conf is not used: the
#    environment comes first.
NETWORK_TIMEOUT = 5
os.environ.setdefault('LDAPNETWORK_TIMEOUT', str(NETWORK_TIMEOUT))

# 2. Waiting for an answer, once connected: the bind, a search, a
#    whoami. This is a wait within asyncio, in a thread of its own, and
#    does not stop anything else. It is the TIMEOUT argument of
#    ASF_LDAPClient, and of search() and whoami(), in seconds; None
#    waits for as long as it takes.
DEFAULT_TIMEOUT = 30

# Connections are made synchronously, in a thread. That is bonsai's
# default, and it is set here to say so: with asynchronous connecting
# there is a bug with GnuTLS, and bonsai then replaces the network
# timeout above with one of its own.
# See: https://github.com/noirello/bonsai/issues/25
# and: https://github.com/noirello/bonsai/issues/69
#
# This is a setting of the whole process, so it is made once. It used
# to be turned off before each connection and on again after it, and a
# connection that turned it on again, while another was being made in
# another thread, turned it on for that one as well.
bonsai.set_connect_async(False)

# Re-map the LDAPSearchScope constants to our namespace.
# These can now be used as (eg.) asfpy.aioldap.SCOPE.SUBTREE
from bonsai import LDAPSearchScope as SCOPE


LOGGER = logging.getLogger(__name__)

# THE SERVER'S CERTIFICATE
#
# The certificate that the server presents is verified: that it was
# issued by a certificate authority that is trusted, and for the host
# name in the URI. Without that, whoever can get between this process
# and the server can answer in the server's place, and is handed the
# password of every bind.
#
# Which authorities are trusted is, in this order:
#   1. the CA_CERT argument of ASF_LDAPClient, a file of certificates;
#   2. what libldap is configured with: LDAPTLS_CACERT or
#      LDAPTLS_CACERTDIR in the environment, or TLS_CACERT or
#      TLS_CACERTDIR in ldap.conf;
#   3. the certificate authorities of the system.
#
# The third is not what libldap does by itself: with nothing configured
# it trusts nobody, and Debian's ldap.conf, which names the system's
# file, is in a package (libldap-common) that is often not installed.

# Where to look for libldap's configuration, as libldap does.
LDAP_CONF_FILES = ['/etc/ldap/ldap.conf', '/etc/openldap/ldap.conf',
                   '/usr/local/etc/openldap/ldap.conf', '~/ldaprc', '~/.ldaprc']

# Where the certificate authorities of the system are kept, on the
# systems we know. The first that exists is used.
SYSTEM_CA_FILES = ['/etc/ssl/certs/ca-certificates.crt',  # Debian, Ubuntu, Alpine
                   '/etc/pki/tls/certs/ca-bundle.crt',    # Fedora, RHEL
                   '/etc/ssl/ca-bundle.pem',              # openSUSE
                   '/etc/ssl/cert.pem']                   # macOS, the BSDs


def libldap_has_ca():
    "Is libldap told, by the environment or an ldap.conf, whom to trust?"
    if os.environ.get('LDAPTLS_CACERT') or os.environ.get('LDAPTLS_CACERTDIR'):
        return True
    if 'LDAPNOINIT' in os.environ:
        return False  # libldap then reads no ldap.conf at all
    files = list(LDAP_CONF_FILES)
    if os.environ.get('LDAPCONF'):
        files.append(os.environ['LDAPCONF'])
    for name in files:
        try:
            with open(os.path.expanduser(name), encoding='utf-8', errors='replace') as conf:
                if any(line.split()[:1] and line.split()[0].upper() in ('TLS_CACERT', 'TLS_CACERTDIR')
                       for line in conf):
                    return True
        except OSError:
            pass
    return False


def system_ca_file():
    "The file of the system's certificate authorities, or None."
    candidates = [os.environ.get('SSL_CERT_FILE'), ssl.get_default_verify_paths().cafile]
    for name in candidates + SYSTEM_CA_FILES:
        if name and os.path.isfile(name):
            return name
    return None


# For a TIMEOUT argument that was not given, as None is a value for it.
_UNSET = object()


class ASF_LDAPConnection:
    def __init__(self, client, executor, timeout=DEFAULT_TIMEOUT):
        # NOTE: must be instantiated within one of the EXECUTOR threads.

        # How long to wait for the server's answer to the bind, and to
        # each search() and whoami() that does not say otherwise.
        self.timeout = timeout

        # Shared Executor holding one or more threads.
        self.executor = executor

        # bonsai.LDAPConnection ties itself to a loop. Thus, whatever
        # loop is used to create the connection must also be used to
        # perform its operations. We will construct that loop here,
        # and use it for all bonsai actions. It does not have any
        # thread affinity, until it is running. Thus, we can use this
        # loop within any thread of the Executor.
        self.loop = asyncio.new_event_loop()

        # In THIS executor thread, we'll perform the synchronous
        # connection, so that the main thread's event loop will
        # not be blocked. (But see TIMEOUTS, at the top of this module,
        # for when the server does not answer.)
        async def do_connect():
            ### for testing: pretend this connection blocks
            #import time; time.sleep(5)

            # Ties to self.loop (the running loop now).
            return await client.connect(is_async=True, timeout=timeout)

        # The underlying LDAP connection, tied to our loop.
        try:
            self.conn = self.loop.run_until_complete(do_connect())
        except BaseException:
            # No connection, so nobody will call close(): give back the
            # loop's file descriptors now, and not when the garbage
            # collector gets round to it. A wrong password ends up here.
            self.loop.close()
            raise

    def close(self):
        if self.conn is not None:
            self.conn.close()
        self.conn = None  # ensure self is unusable
        # The loop holds three file descriptors. Left open, they are only
        # given back when the garbage collector finds the loop.
        if not self.loop.is_closed():
            self.loop.close()
        # Let go of the client's threads too, so that they can stop once
        # the client is gone, though somebody still holds this object.
        self.executor = None

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

    async def search(self, base, attrs, scope=SCOPE.SUBTREE, loop=None,
                     timeout=_UNSET):
        """Search below BASE for ATTRS.

        Waits TIMEOUT seconds for the server, or as long as the client
        was told to if TIMEOUT is not given, and then raises
        asyncio.TimeoutError. None waits for as long as it takes.
        """
        if timeout is _UNSET:
            timeout = self.timeout
        return await self.use_loop(loop,
                                   self.conn.search,
                                   base,
                                   scope,
                                   attrlist=attrs,
                                   timeout=timeout)

    async def whoami(self, loop=None, timeout=_UNSET):
        "As search(), for TIMEOUT."
        if timeout is _UNSET:
            timeout = self.timeout
        return await self.use_loop(loop, self.conn.whoami, timeout=timeout)

    ### TBD ASF-specific custom methods? or use app-specific subclasses?


class ASF_LDAPClient:

    CONNECTION_CLASS = ASF_LDAPConnection

    def __init__(self, uri, binddn, bindpw, ca_cert=None, cert_policy='demand',
                 timeout=DEFAULT_TIMEOUT):
        """A client for the server at URI, that binds as BINDDN.

        The server's certificate is verified. CA_CERT is a file with the
        certificates of the authorities to trust, for a server whose
        certificate was not issued by one that the system trusts already:
        see THE SERVER'S CERTIFICATE, at the top of this module.

        CERT_POLICY is bonsai's: 'demand' verifies, and 'allow' and
        'never' do not, and are for a test server only. Use the same
        policy for every client of a process. libldap keeps what it set
        up for the first connection, so a later client with another
        policy, and no CA_CERT of its own, gets the policy of the first.

        TIMEOUT is how long to wait, in seconds, for the server's answer
        to the bind and to each search; None waits for as long as it
        takes. It is not how long to wait for the connection itself to be
        made: see TIMEOUTS, at the top of this module.
        """
        self.timeout = timeout
        self.client = bonsai.LDAPClient(uri)
        self.client.set_credentials("SIMPLE", binddn, bindpw)
        self.client.set_cert_policy(cert_policy)
        if ca_cert is None and not libldap_has_ca():
            ca_cert = system_ca_file()
        if ca_cert is not None:
            self.client.set_ca_cert(ca_cert)

        self.executor = concurrent.futures.ThreadPoolExecutor(
            thread_name_prefix='aioldap')

    def connect(self, loop=None):
        if loop is None:
            loop = asyncio.get_running_loop()

        # Run (blocking) in an executor thread.
        def blocking_connect():
            return self.CONNECTION_CLASS(self.client, self.executor,
                                         timeout=self.timeout)

        future = loop.run_in_executor(self.executor, blocking_connect)
        #print('CONN-FUTURE:', future)
        return ConnectContextManager(future)

    def close(self):
        """Stop the threads of this client. Its connections can no longer
        be used, and no new ones can be made.

        Without this the threads stop when the client, and every
        connection it made, has been garbage collected. Call it when the
        client is done with, if clients are made often.
        """
        self.executor.shutdown(wait=False)

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
        self.conn = None


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
    import getpass
    u = os.environ.get('AIOLDAP_USER') or getpass.getuser()
    dn = 'uid=%s,ou=people,dc=apache,dc=org' % u
    p = os.environ.get('AIOLDAP_PASSWORD') or getpass.getpass(f"Password for {u}: ")
    c = ASF_LDAPClient('ldaps://ldap-us.apache.org:636', dn, p)
    test_conns(c)
