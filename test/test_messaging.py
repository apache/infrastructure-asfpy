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

import pytest
import asfpy.messaging
import unittest.mock

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
