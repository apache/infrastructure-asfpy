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
""" simple syslog redirect module """

"""Example:
import asfpy.syslog

print = asfpy.syslog.Printer(identity='myapp')
print("Hello, world!") # prints to syslog

print = asfpy.syslog.Printer(stdout=True)
print("Hello!!") # print to syslog AND stdout
"""
import syslog
import os
import sys

class Printer:
    def __init__(self, **kwargs):
        self.copy_to_stdout = kwargs.get('stdout')
        log_options = 0
        log_ident = kwargs.get('identity', os.path.basename(sys.argv[0]))
        facility = syslog.LOG_USER
        if kwargs.get('log_pid'):
            log_options += syslog.LOG_PID
        syslog.openlog(log_ident, logoption=log_options, facility=facility)

    def __call__(self, *args, **kwargs):
        line = ' '.join([str(arg) for arg in args])
        syslog.syslog(line)
        if self.copy_to_stdout:
            print(*args)

