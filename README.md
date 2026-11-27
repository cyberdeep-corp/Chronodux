# Chronodux

**Chronodux** is a lightweight Python service manager for orchestrating threads, background tasks, and code execution lifecycles.

## Installation

```bash
pip install chronodux
```

## Quick Start

```python
from chronodux import Chronodux

def sample_task():
    print("Running managed task...")

manager = Chronodux()
manager.start(sample_task)
```

## License

MIT License
