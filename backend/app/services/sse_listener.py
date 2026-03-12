"""
Squiggle SSE Listener - Maintains persistent connection to Squiggle's Server-Sent Events API.
Receives real-time updates for AFL matches and broadcasts to WebSocket clients.
"""
import requests
import json
import logging
import threading
import time
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)

SSE_URL = "https://api.squiggle.com.au/sse/events"
USER_AGENT = "AFL-Analytics-App/1.0 (educational project)"


class SquiggleSSEListener:
    """Maintains persistent SSE connection to Squiggle and processes events."""

    def __init__(self, socketio=None):
        """
        Initialize SSE listener.

        Args:
            socketio: Flask-SocketIO instance for broadcasting to clients
        """
        self.socketio = socketio
        self.is_running = False
        self.thread: Optional[threading.Thread] = None
        self.reconnect_delay = 1  # Start with 1 second
        self.max_reconnect_delay = 60  # Max 60 seconds
        self._stop_event = threading.Event()

    def start(self):
        """Start SSE listener in background thread."""
        if self.is_running:
            logger.warning("SSE listener already running")
            return

        self.is_running = True
        self._stop_event.clear()
        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()
        logger.info("✓ SSE listener started")

    def stop(self):
        """Stop SSE listener gracefully."""
        if not self.is_running:
            return

        logger.info("Stopping SSE listener...")
        self.is_running = False
        self._stop_event.set()

        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)

        logger.info("✓ SSE listener stopped")

    def _listen_loop(self):
        """Main listening loop with auto-reconnection."""
        while self.is_running and not self._stop_event.is_set():
            try:
                logger.info(f"Connecting to Squiggle SSE: {SSE_URL}")
                self._listen_to_stream()

                # If we get here, connection was closed
                if self.is_running:
                    logger.warning(
                        f"SSE connection closed, reconnecting in {self.reconnect_delay}s..."
                    )
                    time.sleep(self.reconnect_delay)

                    # Exponential backoff
                    self.reconnect_delay = min(
                        self.reconnect_delay * 2, self.max_reconnect_delay
                    )

            except Exception as e:
                if self.is_running:
                    logger.error(f"SSE error: {e}, reconnecting in {self.reconnect_delay}s...")
                    time.sleep(self.reconnect_delay)
                    self.reconnect_delay = min(
                        self.reconnect_delay * 2, self.max_reconnect_delay
                    )

    def _listen_to_stream(self):
        """Connect to SSE stream and process events."""
        response = requests.get(
            SSE_URL,
            headers={"User-Agent": USER_AGENT, "Accept": "text/event-stream"},
            stream=True,
            timeout=None,  # No timeout for SSE
        )

        if response.status_code != 200:
            raise Exception(f"SSE connection failed: {response.status_code}")

        logger.info("✓ SSE connected successfully")
        self.reconnect_delay = 1  # Reset backoff on successful connection

        # Read lines from stream
        for line in response.iter_lines(decode_unicode=True):
            if self._stop_event.is_set():
                break

            if not line or not line.strip():
                continue

            # SSE format: "data: {...}"
            if line.startswith("data: "):
                data_str = line[6:]  # Remove "data: " prefix
                try:
                    self._process_sse_event(data_str)
                except Exception as e:
                    logger.error(f"Error processing SSE event: {e}")
                    # Continue listening despite errors

    def _process_sse_event(self, data_str: str):
        """
        Process a single SSE event from Squiggle.

        Event types:
        - games: Initial array of active games
        - game: Full game state update
        - score: Goal or behind scored
        - complete: Match completion percentage update
        - timestr: Quarter/time update
        - winner: Match outcome
        """
        try:
            data = json.loads(data_str)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in SSE event: {e}")
            return

        # Log event for debugging
        logger.debug(f"SSE event received: {data}")

        # Route to appropriate handler
        if isinstance(data, list):
            # Initial games array
            self._handle_games_event(data)
        elif isinstance(data, dict):
            # Check for specific event indicators
            if "id" in data and "hscore" in data:
                # Full game update or score update
                self._handle_game_update(data)
            else:
                logger.warning(f"Unknown SSE event structure: {data}")

    def _handle_games_event(self, games_data: list):
        """Handle initial games array from SSE."""
        logger.info(f"Received initial games list: {len(games_data)} games")

        # Import here to avoid circular imports
        from app.services.live_game_service import LiveGameService

        for game_data in games_data:
            try:
                LiveGameService.process_game_update(game_data, self.socketio)
            except Exception as e:
                logger.error(f"Error processing game {game_data.get('id')}: {e}")

    def _handle_game_update(self, game_data: dict):
        """Handle game state update from SSE."""
        game_id = game_data.get("id")
        logger.info(f"Game update: {game_id} - {game_data.get('hteam')} vs {game_data.get('ateam')}")

        # Import here to avoid circular imports
        from app.services.live_game_service import LiveGameService

        try:
            LiveGameService.process_game_update(game_data, self.socketio)
        except Exception as e:
            logger.error(f"Error processing game update {game_id}: {e}")


# Global singleton instance
_sse_listener_instance: Optional[SquiggleSSEListener] = None


def get_sse_listener(socketio=None) -> SquiggleSSEListener:
    """Get or create the global SSE listener instance."""
    global _sse_listener_instance
    if _sse_listener_instance is None:
        _sse_listener_instance = SquiggleSSEListener(socketio=socketio)
    return _sse_listener_instance
