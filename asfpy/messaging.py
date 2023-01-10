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

import email.utils
import email.header
import smtplib
import warnings

# Message submission uses port 587.
#   https://www.rfc-editor.org/rfc/rfc6409
SMTP_PORT = 587

# Apache/Infra code defaults to this MSA for sending email.
DEFAULT_MSA = 'mail-relay.apache.org'


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
        headers={ },
):
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

    # Handle threading of email messages.
    if thread_start:
        # Original post. Construct a very specific Message-ID which can
        # be referenced in follow-up emails.
        messageid = thread_msgid(thread_key)
    elif thread_key:
        # This message is a response to the original post, identified by
        # a specific Message-ID that we constructed.
        # Note: avoid modifying the passed HEADERS.
        headers = headers.copy()['In-Reply-To'] = thread_msgid(thread_key)

    # Optional metadata first
    if not messageid:
        messageid = email.utils.make_msgid("asfpy")
    date = email.utils.formatdate()

    # Now the required bits
    recipients = recipient or recipients  # We accept both names, 'cause
    if not recipients:
        raise Exception("No recipients specified for email, can't send!")
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
    smtp_object = smtplib.SMTP(host, SMTP_PORT)
    smtp_object.starttls()
    if auth:
        smtp_object.login(*auth)  # user, pwd
    # Note that we're using the raw sender here...
    smtp_object.sendmail(sender, recipients, msg)
