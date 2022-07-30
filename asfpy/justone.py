# -*- coding: utf-8 -*-
#
# justone.py -- utilities to ensure one process runs at a time
#

# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed
# with this work for additional information regarding copyright
# ownership.  The ASF licenses this file to You under the Apache
# License, Version 2.0 (the "License"); you may not use this file
# except in compliance with the License.  You may obtain a copy of the
# License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.  See the License for the specific language governing
# permissions and limitations under the License.
#

#
# GENERAL OUTLINE
#
# This module will construct a FIFO at given pathname. The process
# designated as "running" will open the FIFO for reading. On exit,
# the FIFO will be closed and unlinked.
#
# A tentative-run process will look for the FIFO. If it doesn't
# exist, then it is clear to run (per above). If it *does* exist,
# then the tentative will test whether a process is reading from
# the FIFO. If yes, then clearly another is running, and the
# tentative will just exit. If there does not appear to be a reader,
# then the module tests if the FIFO is "stale" (based on time) and
# removes it, or exits without running.
#


import os
import errno
import time
import contextlib

STALE = 3600  # seconds

DID_NOT_RUN = object()


def maybe_run(fifo_fname, func, stale=STALE):
    try:
        info = os.stat(fifo_fname)
    except OSError:
        # Some error (assume it doesn't exist), so run the func
        return _run_func(fifo_fname, func)

    # Opening a FIFO in non-blocking will throw ENXIO if no reader
    # is on the other end.
    try:
        fd = os.open(fifo_fname, os.O_WRONLY | os.O_NONBLOCK)

        # Successful open means a reader exists. Thus, we're done.
        os.close(fd)
        return DID_NOT_RUN

    except OSError as e:
        if e.errno == errno.ENOENT:
            # RACE: the FIFO just disappeared. Meaning another
            # process *just* completed. Go ahead and run the func.
            return _run_func(fifo_fname, func)

        # Note: ENXIO means there is no reader on the other end.
        # Bail on anything else, as we can't handle it.
        if e.errno != errno.ENXIO:
            raise

        # Check for a stale FIFO.

        # There is no reader process, but the FIFO exists. Could be
        # a race condition (FIFO is opening/closing in the reader),
        # or maybe a stale FIFO.
        if time.time() - info.st_mtime > stale:
            ### RACE: we might be removing another runner's FIFO
            os.unlink(fifo_fname)
            return _run_func(fifo_fname, func)

        # Not stale (yet). Don't do anything for now.
        return DID_NOT_RUN


def _run_func(fifo_fname, func):
    with _temp_fifo(fifo_fname) as okay:
        if okay:
            return func()


@contextlib.contextmanager
def _temp_fifo(fifo_fname):
    # Create the FIFO
    try:
        os.mkfifo(fifo_fname)
    except OSError:
        # Likely RACE: a FIFO exists/appeared (and mkfifo failed).
        # Let the other process run with this.
        yield False  # not okay
        return  # stop iterating

    try:
        # Open it for reading, to signal "we got this".
        fd = os.open(fifo_fname, os.O_RDONLY | os.O_NONBLOCK)

        try:
            # Okay to run.
            yield True
        finally:
            os.close(fd)

    finally:
        # Note: there might be a RACE where the OPEN fails after
        # we created the FIFO (eg. another process removed it).
        # Not sure how this would happen. Just bail.

        try:
            os.unlink(fifo_fname)
        except OSError:
            # In case the FIFO disappeared somehow: we don't care.
            pass

    # stop iterating
    return
