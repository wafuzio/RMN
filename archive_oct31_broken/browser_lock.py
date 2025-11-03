import os
import time
import errno
import fcntl
from contextlib import contextmanager

DEFAULT_LOCK_PATH = "/tmp/kroger_playwright_browser.lock"

class FileLock:
    def __init__(self, path: str = DEFAULT_LOCK_PATH, timeout: float = 120.0, poll_interval: float = 0.5):
        self.path = path
        self.timeout = timeout
        self.poll_interval = poll_interval
        self._fh = None

    def acquire(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._fh = open(self.path, "w+")
        start = time.time()
        while True:
            try:
                fcntl.lockf(self._fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                # Write PID for observability
                try:
                    self._fh.seek(0)
                    self._fh.truncate()
                    self._fh.write(str(os.getpid()))
                    self._fh.flush()
                except Exception:
                    pass
                return True
            except OSError as e:
                if e.errno not in (errno.EACCES, errno.EAGAIN):
                    raise
                if (time.time() - start) >= self.timeout:
                    return False
                time.sleep(self.poll_interval)

    def release(self):
        try:
            if self._fh:
                fcntl.lockf(self._fh, fcntl.LOCK_UN)
                self._fh.close()
        except Exception:
            pass
        finally:
            self._fh = None

    def __enter__(self):
        ok = self.acquire()
        if not ok:
            raise TimeoutError(f"Timed out waiting for browser lock: {self.path}")
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()
        # Do not suppress exceptions
        return False

@contextmanager
def single_browser_lock(timeout: float = 120.0, path: str = DEFAULT_LOCK_PATH):
    lock = FileLock(path=path, timeout=timeout)
    with lock:
        yield
