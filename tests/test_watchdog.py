import pytest
import asyncio
import time
from auragrid.failsafe.watchdog import WatchdogTimer

@pytest.mark.asyncio
async def test_watchdog_normal_operation():
    watchdog = WatchdogTimer()
    # Speed up intervals for unit tests
    watchdog.interval_s = 0.1
    watchdog.timeout_s = 0.3
    
    await watchdog.start()
    await asyncio.sleep(0.15)
    
    status = watchdog.get_status()
    assert status["running"]
    assert status["write_access_granted"]
    
    await watchdog.stop()

@pytest.mark.asyncio
async def test_watchdog_timeout_revocation():
    watchdog = WatchdogTimer()
    watchdog.interval_s = 0.05
    watchdog.timeout_s = 0.15
    
    await watchdog.start()
    
    # Simulate communication failure
    watchdog.simulate_communication_failure = True
    
    # Wait for timeout (0.15s) to occur
    await asyncio.sleep(0.25)
    
    status = watchdog.get_status()
    assert not status["write_access_granted"]
    
    # Restore communication
    watchdog.simulate_communication_failure = False
    await asyncio.sleep(0.1)
    
    status = watchdog.get_status()
    assert status["write_access_granted"]
    
    await watchdog.stop()
