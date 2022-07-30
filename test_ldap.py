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

import ldif
import asfpy.ldap

PY = ldif.LDIFWriter(None)._needs_base64_encoding
ASF = asfpy.ldap.LDIFWriter_Sane(None)._needs_base64_encoding

def compare(attr, value, same=True):
  py = PY(attr, value.encode('utf-8'))
  asf = ASF(attr, value)
  if same: # should have same result
    if py != asf:
      print(f"NAK: {attr} '{value}' exp: {py} act: {asf}")
  else:
    if py == asf:
      print(f"NAK: {attr} '{value}' exp: {not py} act: {asf}")
      

compare('dn', 'abcd') # expect the same result (False)
compare('dn', ' abcd', False) # super class will give True here

compare('host', 'abcd')
compare('host', 'ab cd')
compare('host', ' abcd')
compare('host', 'abcd ')
compare('host', 'ab\0cd')
# Need some more tests here
