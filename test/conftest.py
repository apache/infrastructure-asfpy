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

"""An LDAP server for the tests of asfpy.aioldap: a real slapd, with TLS,
started for the test session on ports of its own.

The tests that use it are skipped where slapd is not installed, or cannot
be started. On Debian and Ubuntu: apt-get install slapd
"""

import datetime
import ipaddress
import os
import pathlib
import shutil
import signal
import socket
import subprocess
import sys
import time
import types

import pytest

BASE_DN = 'dc=apache,dc=org'
USER_DN = 'uid=testuser,ou=people,' + BASE_DN
USER_PASSWORD = 'correct horse'
PROJECT_BASE = 'ou=project,ou=groups,' + BASE_DN

LDIF = f"""\
dn: {BASE_DN}
objectClass: dcObject
objectClass: organization
o: test
dc: apache

dn: ou=people,{BASE_DN}
objectClass: organizationalUnit
ou: people

dn: {USER_DN}
objectClass: inetOrgPerson
uid: testuser
cn: Test User
sn: User
userPassword: {USER_PASSWORD}

dn: ou=groups,{BASE_DN}
objectClass: organizationalUnit
ou: groups

dn: {PROJECT_BASE}
objectClass: organizationalUnit
ou: project

dn: cn=httpd,{PROJECT_BASE}
objectClass: groupOfNames
cn: httpd
member: {USER_DN}
"""

# Where the schema files are, and the modules of slapd, on the systems we know
SCHEMA_DIRS = ['/etc/ldap/schema', '/etc/openldap/schema', '/usr/local/etc/openldap/schema',
               '/opt/homebrew/etc/openldap/schema']
MODULE_DIRS = ['/usr/lib/ldap', '/usr/lib64/openldap', '/usr/lib/openldap']


def free_port():
    "A port that nothing is listening on."
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def make_certificates(directory):
    """Make a certificate authority and, signed by it, a certificate for a
    server at 127.0.0.1. Returns the paths of (CA certificate, server
    certificate, server key)."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    now = datetime.datetime.now(datetime.timezone.utc)

    def certificate(subject, key, issuer, issuer_key, ca):
        builder = (x509.CertificateBuilder()
                   .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, subject)]))
                   .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer)]))
                   .public_key(key.public_key())
                   .serial_number(x509.random_serial_number())
                   .not_valid_before(now - datetime.timedelta(hours=1))
                   .not_valid_after(now + datetime.timedelta(days=2))
                   .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True))
        if not ca:
            names = [x509.DNSName('localhost'), x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]
            builder = builder.add_extension(x509.SubjectAlternativeName(names), critical=False)
        return builder.sign(issuer_key, hashes.SHA256())

    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_cert = certificate('asfpy test CA', ca_key, 'asfpy test CA', ca_key, ca=True)
    server_cert = certificate('localhost', server_key, 'asfpy test CA', ca_key, ca=False)

    paths = [directory / 'ca.pem', directory / 'server.pem', directory / 'server.key']
    paths[0].write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    paths[1].write_bytes(server_cert.public_bytes(serialization.Encoding.PEM))
    paths[2].write_bytes(server_key.private_bytes(serialization.Encoding.PEM,
                                                  serialization.PrivateFormat.TraditionalOpenSSL,
                                                  serialization.NoEncryption()))
    return paths


@pytest.fixture(scope='session')
def ldap_server(tmp_path_factory):
    """A running slapd with one user and one project. Gives an object with
    uri, user_dn, password, project_base, ca_cert and pid."""
    pytest.importorskip('bonsai', reason='needs the aioldap extra')
    slapd = shutil.which('slapd') or shutil.which('slapd', path='/usr/sbin:/usr/local/sbin:/usr/libexec')
    slapadd = shutil.which('slapadd') or shutil.which('slapadd', path='/usr/sbin:/usr/local/sbin')
    schema = next((d for d in SCHEMA_DIRS if os.path.exists(os.path.join(d, 'inetorgperson.schema'))), None)
    if not slapd or not slapadd or not schema:
        pytest.skip('needs slapd, slapadd and the OpenLDAP schema files (apt-get install slapd)')

    directory = tmp_path_factory.mktemp('slapd')
    ca_cert, server_cert, server_key = make_certificates(directory)
    (directory / 'db').mkdir()
    modules = next((d for d in MODULE_DIRS if list(pathlib.Path(d).glob('back_mdb*'))), None)
    config = directory / 'slapd.conf'
    config.write_text(''.join(f'include {schema}/{name}.schema\n' for name in ('core', 'cosine', 'inetorgperson'))
                      + (f'modulepath {modules}\nmoduleload back_mdb\n' if modules else '')
                      + f'pidfile {directory}/slapd.pid\n'
                      + f'TLSCACertificateFile {ca_cert}\n'
                      + f'TLSCertificateFile {server_cert}\n'
                      + f'TLSCertificateKeyFile {server_key}\n'
                      + 'database mdb\nmaxsize 10485760\n'
                      + f'suffix "{BASE_DN}"\n'
                      + f'rootdn "cn=admin,{BASE_DN}"\nrootpw adminpw\n'
                      + f'directory {directory}/db\n'
                      + 'access to * by * read\n')
    (directory / 'base.ldif').write_text(LDIF)

    port = free_port()
    uri = f'ldaps://127.0.0.1:{port}'
    try:
        subprocess.run([slapadd, '-f', str(config), '-l', str(directory / 'base.ldif')],
                       check=True, capture_output=True, timeout=60)
        # slapd puts itself in the background, and writes its pid to the file
        subprocess.run([slapd, '-f', str(config), '-h', uri + '/'], check=True, capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        pytest.skip(f'slapd could not be started: {e}')
    pidfile = directory / 'slapd.pid'
    for _ in range(100):
        if pidfile.exists() and pidfile.read_text().strip():
            break
        time.sleep(0.1)
    else:
        pytest.skip('slapd did not start')
    pid = int(pidfile.read_text())

    yield types.SimpleNamespace(uri=uri, user_dn=USER_DN, password=USER_PASSWORD, project_base=PROJECT_BASE,
                                ca_cert=str(ca_cert), pid=pid)

    try:
        os.kill(pid, signal.SIGCONT)  # in case a test left it stopped
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass


@pytest.fixture
def run_python():
    """Runs a piece of Python in a process of its own, and returns what it
    printed and how long it took.

    For what can only be seen in a new process: libldap reads its settings
    once, when it is first used, and some of what is tested stops every
    thread of the process that it happens in.
    """
    def run(code, env=None, timeout=60):
        environment = {k: v for k, v in os.environ.items() if not k.startswith('LDAP')}
        environment['PYTHONPATH'] = str(pathlib.Path(__file__).parent.parent)
        environment.update(env or {})
        start = time.monotonic()
        done = subprocess.run([sys.executable, '-c', code], env=environment, capture_output=True,
                              text=True, timeout=timeout, check=False)
        return types.SimpleNamespace(out=done.stdout.strip(), err=done.stderr.strip(),
                                     seconds=time.monotonic() - start)
    return run
