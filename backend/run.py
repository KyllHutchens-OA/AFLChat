"""
AFL Analytics Agent - Application Entry Point
"""
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from app import create_app, socketio

# Create Flask app
app = create_app()

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5001))  # override for local dev (e.g. a worktree on its own port)
    print("=" * 80)
    print("AFL Analytics Agent - Starting Server")
    print("=" * 80)
    print(f"Server running at: http://localhost:{port}")
    print(f"Health check: http://localhost:{port}/api/health")
    print("=" * 80)

    # Run with SocketIO
    socketio.run(
        app,
        host='0.0.0.0',
        port=port,
        debug=False,  # Temporarily disabled for testing
        allow_unsafe_werkzeug=True  # For development only
    )
