# aioldap: an asynchronous LDAP client

`asfpy.aioldap` wraps [bonsai](https://github.com/noirello/bonsai) so that LDAP can be used
from asyncio without holding up the event loop. Install it with the `aioldap` extra:

```console
$ pip install "asfpy[aioldap]"
```

## Usage

```python
import asfpy.aioldap

client = asfpy.aioldap.LDAPClient(
    "ldaps://ldap.example.org:636",
    "uid=someone,ou=people,dc=example,dc=org",
    password,
)

async with client.connect() as conn:  # connects, and binds as the user
    who = await conn.whoami()
    found = await conn.search("ou=groups,dc=example,dc=org", ["member", "owner"])
```

- `client.connect()` makes a connection and binds. A wrong password raises
  `bonsai.errors.AuthenticationError`, and a server that cannot be reached, or whose
  certificate is not accepted, `bonsai.errors.ConnectionError`.
- `conn.search(base, attrs, scope=asfpy.aioldap.SCOPE.SUBTREE)` returns the entries found.
- Leaving the `async with` block closes the connection.

The work is done in threads that belong to the client, one connection to a thread at a time.

## The server's certificate

The certificate that the server presents is verified: it must have been issued by a
certificate authority that is trusted, and for the host name in the URI. Without that,
whoever can get between the process and the server can answer in the server's place, and is
handed the password of every bind.

Which authorities are trusted is the first of these that applies:

1. The `ca_cert` argument of `LDAPClient`: a file with the certificates of the authorities,
   in PEM format. Use it for a server whose certificate comes from an authority of your own.
2. What the LDAP library is configured with: `LDAPTLS_CACERT` or `LDAPTLS_CACERTDIR` in the
   environment, or `TLS_CACERT` or `TLS_CACERTDIR` in `ldap.conf`.
3. The certificate authorities of the system (`/etc/ssl/certs/ca-certificates.crt` on
   Debian and Ubuntu, or what `SSL_CERT_FILE` names).

```python
client = asfpy.aioldap.LDAPClient(uri, binddn, password, ca_cert="/etc/myapp/ldap-ca.pem")
```

When the certificate is not accepted, the error is the one for a server that cannot be
reached, `bonsai.errors.ConnectionError`, and says `Can't contact LDAP server`: the LDAP
library does not say more. If a server that is running cannot be contacted, look at its
certificate first:

```console
$ openssl s_client -connect ldap.example.org:636 -verify_return_error \
    -verify_hostname ldap.example.org </dev/null
```

Up to asfpy 0.60 the certificate was not verified at all, and any certificate was accepted.

### Turning verification off

`cert_policy="allow"` accepts any certificate, as before. It is for a test server, and
nothing else: with it, a password that is sent to the server may be sent to anybody.

Use one policy for every client of a process. The LDAP library keeps what it set up for the
first connection, so a later client that asks for another policy, and has no `ca_cert` of
its own, gets the policy of the first.

## Testing

The tests in `test/test_aioldap.py` run against a real LDAP server: `test/conftest.py`
starts a `slapd` with a certificate of its own, on a port of its own, for the test session.
They are skipped where `slapd` is not installed (`apt-get install slapd` on Debian and
Ubuntu).
