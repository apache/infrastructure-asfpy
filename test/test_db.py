#!/usr/bin/env python3
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

"""Tests of asfpy.db: rows come back as a Box, with the columns as attributes."""

# A fixture is used by naming it as a parameter, which pylint sees as
# shadowing. The queries of a DB are set as attributes at run time, which
# pylint cannot see.
# pylint: disable=redefined-outer-name,no-member

import json

import pytest

import asfpy.db


@pytest.fixture
def db():
    "An in-memory database with one table and two rows."
    database = asfpy.db.DB(':memory:')
    setup = database.cursor_for('create table people (id integer, name text, [home town] text)')
    setup.perform()
    insert = database.cursor_for('insert into people values (?, ?, ?)')
    insert.perform(1, 'alice', 'Austin')
    insert.perform(2, 'bob', 'Boston')
    return database


def test_rows_have_columns_as_attributes(db):
    select = db.cursor_for('select * from people order by id')
    select.perform()
    rows = select.fetchall()
    assert [row.name for row in rows] == ['alice', 'bob']
    assert rows[0].id == 1
    assert rows[0]['home town'] == 'Austin'


def test_a_row_is_still_a_dict(db):
    row = db.cursor_for('select * from people where id = ?').first_row(2)
    assert isinstance(row, dict)
    assert row == {'id': 2, 'name': 'bob', 'home town': 'Boston'}
    assert json.loads(json.dumps(row)) == row


def test_a_missing_column_raises(db):
    row = db.cursor_for('select name from people where id = ?').first_row(1)
    with pytest.raises(AttributeError):
        _ = row.no_such_column
    with pytest.raises(KeyError):
        _ = row['no_such_column']


def test_first_row_of_nothing_is_none(db):
    assert db.cursor_for('select * from people where id = ?').first_row(99) is None


def test_queries_from_a_yaml_file(tmp_path):
    queries = tmp_path / 'queries.yaml'
    queries.write_text(
        'queries:\n'
        '  make_table: create table t (n integer)\n'
        '  add: insert into t values (?)\n'
        '  biggest: select max(n) as biggest from t\n'
    )
    database = asfpy.db.DB(':memory:', yaml_fname=str(queries))
    database.make_table.perform()
    database.add.perform(3)
    database.add.perform(7)
    assert database.biggest.first_row().biggest == 7


def test_a_query_may_not_shadow_an_attribute(tmp_path):
    queries = tmp_path / 'queries.yaml'
    queries.write_text('queries:\n  conn: select 1\n')
    with pytest.raises(ValueError, match='duplicate: conn'):
        asfpy.db.DB(':memory:', yaml_fname=str(queries))
