#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
 #the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"SQLite document-store wrapper for ASF."

import sqlite3
import typing

DEFAULT_ISOLATION_LEVEL = None  # When None, enables auto-commit mode in sqlite
# https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.isolation_level

class AsfpyDBError(Exception):
    pass


class DB:
    def __init__(self, fp: str, isolation_level: typing.Optional[str] = DEFAULT_ISOLATION_LEVEL):
        self.connector = sqlite3.connect(fp, isolation_level=isolation_level)
        self.connector.row_factory = sqlite3.Row
        self.cursor = self.connector.cursor()
        # Need sqlite 3.25.x or higher for upserts
        self.upserts_supported: bool = (sqlite3.sqlite_version >= "3.25.0")

    def run(self, cmd: str, *args):
        """
        Runs an SQLITE command in a cursor, but does not commit changes to disk
        @param cmd: The command to run
        @param args: Optional interpolated arguments
        """
        self.cursor.execute(cmd, args)

    def runc(self, cmd: str, *args):
        """
        Runs an SQLITE command and commits the changes to disk
        @param cmd: The command to run
        @param args: Optional interpolated arguments
        """
        self.cursor.execute(cmd, args)
        self.connector.commit()

    def delete(self, table: str, **target):
        """
        Deletes one or more matching entries from a table where a specific document key/value matches.
        @param table: The table to remove entries from
        @param target: Variable key/value pairs to form the selection match. For instance, user=janedoe
        """
        if not target:
            raise AsfpyDBError("DELETE must have at least one defined target value for locating where to delete from")
        items = target.items()  # Use the same ordering for keys/values
        search = " AND ".join("`%s` = ?" % uk for uk, uv in items)
        values = [uv for uk, uv in items]
        statement = f'DELETE FROM {table} WHERE {search}'
        self.runc(statement, *values)

    def update(self, table: str, document: dict, **target):
        """
        Updates one or more rows in a table where the target key/value pair matches
        Example:
            update('accounts', { 'name': 'jane doe', 'password': '1245' }, user_id='janedoe')
            would update any rows where user_id is 'janedoe' and set name and password.
        @param table: The table to edit
        @param document: The document, as a dict, to update (target values)
        @param target: The search key/value pair for finding the right document.
        """
        if not target:
            raise AsfpyDBError("UPDATE must have at one defined target to specify the row to update")
        k, v = next(iter(target.items()))
        items = document.items()  # Use the same ordering for keys/values
        columns = ", ".join("%s = ?" % uk for uk, uv in items)
        statement = f'UPDATE {table} SET {columns} WHERE {k} = ?;'
        values = [uv for uk, uv in items]
        values.append(v)  # unique constraint
        self.runc(statement, *values)

    def insert(self, table: str, document: dict):
        """
        Inserts a row into a table
        @param table: The table to insert the row into
        @param document: The row data, as a dict, to insert.
        """
        items = document.items()  # Use the same ordering for keys/values
        columns = ", ".join("`%s`" % uk for uk, uv in items)
        questionmarks = ", ".join(['?'] * len(items))
        statement = f'INSERT INTO {table} ({columns}) VALUES ({questionmarks});'
        values = [uv for uk, uv in items]
        self.runc(statement, *values)

    def upsert(self, table: str, document: dict, **target):
        """
        Performs an upsert in a table with unique constraints. Insert if not present, update otherwise.
        @param table: The table to upsert into
        @param document: The document to insert/update (depending on whether it exists)
        @param target: Target search key/value parameters to look for existing document.
        """
        # Always have the target identifier as part of the row
        if not target:
            raise AsfpyDBError("UPSERTs must have at least one defined target value for locating where to upsert")
        k, v = next(iter(target.items()))
        document[k] = v

        # table: foo
        # bar: 1
        # baz: 2
        # INSERT INTO foo (bar,baz) VALUES (?,?) ON CONFLICT (bar) DO UPDATE SET (bar=?, foo=?) WHERE bar=?,(1,2,1,2,1,)
        if self.upserts_supported:
            items = document.items()  # Use the same ordering for keys/values
            variables = ", ".join("`%s`" % uk for uk, uv in items)
            questionmarks = ", ".join(['?'] * len(items))
            upserts = ", ".join("`%s` = ?" % uk for uk, uv in items)

            statement = f'INSERT INTO {table} ({variables}) VALUES ({questionmarks}) ON CONFLICT({k}) DO UPDATE SET {upserts} WHERE {k} = ?;'
            # insert values, update values, and the unique constraint value
            values = ([uv for uk, uv in items] * 2) + [v]
            self.runc(statement, *values)
        # Older versions of sqlite do not support 'ON CONFLICT', so we'll have to work around that...
        else:
            try:  # Try to insert
                self.insert(table, document)
            except sqlite3.IntegrityError: # Conflict, update instead
                self.update(table, document, **target)

    def fetch(self, table: str, limit: int = 1, **params) -> typing.Iterator[dict]:
        """
        Searches a table for matching params, returns up to $limit items that match, as dicts in an iterator.
        If no limit is specified, returns all matches.
        @param table: Table to fetch rows from
        @param limit: The maximum number of rows to fetch. Can be None, for all rows
        @param params: Search parameters as key/value pairs
        @return: An iterator with all the found rows as dicts
        """
        if params:
            items = params.items()  # Use the same ordering for keys/values
            search = " AND ".join("`%s` = ?" % uk for uk, uv in items)
            values = [uv for uk, uv in items]
        else:
            search = "1"
            values = []
        statement = f'SELECT * FROM {table} WHERE {search}'
        if limit:
            statement += f' LIMIT {limit}'
            rows_left = limit
        self.cursor.execute(statement, values)
        while True:
            rowset = self.cursor.fetchmany()
            if not rowset:
                return  # break iteration
            for row in rowset:
                yield dict(row)
            if limit:
                rows_left -= len(rowset)
                assert rows_left >= 0
                if rows_left == 0:
                    return  # break iteration

    def fetchone(self, table_name: str, **params) -> typing.Optional[dict]:
        """
        Fetches a single row from a table, or None if no match was found.
        @param table_name: The table to search in
        @param params: Search parameters as key/value pairs
        @return: If a match was found, returns the matching row as a dict, else None
        """
        try:
            return next(self.fetch(table_name, **params))
        except StopIteration:  # No more entries!
            return None

    def table_exists(self, table: str) -> bool:
        """
        Checks if a table exists in the database
        @param table: The table to look for
        @return: Boolean True or False, depending on whether the table exists.
        """
        return self.fetchone('sqlite_master', type='table', name=table) and True or False


def test(dbname=':memory:'):
    testdb = db(dbname)
    cstatement = '''CREATE TABLE test (
                      foo   varchar unique,
                      bar   varchar,
                      baz   real
                      )'''

    # Create if not already here
    try:
        testdb.runc(cstatement)
    except sqlite3.OperationalError as e:  # Table exists
        assert str(e) == "table test already exists"

    # Insert (may fail if already tested)
    try:
        testdb.insert('test', {'foo': 'foo1234', 'bar': 'blorgh', 'baz': 5})
    except sqlite3.IntegrityError as e:
        assert str(e) == "UNIQUE constraint failed: test.foo"

    # This must fail
    try:
        testdb.insert('test', {'foo': 'foo1234', 'bar': 'blorgh', 'baz': 2})
    except sqlite3.IntegrityError as e:
        assert str(e) == "UNIQUE constraint failed: test.foo"

    # This must pass
    testdb.upsert('test', {'foo': 'foo1234', 'bar': 'blorgssh', 'baz': 8}, foo='foo1234')

    # This should fail with no target specified
    try:
        testdb.upsert('test', {'foo': 'foo1234', 'bar': 'blorgssh', 'baz': 8})
    except AsfpyDBError as e:
        assert str(e) == "UPSERTs must have at least one defined target value for locating where to upsert"

    # This should all pass
    testdb.update('test', {'foo': 'foo4321'}, foo='foo1234')
    obj = testdb.fetchone('test', foo='foo4321')
    assert type(obj) is dict and obj.get('foo') == 'foo4321'
    obj = testdb.fetch('test', limit=5, foo = 'foo4321')
    assert str(type(obj)) == "<class 'generator'>"
    assert next(obj).get('foo') == 'foo4321'
    obj = testdb.fetchone('test', foo='foo9999')
    assert obj is None
    testdb.delete('test', foo='foo4321')
    assert testdb.table_exists('test')
    assert not testdb.table_exists('test2')

    # Let's insert 1000 rows, and perform a repeated fetch.
    for i in range(1000):
        testdb.insert('test', {'foo': str(i), 'bar': str(i), 'baz': i})
    count = 0
    for row in testdb.fetch('test', limit=None):
        assert int(row['foo']) == count
        count += 1
    assert count == 1000

    # Change the arraysize, and run it again.
    testdb.cursor.arraysize = 97  # ensure last fetch is short
    count = 0
    for row in testdb.fetch('test', limit=None):
        assert int(row['foo']) == count
        count += 1
    assert count == 1000

    # One more run, with a limit. Leave the arraysize.
    count = 0
    for row in testdb.fetch('test', limit=30):
        assert int(row['foo']) == count
        count += 1
    assert count == 30


# Backwards compatibility
db = DB

if __name__ == '__main__':
    test()
