"""Application settings"""

import os

# Flask settings
FLASK_ENV = os.getenv('FLASK_ENV', 'development')
FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'True') == 'True'
HOST = os.getenv('HOST', '0.0.0.0')
PORT = int(os.getenv('PORT', 5000))

# Simulation settings
DEFAULT_TIME_STEP_HOURS = 1.0
MAX_SIMULATION_DAYS = 365

# Firebase settings
FIREBASE_PROJECT_ID = os.getenv('FIREBASE_PROJECT_ID', None)
FIREBASE_CREDENTIALS_PATH = os.getenv('FIREBASE_CREDENTIALS_PATH', None)

# Logging settings
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# Agent settings
AGENT_PLANNING_INTERVAL_HOURS = 6.0
AGENT_MEMORY_RETENTION_DAYS = 30

