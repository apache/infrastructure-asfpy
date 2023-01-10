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

import setuptools


def main():
    setuptools.setup(name='asfpy',
        version='0.46',
        description='ASF Common Python Methods',
        long_description="This is a common set of functions used by the ASF Infrastructure team such as libraries for sending email, ldap management and generic process daemonization.",
        long_description_content_type = "text/plain",
        url='https://github.com/apache/infrastructure-asfpy/',
        author='ASF Infrastructure',
        author_email='users@infra.apache.org',
        license='Apache',
        packages=['asfpy'],
        install_requires=[
            'requests',
            'ezt',
            'stdiomask',
            'requests',
            'aiohttp',
            'asyncinotify',
        ],
        extras_require= {
            'ldap': ['python-ldap'],
            'aioldap': ['bonsai'],
        },
        zip_safe=False)


if __name__ == '__main__':
    main()
