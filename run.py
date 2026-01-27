"""Flask entry point"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app
from config.settings import HOST, PORT

if __name__ == '__main__':
    app = create_app()
    
    print("\n" + "="*60)
    print("🌱 Plant Simulator API Server Starting...")
    print("="*60)
    print(f"📍 Server: http://{HOST}:{PORT}")
    print(f"📍 Health: http://{HOST}:{PORT}/health")
    print(f"📍 Simulation API: http://{HOST}:{PORT}/api/simulation")
    print(f"📍 Agent API: http://{HOST}:{PORT}/api/agents")
    print("="*60 + "\n")
    
    app.run(debug=True, host=HOST, port=PORT)

