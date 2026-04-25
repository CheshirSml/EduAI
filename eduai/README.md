# EduAI Core

Intelligent Educational Ecosystem - Alpha Version

## Quick Start

### 1. Clone and Setup

```bash
cd eduai
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your API keys
```

### 3. Run with Docker (Recommended)

```bash
docker-compose up --build
```

### 4. Run Locally

```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

## OpenWebUI Integration

1. Start the EduAI service
2. In OpenWebUI, go to Settings → Connections
3. Add a new connection:
   - Base URL: `http://localhost:8000/v1`
   - API Key: (any value, not used in alpha)
4. Select the model and start chatting

## API Endpoints

- `POST /v1/chat/completions` - OpenAI-compatible chat endpoint
- `GET /health` - Health check

## Project Structure

```
eduai/
├── src/
│   ├── core/          # Core logic, LLM client
│   ├── routers/       # API route handlers
│   ├── services/      # Business logic (homework checker, etc.)
│   ├── models/        # Pydantic schemas
│   ├── config.py      # Configuration management
│   └── main.py        # Application entry point
├── tests/             # Unit and integration tests
├── configs/           # Configuration files
├── logs/              # Log files
├── .env.example       # Environment template
├── docker-compose.yml
└── requirements.txt
```

## License

MIT
