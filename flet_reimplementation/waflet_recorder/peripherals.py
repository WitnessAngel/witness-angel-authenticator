"""Raspberry Pi peripherals: e-paper, LCD, GPIO buttons, Button SHIM (01 §10.2, 02 §9, 03 §6.8).

Only the interface and a no-op default exist. NOT implemented (hardware drivers, untestable here): Waveshare/DFRobot
e-paper, Waveshare LCD HAT, GPIO button callbacks (pins in 01 §10.2), Pimoroni Button SHIM LED/buttons.
A driver is a `Peripherals` subclass returned by `create_peripherals`; it receives the service to call
`service.toggle_recording()` (button 1 / shim A) and `service.get_service_status()` (e-paper refresh).
"""
import logging

logger = logging.getLogger(__name__)


class Peripherals:
    """No-op implementation, also the base class."""

    def setup(self, service):
        """Called once at service boot, on a Pi only. Failures must be logged, not raised (OI-23)."""

    def on_recording_state_changed(self, is_recording):
        """True/False after each start/stop (e-paper refresh after a change: OI-24)."""

    def on_activity(self, notification_type, **kwargs):
        """RECORDING_PROGRESS (+ notification_color) -> LED blink; IMAGE_PREVIEW (+ notification_image) -> LCD."""

    def shutdown(self):
        """Release the hardware."""


def create_peripherals(settings) -> Peripherals:
    configured = [settings.epaper_type, settings.lcd_type, settings.enable_button_shim]
    if settings.is_raspberry_pi and any(configured):
        logger.warning("Peripheral drivers are not implemented in this edition (epaper=%r, lcd=%r, button_shim=%r): "
                       "ignored", settings.epaper_type, settings.lcd_type, settings.enable_button_shim)
    return Peripherals()
