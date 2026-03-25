# PlantLab Simulation

## Can test via: 
https://plantlab-simulator-115544415132.us-central1.run.app

---

## Video Preview 
## Video Preview
[![Demo video](https://github.com/user-attachments/assets/7830e434-1b15-44c1-8b72-65de5b6c24ab)](https://youtu.be/owrrNu0Fdq8)


---

A full-stack plant care app: Flutter web frontend + Flask/Python backend, deployed on Google Cloud Run.

Users add real plants, upload photos, and get AI-powered health analysis (Gemini vision model + XGBoost stress prediction). The backend also runs a physics-based plant growth simulation with a multi-agent monitoring system.

---

<img width="1134" height="305" alt="Stack Diagram" src="https://github.com/user-attachments/assets/7297f399-d59b-46f1-ba96-cefb40aa28ff" />

## Stack

| Layer | Technology |
|---|---|
| Frontend | Flutter web (Dart) |
| Backend | Flask + Gunicorn (Python 3.12) |
| AI | Gemini 2.5 Flash (vision) + XGBoost (stress prediction) |
| Database | Firestore (Firebase) |
| Auth | Firebase Auth |
| Billing | Stripe |
| Deployment | Google Cloud Run |
| MQTT | Eclipse Mosquitto (optional IoT sensor integration) |

---

![alt text]()


## Local development

### Prerequisites

- Python 3.12+
- Flutter SDK
- Firebase project with Firestore + Auth enabled
- Gemini API key

### Setup

```bash
# 1. Clone and enter the project
git clone <repo-url>
cd PlantLabSimulation

# 2. Create and activate Python virtual environment
python3 -m venv venv
source venv/bin/activate          # macOS / Linux
# venv\Scripts\activate           # Windows

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Set up environment variables
cp .env.example .env
# Edit .env — fill in FIREBASE_*, GEMINI_API_KEY, STRIPE_*, APP_URL

# 5. Build the Flutter web app (bakes API_BASE_URL into the JS)
bash build_web.sh

# 6. Start the Flask dev server (port 5010)
python run.py
```

Open **http://localhost:5010** in your browser.

> **Important:** every time you change `APP_URL` or Firebase web vars in `.env`,
> re-run `bash build_web.sh` — these values are compiled into the Flutter JS at
> build time and are not read at runtime.

---

## Deployment — Google Cloud Run

```bash
# Authenticate with Google Cloud
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# Build Flutter, build Docker image via Cloud Build, and deploy
bash deploy.sh
```

`deploy.sh` reads your `.env`, validates required vars, rebuilds the Flutter web
app if Flutter is in your PATH, then runs `gcloud run deploy --source .`.

All secrets (`GEMINI_API_KEY`, Stripe keys, etc.) are passed to Cloud Run as
environment variables — they are never baked into the Docker image.

---

## Project structure

```
PlantLabSimulation/
│
├── app/                          # Flask application
│   ├── __init__.py               # create_app() factory + blueprint registration
│   ├── routes/
│   │   ├── simulation_routes.py  # POST /api/simulation/start|stop|step|state
│   │   ├── agent_routes.py       # GET|POST /api/agents/*
│   │   ├── gemini_routes.py      # POST /api/gemini/identify|health
│   │   ├── plant_routes.py       # GET|POST /api/plants
│   │   ├── auth_routes.py        # GET|POST|PUT /api/auth/profile
│   │   ├── stripe_routes.py      # POST /api/stripe/create-checkout-session
│   │   └── mqtt_routes.py        # GET|POST /api/mqtt/config|latest
│   └── templates/                # Built Flutter web files (output of build_web.sh)
│
├── plant_lab_simulator/          # Flutter web app (Dart source)
│   └── lib/
│       ├── screens/              # UI screens (home, auth, dashboard, onboarding…)
│       ├── services/             # ApiClient, GeminiService, FirestoreService
│       └── models/               # PlantRecord, HealthCheck, PlantState
│
├── models/                       # Simulation engine (Python)
│   ├── engine.py                 # SimulationEngine — physics tick loop
│   └── actions.py                # Watering, nutrients, environment actions
│
├── agents/                       # Multi-agent system
│   ├── planner.py                # Rule-based + LLM decision making
│   ├── executor.py               # Applies agent decisions to the simulation
│   ├── memory.py                 # Agent memory (Firestore-backed)
│   └── reasoning.py              # Gemini/LLM reasoning (optional)
│
├── services/                     # Backend services
│   ├── user_service.py           # Firebase Auth token verification + user profiles
│   ├── stress_prediction_service.py  # XGBoost water/nutrient/temp stress models
│   └── logging_service.py        # Structured logging
│
├── trained_models/               # XGBoost .json model files
├── config/
│   └── settings.py               # Loads .env, initialises Firebase
│
├── plant-metrics-mqtt/           # Optional: MQTT publisher/subscriber container
│
├── Dockerfile                    # Flask + Gunicorn container (Cloud Run)
├── wsgi.py                       # Gunicorn entry point
├── run.py                        # Local dev entry point (port 5010)
├── build_web.sh                  # Flutter web build → app/templates/
├── deploy.sh                     # One-command Cloud Run deployment
├── requirements.txt
└── .env.example                  # Environment variable template
```

---

<img width="984" height="553" alt="Screenshot 2026-02-28 at 9 15 51 PM" src="https://github.com/user-attachments/assets/05b76f1c-b005-4083-8f86-f099e21b99d9" />


## API reference

### Health
| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Container health check (required by Cloud Run) |

### Gemini AI
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/gemini/identify` | Identify plant species from image or text name |
| `POST` | `/api/gemini/health` | Full AI health check: Gemini vision + XGBoost stress prediction |

### Plants
| Method | Path | Description |
|---|---|---|
| `GET` | `/api/plants` | List authenticated user's plants |
| `POST` | `/api/plants` | Add a new plant |
| `GET` | `/api/plants/<id>/health-checks` | Health check history for a plant |

### Auth / profile
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/auth/profile` | Create or fetch user profile |
| `GET` | `/api/auth/profile` | Get current user's profile |
| `PUT` | `/api/auth/profile` | Update profile fields |

### Simulation
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/simulation/start` | Start a plant growth simulation |
| `GET` | `/api/simulation/state` | Get current simulation state |
| `GET` | `/api/simulation/history` | Simulation tick history |
| `POST` | `/api/simulation/step` | Advance simulation by N hours |
| `POST` | `/api/simulation/stop` | Stop the running simulation |
| `POST` | `/api/simulation/regime` | Update automated daily care regime |

### Agents
| Method | Path | Description |
|---|---|---|
| `GET` | `/api/agents/status` | Agent statistics |
| `GET` | `/api/agents/diagnostics` | Recent reasoning diagnostics |
| `POST` | `/api/agents/execute` | Execute a manual action (watering, nutrients…) |
| `GET` | `/api/agents/executor/log` | Action execution log |
| `POST` | `/api/agents/monitor/enable` | Enable / disable monitor agent |

### Stripe
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/stripe/create-checkout-session` | Start Stripe checkout (Pro upgrade) |
| `GET` | `/api/stripe/subscription-status` | Check user's current plan |
| `POST` | `/api/stripe/webhook` | Stripe webhook receiver |

### MQTT
| Method | Path | Description |
|---|---|---|
| `GET` | `/api/mqtt/config` | Current MQTT broker config |
| `POST` | `/api/mqtt/config` | Update MQTT broker config |
| `GET` | `/api/mqtt/latest` | Latest sensor reading from Firestore |

---

## Environment variables

See [.env.example](.env.example) for the full list with descriptions.

| Variable | Required | Description |
|---|---|---|
| `FIREBASE_PROJECT_ID` | Yes | Firebase / GCP project ID |
| `FIREBASE_CREDENTIALS_PATH` | Local only | Service-account JSON path (Cloud Run uses ADC) |
| `GEMINI_API_KEY` | Yes | Gemini API key for AI health checks |
| `STRIPE_SECRET_KEY` | Yes | Stripe secret key |
| `STRIPE_WEBHOOK_SECRET` | Yes | Stripe webhook signing secret |
| `APP_URL` | Production | Public Cloud Run URL — drives Stripe redirects and Flutter's `API_BASE_URL` |
| `CORS_ORIGINS` | Production | Comma-separated allowed origins for `/api/*` |
| `FLASK_ENV` | No | `production` or `development` (default: `development`) |
| `LOG_LEVEL` | No | `INFO`, `DEBUG`, etc. (default: `INFO`) |
