# Chronodux

**Chronodux** is a lightweight Python service manager for orchestrating threads, background tasks, and code execution lifecycles.

It provides a unified interface for managing Python threads and concurrent execution through two execution backends:

- **Threading** — Direct execution using Python's `threading.Thread`.
- **Concurrent** — Managed execution using `concurrent.futures.ThreadPoolExecutor`.

Chronodux also provides task tracking, cooperative cancellation, service lifecycle management, execution results, and basic health monitoring.

## Features

- **Dual Execution Backends:** Choose between `threading` and `concurrent` execution.
- **Task Management:** Start, retrieve, monitor, join, cancel, and remove tasks.
- **Task Context:** Pass execution context into tasks for cooperative termination.
- **Result Handling:** Retrieve task results and access execution exceptions.
- **Service Management:** Register, start, stop, restart, and unregister reusable services.
- **Concurrency Utilities:** Submit concurrent tasks, run individual threads, and wait for futures.
- **Execution Metrics:** Monitor task counts and execution states.
- **Health Monitoring:** Retrieve manager status and execution statistics.
- **Lifecycle Management:** Shut down the manager or use it as a context manager.
- **Lightweight:** Uses Python's standard library without external runtime dependencies.

## Requirements

- Python 3.9 or newer.

## Installation

Install Chronodux using pip:

```bash
pip install chronodux
```

## Quick Start

Create a manager and start a background task:

```python
from chronodux import Chronodux

def sample_task():
    print("Running managed task...")

manager = Chronodux()

task = manager.start(sample_task)

manager.join(task.id)

print(manager.status(task.id))

manager.shutdown()
```

## Execution Backends

Chronodux supports two execution backends.

### 1. Threading Backend

The default backend uses Python threads.

```python
from chronodux import Chronodux

manager = Chronodux(backend="threading")

def worker():
    print("Executing through threading")

task = manager.start(worker)

manager.join(task.id)
manager.shutdown()
```

### 2. Concurrent Backend

The concurrent backend uses `ThreadPoolExecutor` to manage execution through a thread pool.

```python
from chronodux import Chronodux

manager = Chronodux(
    backend="concurrent",
    max_workers=4
)

def worker():
    return "Concurrent execution completed"

task = manager.start(worker)

print(manager.result(task.id))

manager.shutdown()
```

`max_workers` controls the maximum number of worker threads in the executor.

## Task Management

Chronodux provides methods for managing individual tasks.

### Start a Task

```python
task = manager.start(
    target_function,
    "argument",
    name="MyTask"
)
```

Additional options:

```python
task = manager.start(
    target_function,
    backend="threading",
    name="MyTask",
    daemon=False
)
```

Available parameters:

| Parameter | Description |
| --- | --- |
| `target` | Callable to execute |
| `*args` | Positional arguments for the target |
| `backend` | Execution backend override |
| `name` | Task name |
| `daemon` | Daemon setting for threading tasks |
| `pass_context` | Inject a `TaskContext` into the target |
| `**kwargs` | Keyword arguments for the target |

### Retrieve a Task

```python
task = manager.get(task.id)

print(task.id)
print(task.name)
print(task.status)
print(task.backend)
```

### List Tasks

```python
tasks = manager.list_tasks()

for task in tasks:
    print(task.name, task.status)
```

Filter by status:

```python
running_tasks = manager.list_tasks(status="running")
```

Available task statuses:

- `pending`
- `running`
- `completed`
- `failed`
- `cancelled`

### Check Task Status

```python
# Individual task
print(manager.status(task.id))

# All managed tasks
print(manager.status())
```

### Retrieve Results

```python
result = manager.result(task.id)

print(result)
```

The method returns the task result and propagates execution exceptions. An optional timeout can be supplied:

```python
result = manager.result(task.id, timeout=10)
```

### Wait for Tasks

Wait for an individual task:

```python
manager.join(task.id)
```

Wait for all managed tasks:

```python
manager.join()
```

Use a timeout when necessary:

```python
manager.join(timeout=10)
```

### Stop or Cancel a Task

```python
manager.stop(task.id)
```

`cancel()` is an alias for `stop()`:

```python
manager.cancel(task.id)
```

**Important:** Python threads cannot be forcibly terminated safely. Running tasks must cooperate with termination requests using `TaskContext`.

### Remove Tasks

Remove a completed task:

```python
manager.remove(task.id)
```

Clear completed tasks:

```python
manager.clear()
```

## Task Context and Cooperative Cancellation

Chronodux supports passing a `TaskContext` object into a task.

This allows a task to check whether termination has been requested.

```python
from chronodux import Chronodux

manager = Chronodux()

def background_worker(context):
    while not context.stop_requested:
        print("Worker is running...")

        if context.wait(1):
            break

    print("Worker stopped.")

task = manager.start(
    background_worker,
    pass_context=True
)
```

Request termination:

```python
manager.stop(task.id)

manager.join(task.id)
```

Available `TaskContext` properties and methods:

| Member | Description |
| --- | --- |
| `id` | Associated task ID |
| `name` | Associated task name |
| `stop_requested` | Checks whether termination was requested |
| `stop()` | Requests cooperative termination |
| `wait(timeout)` | Waits for a termination request |
| `raise_if_stopped()` | Raises `InterruptedError` if termination was requested |

## Service Management

Chronodux supports registering reusable named services and managing their execution lifecycle.

### Register a Service

```python
def background_service():
    print("Service started")

manager.register_service(
    "example-service",
    background_service
)
```

### Start a Service

```python
task = manager.start_service("example-service")
```

An optional backend can be specified:

```python
task = manager.start_service(
    "example-service",
    backend="concurrent"
)
```

### Stop a Service

```python
manager.stop_service("example-service")
```

### Restart a Service

```python
manager.restart_service("example-service")
```

### Unregister a Service

```python
manager.unregister_service("example-service")
```

Optionally request termination before unregistering:

```python
manager.unregister_service(
    "example-service",
    stop=True
)
```

### List Registered Services

```python
services = manager.list_services()

print(services)
```

The returned dictionary contains service names, associated task IDs, and service execution statuses.

## Concurrency Utilities

Chronodux provides convenience methods for selecting an execution backend explicitly.

### Submit Concurrent Tasks

```python
task = manager.submit(
    background_function,
    "argument"
)
```

### Run a Thread

```python
task = manager.run_thread(
    background_function,
    "argument"
)
```

### Wait for Concurrent Tasks

```python
done, not_done = manager.wait()
```

Customise the waiting behaviour:

```python
done, not_done = manager.wait(
    timeout=5,
    return_when="ALL_COMPLETED"
)
```

The `return_when` parameter accepts the standard `concurrent.futures` completion constants, including:

- `ALL_COMPLETED`
- `FIRST_COMPLETED`
- `FIRST_EXCEPTION`

## Monitoring and Metrics

Chronodux provides basic execution statistics.

### Metrics

```python
metrics = manager.metrics()

print(metrics)
```

Example structure:

```python
{
    "total": 5,
    "pending": 0,
    "running": 2,
    "completed": 2,
    "failed": 1,
    "cancelled": 0
}
```

### Health Information

```python
health = manager.health()

print(health)
```

Health information includes:

- Manager name
- Package version
- Default execution backend
- Manager active state
- Execution metrics

## Manager Lifecycle

### Shutdown

Shut down the manager:

```python
manager.shutdown()
```

Optional parameters:

```python
manager.shutdown(
    wait=True,
    cancel_futures=False
)
```

- `wait`: Wait for managed execution to finish.
- `cancel_futures`: Attempt to cancel pending executor futures.

Running tasks receive cooperative termination requests. Running threads cannot be forcibly terminated.

### Context Manager

Chronodux also supports Python's context manager protocol:

```python
from chronodux import Chronodux

with Chronodux() as manager:
    task = manager.start(
        lambda: print("Managed execution")
    )

    manager.join(task.id)
```

The manager automatically shuts down when the context exits.

## Exceptions

Chronodux exposes the following exceptions:

| Exception | Description |
| --- | --- |
| `ChronoduxError` | Base exception for Chronodux |
| `TaskNotFoundError` | Requested task does not exist |
| `ServiceNotFoundError` | Requested service does not exist |
| `ManagerShutdownError` | Operation attempted after manager shutdown |
| `InvalidBackendError` | Unsupported execution backend selected |

Import exceptions directly:

```python
from chronodux import (
    Chronodux,
    ChronoduxError,
    TaskNotFoundError,
    ServiceNotFoundError,
    ManagerShutdownError,
    InvalidBackendError
)
```

## Public API

Chronodux exports the following public objects:

```python
from chronodux import (
    __version__,
    Chronodux,
    Task,
    TaskContext,
    ChronoduxError,
    TaskNotFoundError,
    ServiceNotFoundError,
    ManagerShutdownError,
    InvalidBackendError
)
```

## Project Structure

```text
Chronodux/
├── .github/
│   └── workflows/
│       ├── build.yml
│       ├── release.yml
│       └── tests.yml
│
├── src/
│   └── chronodux/
│       └── __init__.py
│
├── tests/
│   └── test_manager.py
│
├── LICENSE
├── README.md
└── pyproject.toml
```

## Development

Clone the repository:

```bash
git clone https://github.com/cyberdeep-corp/Chronodux.git
cd Chronodux
```

Install the package in editable mode:

```bash
python -m pip install -e .
```

Run the test suite:

```bash
python -m unittest discover -s tests -v
```

Build distributions:

```bash
python -m pip install --upgrade build twine
python -m build
python -m twine check --strict dist/*
```

## License

Chronodux is distributed under the **Union Open Source License (UOSL-1.0)**.

See the [`LICENSE`](LICENSE) file for the complete license terms.

Published and maintained by:

**Union Foundation**  
CyberDeep Union Foundation Groups  
An organisational group under CyberDeep Corporate

Website: <https://union.cyberdeep.qzz.io>

## Project Information

- **Package:** `chronodux`
- **Version:** `0.1.0`
- **Author:** Samriddha Maity
- **Development:** SamWorks Studios
- **Organisation:** CyberDeep Corporate
- **Repository:** <https://github.com/cyberdeep-corp/Chronodux>
- **Homepage:** <https://samworks.cyberdeep.qzz.io>
- **License:** UOSL-1.0
