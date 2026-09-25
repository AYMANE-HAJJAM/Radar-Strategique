from concurrent.futures import Future, ThreadPoolExecutor
from threading import BoundedSemaphore
from typing import Callable, Protocol


class JobRunner(Protocol):
    def submit(self, task: Callable, *args) -> Future: ...
    def shutdown(self) -> None: ...


class LocalJobRunner:
    """Bounded local executor. Radar business logic has no dependency on threads."""
    def __init__(self, max_workers=2, capacity=5):
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix='radar')
        self.slots = BoundedSemaphore(capacity)

    def submit(self, task, *args):
        if not self.slots.acquire(blocking=False):
            raise RuntimeError('Local job queue is full.')
        try:
            future = self.executor.submit(task, *args)
        except Exception:
            self.slots.release()
            raise
        future.add_done_callback(lambda _: self.slots.release())
        return future

    def shutdown(self):
        self.executor.shutdown(wait=True)
