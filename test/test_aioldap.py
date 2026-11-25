#!/usr/bin/env python3
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

"""Tests of asfpy.aioldap against a real LDAP server (see conftest.py).

They are skipped where bonsai or slapd is not installed.
"""

import asyncio
import contextlib
import itertools
import os
import signal
import socket
import threading
import time
import types

import pytest

bonsai = pytest.importorskip('bonsai', reason='needs the aioldap extra')

import asfpy.aioldap  # noqa: E402  pylint: disable=wrong-import-position


def open_files():
    "How many file descriptors this process has open."
    if not os.path.isdir('/proc/self/fd'):
        pytest.skip('needs /proc to count open files')
    return len(os.listdir('/proc/self/fd'))


def client_for(server, password=None, **kwargs):
    "A client that trusts the authority of the test server's certificate."
    kwargs.setdefault('ca_cert', server.ca_cert)
    return asfpy.aioldap.LDAPClient(server.uri, server.user_dn, password or server.password, **kwargs)


@contextlib.contextmanager
def silent_server():
    """A server that accepts connections and then says nothing, as an LDAP
    server does that is overloaded, or has stopped. Gives its port."""
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(20)
    accepted = []

    def accept():
        with contextlib.suppress(OSError):
            while True:
                accepted.append(listener.accept()[0])

    threading.Thread(target=accept, daemon=True).start()
    try:
        yield listener.getsockname()[1]
    finally:
        listener.close()
        for conn in accepted:
            conn.close()


def stop(server):
    """Make the LDAP server stand still, until it is sent SIGCONT. The
    signal takes a moment to do that, so wait until it has."""
    os.kill(server.pid, signal.SIGSTOP)
    stat = f'/proc/{server.pid}/stat'
    for _ in range(200):
        if not os.path.exists(stat):
            time.sleep(0.2)  # no /proc to ask: give it time instead
            break
        with open(stat, encoding='ascii') as f:
            if f.read().rsplit(')', 1)[1].split()[0] == 'T':
                break
        time.sleep(0.01)


@contextlib.contextmanager
def stopped(server):
    "The LDAP server stands still for as long as this lasts."
    stop(server)
    try:
        yield
    finally:
        os.kill(server.pid, signal.SIGCONT)


# ---- The settings that are made when the module is imported ----

def test_network_timeout_is_set_for_libldap(run_python):
    "libldap is given a time limit for reaching the server, as it has none of its own"
    done = run_python("import os, asfpy.aioldap as a; print(os.environ['LDAPNETWORK_TIMEOUT'], a.NETWORK_TIMEOUT)")
    assert done.out == '5 5', done.err


def test_network_timeout_from_the_environment_is_kept(run_python):
    done = run_python("import os, asfpy.aioldap; print(os.environ['LDAPNETWORK_TIMEOUT'])",
                      env={'LDAPNETWORK_TIMEOUT': '42'})
    assert done.out == '42', done.err


def test_default_timeout():
    assert asfpy.aioldap.DEFAULT_TIMEOUT == 30
    client = asfpy.aioldap.LDAPClient('ldaps://127.0.0.1:1', 'uid=x', 'y')
    assert client.timeout == 30
    assert asfpy.aioldap.LDAPClient('ldaps://127.0.0.1:1', 'uid=x', 'y', timeout=None).timeout is None
    client.close()


# ---- What worked before still works ----

def test_search_and_whoami(ldap_server):
    async def main():
        client = client_for(ldap_server)
        async with client.connect() as conn:
            found = await conn.search(ldap_server.project_base, ['member'])
            who = await conn.whoami()
        client.close()
        return found, who

    found, who = asyncio.run(main())
    assert who == 'dn:' + ldap_server.user_dn
    (project,) = [entry for entry in found if 'member' in entry]
    assert str(project['dn']) == 'cn=httpd,' + ldap_server.project_base
    assert project['member'] == [ldap_server.user_dn]


def test_wrong_password_is_refused(ldap_server):
    async def main():
        async with client_for(ldap_server, password='wrong').connect():
            pass

    with pytest.raises(bonsai.errors.AuthenticationError):
        asyncio.run(main())


def test_several_connections_side_by_side(ldap_server):
    async def one():
        async with client_for(ldap_server).connect() as conn:
            return await conn.whoami()

    async def main():
        return await asyncio.gather(*[one() for _ in range(8)])

    assert asyncio.run(main()) == ['dn:' + ldap_server.user_dn] * 8


# ---- Waiting for an answer has a limit ----

def test_search_gives_up_on_a_server_that_does_not_answer(ldap_server):
    """The server is there for the connection, and then stops. The search
    ends at its time limit, and nothing else is held up meanwhile."""
    beats = []

    async def heartbeat():
        while True:
            beats.append(time.monotonic())
            await asyncio.sleep(0.1)

    async def main():
        pulse = asyncio.ensure_future(heartbeat())
        async with client_for(ldap_server, timeout=1).connect() as conn:
            start = time.monotonic()
            with stopped(ldap_server):
                with pytest.raises(asyncio.TimeoutError):
                    await conn.search(ldap_server.project_base, ['member'])
            waited = time.monotonic() - start
        pulse.cancel()
        return waited

    waited = asyncio.run(main())
    assert 0.9 < waited < 5
    # The event loop went on running while the search waited
    assert max(later - earlier for earlier, later in itertools.pairwise(beats)) < 0.7


def test_search_timeout_can_be_given_for_one_search(ldap_server):
    async def main():
        async with client_for(ldap_server, timeout=30).connect() as conn:
            assert conn.timeout == 30
            start = time.monotonic()
            with stopped(ldap_server):
                with pytest.raises(asyncio.TimeoutError):
                    await conn.search(ldap_server.project_base, ['member'], timeout=0.5)
                with pytest.raises(asyncio.TimeoutError):
                    await conn.whoami(timeout=0.5)
            return time.monotonic() - start

    assert asyncio.run(main()) < 5


def test_search_without_a_time_limit_waits(ldap_server):
    "timeout=None is as it was before: the search waits for the server, however long"
    async def main():
        async with client_for(ldap_server, timeout=None).connect() as conn:
            stop(ldap_server)
            threading.Timer(1.5, os.kill, (ldap_server.pid, signal.SIGCONT)).start()
            start = time.monotonic()
            found = await conn.search(ldap_server.project_base, ['member'])
            return found, time.monotonic() - start

    try:
        found, waited = asyncio.run(main())
    finally:
        os.kill(ldap_server.pid, signal.SIGCONT)
    assert found and waited > 1.2


# ---- Reaching the server has a limit ----

CONNECT = """
import asyncio, sys, time, asfpy.aioldap
async def connect(uri):
    start = time.monotonic()
    try:
        async with asfpy.aioldap.LDAPClient(uri, sys.argv[2], sys.argv[3]).connect() as conn:
            await conn.whoami()
        return 'connected'
    except Exception as e:
        return '%s after %.1f' % (type(e).__name__, time.monotonic() - start)
async def main():
    for uri in sys.argv[1].split(','):
        print(await connect(uri))
asyncio.run(main())
"""


def connect_from_a_new_process(run_python, server, uris, network_timeout='2'):
    "With NETWORK_TIMEOUT as None, the process is left to asfpy's own default."
    code = CONNECT.replace('sys.argv[1]', repr(','.join(uris)))
    code = code.replace('sys.argv[2]', repr(server.user_dn)).replace('sys.argv[3]', repr(server.password))
    env = {'LDAPNETWORK_TIMEOUT': network_timeout} if network_timeout else {}
    env['LDAPTLS_CACERT'] = server.ca_cert  # so that the test server's certificate verifies
    return run_python(code, env=env, timeout=60)


def test_connecting_gives_up_on_a_server_that_does_not_answer(ldap_server, run_python):
    """Without the network timeout this waits for as long as the server
    keeps the connection open, and every thread of the process with it."""
    with silent_server() as port:
        done = connect_from_a_new_process(run_python, ldap_server, [f'ldaps://127.0.0.1:{port}'])
    assert done.out.startswith('ConnectionError after 2.'), (done.out, done.err)
    assert done.seconds < 15


def test_connecting_gives_up_by_default(ldap_server, run_python):
    """Nothing in the environment: asfpy's own limit applies. Before there
    was one, this waited for as long as the server kept the connection."""
    with silent_server() as port:
        done = connect_from_a_new_process(run_python, ldap_server, [f'ldaps://127.0.0.1:{port}'],
                                          network_timeout=None)
    assert done.out.startswith('ConnectionError after 5.'), (done.out, done.err)


def test_connecting_gives_up_after_another_connection_was_made(ldap_server, run_python):
    """The time limit holds for every connection of a process, and not
    only for the first, although libldap reads it only once."""
    with silent_server() as port:
        silent = f'ldaps://127.0.0.1:{port}'
        done = connect_from_a_new_process(run_python, ldap_server, [ldap_server.uri, silent, ldap_server.uri, silent])
    lines = done.out.splitlines()
    assert len(lines) == 4, (done.out, done.err)
    assert lines[0] == lines[2] == 'connected'
    assert lines[1].startswith('ConnectionError after 2.') and lines[3].startswith('ConnectionError after 2.')


def test_nothing_listening_fails_at_once(ldap_server, run_python):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    done = connect_from_a_new_process(run_python, ldap_server, [f'ldaps://127.0.0.1:{port}'])
    assert done.out.startswith('ConnectionError after 0.'), (done.out, done.err)


# ---- What a connection holds is given back ----

def test_closed_connections_leave_no_files_open(ldap_server):
    "Each connection has an event loop of its own, with three file descriptors"
    async def main():
        client = client_for(ldap_server)
        async with client.connect() as conn:
            await conn.whoami()
        before = open_files()
        connections = []
        for _ in range(20):
            async with client.connect() as conn:
                await conn.whoami()
            connections.append(conn)  # held, so the garbage collector does not tidy up for us
        after = open_files()
        assert all(conn.loop.is_closed() and conn.conn is None for conn in connections)
        client.close()
        return before, after

    before, after = asyncio.run(main())
    assert after <= before


def test_failed_connection_closes_its_event_loop(ldap_server, monkeypatch):
    """A wrong password must not cost three file descriptors each time: the
    loop that was made for the connection is closed when the bind fails"""
    made = []
    new_event_loop = asyncio.new_event_loop

    def recording_new_event_loop():
        made.append(new_event_loop())
        return made[-1]

    async def main():
        monkeypatch.setattr(asfpy.aioldap.asyncio, 'new_event_loop', recording_new_event_loop)
        for _ in range(5):
            with pytest.raises(bonsai.errors.AuthenticationError):
                async with client_for(ldap_server, password='wrong').connect():
                    pass

    asyncio.run(main())
    assert len(made) == 5
    assert all(loop.is_closed() for loop in made)


def test_closing_a_connection_twice(ldap_server):
    async def main():
        client = client_for(ldap_server)
        async with client.connect() as conn:
            await conn.whoami()
        conn.close()
        conn.close()
        client.close()

    asyncio.run(main())


def test_closing_a_client_stops_its_threads(ldap_server):
    async def main():
        clients = [client_for(ldap_server) for _ in range(5)]
        threads = []
        for client in clients:
            async with client.connect() as conn:
                await conn.whoami()
            threads.extend(client.executor._threads)  # pylint: disable=protected-access
        assert len(threads) >= 5 and all(thread.is_alive() for thread in threads)
        for client in clients:
            client.close()
        for _ in range(50):
            if not any(thread.is_alive() for thread in threads):
                break
            await asyncio.sleep(0.1)
        return [thread for thread in threads if thread.is_alive()]

    assert asyncio.run(main()) == []


# ---- The server's certificate is verified ----
#
# Each of these is tried in a process of its own: libldap keeps what it
# set up for the first connection of a process.

VERIFY = """
import asyncio, asfpy.aioldap
async def main():
    client = asfpy.aioldap.LDAPClient(URI, DN, PASSWORD, **KWARGS)
    try:
        async with client.connect() as conn:
            print('connected', await conn.whoami())
    except Exception as e:
        print('refused', type(e).__name__)
asyncio.run(main())
"""


def verify(run_python, server, uri=None, env=None, **kwargs):
    "What a new process gets from the test server, with these arguments to LDAPClient: 'connected' or 'refused'"
    code = (VERIFY.replace('URI', repr(uri or server.uri)).replace('DN', repr(server.user_dn))
            .replace('PASSWORD', repr(server.password)).replace('KWARGS', repr(kwargs)))
    done = run_python(code, env=env)
    assert done.out.split()[:1] in (['connected'], ['refused']), (done.out, done.err)
    return done.out.split()[0]


def test_certificate_from_an_unknown_authority_is_refused(ldap_server, run_python):
    """The default. The test server's certificate was issued by an authority
    that nobody trusts, as that of somebody in the middle would be."""
    assert verify(run_python, ldap_server) == 'refused'


def test_certificate_from_a_trusted_authority_is_accepted(ldap_server, run_python):
    assert verify(run_python, ldap_server, ca_cert=ldap_server.ca_cert) == 'connected'


def test_certificate_from_another_authority_is_refused(ldap_server, run_python):
    assert verify(run_python, ldap_server, ca_cert=ldap_server.other_ca_cert) == 'refused'


def test_certificate_for_another_name_is_refused(ldap_server, run_python):
    "Issued by the trusted authority, but not for the name that was connected to"
    if not ldap_server.other_name_uri:
        pytest.skip('needs a second address for the test server')
    assert verify(run_python, ldap_server, ldap_server.other_name_uri, ca_cert=ldap_server.ca_cert) == 'refused'
    # ... and the server is there, at that address
    assert verify(run_python, ldap_server, ldap_server.other_name_uri, cert_policy='allow') == 'connected'


def test_authority_from_the_environment_of_libldap(ldap_server, run_python):
    "LDAPTLS_CACERT is libldap's own setting, and is left to do its work"
    assert verify(run_python, ldap_server, env={'LDAPTLS_CACERT': ldap_server.ca_cert}) == 'connected'
    assert verify(run_python, ldap_server, env={'LDAPTLS_CACERT': ldap_server.other_ca_cert}) == 'refused'


def test_authority_from_ldap_conf(ldap_server, run_python, tmp_path):
    conf = tmp_path / 'ldap.conf'
    conf.write_text(f'# a comment\nTLS_CACERT {ldap_server.ca_cert}\n')
    assert verify(run_python, ldap_server, env={'LDAPCONF': str(conf)}) == 'connected'


def test_authorities_of_the_system_are_used_when_nothing_else_is_given(ldap_server, run_python):
    """libldap trusts nobody unless it is told whom. SSL_CERT_FILE stands in
    here for the system's file of certificate authorities."""
    assert verify(run_python, ldap_server, env={'SSL_CERT_FILE': ldap_server.ca_cert}) == 'connected'
    assert verify(run_python, ldap_server, env={'SSL_CERT_FILE': ldap_server.other_ca_cert}) == 'refused'


def test_ca_cert_argument_comes_before_the_environment(ldap_server, run_python):
    env = {'LDAPTLS_CACERT': ldap_server.other_ca_cert, 'SSL_CERT_FILE': ldap_server.other_ca_cert}
    assert verify(run_python, ldap_server, env=env, ca_cert=ldap_server.ca_cert) == 'connected'


@pytest.mark.parametrize('policy', ['allow', 'never'])
def test_verification_can_be_turned_off_for_a_test_server(ldap_server, run_python, policy):
    "As it was for everybody before: any certificate will do"
    assert verify(run_python, ldap_server, cert_policy=policy) == 'connected'


def test_wrong_password_is_told_apart_from_a_certificate_that_is_refused(ldap_server):
    async def attempt(**kwargs):
        async with client_for(ldap_server, **kwargs).connect():
            pass

    with pytest.raises(bonsai.errors.AuthenticationError):
        asyncio.run(attempt(password='wrong'))
    with pytest.raises(bonsai.errors.ConnectionError):
        asyncio.run(attempt(ca_cert=ldap_server.other_ca_cert))


# ---- Whom to trust, when the caller does not say ----

def test_libldap_has_ca(monkeypatch, tmp_path):
    for name in ('LDAPTLS_CACERT', 'LDAPTLS_CACERTDIR', 'LDAPCONF', 'LDAPNOINIT'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(asfpy.aioldap, 'LDAP_CONF_FILES', [str(tmp_path / 'not-there.conf')])
    assert asfpy.aioldap.libldap_has_ca() is False

    monkeypatch.setenv('LDAPTLS_CACERT', '/some/ca.pem')
    assert asfpy.aioldap.libldap_has_ca() is True
    monkeypatch.delenv('LDAPTLS_CACERT')
    monkeypatch.setenv('LDAPTLS_CACERTDIR', '/some/certs')
    assert asfpy.aioldap.libldap_has_ca() is True
    monkeypatch.delenv('LDAPTLS_CACERTDIR')

    conf = tmp_path / 'ldap.conf'
    conf.write_text('#TLS_CACERT /commented/out.pem\nBASE dc=example,dc=org\n\n')
    monkeypatch.setattr(asfpy.aioldap, 'LDAP_CONF_FILES', [str(conf)])
    assert asfpy.aioldap.libldap_has_ca() is False
    conf.write_text('BASE dc=example,dc=org\n  tls_cacert\t/etc/ssl/certs/ca-certificates.crt\n')
    assert asfpy.aioldap.libldap_has_ca() is True
    monkeypatch.setenv('LDAPNOINIT', '1')  # libldap reads no ldap.conf then
    assert asfpy.aioldap.libldap_has_ca() is False
    monkeypatch.delenv('LDAPNOINIT')

    monkeypatch.setattr(asfpy.aioldap, 'LDAP_CONF_FILES', [])
    assert asfpy.aioldap.libldap_has_ca() is False
    monkeypatch.setenv('LDAPCONF', str(conf))
    assert asfpy.aioldap.libldap_has_ca() is True


def test_system_ca_file(monkeypatch, tmp_path):
    monkeypatch.delenv('SSL_CERT_FILE', raising=False)
    monkeypatch.setattr(asfpy.aioldap.ssl, 'get_default_verify_paths', lambda: types.SimpleNamespace(cafile=None))
    monkeypatch.setattr(asfpy.aioldap, 'SYSTEM_CA_FILES', [str(tmp_path / 'not-there.pem')])
    assert asfpy.aioldap.system_ca_file() is None

    first, second = tmp_path / 'first.pem', tmp_path / 'second.pem'
    second.write_text('certificates')
    monkeypatch.setattr(asfpy.aioldap, 'SYSTEM_CA_FILES', [str(first), str(second)])
    assert asfpy.aioldap.system_ca_file() == str(second)
    first.write_text('certificates')
    assert asfpy.aioldap.system_ca_file() == str(first)

    monkeypatch.setenv('SSL_CERT_FILE', str(second))
    assert asfpy.aioldap.system_ca_file() == str(second)
    monkeypatch.setenv('SSL_CERT_FILE', str(tmp_path / 'not-there.pem'))
    assert asfpy.aioldap.system_ca_file() == str(first)


def test_client_is_given_an_authority_only_when_libldap_has_none(monkeypatch, tmp_path):
    bundle = tmp_path / 'system.pem'
    bundle.write_text('certificates')
    monkeypatch.setattr(asfpy.aioldap, 'system_ca_file', lambda: str(bundle))

    monkeypatch.setattr(asfpy.aioldap, 'libldap_has_ca', lambda: False)
    client = asfpy.aioldap.LDAPClient('ldaps://127.0.0.1:1', 'uid=x', 'y')
    assert client.client.ca_cert == str(bundle)
    assert client.client.cert_policy == 2  # bonsai's number for 'demand'
    client.close()

    monkeypatch.setattr(asfpy.aioldap, 'libldap_has_ca', lambda: True)
    client = asfpy.aioldap.LDAPClient('ldaps://127.0.0.1:1', 'uid=x', 'y')
    assert not client.client.ca_cert  # left to libldap
    client.close()

    client = asfpy.aioldap.LDAPClient('ldaps://127.0.0.1:1', 'uid=x', 'y', ca_cert='/my/own/ca.pem')
    assert client.client.ca_cert == '/my/own/ca.pem'
    client.close()
