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

import socket

def whoami():
    """Returns the FQDN of the box the program runs on"""
    try:
        # Get local hostname (what you see in the terminal)
        local_hostname = socket.gethostname()
        # Get all address info segments for the local host
        canonical_names = [
            address[3]
            for address in socket.getaddrinfo(local_hostname, None, 0, socket.SOCK_DGRAM, 0, socket.AI_CANONNAME)
            if address[3]
        ]
        # For each canonical name, see if we find $local_hostname.something.tld, and if so, return that.
        if canonical_names:
            prefix = str(local_hostname) + "."
            for name in canonical_names:
                if name.startswith(prefix):
                    return name
            # No match, just return the first occurrence.
            return canonical_names[0]
    except socket.error:
        pass
    # Fall back to socket.getfqdn
    return socket.getfqdn()

if __name__ == "__main__":
    print(whoami())

