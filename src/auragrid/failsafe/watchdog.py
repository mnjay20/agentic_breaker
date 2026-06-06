import asyncio
import logging
import time
from typing import Dict
from auragrid.config import settings

logger = logging.getLogger("auragrid.watchdog")

class WatchdogTimer:
    def __init__(self):
        self.interval_s = settings.watchdog_interval_s
        self.timeout_s = settings.watchdog_timeout_s
        
        self.last_ping_sent: float = 0.0
        self.last_ping_ack: float = 0.0
        self.write_access: bool = True
        self.running: bool = False
        
        # Test simulation flags
        self.simulate_communication_failure: bool = False
        
        self._task: asyncio.Task | None = None

    async def start(self):
        """Starts the background watchdog keep-alive loop."""
        if self.running:
            return
        self.running = True
        self.last_ping_ack = time.time()
        self.write_access = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Watchdog keep-alive task started.")

    async def stop(self):
        """Stops the watchdog keep-alive loop."""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Watchdog keep-alive task stopped.")

    async def _loop(self):
        while self.running:
            try:
                await asyncio.sleep(self.interval_s)
                self.last_ping_sent = time.time()
                
                # Simulate keep-alive ping to SCADA
                if self.simulate_communication_failure:
                    logger.warning("Watchdog ping failed: simulated communication failure.")
                else:
                    # Ping succeeded instantly
                    self.last_ping_ack = time.time()
                    logger.debug("Watchdog heartbeat ping sent and acknowledged.")

                # Check for timeout / revocation condition
                elapsed_since_ack = time.time() - self.last_ping_ack
                if elapsed_since_ack > self.timeout_s:
                    if self.write_access:
                        self.write_access = False
                        logger.critical(
                            f"WATCHDOG TIMEOUT: SCADA has not acknowledged a ping for {elapsed_since_ack:.1f}s "
                            f"(limit {self.timeout_s}s). Revoking agent write access! Reverting to manual mode."
                        )
                else:
                    # Recover access if communication is restored
                    if not self.write_access:
                        self.write_access = True
                        logger.info("Watchdog communication restored. Agent write access re-granted.")
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in watchdog loop: {e}")

    def get_status(self) -> Dict:
        """Returns the current status of the watchdog timer."""
        elapsed_since_ack = time.time() - self.last_ping_ack
        return {
            "running": self.running,
            "write_access_granted": self.write_access,
            "last_ping_sent_timestamp": self.last_ping_sent,
            "last_ping_ack_timestamp": self.last_ping_ack,
            "seconds_since_last_ack": round(elapsed_since_ack, 1),
            "timeout_threshold_seconds": self.timeout_s,
            "simulating_failure": self.simulate_communication_failure
        }

# Singleton instance of WatchdogTimer
watchdog = WatchdogTimer()
