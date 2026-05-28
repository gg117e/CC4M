"""Thread-local stdout proxy utilities for concurrent job logging."""

from contextlib import contextmanager
from typing import Iterator, TextIO
import threading


class ThreadLocalStdoutProxy:
    """Route writes to per-thread stream while keeping a global stdout object."""

    def __init__(self, default_stream: TextIO):
        self._default_stream = default_stream
        self._local = threading.local()

    def _get_stream(self) -> TextIO:
        stream = getattr(self._local, "stream", None)
        if stream is None:
            return self._default_stream
        return stream

    @contextmanager
    def redirect(self, stream: TextIO) -> Iterator[None]:
        previous_stream = getattr(self._local, "stream", None)
        self._local.stream = stream
        try:
            yield
        finally:
            if previous_stream is None:
                if hasattr(self._local, "stream"):
                    delattr(self._local, "stream")
            else:
                self._local.stream = previous_stream

    def write(self, text: str) -> int:
        return self._get_stream().write(text)

    def flush(self) -> None:
        self._get_stream().flush()
