#
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# ----
#
# Convenience wrapper for working with a SQLite database.
#
# This wrapper has several primary purposes:
#
#   1. Easily create a cursor for each statement that might be
#      executed by the application.
#   2. Remember the specific string object for those statements,
#      and re-use them in cursor.execute() for better performance.
#   3. Rows fetched with SELECT statements are wrapped into a
#      EasyDict() instance, such that columns can be easily
#      accessed as attributes.
#

import sqlite3

import yaml
import easydict


class DB:

    def __init__(self, fname, yaml_fname=None, yaml_section='queries'):

        def row_factory(cursor, row):
            # Enable attribute access. Disable integer index access.
            return easydict.EasyDict(sqlite3.Row(cursor, row))

        # Note: isolation_level=None means autocommit mode.
        self.conn = sqlite3.connect(fname, isolation_level=None)
        self.conn.row_factory = row_factory

        yml = yaml.safe_load(open(yaml_fname))
        for name, sql in yml[yaml_section].items():
            if hasattr(self, name):
                ### fix this exception
                raise Exception(f'duplicate: {name}')
            print(f'{name}: {sql}')
            setattr(self, name, _Cursor(self.conn, sql))

    def cursor_for(self, statement):
        return _Cursor(self.conn, statement)


class _Cursor(sqlite3.Cursor):

    def __init__(self, conn, statement):
        super().__init__(conn)
        self.statement = statement

    def perform(self, params=()):
        "Perform the statement with PARAMs, or prepare the query."

        # Use the exact same STATEMENT each time. Python's SQLite module
        # caches the parsed statement, if the string is the same object.
        self.execute(self.statement, params)

    def first_row(self, params=()):
        "Helper method to fetch the first row of a query."
        self.perform(params)
        row = self.fetchone()
        # We do not want to close the cursor. Thus, we must run the fetch
        # to completion instead. For queries using .first_row() this should
        # be no further rows.
        _ = self.fetchall()
        return row
