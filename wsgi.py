"""WSGI entry point for Gunicorn and Cloud Run"""

import os
import logging
from pathlib import Path

# Load .env before anything else so os.getenv() works for all routes.
# run.py loads it via config.settings, but gunicorn uses wsgi.py directly
# and never imports config.settings — so GEMINI_API_KEY would be missing.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass  # python-dotenv not installed; rely on real env vars set by Cloud Run

from app import create_app

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create Flask app
app = create_app()

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
