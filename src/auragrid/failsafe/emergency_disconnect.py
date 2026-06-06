import logging

logger = logging.getLogger("auragrid.emergency_disconnect")

class EmergencyDisconnect:
    def __init__(self):
        self._is_active: bool = False

    @property
    def is_active(self) -> bool:
        """Returns True if the emergency disconnect switch has been activated."""
        return self._is_active

    def activate(self):
        """Activates the emergency disconnect switch, immediately blocking the agent."""
        if not self._is_active:
            self._is_active = True
            logger.critical("EMERGENCY DISCONNECT SWITCH ACTIVATED! All agent SCADA access is cut off.")

    def deactivate(self):
        """Deactivates the emergency disconnect switch (requires operator action)."""
        if self._is_active:
            self._is_active = False
            logger.info("Emergency disconnect switch deactivated. Resetting communication channels.")

# Singleton instance of EmergencyDisconnect
emergency_disconnect = EmergencyDisconnect()
