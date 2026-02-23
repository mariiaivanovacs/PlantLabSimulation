"""Application settings"""

import os
from pathlib import Path

# ── Load .env file at startup ────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"  # Go up to project root
    load_dotenv(env_path, override=False)
except ImportError:
    pass  # python-dotenv not installed

# ── Flask settings ──────────────────────────────────────────────────────────
FLASK_ENV = os.getenv('FLASK_ENV', 'development')
FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'False') == 'True'
HOST = os.getenv('HOST', '0.0.0.0')
PORT = int(os.getenv('PORT', 5010))  # Local dev: 5010, Cloud Run: 8080

# Security: SECRET_KEY is required in production
SECRET_KEY = os.getenv('SECRET_KEY')
if FLASK_ENV == 'production' and not SECRET_KEY:
    raise ValueError('SECRET_KEY environment variable is required in production')

# CORS origins - restrict in production
CORS_ORIGINS = os.getenv('CORS_ORIGINS', '*').split(',')

DEFAULT_TIME_STEP_HOURS = 1.0
MAX_SIMULATION_DAYS = 365

# ── Firebase settings ───────────────────────────────────────────────────────
FIREBASE_PROJECT_ID = os.getenv('FIREBASE_PROJECT_ID', 'plant-lab-simulation-4e1c5')
FIREBASE_CREDENTIALS_PATH = os.getenv('FIREBASE_CREDENTIALS_PATH', None)

def initialize_firebase():
    """
    Инициализирует Firebase с приоритетом безопасности:
    1. Локально → JSON-файл (если указан и существует)
    2. Cloud Run → Application Default Credentials (без файла)
    """
    import firebase_admin
    from firebase_admin import credentials
    
    if firebase_admin._apps:
        return  # Уже инициализировано
    
    # 🥇 Приоритет 1: JSON-файл (для локальной разработки и при наличии)
    creds_path = FIREBASE_CREDENTIALS_PATH
    
    # Resolve relative path to project root if needed
    if creds_path:
        creds_file = Path(creds_path)
        if not creds_file.is_absolute():
            project_root = Path(__file__).parent.parent
            creds_file = project_root / creds_path
        
        if creds_file.exists():
            try:
                cred = credentials.Certificate(str(creds_file))
                firebase_admin.initialize_app(cred, {'projectId': FIREBASE_PROJECT_ID})
                print(f"✅ Firebase: JSON-file ({creds_file})")
                return True
            except Exception as cert_error:
                print(f"⚠️ Firebase: Certificate init failed ({cert_error}) — trying ADC")
    
    # 🥈 Приоритет 2: ADC (для Cloud Run и gcloud auth)
    try:
        cred = credentials.ApplicationDefault()
        firebase_admin.initialize_app(cred, {'projectId': FIREBASE_PROJECT_ID})
        print(f"✅ Firebase: Application Default Credentials (project: {FIREBASE_PROJECT_ID})")
        return True
    except Exception as adc_error:
        # ⚠️ Critical error
        print(f"❌ Firebase: credentials not found")
        print(f"   ADC error: {adc_error}")
        print(f"   Credentials path: {creds_path}")
        print(f"   File exists: {creds_file.exists() if creds_path else 'N/A'}")
        raise Exception(
            "Firebase credentials not found. "
            "Set FIREBASE_CREDENTIALS_PATH for local dev or set up gcloud ADC for Cloud Run."
        )

# ── Logging settings ────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# ── Agent settings ──────────────────────────────────────────────────────────
AGENT_PLANNING_INTERVAL_HOURS = 6.0
AGENT_MEMORY_RETENTION_DAYS = 30