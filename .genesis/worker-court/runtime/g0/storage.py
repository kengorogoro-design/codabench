from __future__ import annotations

import os
from pathlib import Path
import tempfile


def atomic_replace(path: Path, data: bytes, before_commit=None):
    """Same-directory fsync/replace. Failure before commit preserves old bytes."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.'+path.name+'.', dir=path.parent)
    tmp = Path(name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if before_commit is not None:
            before_commit()
        os.replace(tmp, path)
        if os.name == 'posix':
            dfd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
    finally:
        tmp.unlink(missing_ok=True)
