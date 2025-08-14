import asyncio
from collections import defaultdict
from collections.abc import Hashable

# A thread-safe wrapper for locking on arbitrary hashable values
# Does not cleanup
class ScopedLock:
    def __init__(self):
        self._locks = defaultdict(asyncio.Lock)
        self._lock = asyncio.Lock()

    async def on(self, scope: Hashable):
        async with self._lock:
            lock = self._locks[scope]
        return lock
