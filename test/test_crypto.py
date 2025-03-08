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
import asfpy.crypto
import pathlib

TESTMSG = "Hello, world!"
TEST_ROOT = pathlib.Path(__file__).parent


def test_ed25519_keypair():
    keypair = asfpy.crypto.ED25519()
    assert keypair.pubkey, "Could not find pubkey"
    assert keypair.privkey, "Could not find privkey"
    test_token = keypair.sign_data(TESTMSG)

    # Test verification with proper and invalid sig
    assert keypair.verify_response(test_token) == TESTMSG, "Verification of test token failed!"
    assert keypair.verify_response("foo:bar") is None, "Verification succeeded with bogus token, not supposed to happen!"


def test_existing_keys():
    public_pem = open(TEST_ROOT / "data/ed25519_pubkey.pem").read()
    private_pem = open(TEST_ROOT / "data/ed25519_privkey.pem").read()
    pubkeypair = asfpy.crypto.ED25519(pubkey=public_pem)
    privkeypair = asfpy.crypto.ED25519(privkey=private_pem)
    print(privkeypair._privkey.public_key())

    # Test readability of private test key
    assert privkeypair.privkey is not None, "Private key is empty when it shouldn't be!"
    assert privkeypair.pubkey is not None, "Public key is empty when it shouldn't be!"

    # Test readability of public test key
    assert pubkeypair.pubkey is not None, "Public key is empty when it shouldn't be!"
    with pytest.raises(AssertionError):  # Private key shouldn't exist
        print(pubkeypair.privkey)

    # Sign with private key
    test_token = privkeypair.sign_data(TESTMSG)

    # Test verification with proper and invalid sig with imported public key
    assert pubkeypair.verify_response(test_token) == TESTMSG, "Verification of test token failed!"
    assert pubkeypair.verify_response("foo:bar") is None, "Verification succeeded with bogus token, not supposed to happen!"
