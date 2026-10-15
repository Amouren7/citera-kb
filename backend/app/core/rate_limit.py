"""进程内滑动窗口限流。

演示环境是单进程单 worker 容器，用进程内计数足够，不引入 Redis（免费平台内存有限，
契约 §8.3 明确不增加常驻进程）。限流阈值见契约 §4.2。
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, cost: int = 1) -> bool:
        now = time.monotonic()
        with self._lock:
            bucket = self._hits[key]
            cutoff = now - self.window
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) + cost > self.limit:
                return False
            for _ in range(cost):
                bucket.append(now)
            return True

    def remaining(self, key: str) -> int:
        now = time.monotonic()
        with self._lock:
            bucket = self._hits[key]
            cutoff = now - self.window
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            return max(0, self.limit - len(bucket))

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


# 按契约 §4.2 的三档阈值
auth_limiter = SlidingWindowLimiter(limit=10, window_seconds=60)      # 登录/注册，按 IP
ask_limiter = SlidingWindowLimiter(limit=20, window_seconds=60)       # 提问，按用户
upload_limiter = SlidingWindowLimiter(limit=10, window_seconds=60)    # 上传，按用户


def reset_all() -> None:
    for limiter in (auth_limiter, ask_limiter, upload_limiter):
        limiter.reset()
