#!/usr/bin/env python3
import subprocess
import asyncio.subprocess
import base64

"""Python wrappers for common CLI tools"""


def ldapsearch_parse(indata: str):
    """Parses ldapsearch output into structured python data"""
    results = []
    bunch = {}
    for line in indata.splitlines(keepends=False):
        if not line:  # The end of a bunch always ends with a blank line.
            results.append(bunch)
            bunch = {}
        else:
            key, value = line.split(":", maxsplit=1)
            if value.startswith(":"):  # Base64
                value = base64.standard_b64decode(value[2:]).decode("utf-8")
            else:
                value = value.strip()
            if key not in bunch:
                bunch[key] = list()
            bunch[key].append(value)
    return results  # Return the list of results


def ldapsearch_cliargs(ldap_base, ldap_scope, ldap_query, ldap_attrs):
    """Constructs a list of command line arguments for asfldapsearch"""
    cliargs = [
        "/usr/bin/asfldapsearch",  # Executable
        "-x",  # Simple bind
        "-LLL",  # be very concise
        "-b",  # Set base of search operations to...
        ldap_base,
        "-s",  # Limit scope to...
        ldap_scope,
        "-o",
        "ldif-wrap=no",  # Don't wrap long lines
        ldap_query,  # This is our query
    ]
    # Check if attrs is a list or a single string, adjust cliargs accordingly...
    if isinstance(ldap_attrs, list) or isinstance(ldap_attrs, tuple):
        cliargs.extend(ldap_attrs)
    elif isinstance(ldap_attrs, str):
        cliargs.append(ldap_attrs)
    # Return the cli arg list
    return cliargs


def ldapsearch_cli(
    ldap_base="dc=apache,dc=org",
    ldap_scope="sub",
    ldap_query="*",
    ldap_attrs=("cn",),
):
    """Runs a search in LDAP using (asf)ldapsearch and returns the results as a list of dictionaries
    :param ldap_base:  The base for the LDAP search
    :param ldap_scope: The scope of the search. Can be: base, one, sub, children.
    :param ldap_query: The LDAP query to filter by
    :param ldap_attrs: The LDAP attribute elements to include in the result.
    """

    # Run asfldapsearch tool, parse the output and return the data structure
    cliargs = ldapsearch_cliargs(ldap_base, ldap_scope, ldap_query, ldap_attrs)
    output = subprocess.run(cliargs, stdout=subprocess.PIPE).stdout.decode("us-ascii")
    return ldapsearch_parse(output)


async def ldapsearch_cli_async(
    ldap_base="dc=apache,dc=org",
    ldap_scope="sub",
    ldap_query="*",
    ldap_attrs=("cn",),
):
    """Runs an async search in LDAP using (asf)ldapsearch and returns the results as a list of dictionaries
    :param ldap_base:  The base for the LDAP search
    :param ldap_scope: The scope of the search. Can be: base, one, sub, children.
    :param ldap_query: The LDAP query to filter by
    :param ldap_attrs: The LDAP attribute elements to include in the result.
    """

    # Run asfldapsearch tool, parse the output and return the data structure
    cliargs = ldapsearch_cliargs(ldap_base, ldap_scope, ldap_query, ldap_attrs)
    proc = await asyncio.subprocess.create_subprocess_exec(cliargs[0], *cliargs[1:], stdout=asyncio.subprocess.PIPE)
    await proc.wait()
    output = (await proc.stdout.read()).decode("us-ascii")
    return ldapsearch_parse(output)
