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

client.close()
```

- `client.connect()` makes a connection and binds. A wrong password raises
  `bonsai.errors.AuthenticationError`, and a server that cannot be reached
  `bonsai.errors.ConnectionError`.
- `conn.search(base, attrs, scope=asfpy.aioldap.SCOPE.SUBTREE)` returns the entries found.
- Leaving the `async with` block closes the connection.
- `client.close()` stops the client's threads. Without it they stop when the client and its
  connections have been garbage collected. Call it if you make clients often, one for each
  user who logs in for instance.

The work is done in threads that belong to the client, one connection to a thread at a time.

## Time limits

There are two, for two parts of the work.

| | Reaching the server | Waiting for an answer |
|---|---|---|
| Covers | The TCP connection, and the TLS handshake | The bind, and each `search()` and `whoami()` |
| Default | 5 seconds | 30 seconds |
| Set with | `LDAPNETWORK_TIMEOUT` in the environment | `timeout=` of `LDAPClient`, `search()` or `whoami()` |
| When it is passed | `bonsai.errors.ConnectionError` | `asyncio.TimeoutError` |
| Meanwhile | **Every thread of the process stands still** | Nothing else is held up |

### Reaching the server

While a connection is being made, bonsai waits inside the LDAP library and holds Python's
global lock. If the server does not answer, because it is overloaded or because a firewall
is dropping the packets, every thread of the process stops until the wait is over: the
event loop too, and with it every other request that the process is serving. Running the
connection in a thread does not help, and neither does a timeout from asyncio, as the loop
that would apply it is not running either.

What ends the wait is the LDAP library's own network timeout. `asfpy.aioldap` sets it to 5
seconds (`asfpy.aioldap.NETWORK_TIMEOUT`) when the module is imported, unless the
environment already has a value. Without it the wait lasts until the operating system gives
up on the connection, which is minutes, or for as long as a server that says nothing keeps
the connection open.

- To use another value, set `LDAPNETWORK_TIMEOUT`, in seconds, in the environment of the
  process, before it starts. Keep it short: it is how long the whole process can stand still
  for each connection that is tried.
- The LDAP library reads the value once, when it is first used in the process. Setting it
  later, from Python, has no effect.
- It applies to everything in the process that uses the LDAP library, and to programs that
  the process starts, `ldapsearch` for instance.
- A `NETWORK_TIMEOUT` in `ldap.conf` is not used, since the environment comes first.

A server that is not there at all, with nothing listening on the port, is refused at once
and is not a problem.

### Waiting for an answer

Once connected, waiting for the server is a wait within asyncio, and holds nothing else up.
`LDAPClient(..., timeout=30)` is how long to wait for the bind and for each search, and a
single `search()` or `whoami()` can be given a `timeout` of its own. `None` waits for as long
as it takes.

## Testing

The tests in `test/test_aioldap.py` run against a real LDAP server: `test/conftest.py`
starts a `slapd` with a certificate of its own, on a port of its own, for the test session.
They are skipped where `slapd` is not installed (`apt-get install slapd` on Debian and
Ubuntu).
