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

import email.utils
import email.header
import smtplib


def uniaddr(addr):
    """ Unicode-format an email address """
    bits = email.utils.parseaddr(addr)
    return email.utils.formataddr((email.header.Header(bits[0], 'utf-8').encode(), bits[1]))


def mail(
        host='mail-relay.apache.org:587',
        sender="Apache Infrastructure <users@infra.apache.org>",
        recipient=None,  # str
        recipients=None,  # str, or iterable
        subject='No subject',
        message=None,
        messageid=None,
        headers=None
):
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
        # Do not modify the caller's object; or turn iterable into a list.
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
            val = email.header.Header(val, 'utf-8').encode()
            extra += u"%s: %s\n" % (key, val)
    extra += u"\n"

    if not message:
        raise Exception("No message body provided!")

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
    smtp_object = smtplib.SMTP(host)
    smtp_object.starttls()
    # Note that we're using the raw sender here...
    smtp_object.sendmail(sender, recipients, msg)
