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
            self._pubkey = None
        else:
            self._privkey = cryptography.hazmat.primitives.asymmetric.ed25519.Ed25519PrivateKey.generate()
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

    def generate_auth_token(self):
        """Generates a token of authenticity using the private key. This token can be verified using the public key.
        The token uses the format 'hextoken:hextoken-signature' where hextoken is a random 32 byte string and
        hextoken-signature is the signed counterpart."""
        token_nonce = secrets.token_hex(32)
        signed_token = self._privkey.sign(token_nonce.encode("us-ascii"))
        response = token_nonce + ":" + base64.b64encode(signed_token).decode("us-ascii")
        return response

    def verify_authenticity_token(self, token):
        """Verifies the authenticity of a token. If signed by the private key, returns True, otherwise False."""
        try:
            hex_bit, signature = token.split(":", 1)
            signature = base64.b64decode(signature)
        except ValueError:  # Bad token format or invalid base64 signature, FAILURE.
            return False
        try:
            self._pubkey.verify(signature, hex_bit.encode("us-ascii"))
            return True
        except cryptography.exceptions.InvalidSignature:
            return False
