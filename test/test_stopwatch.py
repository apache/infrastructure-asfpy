import time
import asyncio
from asfpy.stopwatch import Stopwatch

# Configure logging to see output
import logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
_LOGGER = logging.getLogger(__name__)

def test_instance_with_reset():
    stopwatch = Stopwatch(name="Instance Reset Test")
    time.sleep(0.5)
    _LOGGER.info(f"First check: {stopwatch.elapsed_ms():.2f} ms")
    stopwatch.reset()  # Reset the timer
    time.sleep(0.2)
    _LOGGER.info(f"Second check after reset: {stopwatch.elapsed_ms():.2f} ms")

def test_context_manager():
    with Stopwatch(name="Context Manager Test"):
        time.sleep(0.5)
        _LOGGER.info("Work done in block")

def test_context_manager_antipattern():
    _LOGGER.info("Demonstrating anti-pattern: constructing Stopwatch before with block")
    stopwatch = Stopwatch(name="Anti-pattern Test")
    time.sleep(0.3)  # Simulate delay between construction and with block
    with stopwatch:
        time.sleep(0.5)
        _LOGGER.info("Work done in block (timing includes construction delay)")

@Stopwatch(name="Slow Sync Task")
def slow_sync_function():
    time.sleep(1)
    return "Done sync"

@Stopwatch(name="Slow Async Task")
async def slow_async_function():
    await asyncio.sleep(1)
    return "Done async"

if __name__ == "__main__":
    # Run instance with reset test
    _LOGGER.info("\n=== Testing instance with reset ===")
    test_instance_with_reset()

    # Run context manager test
    _LOGGER.info("\n=== Testing context manager ===")
    test_context_manager()

    # Run anti-pattern test
    _LOGGER.info("\n=== Testing context manager anti-pattern ===")
    test_context_manager_antipattern()

    # Run decorator examples
    _LOGGER.info("\n=== Testing sync decorator ===")
    slow_sync_function()

    _LOGGER.info("\n=== Testing async decorator ===")
    asyncio.run(slow_async_function())