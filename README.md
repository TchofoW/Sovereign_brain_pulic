# Sovereign Brain

Sovereign Brain is a high-performance telemetry-driven control plane for intelligent network optimization. It ingests live router telemetry, evaluates system health in real time, and applies adaptive QoS and queue management decisions to maintain throughput, reduce latency, and improve link stability under changing network conditions.

The system is designed around a closed-loop control model:
- Phase 1: collect telemetry and compute operational context
- Phase 2: evaluate guardrails, fuzzy control logic, and ML-based optimization
- Phase 3: confirm post-adjustment state and score the operational outcome

This project is intended for adaptive networking, wireless performance tuning, traffic shaping, and intelligent queue discipline selection in constrained or unstable network environments.

## Key Features

- Real-time router telemetry ingestion
- Tiered control architecture:
  - Tier 1: safety guardrails
  - Tier 2: fuzzy logic adaptation
  - Tier 3: reinforcement learning optimization
- PostgreSQL-backed state persistence
- QoS command generation for downstream network clients
- Closed-loop validation and reward scoring
- Docker-ready deployment
- FastAPI API for telemetry, monitoring, and health checks

## Architecture

Sovereign Brain is built around a layered control pipeline:

1. Raw telemetry is accepted from routers or edge devices
2. A telemetry context matrix is built from network and queue data
3. Execution safety rules are evaluated
4. Fuzzy logic computes a dynamic adjustment scalar
5. ML policy selects the best action based on historical performance
6. Final QoS commands are returned to the network client
7. Post-change telemetry is submitted for evaluation and scoring

## API Overview

### Health Check
- GET `/health`

Returns service status and database availability.

### Telemetry Ingestion
- POST `/api/telemetry`

Accepts router telemetry and returns QoS adjustment instructions.

### Confirmation / Post-Execution Update
- POST `/api/telemetry/confirm`

Receives post-adjustment metrics and stores recovery-time and reward-score analytics.

## Database

The project uses PostgreSQL for persistent storage instead of Redis. This supports:
- telemetry run tracking
- historical router state
- ML Q-table persistence
- reward and recovery analysis

## Environment Variables

Set the following environment variables before running the app:

```bash
POSTGRES_HOST=dpg-daul4pp42hec73et8rjg-a.ohio-postgres.render.com
POSTGRES_PORT=5432
POSTGRES_DB=brain_db_81ky
POSTGRES_USER=william
POSTGRES_PASSWORD=QPXAaSDcKFFiEIuH9071hpGZ4DHBrc5O
```

## Local Development

### 1. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the API

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8080
```

## Docker

```bash
docker build -t sovereign-brain .
docker run -p 8080:8080 sovereign-brain
```

## Project Structure

```text
.
├── main.py
├── config.py
├── Dockerfile
├── requirements.txt
├── core/
│   ├── pipeline.py
│   └── telemetry_store.py
├── algorithms/
│   ├── tier1_guardrails.py
│   ├── tier2_fuzzy.py
│   └── tier3_ml.py
└── README.md
```

## Use Cases

- Wireless network optimization
- Adaptive QoS enforcement
- Traffic shaping in edge deployments
- Queue discipline tuning
- Real-time latency and throughput correction
- RL-driven decision systems for network operations

## License

This project is intended for research, experimentation, and operational deployment in controlled environments. Please review and confirm licensing terms before production use.

## Notes

Sovereign Brain is built for adaptive, data-driven decision making at the network edge. It is especially relevant in environments where link quality, congestion, packet loss, and wireless interference vary over time and require continuous optimization.
```
