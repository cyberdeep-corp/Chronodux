
"""
Chronodux
---------
Hybrid Python Threading and Concurrent Execution Manager.

Version: 0.1.0
Package: chronodux
"""

__version__ = "0.1.0"
__author__ = "SamWorks Studios"
__license__ = "UOSL-1.0"

import threading
import concurrent.futures
import uuid
import time

from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# ============================================================
# EXCEPTIONS
# ============================================================

class ChronoduxError(Exception):
    """Base exception for Chronodux."""


class TaskNotFoundError(ChronoduxError):
    """Raised when a task cannot be found."""


class ServiceNotFoundError(ChronoduxError):
    """Raised when a service cannot be found."""


class ManagerShutdownError(ChronoduxError):
    """Raised when operating on a shut-down manager."""


class InvalidBackendError(ChronoduxError):
    """Raised when an unsupported execution backend is selected."""


# ============================================================
# TASK CONTEXT
# ============================================================

class TaskContext:
    """Execution context supplied to managed tasks."""

    def __init__(self, task_id: str, name: str):
        self.id = task_id
        self.name = name
        self._stop_event = threading.Event()

    @property
    def stop_requested(self):
        return self._stop_event.is_set()

    def stop(self):
        """Request cooperative task termination."""
        self._stop_event.set()

    def wait(self, timeout=None):
        """Wait until termination is requested."""
        return self._stop_event.wait(timeout)

    def raise_if_stopped(self):
        """Raise if termination has been requested."""
        if self.stop_requested:
            raise InterruptedError("Task termination requested.")


# ============================================================
# TASK MODEL
# ============================================================

@dataclass
class Task:
    """Represents an individual execution task."""

    id: str
    name: str
    target: Callable
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    backend: str = "threading"

    status: str = "pending"
    result: Any = None
    exception: Optional[BaseException] = None

    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    thread: Optional[threading.Thread] = None
    future: Optional[concurrent.futures.Future] = None
    context: Optional[TaskContext] = None

    def is_alive(self):
        """Check whether the task is currently executing."""
        if self.thread:
            return self.thread.is_alive()

        if self.future:
            return self.future.running()

        return False

    @property
    def done(self):
        return self.status in ("completed", "failed", "cancelled")

    @property
    def duration(self):
        """Return execution duration in seconds."""
        if not self.started_at:
            return None

        end = self.finished_at or datetime.now(timezone.utc)
        return (end - self.started_at).total_seconds()


# ============================================================
# CHRONODUX CORE
# ============================================================

class Chronodux:
    """
    Hybrid service manager for Python threads and concurrent tasks.

    Supported engines:
        - threading
        - concurrent
    """

    BACKENDS = ("threading", "concurrent")

    def __init__(
        self,
        backend="threading",
        max_workers=None,
        thread_name_prefix="Chronodux",
        daemon=False,
    ):
        self._validate_backend(backend)

        self.backend = backend
        self.max_workers = max_workers
        self.daemon = daemon

        self._tasks = {}
        self._services = {}

        self._lock = threading.RLock()
        self._shutdown = False

        self._executor = None

        if backend == "concurrent":
            self._executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=max_workers,
                thread_name_prefix=thread_name_prefix,
            )

    # --------------------------------------------------------
    # INTERNAL UTILITIES
    # --------------------------------------------------------

    @classmethod
    def _validate_backend(cls, backend):
        if backend not in cls.BACKENDS:
            raise InvalidBackendError(
                f"Unsupported backend: {backend}. "
                f"Choose from {cls.BACKENDS}."
            )

    def _ensure_active(self):
        if self._shutdown:
            raise ManagerShutdownError(
                "Chronodux manager has been shut down."
            )

    def _get_task(self, task_id):
        with self._lock:
            task = self._tasks.get(task_id)

        if task is None:
            raise TaskNotFoundError(
                f"Task '{task_id}' was not found."
            )

        return task

    # --------------------------------------------------------
    # TASK EXECUTION
    # --------------------------------------------------------

    def start(
        self,
        target,
        *args,
        backend=None,
        name=None,
        daemon=None,
        pass_context=False,
        **kwargs,
    ):
        """
        Start a task using the selected execution backend.

        pass_context=True injects TaskContext as the first argument
        to the target callable.
        """

        self._ensure_active()

        if not callable(target):
            raise TypeError("target must be callable.")

        selected_backend = backend or self.backend
        self._validate_backend(selected_backend)

        task_id = uuid.uuid4().hex

        task = Task(
            id=task_id,
            name=name or getattr(target, "__name__", "ChronoduxTask"),
            target=target,
            args=args,
            kwargs=kwargs,
            backend=selected_backend,
        )

        task.context = TaskContext(task_id, task.name)

        with self._lock:
            self._ensure_active()
            self._tasks[task_id] = task

        def runner():
            with self._lock:
                if task.status == "cancelled":
                    return None

                task.status = "running"
                task.started_at = datetime.now(timezone.utc)

            try:
                call_args = task.args

                if pass_context:
                    call_args = (task.context,) + call_args

                result = task.target(*call_args, **task.kwargs)

                with self._lock:
                    task.result = result

                    if task.status != "cancelled":
                        task.status = "completed"

                return result

            except BaseException as exc:
                with self._lock:
                    task.exception = exc

                    if task.status != "cancelled":
                        task.status = "failed"

                raise

            finally:
                with self._lock:
                    task.finished_at = datetime.now(timezone.utc)

        if selected_backend == "threading":

            thread = threading.Thread(
                target=runner,
                name=task.name,
                daemon=self.daemon if daemon is None else daemon,
            )

            task.thread = thread

            try:
                thread.start()
            except BaseException:
                with self._lock:
                    self._tasks.pop(task_id, None)
                raise

        
        else:
            try:
                with self._lock:
                    self._ensure_active()

                    if self._executor is None:
                        self._executor = (
                            concurrent.futures.ThreadPoolExecutor(
                                max_workers=self.max_workers,
                                thread_name_prefix="Chronodux",
                            )
                        )

                    task.future = self._executor.submit(runner)

            except BaseException:
                with self._lock:
                    self._tasks.pop(task_id, None)
                raise

        return task

    # --------------------------------------------------------
    # TASK MANAGEMENT
    # --------------------------------------------------------

    def get(self, task_id):
        """Retrieve a task by ID."""
        return self._get_task(task_id)

    def list_tasks(self, status=None):
        """Return all tasks, optionally filtered by status."""
        with self._lock:
            tasks = list(self._tasks.values())

        if status:
            tasks = [t for t in tasks if t.status == status]

        return tasks

    def status(self, task_id=None):
        """Return one task's status or all task statuses."""
        if task_id:
            return self._get_task(task_id).status

        with self._lock:
            return {
                task_id: task.status
                for task_id, task in self._tasks.items()
            }

    def stop(self, task_id):
        """
        Request cooperative termination.

        Python cannot safely force-kill a running thread.
        Tasks must cooperate using TaskContext.
        """

        task = self._get_task(task_id)

        if task.done:
            return False

        task.context.stop()

        if task.future:
            if task.future.cancel():
                with self._lock:
                    task.status = "cancelled"
                    task.finished_at = datetime.now(timezone.utc)
                return True

        return True

    def cancel(self, task_id):
        """Alias for stop()."""
        return self.stop(task_id)

    def join(self, task_id=None, timeout=None):
        """Wait for one task or all managed tasks."""

        if task_id:
            tasks = [self._get_task(task_id)]
        else:
            tasks = self.list_tasks()

        deadline = (
            time.monotonic() + timeout
            if timeout is not None else None
        )

        for task in tasks:
            remaining = (
                max(0, deadline - time.monotonic())
                if deadline is not None else None
            )

            if task.thread:
                task.thread.join(remaining)

            elif task.future:
                try:
                    task.future.result(timeout=remaining)
                except concurrent.futures.TimeoutError:
                    raise
                except BaseException:
                    pass

        return all(task.done for task in tasks)

    def result(self, task_id, timeout=None):
        """Retrieve the task result, propagating execution errors."""
        task = self._get_task(task_id)

        if task.future:
            return task.future.result(timeout=timeout)

        if task.thread:
            task.thread.join(timeout)

            if task.thread.is_alive():
                raise TimeoutError("Task is still running.")

        if task.exception:
            raise task.exception

        if not task.done:
            raise TimeoutError("Task has not completed.")

        return task.result

    def remove(self, task_id):
        """Remove a completed task from the manager."""
        task = self._get_task(task_id)

        if not task.done:
            raise ChronoduxError(
                "Cannot remove a task that is still running."
            )

        with self._lock:
            del self._tasks[task_id]

        return True

    def clear(self, completed_only=True):
        """Clear completed tasks or all safely removable tasks."""
        with self._lock:
            removable = [
                task_id
                for task_id, task in self._tasks.items()
                if not completed_only or task.done
            ]

            for task_id in removable:
                del self._tasks[task_id]

        return len(removable)

    # --------------------------------------------------------
    # SERVICE MANAGEMENT
    # --------------------------------------------------------

    def register_service(self, name, target, *args, **kwargs):
        """Register a reusable named service."""

        self._ensure_active()

        if not callable(target):
            raise TypeError("Service target must be callable.")

        if not name:
            raise ValueError("Service name cannot be empty.")

        with self._lock:
            if name in self._services:
                raise ChronoduxError(
                    f"Service '{name}' is already registered."
                )

            self._services[name] = {
                "target": target,
                "args": args,
                "kwargs": kwargs,
                "task_id": None,
            }

        return name

    def start_service(self, name, backend=None):
        """Start a registered service."""

        self._ensure_active()

        with self._lock:
            service = self._services.get(name)

            if service is None:
                raise ServiceNotFoundError(name)

            current_id = service["task_id"]

            if current_id:
                current = self._tasks.get(current_id)

                if current and not current.done:
                    raise ChronoduxError(
                        f"Service '{name}' is already running."
                    )

            target = service["target"]
            args = service["args"]
            kwargs = service["kwargs"]

        task = self.start(
            target,
            *args,
            backend=backend,
            name=name,
            **kwargs,
        )

        with self._lock:
            service["task_id"] = task.id

        return task

    def stop_service(self, name):
        """Stop a registered service."""

        with self._lock:
            service = self._services.get(name)

            if service is None:
                raise ServiceNotFoundError(name)

            task_id = service["task_id"]

        if not task_id:
            return False

        return self.stop(task_id)

    def restart_service(self, name, backend=None):
        """Restart a registered service."""

        with self._lock:
            service = self._services.get(name)

            if service is None:
                raise ServiceNotFoundError(name)

            task_id = service["task_id"]

        if task_id:
            task = self._get_task(task_id)

            if not task.done:
                self.stop(task_id)
                self.join(task_id)

        return self.start_service(name, backend=backend)

    def unregister_service(self, name, stop=False):
        """Unregister a service."""

        if stop:
            self.stop_service(name)

        with self._lock:
            if name not in self._services:
                raise ServiceNotFoundError(name)

            del self._services[name]

        return True

    def list_services(self):
        """List registered service names and statuses."""

        with self._lock:
            services = dict(self._services)

        result = {}

        for name, service in services.items():
            task_id = service["task_id"]
            task = self._tasks.get(task_id) if task_id else None

            result[name] = {
                "task_id": task_id,
                "status": task.status if task else "stopped",
            }

        return result

    # --------------------------------------------------------
    # CONCURRENCY UTILITIES
    # --------------------------------------------------------

    def submit(self, target, *args, **kwargs):
        """Submit a task explicitly to the concurrent engine."""

        return self.start(
            target,
            *args,
            backend="concurrent",
            **kwargs,
        )

    def run_thread(self, target, *args, **kwargs):
        """Execute a task explicitly using threading."""

        return self.start(
            target,
            *args,
            backend="threading",
            **kwargs,
        )

    def wait(self, timeout=None, return_when="ALL_COMPLETED"):
        """Wait for all concurrent futures."""

        futures = [
            task.future
            for task in self.list_tasks()
            if task.future is not None
        ]

        if not futures:
            return set(), set()

        return concurrent.futures.wait(
            futures,
            timeout=timeout,
            return_when=return_when,
        )

    # --------------------------------------------------------
    # MONITORING
    # --------------------------------------------------------

    def metrics(self):
        """Return execution statistics."""

        tasks = self.list_tasks()

        return {
            "total": len(tasks),
            "pending": sum(t.status == "pending" for t in tasks),
            "running": sum(t.status == "running" for t in tasks),
            "completed": sum(t.status == "completed" for t in tasks),
            "failed": sum(t.status == "failed" for t in tasks),
            "cancelled": sum(t.status == "cancelled" for t in tasks),
        }

    def health(self):
        """Return manager health information."""

        return {
            "name": "Chronodux",
            "version": __version__,
            "backend": self.backend,
            "active": not self._shutdown,
            "metrics": self.metrics(),
        }

    # --------------------------------------------------------
    # SHUTDOWN
    # --------------------------------------------------------

    def shutdown(self, wait=True, cancel_futures=False):
        """
        Shut down Chronodux.

        Running threading tasks receive cooperative stop requests.
        Running concurrent tasks cannot be forcibly terminated.
        """

        with self._lock:
            if self._shutdown:
                return False

            self._shutdown = True
            tasks = list(self._tasks.values())

        for task in tasks:
            if not task.done:
                task.context.stop()

                if task.future and cancel_futures:
                    if task.future.cancel():
                        with self._lock:
                            task.status = "cancelled"
                            task.finished_at = datetime.now(timezone.utc)

        if self._executor:
            self._executor.shutdown(
                wait=wait,
                cancel_futures=cancel_futures,
            )

        if wait:
            for task in tasks:
                if task.thread:
                    task.thread.join()

        return True

    # --------------------------------------------------------
    # CONTEXT MANAGER
    # --------------------------------------------------------

    def __enter__(self):
        self._ensure_active()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.shutdown(wait=True)
        return False

    def __repr__(self):
        return (
            f"<Chronodux version={__version__!r} "
            f"backend={self.backend!r} "
            f"tasks={len(self._tasks)}>"
        )


# ============================================================
# PUBLIC API
# ============================================================

__all__ = [
    "__version__",
    "Chronodux",
    "Task",
    "TaskContext",
    "ChronoduxError",
    "TaskNotFoundError",
    "ServiceNotFoundError",
    "ManagerShutdownError",
    "InvalidBackendError",
]
