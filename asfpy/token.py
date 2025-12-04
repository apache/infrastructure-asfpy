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

# token.py
# Secure 160-bit Bech32m-encoded tokens with provider suffix and expiration

import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from bech32 import bech32_encode, bech32_decode, convertbits, Encoding

# Valid providers (you can extend this set)
VALID_PROVIDERS = {
    "local", "google", "github", "microsoft", "apple",
    "discord", "twitter", "facebook", "amazon"
}

# Bech32m uses 5-bit groups; 160 bits = 20 bytes → 32 × 5-bit words + version byte if needed
TOKEN_ENTROPY_BYTES = 20  # 160 bits


def create(provider: str, days_valid: int = 365) -> str:
    """
    Create a new secret token.
    
    Format: obvious_secret_<bech32m-encoded-160bits>_<provider>
    The Bech32m part includes a 4-character checksum embedded in the encoding.
    """
    if provider not in VALID_PROVIDERS:
        raise ValueError(f"Invalid provider. Must be one of: {', '.join(sorted(VALID_PROVIDERS))}")

    entropy = secrets.token_bytes(TOKEN_ENTROPY_BYTES)
    data_5bit = convertbits(entropy, 8, 5, True)
    assert data_5bit is not None

    bech32_part = bech32_encode("t", data_5bit, Encoding.BECH32M)  # "t" = short neutral HRP
    token = f"obvious_secret_{bech32_part}_{provider}"
    return token


def validate(token: str) -> Tuple[bool, str, Optional[str]]:
    """
    Validate a token string.
    Returns (is_valid: bool, reason: str, provider: str | None)
    """
    parts = token.split("_", 3)
    if len(parts) != 4 or parts[0] != "obvious" or parts[1] != "secret":
        return False, "Incorrect prefix (must be obvious_secret_...)", None

    bech32_part, provider = parts[2], parts[3]

    if provider not in VALID_PROVIDERS:
        return False, f"Unknown provider: {provider}", None

    hrp, data_5bit = bech32_decode(bech32_part, Encoding.BECH32M)
    if hrp != "t" or data_5bit is None:
        return False, "Invalid or non-Bech32m part", None

    # Convert back to 20 bytes to confirm length
    data_8bit = convertbits(data_5bit, 5, 8, False)
    if data_8bit is None or len(data_8bit) != TOKEN_ENTROPY_BYTES:
        return False, "Incorrect payload length", None

    return True, "valid", provider


def extract_entropy(token: str) -> Optional[bytes]:
    """Helper: extract the raw 20-byte entropy from a valid token"""
    is_valid, reason, _ = validate(token)
    if not is_valid:
        raise ValueError(f"Invalid token: {reason}")

    bech32_part = token.split("_", 3)[2]
    _, data_5bit = bech32_decode(bech32_part, Encoding.BECH32M)
    data_8bit = convertbits(data_5bit, 5, 8, False)
    return bytes(data_8bit)


# ----------------------------------------------------------------------
# SQLite-backed Token Storage
# ----------------------------------------------------------------------
class TokenStorage:
    def __init__(self, db_path: str = "tokens.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS tokens (
                    entropy BLOB PRIMARY KEY,      -- 20 random bytes
                    token   TEXT UNIQUE,           -- full materialized token (for lookup)
                    provider TEXT NOT NULL,
                    created  TEXT NOT NULL,         -- ISO 8601 UTC
                    expires  TEXT,                 -- ISO 8601 UTC, NULL = never
                    revoked  INTEGER DEFAULT 0     -- 1 = revoked
                )
            """)

    def insert(self,
               provider: str,
               days_valid: Optional[int] = 365) -> str:
        """Create and store a new token. Returns the materialized token."""
        token = create(provider, days_valid)
        entropy = extract_entropy(token)

        expires = None
        if days_valid is not None:
            expires_dt = datetime.now(timezone.utc) + timedelta(days=days_valid)
            expires = expires_dt.isoformat()

        with sqlite3.connect(self.db_path) as con:
            con.execute("""
                INSERT INTO tokens(entropy, token, provider, created, expires)
                VALUES (?, ?, ?, ?, ?)
            """, (
                entropy,
                token,
                provider,
                datetime.now(timezone.utc).isoformat(),
                expires
            ))
        return token

    def is_valid(self, token: str) -> Tuple[bool, str]:
        """Check if token exists, is not revoked, and not expired."""
        valid, reason, provider = validate(token)
        if not valid:
            return False, reason

        entropy = extract_entropy(token)

        with sqlite3.connect(self.db_path) as con:
            row = con.execute("""
                SELECT revoked, expires FROM tokens WHERE entropy = ?
            """, (entropy,)).fetchone()

        if not row:
            return False, "Token not found in database"

        revoked, expires_iso = row
        if revoked:
            return False, "Token has been revoked"

        if expires_iso:
            expires_dt = datetime.fromisoformat(expires_iso.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > expires_dt:
                return False, "Token has expired"

        return True, "valid"

    def revoke(self, token: str) -> bool:
        """Mark token as revoked."""
        try:
            entropy = extract_entropy(token)
        except ValueError:
            return False

        with sqlite3.connect(self.db_path) as con:
            cur = con.execute("""
                UPDATE tokens SET revoked = 1 WHERE entropy = ?
            """, (entropy,))
            return cur.rowcount > 0

    def delete(self, token: str) -> bool:
        """Permanently delete a token record."""
        try:
            entropy = extract_entropy(token)
        except ValueError:
            return False

        with sqlite3.connect(self.db_path) as con:
            cur = con.execute("DELETE FROM tokens WHERE entropy = ?", (entropy,))
            return cur.rowcount > 0

    def list_active(self):
        """Return list of active (non-revoked, non-expired) tokens."""
        with sqlite3.connect(self.db_path) as con:
            rows = con.execute("""
                SELECT token, provider, created, expires FROM tokens
                WHERE revoked = 0
                  AND (expires IS NULL OR expires > ?)
                ORDER BY created DESC
            """, (datetime.now(timezone.utc).isoformat(),)).fetchall()
        return rows
