#!/usr/bin/env python
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

"""
This is the standardized email library for sending emails.
It handles encoding options and required metadata,
as well as defaulting where bits are missing.

It also contains hipchat and stride integrations
"""

#
# Find users of this module:
#  https://github.com/search?q=org%3Aapache+asfpy+messaging&type=code
#
# note: there may be some in svn:infra/trunk
#

if not __debug__:
    raise RuntimeError("This code requires Assertions to be enabled")

import email.utils
import email.header
import re
import smtplib
import warnings

# Message submission uses port 587.
#   https://www.rfc-editor.org/rfc/rfc6409
SMTP_PORT = 587

# Apache/Infra code defaults to this MSA for sending email.
DEFAULT_MSA = 'mail-relay.apache.org'


# The name of a header field: printable US-ASCII, without the colon that ends it.
#   https://www.rfc-editor.org/rfc/rfc5322#section-2.2
_FIELD_NAME_RE = re.compile(r'[!-9;-~]+')


def _check_field_name(name):
    """Raise ValueError unless NAME can be the name of a header field.

    The message is put together as text, so a name with a newline, a colon
    or a space in it would not be the name of one header: it would end the
    header, or start another one, of the caller's caller's choosing.
    """
    if not isinstance(name, str) or not _FIELD_NAME_RE.fullmatch(name):
        raise ValueError('Not a valid name for an email header: %r' % (name,))


def _check_field_value(what, value):
    """Raise ValueError if VALUE cannot be the value of a header field.

    A carriage return or a line feed ends the header, and what follows it
    becomes a header of its own (a Bcc, say), or the start of the body.
    WHAT says which argument the value came from, for the error message.
    """
    if '\r' in value or '\n' in value or '\x00' in value:
        raise ValueError('%s may not contain a line break: %r' % (what, value))


def uniaddr(addr):
    """ Unicode-format an email address """
    bits = email.utils.parseaddr(addr)
    return email.utils.formataddr((email.header.Header(bits[0], 'utf-8').encode(), bits[1]))


def thread_msgid(key):
    "Return a reproducible Message-ID value."
    return'<asfpy-%s@apache.org>' % (key,)


def mail(
        ### need py2 compat. FUTURE:
        # *,  # Parameters must be passed as arg=value, not positionally
        host=DEFAULT_MSA,
        ### maybe accept a port? for now: always 587

        # These are required:
        sender="Apache Infrastructure <users@infra.apache.org>",
        recipient=None,  # str
        recipients=None,  # str, or iterable
        subject=None,
        message=None,

        thread_start=False,
        thread_key=None,

        auth=None,  # (user, pass)

        # Deprecated:  (use thread_*)
        messageid=None,
        headers=None,
):
    if headers is None:
        headers = { }
    elif not isinstance(headers, dict):
        raise TypeError("Argument headers must be a dict") 

    # Deprecating these parameters. Use THREAD_* instead.
    if messageid or headers:
        warnings.warn('Use THREAD_* instead of MESSAGEID and/or HEADERS.',
                      DeprecationWarning)

    # We have expectations. Enforce them.
    assert message, 'Message body is required.'
    assert (not messageid and not headers) \
        or (not thread_start and not thread_key), \
        'MESSAGEID and HEADERS or THREAD_*, but not both'
    assert (not thread_start) or thread_key, \
        'THREAD_KEY must be provided when starting a thread'
    assert sender and (recipient or recipients) and subject and message, \
        'All required arguments must be provided.'

    # MESSAGEID, THREAD_KEY and HEADERS go into the header of the message
    # as they are, so none of them may bring a line break with it: that
    # would let whoever supplied the value add headers of their own.
    # (SUBJECT, SENDER and the recipients are encoded below, which deals
    # with line breaks in them.)
    if messageid:
        _check_field_value('messageid', str(messageid))
    if thread_key:
        _check_field_value('thread_key', str(thread_key))
    for key, val in headers.items():
        _check_field_name(key)
        _check_field_value('Header %s' % (key,), str(val))

    # Handle threading of email messages.
    if thread_start:
        # Original post. Construct a very specific Message-ID which can
        # be referenced in follow-up emails.
        messageid = thread_msgid(thread_key)
    elif thread_key:
        # This message is a response to the original post, identified by
        # a specific Message-ID that we constructed.
        # Note: avoid modifying the passed HEADERS.
        headers = headers.copy()
        headers['In-Reply-To'] = thread_msgid(thread_key)

    # Optional metadata first
    if not messageid:
        messageid = email.utils.make_msgid("asfpy")
    date = email.utils.formatdate()

    # Now the required bits
    recipients = recipient or recipients  # We accept both names, 'cause
    if not recipients:
        raise ValueError("No recipients specified for email, can't send!")
    # We want this as a list
    if isinstance(recipients, str):
        recipients = [recipients]
    else:
        # Do not modify the caller's list, by copying it;
        # or: turn an iterable into a list, so we can munge it.
        recipients = list(recipients)

    # py 2 vs 3 conversion
    if isinstance(sender, bytes):
        sender = sender.decode('utf-8', errors='replace')
    if isinstance(message, bytes):
        message = message.decode('utf-8', errors='replace')
    for i, rec in enumerate(recipients):
        if isinstance(rec, bytes):
            rec = rec.decode('utf-8', errors='replace')
            recipients[i] = rec

    # Recipient, Subject and Sender might be unicode.
    subject_encoded = email.header.Header(subject, 'utf-8').encode()
    sender_encoded = uniaddr(sender)
    recipient_encoded = ", ".join([uniaddr(x) for x in recipients])

    extra = u""
    if headers:
        for key, val in headers.items():
            try:
                str(val).encode("us-ascii")
            except UnicodeEncodeError:  # String has non-ascii elements, convert
                val = email.header.Header(val, 'utf-8').encode()
            extra += u"%s: %s\n" % (key, val)
    extra += u"\n"

    # Construct the email
    msg = u"""From: %s
To: %s	
Subject: %s
Message-ID: %s
Date: %s
Content-Type: text/plain; charset=utf-8
Content-Transfer-Encoding: 8bit
%s
%s
""" % (sender_encoded, recipient_encoded, subject_encoded, messageid, date, extra, message)
    msg = msg.encode('utf-8', errors='replace')
    # Try to dispatch message, do a raw fail if stuff happens.
    if ":" in host:  # Port specified in hostname
        smtp_object = smtplib.SMTP(host)
    else:  # Default port
        smtp_object = smtplib.SMTP(host, SMTP_PORT)
    smtp_object.starttls()
    if auth:
        smtp_object.login(*auth)  # user, pwd
    # Note that we're using the raw sender here...
    smtp_object.sendmail(sender, recipients, msg)
