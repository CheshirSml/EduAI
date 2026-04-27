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

**Get GigaChat API credentials:**
1. Visit [Sber Developers](https://developers.sber.ru/docs/ru/gigachat/individuals-quickstart)
2. Register and create a new project
3. Get your `client_id` and `client_secret`

**Setup .env file:**
```bash
cp .env.example .env
# Edit .env with your GigaChat credentials
```

Required environment variables:
- `GIGACHAT_CLIENT_ID` - Your GigaChat client ID
- `GIGACHAT_CLIENT_SECRET` - Your GigaChat client secret
- `GIGACHAT_SCOPE` - API scope (default: `GIGACHAT_API_PERS`)

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
   - API Key: (any value, not required for GigaChat OAuth)
4. Select the "GigaChat" model and start chatting

## API Endpoints

- `POST /v1/chat/completions` - OpenAI-compatible chat endpoint
- `GET /health` - Health check

## Features

- **GigaChat Integration**: Full support for Sber GigaChat API via OAuth 2.0
- **OpenWebUI Compatible**: Drop-in replacement for OpenAI API
- **Homework Checker**: Automatic homework evaluation with structured feedback
- **Intent Routing**: Intelligent request routing based on user intent
- **Streaming Support**: Real-time response streaming for better UX

## Project Structure

```
eduai/
├── src/
│   ├── core/          # Core logic, LLM client, GigaChat auth
│   ├── routers/       # API route handlers, intent classification
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

## Authentication

EduAI uses GigaChat OAuth 2.0 authentication:
- Tokens are automatically obtained and refreshed
- Token lifetime: 30 minutes (auto-refresh at 80% of lifetime)
- No manual API key management required

## License

MIT
