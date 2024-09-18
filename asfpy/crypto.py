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
"""Auxiliary crypto features. Just ED25519 signing for now."""
import binascii

import cryptography.exceptions
import cryptography.hazmat.primitives.asymmetric.ed25519
import cryptography.hazmat.primitives.serialization
import secrets
import base64

# Defaults PEM format for our ED25519 keys
ED25519_ENCODING = cryptography.hazmat.primitives.serialization.Encoding.PEM
ED25519_PRIVKEY_FORMAT = cryptography.hazmat.primitives.serialization.PrivateFormat.PKCS8
ED25519_PUBKEY_FORMAT = cryptography.hazmat.primitives.serialization.PublicFormat.SubjectPublicKeyInfo
ED25519_PEM_ENCRYPTION = cryptography.hazmat.primitives.serialization.NoEncryption()


class ED25519:
    def __init__(self, pubkey: str = None, privkey: str = None):
        """Loads an existing ED25519 key or instantiates a new ED25519 key pair.
        If pubkey is set, it loads it as a PEM-formatted key, same with privkey.
        If no public or private key is passed on, a new keypair is created instead."""
        if pubkey:
            self._pubkey = cryptography.hazmat.primitives.serialization.load_pem_public_key(pubkey.encode("us-ascii"))
            self._privkey = None
        elif privkey:
            self._privkey = cryptography.hazmat.primitives.serialization.load_pem_private_key(
                privkey.encode("us-ascii"), password=None
            )
        else:
            self._privkey = cryptography.hazmat.primitives.asymmetric.ed25519.Ed25519PrivateKey.generate()

        # Private keys can be used to generate as many public keys as needed, so we can create one for testing.
        if self._privkey:
            self._pubkey = self._privkey.public_key()

    @property
    def pubkey(self):
        """ "Returns the public key (if present) in PEM format"""
        assert self._pubkey, "No public key found, cannot PEM-encode nothing!"
        return self._pubkey.public_bytes(encoding=ED25519_ENCODING, format=ED25519_PUBKEY_FORMAT).decode("us-ascii")

    @property
    def privkey(self):
        """ "Returns the private key (if present) in PEM format"""
        assert self._privkey, "No public key found, cannot PEM-encode nothing!"
        return self._privkey.private_bytes(
            encoding=ED25519_ENCODING, format=ED25519_PRIVKEY_FORMAT, encryption_algorithm=ED25519_PEM_ENCRYPTION
        ).decode("us-ascii")

    def sign_data(self, data: str = "", output_b64=False):
        """Signs a string with the private key for authenticity purposes.
        The signature includes a nonce for randomizing the response and returns three lines, split by newline:
        data-plus-nonce-signature
        nonce
        data

        The blob can be verified by verify_data, which will return the verified data if the signature is valid,
        else None.

        If output_b64 is True, the signed data is base64-encoded and returned as a single line. This can be
        useful for HTTP-based access tokens.
        """
        nonce = secrets.token_hex(32)
        data_plus_nonce = "\n".join([nonce, data])
        data_signature = self._privkey.sign(data_plus_nonce.encode("us-ascii"))
        response = "\n".join([base64.b64encode(data_signature).decode("us-ascii"), nonce, data])
        if output_b64:
            response = base64.b64encode(response.encode('us-ascii')).decode('us-ascii')
        return response

    def verify_response(self, data: str):
        """Verifies the authenticity of a data blob. If signed by the private key,
        returns the original data that was signed, otherwise None"""
        try:
            if "\n" not in data:  # base64-encoded one-liner?
                try:
                    data = base64.b64decode(data).decode('us-ascii')
                except binascii.Error:  # Not base64!
                    return None
            signature, data_plus_nonce = data.split("\n", 1)
            signature = base64.b64decode(signature)
        except ValueError:  # Bad token format or invalid base64 signature, FAILURE.
            return
        try:
            _nonce, data_verified = data_plus_nonce.split("\n", 1)
            self._pubkey.verify(signature, data_plus_nonce.encode("us-ascii"))
            return data_verified
        except cryptography.exceptions.InvalidSignature:
            return
