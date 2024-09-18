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
import functools

import yaml
import easydict


class DB:
    """Wrapper/functional class for accessing Sqlite3 databases.

    This class focuses on returning EasyDict instances for query results,
    so that columns can be indexed by name instead of position.

    In addition, it makes it easy to create cursors for later usage. Naming
    the cursors establishes a self-documenting mechanism when performing
    the statement or query. These cursors may be establishing through the
    use a .yaml file to clarify the SQL operations in a file for that
    purpose, instead of mixing them throughout a codebase.
    """

    def __init__(self, fname, yaml_fname=None, yaml_section='queries'):

        def row_factory(cursor, row):
            "Return an EasyDict of the row, for attribute access."
            return easydict.EasyDict(sqlite3.Row(cursor, row))

        # Note: isolation_level=None means autocommit mode.
        self.conn = sqlite3.connect(fname, isolation_level=None)
        self.conn.row_factory = row_factory

        # If a YAML file containing SQL queries is presented, then create
        # cursors for each statement, and storing those cursors as (named)
        # attributes on SELF, for later use by the calling application.
        if yaml_fname:
            # Note: this could be a general configuration file for the
            # application. We'll look at just one section of it.
            yml = yaml.safe_load(open(yaml_fname))

            # The YAML_SECTION (default "queries") should have names of
            # queries, to use as attributes, and the value should be the
            # SQL statement/query.
            for name, sql in yml.get(yaml_section, { }).items():
                if hasattr(self, name):
                    ### ValueError seems to be the bog standard for duplicates
                    raise ValueError(f'duplicate: {name}')
                #print(f'{name}: {sql}')
                setattr(self, name, self.cursor_for(sql))

    def cursor_for(self, statement):
        "Return our custom cursor for the given statement."
        return self.conn.cursor(_Cursor.factory_for(statement))


class _Cursor(sqlite3.Cursor):
    "A cursor subclass providing helper methods."

    @classmethod
    def factory_for(cls, statement):
        "Return a factory to construct instances for the given STATEMENT."
        return functools.partial(cls, statement)

    def __init__(self, statement, conn):
        super().__init__(conn)
        self.statement = statement

    def perform(self, *params):
        "Perform the statement with PARAMs, or prepare the query."

        # Use the exact same STATEMENT each time. Python's SQLite module
        # caches the parsed statement, if the string is the same object.
        self.execute(self.statement, params)

    def first_row(self, *params):
        "Helper method to fetch the first row of a query."
        self.perform(*params)
        row = self.fetchone()
        # We do not want to close the cursor. Thus, we must run the fetch
        # to completion instead. For queries using .first_row() this should
        # be no further rows.
        _ = self.fetchall()
        return row  # note the ROW_FACTORY implies this is an EasyDict


if __name__ == '__main__':
    ### maybe run some tests?
    import sys
    sys.stderr.write('ERROR: this module is not for command line use.\n')
    sys.exit(1)
