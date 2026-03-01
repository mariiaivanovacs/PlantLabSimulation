# Plant Simulator

Can test via: https://plantlab-simulator-115544415132.us-central1.run.app/

Main branch - development.

Advanced plant growth simulation with Flask API and multi-agent control system.

## 🚀 Quick Start

### Flask API Server
```bash
# Install dependencies
pip install -r requirements.txt

# Run Flask server
python run.py
```

Server: **http://localhost:5000**

### CLI Mode
```bash
# List available plants
python main.py list

# Run simulation
python main.py run tomato 30
```

## 📁 Project Structure

```
plant_simulator/
│
├── app/                          # 🌐 Flask application layer
│   ├── __init__.py               # create_app() factory
│   ├── routes/
│   │   ├── health.py
│   │   ├── simulation_routes.py
│   │   └── agent_routes.py
│   └── schemas.py                # Request/response validation
│
├── simulation/                   # 🌿 Core simulation engine
│   ├── engine.py                 # Main SimulationEngine class
│   ├── state.py                  # PlantState
│   ├── plant_profile.py          # PlantProfile
│   ├── growth.py                 # Growth + biomass logic
│   ├── water_balance.py          # Soil moisture + ET
│   ├── nutrients.py              # EC + uptake
│   ├── sensors.py                # Noise, drift, delay
│   └── actions.py                # Irrigation/light/nutrient effects
│
├── agents/                       # 🤖 Agent layer
│   ├── planner.py                # Decision-making logic
│   ├── executor.py               # Turns decisions into sim actions
│   ├── memory.py                 # Reads/writes history from Firebase
│   └── rules.py                  # Heuristics / control strategies
│
├── services/                     # 🔌 External services
│   ├── firebase_service.py       # Firebase integration
│   └── logging_service.py        # Centralized logging
│
├── data/                         # 🌱 Static data
│   ├── default_plants.py         # Default plant profiles
│   └── initializer.py            # Data initialization
│
├── config/                       # ⚙️ Configuration
│   ├── settings.py               # App settings
│   └── .env.example              # Environment template
│
├── cli/                          # 💻 CLI commands
│   └── commands.py               # CLI interface
│
├── run.py                        # ▶ Flask entry point
├── main.py                       # CLI entry point
└── requirements.txt
```

## 🔌 API Endpoints

### System
- `GET /` - API info
- `GET /health` - Health check

### Simulation
- `POST /api/simulation/start` - Start simulation
- `POST /api/simulation/step` - Step simulation
- `GET /api/simulation/state` - Get current state

### Agents
- `POST /api/agents/plan` - Get agent plan
- `POST /api/agents/execute` - Execute action

## 🧪 Example Usage

### API
```bash
# Start simulation
curl -X POST http://localhost:5000/api/simulation/start \
  -H "Content-Type: application/json" \
  -d '{"plant_type": "tomato", "duration_days": 30}'

# Get state
curl http://localhost:5000/api/simulation/state
```

### CLI
```bash
# Run 30-day tomato simulation
python main.py run tomato 30

# List available plants
python main.py list
```

## 🌱 Available Plants

- **tomato** - Max height: 200cm, Growth rate: 1.0
- **lettuce** - Max height: 30cm, Growth rate: 0.8
- **basil** - Max height: 60cm, Growth rate: 1.2

## 🤖 Agent System

- **Planner**: Evaluates rules and generates action plans
- **Executor**: Applies actions to simulation
- **Memory**: Stores/retrieves history from Firebase
- **Rules**: Heuristic control strategies

## ⚙️ Configuration

Copy `.env.example` to `.env` and configure:
```bash
cp config/.env.example .env
```

Edit `.env` with your settings.

