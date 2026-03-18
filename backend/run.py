"""
AFL Analytics Agent - Application Entry Point
"""
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from app import create_app, socketio

# Create Flask app
app = create_app()

if __name__ == '__main__':
    print("=" * 80)
    print("AFL Analytics Agent - Starting Server")
    print("=" * 80)
    print("Server running at: http://localhost:5000")
    print("Health check: http://localhost:5000/api/health")
    print("=" * 80)

    # Run with SocketIO
    socketio.run(
        app,
        host='0.0.0.0',
        port=5001,  # Changed from 5000 due to macOS AirPlay Receiver
        debug=False,  # Temporarily disabled for testing
        allow_unsafe_werkzeug=True  # For development only
    )
