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

"""Template Watcher class."""
#
# TYPICAL USAGE:
#
#   tw = twatcher.TemplateWatcher()
#   T_1 = tw.load_template(PATH_1)
#   T_2 = tw.load_template(PATH_2)
#   T_3 = tw.load_template(PATH_3, base_format=ezt.FORMAT_HTML)
#   loop.create_task(tw.watch_forever())
#
# If PATH_* is modified, then T_* will be updated (in place) with
# the new template contents.
#

import logging

import ezt
import watchfiles

LOGGER = logging.getLogger(__name__)


class TemplateWatcher:

    def __init__(self):
        # PATH : (ezt.Template, BASE_FORMAT)
        self.templates = { }

        self.files = set()

    def load_template(self, path, **kwargs):
        """Load template at PATH with **KWARGS.

        Note: it is best to use absolute paths, to avoid problems if
        the current directory changes.

        Returns an instance of ezt.Template()
        """

        LOGGER.info(f'Watching: {path}')
        t = ezt.Template(path, **kwargs)
        bf = kwargs.get('base_format', ezt.FORMAT_RAW)

        # Use str(path) in case PATH is a pathlib.Path instance.
        self.templates[str(path)] = (t, bf)

        self.files.add(path)

        return t

    @staticmethod
    def watch_filter(change: watchfiles.Change, path: str) -> bool:
        return change in {watchfiles.Change.added, watchfiles.Change.modified}

    async def watch_forever(self):
        async for changes in watchfiles.awatch(*self.files, watch_filter=self.watch_filter):
            for event in changes:
                path = str(event[1])
                LOGGER.info(f'Template changed: {path}')
                #print(event)

                # Reparse the file.
                t, bf = self.templates[path]
                t.parse_file(path, bf)


def test_watcher(fnames):
    logging.basicConfig(level=logging.DEBUG)
    tw = TemplateWatcher()
    for path in fnames:
        _ = tw.load_template(path)
    import asyncio
    asyncio.run(tw.watch_forever())


if __name__ == '__main__':
    import sys
    test_watcher(sys.argv[1:])
