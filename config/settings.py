"""Application settings"""

import os

# ── Flask settings ──────────────────────────────────────────────────────────
FLASK_ENV = os.getenv('FLASK_ENV', 'development')
FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'False') == 'True'
HOST = os.getenv('HOST', '0.0.0.0')
PORT = int(os.getenv('PORT', 8080))  # Cloud Run требует 8080

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
    1. Cloud Run → Application Default Credentials (без файла)
    2. Локально → JSON-файл (если указан и существует)
    """
    import firebase_admin
    from firebase_admin import credentials
    
    if firebase_admin._apps:
        return  # Уже инициализировано
    
    try:
        # 🥇 Приоритет 1: ADC (для Cloud Run и gcloud auth)
        cred = credentials.ApplicationDefault()
        firebase_admin.initialize_app(cred, {'projectId': FIREBASE_PROJECT_ID})
        print(f"✅ Firebase: Application Default Credentials (project: {FIREBASE_PROJECT_ID})")
        return True
        
    except Exception as adc_error:
        # 🥈 Приоритет 2: JSON-файл (для локальной разработки)
        if FIREBASE_CREDENTIALS_PATH and os.path.exists(FIREBASE_CREDENTIALS_PATH):
            cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
            firebase_admin.initialize_app(cred, {'projectId': FIREBASE_PROJECT_ID})
            print(f"✅ Firebase: JSON-файл ({FIREBASE_CREDENTIALS_PATH})")
            return True
        else:
            # ⚠️ Критическая ошибка
            print(f"❌ Firebase: не найдены учётные данные")
            print(f"   ADC ошибка: {adc_error}")
            print(f"   Путь к JSON: {FIREBASE_CREDENTIALS_PATH}")
            raise Exception(
                "Firebase credentials not found. "
                "Set FIREBASE_CREDENTIALS_PATH for local dev or ensure ADC is configured for Cloud Run."
            )

# ── Logging settings ────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# ── Agent settings ──────────────────────────────────────────────────────────
AGENT_PLANNING_INTERVAL_HOURS = 6.0
AGENT_MEMORY_RETENTION_DAYS = 30