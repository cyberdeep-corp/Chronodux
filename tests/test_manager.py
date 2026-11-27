
import threading
import time
import unittest

from chronodux import (
    Chronodux,
    TaskContext,
    ChronoduxError,
    TaskNotFoundError,
    ServiceNotFoundError,
    ManagerShutdownError,
    InvalidBackendError,
)


class TestChronodux(unittest.TestCase):

    def setUp(self):
        self.manager = Chronodux()

    def tearDown(self):
        if self.manager.health()["active"]:
            self.manager.shutdown(wait=True)

    # --------------------------------------------------------
    # INITIALIZATION
    # --------------------------------------------------------

    def test_initialization(self):
        self.assertEqual(self.manager.backend, "threading")
        self.assertTrue(self.manager.health()["active"])

    def test_concurrent_initialization(self):
        manager = Chronodux(backend="concurrent", max_workers=3)

        try:
            self.assertEqual(manager.backend, "concurrent")
            self.assertIsNotNone(manager._executor)
        finally:
            manager.shutdown()

    def test_invalid_backend(self):
        with self.assertRaises(InvalidBackendError):
            Chronodux(backend="invalid")

    # --------------------------------------------------------
    # THREADING EXECUTION
    # --------------------------------------------------------

    def test_thread_execution(self):
        task = self.manager.start(lambda: "thread-result")

        self.manager.join(task.id)

        self.assertEqual(task.status, "completed")
        self.assertEqual(self.manager.result(task.id), "thread-result")

    def test_thread_arguments(self):
        def add(a, b):
            return a + b

        task = self.manager.start(add, 10, 20)

        self.manager.join(task.id)

        self.assertEqual(self.manager.result(task.id), 30)

    def test_thread_keyword_arguments(self):
        def greet(name, greeting="Hello"):
            return f"{greeting}, {name}"

        task = self.manager.start(
            greet,
            name="Sam",
            greeting="Welcome",
        )

        self.manager.join(task.id)

        self.assertEqual(
            self.manager.result(task.id),
            "Welcome, Sam",
        )

    def test_run_thread_alias(self):
        task = self.manager.run_thread(lambda: 100)

        self.manager.join(task.id)

        self.assertEqual(task.backend, "threading")
        self.assertEqual(task.result, 100)

    # --------------------------------------------------------
    # CONCURRENT EXECUTION
    # --------------------------------------------------------

    def test_concurrent_execution(self):
        manager = Chronodux(
            backend="concurrent",
            max_workers=3,
        )

        try:
            task = manager.start(lambda: "concurrent-result")

            manager.join(task.id)

            self.assertEqual(task.status, "completed")
            self.assertEqual(
                manager.result(task.id),
                "concurrent-result",
            )
        finally:
            manager.shutdown()

    def test_submit_alias(self):
        task = self.manager.submit(lambda: 200)

        self.manager.join(task.id)

        self.assertEqual(task.backend, "concurrent")
        self.assertEqual(task.result, 200)

    def test_mixed_backend_execution(self):
        """A threading manager should support concurrent tasks on demand."""

        thread_task = self.manager.start(
            lambda: "thread",
            backend="threading",
        )

        concurrent_task = self.manager.start(
            lambda: "concurrent",
            backend="concurrent",
        )

        self.manager.join()

        self.assertEqual(thread_task.result, "thread")
        self.assertEqual(concurrent_task.result, "concurrent")

    # --------------------------------------------------------
    # TASK MANAGEMENT
    # --------------------------------------------------------

    def test_unique_task_ids(self):
        first = self.manager.start(lambda: 1)
        second = self.manager.start(lambda: 2)

        self.assertNotEqual(first.id, second.id)

    def test_get_task(self):
        task = self.manager.start(lambda: True)

        self.assertEqual(
            self.manager.get(task.id).id,
            task.id,
        )

    def test_missing_task(self):
        with self.assertRaises(TaskNotFoundError):
            self.manager.get("unknown-task")

    def test_list_tasks(self):
        self.manager.start(lambda: 1)
        self.manager.start(lambda: 2)

        self.assertEqual(len(self.manager.list_tasks()), 2)

    def test_task_status(self):
        task = self.manager.start(lambda: True)

        self.manager.join(task.id)

        self.assertEqual(
            self.manager.status(task.id),
            "completed",
        )

    def test_task_removal(self):
        task = self.manager.start(lambda: True)

        self.manager.join(task.id)

        self.assertTrue(self.manager.remove(task.id))
        self.assertEqual(len(self.manager.list_tasks()), 0)

    def test_clear_completed_tasks(self):
        self.manager.start(lambda: 1)
        self.manager.start(lambda: 2)

        self.manager.join()

        removed = self.manager.clear()

        self.assertEqual(removed, 2)
        self.assertEqual(len(self.manager.list_tasks()), 0)

    # --------------------------------------------------------
    # TASK CONTEXT AND CANCELLATION
    # --------------------------------------------------------

    def test_context_injection(self):
        def worker(context):
            return isinstance(context, TaskContext)

        task = self.manager.start(
            worker,
            pass_context=True,
        )

        self.manager.join(task.id)

        self.assertTrue(task.result)

    def test_cooperative_cancellation(self):
        started = threading.Event()

        def worker(context):
            started.set()

            while not context.stop_requested:
                context.wait(0.05)

            return "stopped"

        task = self.manager.start(
            worker,
            pass_context=True,
        )

        self.assertTrue(started.wait(2))

        self.assertTrue(self.manager.stop(task.id))
        self.manager.join(task.id, timeout=2)

        self.assertEqual(task.status, "completed")
        self.assertEqual(task.result, "stopped")

    def test_cancel_completed_task(self):
        task = self.manager.start(lambda: "done")

        self.manager.join(task.id)

        self.assertFalse(self.manager.cancel(task.id))

    # --------------------------------------------------------
    # EXCEPTION HANDLING
    # --------------------------------------------------------

    def test_task_exception(self):
        def failing_task():
            raise ValueError("Test exception")

        task = self.manager.start(failing_task)

        self.manager.join(task.id)

        self.assertEqual(task.status, "failed")
        self.assertIsInstance(task.exception, ValueError)

        with self.assertRaises(ValueError):
            self.manager.result(task.id)

    def test_non_callable_target(self):
        with self.assertRaises(TypeError):
            self.manager.start("not-callable")

    # --------------------------------------------------------
    # SERVICE MANAGEMENT
    # --------------------------------------------------------

    def test_register_service(self):
        result = self.manager.register_service(
            "test-service",
            lambda: "service-result",
        )

        self.assertEqual(result, "test-service")
        self.assertIn("test-service", self.manager.list_services())

    def test_duplicate_service(self):
        self.manager.register_service("service", lambda: None)

        with self.assertRaises(ChronoduxError):
            self.manager.register_service("service", lambda: None)

    def test_start_service(self):
        self.manager.register_service(
            "worker",
            lambda: "running",
        )

        task = self.manager.start_service("worker")

        self.manager.join(task.id)

        self.assertEqual(task.result, "running")
        self.assertEqual(
            self.manager.list_services()["worker"]["status"],
            "completed",
        )

    def test_restart_service(self):
        self.manager.register_service(
            "worker",
            lambda: "restarted",
        )

        first = self.manager.start_service("worker")
        self.manager.join(first.id)

        second = self.manager.restart_service("worker")
        self.manager.join(second.id)

        self.assertNotEqual(first.id, second.id)
        self.assertEqual(second.result, "restarted")

    def test_stop_completed_service(self):
        self.manager.register_service("worker", lambda: None)

        task = self.manager.start_service("worker")
        self.manager.join(task.id)

        self.assertFalse(self.manager.stop_service("worker"))

    def test_missing_service(self):
        with self.assertRaises(ServiceNotFoundError):
            self.manager.start_service("unknown")

    def test_unregister_service(self):
        self.manager.register_service("worker", lambda: None)

        self.assertTrue(
            self.manager.unregister_service("worker")
        )

        self.assertNotIn("worker", self.manager.list_services())

    # --------------------------------------------------------
    # MONITORING
    # --------------------------------------------------------

    def test_metrics(self):
        task = self.manager.start(lambda: "complete")

        self.manager.join(task.id)

        metrics = self.manager.metrics()

        self.assertEqual(metrics["total"], 1)
        self.assertEqual(metrics["completed"], 1)
        self.assertEqual(metrics["failed"], 0)

    def test_health(self):
        health = self.manager.health()

        self.assertEqual(health["name"], "Chronodux")
        self.assertEqual(health["version"], "0.1.0")
        self.assertTrue(health["active"])

    # --------------------------------------------------------
    # SHUTDOWN
    # --------------------------------------------------------

    def test_shutdown(self):
        self.assertTrue(self.manager.shutdown())
        self.assertFalse(self.manager.health()["active"])

    def test_double_shutdown(self):
        self.manager.shutdown()

        self.assertFalse(self.manager.shutdown())

    def test_start_after_shutdown(self):
        self.manager.shutdown()

        with self.assertRaises(ManagerShutdownError):
            self.manager.start(lambda: None)

    def test_context_manager(self):
        with Chronodux() as manager:
            task = manager.start(lambda: "context-result")
            manager.join(task.id)

            self.assertEqual(task.result, "context-result")

        self.assertFalse(manager.health()["active"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
