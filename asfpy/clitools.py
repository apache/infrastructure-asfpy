#!/usr/bin/env python3
import subprocess
import base64

"""Python wrappers for common CLI tools"""


def ldapsearch_cli(
        ldap_base="dc=apache,dc=org",
        ldap_scope="sub",
        ldap_query="*",
        ldap_attrs=(
            "cn",
        ),
):
    """Runs a search in LDAP using (asf)ldapsearch and returns the results as a list of dictionaries
    :param ldap_base:  The base for the LDAP search
    :param ldap_scope: The scope of the search. Can be: base, one, sub, children.
    :param ldap_query: The LDAP query to filter by
    :param ldap_attrs: The LDAP attribute elements to include in the result.
    """
    cliargs = [
        "/usr/bin/asfldapsearch",  # Executable
        "-x",                      # Simple bind
        "-LLL",                    # be very concise
        "-b",                      # Bind to...
        ldap_base,
        "-s",                      # Limit scope to...
        ldap_scope,
        ldap_query,                # This is our query
    ]
    # Check if attrs is a list or a single string, adjust cliargs accordingly...
    if isinstance(ldap_attrs, list) or isinstance(ldap_attrs, tuple):
        cliargs.extend(ldap_attrs)
    elif isinstance(ldap_attrs, str):
        cliargs.append(ldap_attrs)
    
    # Run asfldapsearch tool, and yield each bunch of data as a they appear.
    bunch = {}
    for line in subprocess.run(cliargs, stdout=subprocess.PIPE).stdout.decode("us-ascii").splitlines(keepends=False):
        if not line:  # The end of a bunch always ends with a blank line.
            yield bunch
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
