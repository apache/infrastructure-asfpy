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

"""Tests of asfpy.aioldap against a real LDAP server (see conftest.py).

They are skipped where bonsai or slapd is not installed.
"""

import asyncio
import types

import pytest

bonsai = pytest.importorskip('bonsai', reason='needs the aioldap extra')

import asfpy.aioldap  # pylint: disable=wrong-import-position


def client_for(server, password=None, **kwargs):
    "A client that trusts the authority of the test server's certificate."
    kwargs.setdefault('ca_cert', server.ca_cert)
    return asfpy.aioldap.LDAPClient(server.uri, server.user_dn, password or server.password, **kwargs)


# ---- Connecting, binding, searching ----

def test_connect_and_search(ldap_server):
    async def main():
        async with client_for(ldap_server).connect() as conn:
            who = await conn.whoami()
            found = await conn.search(ldap_server.project_base, ['member'])
        return who, found

    who, found = asyncio.run(main())
    assert who == 'dn:' + ldap_server.user_dn
    assert [str(entry.dn) for entry in found if 'member' in entry] == ['cn=httpd,' + ldap_server.project_base]


def test_wrong_password_is_refused(ldap_server):
    async def main():
        async with client_for(ldap_server, password='wrong').connect():
            pass

    with pytest.raises(bonsai.errors.AuthenticationError):
        asyncio.run(main())


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

    monkeypatch.setattr(asfpy.aioldap, 'libldap_has_ca', lambda: True)
    client = asfpy.aioldap.LDAPClient('ldaps://127.0.0.1:1', 'uid=x', 'y')
    assert not client.client.ca_cert  # left to libldap

    client = asfpy.aioldap.LDAPClient('ldaps://127.0.0.1:1', 'uid=x', 'y', ca_cert='/my/own/ca.pem')
    assert client.client.ca_cert == '/my/own/ca.pem'
