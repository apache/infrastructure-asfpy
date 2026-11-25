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

import unittest.mock

import pytest

import asfpy.messaging


# run with mock; return message as array
def mock_smtplib(kwargs):
    with unittest.mock.patch('smtplib.SMTP', autospec=True) as smtpmock:
        asfpy.messaging.mail(**kwargs)
        for name, args, _ in smtpmock.method_calls:
            if name.endswith('sendmail'):
                _, _, msg = args
                return msg.split(b'\n')
    raise AssertionError("Failed to extract message from smtplib call")

def test_arguments():
    with pytest.raises(AssertionError) as excinfo:
        asfpy.messaging.mail()
    assert 'Message body is required.' in str(excinfo.value)

    with pytest.raises(AssertionError) as excinfo:
        asfpy.messaging.mail(message='Test body')
    assert 'All required arguments must be provided.' in str(excinfo.value)

    with pytest.raises(TypeError) as excinfo:
        asfpy.messaging.mail(message='Test body2', headers='')
    assert 'headers must be a dict' in str(excinfo.value)

    base = { "message":'Test body3', "subject": 'Subject', "recipient": 'nemo@invalid', "host": 'localhost' }
    msg = mock_smtplib(base)
    assert 'Message-ID:' in str(msg)

    base.update({"thread_start": False, "thread_key": None})
    msg = mock_smtplib(base)
    assert 'Message-ID:' in str(msg)

    base.update({"thread_start": True, "thread_key": None})
    with pytest.raises(AssertionError) as excinfo:
        asfpy.messaging.mail(**base)
    assert 'THREAD_KEY must be provided when starting a thread' in str(excinfo.value)

    base.update({"thread_start": True, "thread_key": 'testKey'})
    msg = mock_smtplib(base)
    assert 'Message-ID: <asfpy-testKey@apache.org>' in str(msg)
    assert 'In-Reply-To:' not in str(msg)

    base.update({"thread_start": False, "thread_key": 'testKey'})
    msg = mock_smtplib(base)
    assert 'In-Reply-To: <asfpy-testKey@apache.org>' in str(msg)
    assert 'Message-ID: <asfpy-testKey@apache.org>' not in str(msg)


# Nothing that goes into the header of the message as it is may bring a
# line break with it, or the caller of our caller could add headers.
BASE = {"message": 'Body', "subject": 'Subject', "recipient": 'nemo@invalid', "host": 'localhost'}

INJECTIONS = [
    {"headers": {"X-Foo": "bar\nBcc: evil@invalid"}},
    {"headers": {"X-Foo": "bar\r\nBcc: evil@invalid"}},
    {"headers": {"X-Foo": "bar\rBcc: evil@invalid"}},
    {"headers": {"X-Foo": "bar\n"}},  # ends the headers early
    {"headers": {"X-Foo": "bar\n\nA body of their own"}},
    {"headers": {"X-Foo: bar\nBcc": "evil@invalid"}},
    {"headers": {"X-Foo\nBcc": "evil@invalid"}},
    {"headers": {"X Foo": "bar"}},
    {"headers": {"X-Foo:": "bar"}},
    {"headers": {"": "bar"}},
    {"headers": {"X-F\u00f6\u00f6": "bar"}},
    {"headers": {42: "bar"}},
    {"messageid": "<x@invalid>\nBcc: evil@invalid"},
    {"messageid": "<x@invalid>\r\nBcc: evil@invalid"},
    {"thread_start": True, "thread_key": "k>\nBcc: evil@invalid\nX-Y: <"},
    {"thread_start": False, "thread_key": "k>\nBcc: evil@invalid\nX-Y: <"},
    {"thread_start": False, "thread_key": "k\r\n"},
]

@pytest.mark.parametrize("extra", INJECTIONS)
@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_header_injection_is_refused(extra):
    kwargs = dict(BASE, **extra)
    with unittest.mock.patch('smtplib.SMTP', autospec=True) as smtpmock:
        with pytest.raises(ValueError):
            asfpy.messaging.mail(**kwargs)
        # Nothing was sent, and no connection was made.
        assert not smtpmock.called

def _headers_of(msg):
    "The header lines of a message returned by mock_smtplib()."
    return [line.decode('utf-8') for line in msg[:msg.index(b'')]]

@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_headers_that_are_in_order_still_work():
    msg = mock_smtplib(dict(BASE, headers={"X-Foo": "bar", "Reply-To": "a@invalid", "X-Count": 3,
                                           "X-Name": "Bj\u00f6rn"}))
    headers = _headers_of(msg)
    assert 'X-Foo: bar' in headers
    assert 'Reply-To: a@invalid' in headers
    assert 'X-Count: 3' in headers
    assert 'X-Name: =?utf-8?b?QmrDtnJu?=' in headers
    msg = mock_smtplib(dict(BASE, messageid='<abc.123@invalid>'))
    assert 'Message-ID: <abc.123@invalid>' in _headers_of(msg)
    msg = mock_smtplib(dict(BASE, thread_key='INFRA-1234 / a key with spaces'))
    assert 'In-Reply-To: <asfpy-INFRA-1234 / a key with spaces@apache.org>' in _headers_of(msg)

@pytest.mark.parametrize("extra, absent", [
    ({"subject": "Hello\r\nBcc: evil@invalid"}, "Bcc"),
    ({"subject": "Hello\nBcc: evil@invalid"}, "Bcc"),
    ({"sender": "A <a@invalid>\r\nBcc: evil@invalid"}, "Bcc"),
    ({"sender": "A\nBcc: evil@invalid <a@invalid>"}, "Bcc"),
    ({"recipient": "nemo@invalid\nBcc: evil@invalid"}, "Bcc"),
])
def test_subject_and_addresses_cannot_add_a_header(extra, absent):
    """These were never open to it: they are encoded, not put in as they are.
    (A line break in an address is then refused by smtplib, for the envelope.)"""
    msg = mock_smtplib(dict(BASE, **extra))
    assert not [line for line in _headers_of(msg) if line.startswith(absent + ':')]
    assert len([line for line in _headers_of(msg) if line.startswith('Subject:')]) == 1
