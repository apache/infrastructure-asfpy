# Stopwatch Module Documentation

The `Stopwatch` class provides a flexible way to measure and log the execution time of code in Python. It supports three primary usage patterns: as a **decorator** for functions, as a **context manager** for code blocks, and through **explicit instantiation** for manual timing control. It also supports both synchronous and asynchronous functions when used as a decorator. The class logs durations in milliseconds using the logger defined in the calling module (or the root logger if none is defined).

## Overview

The `Stopwatch` class measures elapsed time since its instantiation or reset, providing methods to format and retrieve durations. It can be used to:
- Decorate synchronous or asynchronous functions to log their execution time.
- Wrap code blocks in a `with` statement to log block execution time.
- Manually track elapsed time via instance methods for custom timing scenarios.

An optional `name` parameter allows custom labeling of operations, and the class automatically generates descriptive names if none is provided.

## Installation

The `Stopwatch` class is contained in `stopwatch.py`. Ensure the module is in your Python path or project directory. No external dependencies are required beyond the standard library (`time`, `logging`, `inspect`, `asyncio`, `functools`).

## Usage

### 1. Decorator Usage

Use `Stopwatch` as a decorator to measure and log the execution time of a function. It supports both synchronous and asynchronous functions, automatically detecting the function type using `asyncio.iscoroutinefunction()`.

**Syntax**:
```python
@Stopwatch(name="Optional Task Name")
def my_function():
    # Code here
```

**Example**:
```python
from stopwatch import Stopwatch

@Stopwatch(name="Slow Sync Task")
def slow_sync_function():
    time.sleep(1)
    return "Done sync"

@Stopwatch(name="Slow Async Task")
async def slow_async_function():
    await asyncio.sleep(1)
    return "Done async"

# Run examples
slow_sync_function()  # Logs: Slow Sync Task took 1000.15 ms
import asyncio
asyncio.run(slow_async_function())  # Logs: Slow Async Task took 1000.22 ms
```

**Behavior**:
- If `name` is not provided, the decorator sets the name to `Function '<function_name>'`.
- The start time is reset at the beginning of each function call.
- The duration is logged in milliseconds when the function completes, using the module's `_LOGGER` or the root logger.

### 2. Context Manager Usage

Use `Stopwatch` as a context manager to measure and log the execution time of a code block within a `with` statement. The instance should be created directly in the `with` statement to ensure accurate timing.

**Syntax**:
```python
with Stopwatch(name="Optional Block Name"):
    # Code block here
```

**Example**:
```python
from stopwatch import Stopwatch

def main():
    with Stopwatch(name="Main Block"):
        time.sleep(0.5)
        print("Work done in block")

main()  # Logs: Main Block took 500.18 ms
```

**Behavior**:
- If `name` is not provided, the context manager sets the name to `Block in <function_name> at line <line_number>`.
- The start time is set when the `Stopwatch` instance is created (at `with` entry).
- The duration is logged in milliseconds when the block exits, using the module's `_LOGGER` or the root logger.

### 3. Explicit Instantiation

Create a `Stopwatch` instance manually to track elapsed time using the `elapsed_ms()` and `reset()` methods. This is useful for custom timing scenarios where you need to check elapsed time at multiple points.

**Syntax**:
```python
stopwatch = Stopwatch(name="Optional Task Name")
# Do work
print(stopwatch.elapsed_ms())  # Get elapsed time in milliseconds
stopwatch.reset()  # Reset the timer
# Do more work
print(stopwatch.elapsed_ms())  # Get new elapsed time
```

**Example**:
```python
from stopwatch import Stopwatch
import time

stopwatch = Stopwatch(name="Instance Reset Test")
time.sleep(0.5)
print(f"First check: {stopwatch.elapsed_ms():.2f} ms")  # ~500 ms
stopwatch.reset()
time.sleep(0.2)
print(f"Second check after reset: {stopwatch.elapsed_ms():.2f} ms")  # ~200 ms
```

**Behavior**:
- The start time is set at instantiation or after calling `reset()`.
- `elapsed_ms()` returns the time since the last start or reset in milliseconds.
- `format()` can be used to generate a log message, but logging must be done manually (e.g., via `stopwatch.logger.info(stopwatch.format())`).

### Anti-Pattern: Pre-Constructed Stopwatch in Context Manager

**Avoid** creating a `Stopwatch` instance before using it in a `with` statement, as this leads to incorrect timing. The `start_time` is set at instantiation, so any delay between construction and the `with` block will be included in the logged duration, inflating the reported time.

**Example (Incorrect)**:
```python
from stopwatch import Stopwatch
import time

stopwatch = Stopwatch(name="Anti-pattern Test")
time.sleep(0.3)  # Delay before with block
with stopwatch:
    time.sleep(0.5)
    print("Work done in block")
# Logs: Anti-pattern Test took 800.32 ms (includes 0.3s delay)
```

**Correct Approach**:
Instantiate the `Stopwatch` directly in the `with` statement to ensure `start_time` is set at block entry:
```python
with Stopwatch(name="Correct Test"):
    time.sleep(0.5)
    print("Work done in block")
# Logs: Correct Test took 500.18 ms
```

## Methods

### `__init__(name=None)`
Initializes the `Stopwatch` with an optional task name.
- **Parameters**:
  - `name` (str, optional): Custom name for the operation. If `None`, a default name is set based on context (function name for decorators, function and line number for context managers, or "Operation" otherwise).
- Sets `start_time` to the current time and initializes the logger from the caller's module (or root logger).

### `format(duration_ms=None)`
Formats a string with the operation name and duration in milliseconds.
- **Parameters**:
  - `duration_ms` (float, optional): Duration in milliseconds. If `None`, uses `elapsed_ms()`.
- **Returns**: A string in the format `"<name or 'Operation'> took <duration_ms>.2f ms"`.

### `elapsed_ms()`
Returns the elapsed time since `start_time` in milliseconds.
- **Returns**: Float representing milliseconds since the last `start_time` reset.

### `reset()`
Resets `start_time` to the current time, restarting the timer.
- Useful for explicit instantiation scenarios to measure new intervals.

### `__call__(func)`
Decorates a function to measure and log its execution time.
- **Parameters**:
  - `func`: The function to decorate (synchronous or asynchronous).
- Sets `name` to `Function '<func.__name__>'` if not provided.
- Resets `start_time` at each function call and logs duration on completion.

### `__enter__()`
Enters a context manager, setting the name if not provided (to `Block in <function_name> at line <line_number>`).
- **Returns**: The `Stopwatch` instance.

### `__exit__(exc_type, exc_val, exc_tb)`
Exits the context manager, logging the duration using `format()`.

## Logging
- The `Stopwatch` uses the `_LOGGER` attribute from the module where it is instantiated or applied. If no `_LOGGER` is defined, it falls back to the root logger (`logging.getLogger()`).
- Log messages are output at the `INFO` level in the format: `<name or 'Operation'> took <duration_ms>.2f ms`.

## Example Output
Using the test module (`test_stopwatch.py`), example output might look like:
```
=== Testing instance with reset ===
First check: 500.12 ms
Second check after reset: 200.25 ms

=== Testing context manager ===
Work done in block
Context Manager Test took 500.18 ms

=== Testing context manager anti-pattern ===
Demonstrating anti-pattern: constructing Stopwatch before with block
Work done in block (timing includes construction delay)
Anti-pattern Test took 800.32 ms

=== Testing sync decorator ===
Slow Sync Task took 1000.15 ms

=== Testing async decorator ===
Slow Async Task took 1000.22 ms
```

## Notes
- **Accuracy**: Timing is based on `time.time()`, which provides wall-clock time in seconds. Durations are converted to milliseconds for logging.
- **Async Support**: The decorator automatically handles asynchronous functions using `await`, ensuring compatibility with `asyncio`.
- **Anti-Pattern**: Always instantiate `Stopwatch` in the `with` statement for context manager usage to avoid including pre-construction delays in the measured duration.
- **Thread Safety**: The `Stopwatch` is not thread-safe. Use separate instances for concurrent operations.