# Hydra - Distributed LLM Orchestration System

A multi-model code synthesis system that orchestrates local LLMs for code generation tasks. Built on SOLLOL for distributed inference and load balancing.

## Overview

Hydra coordinates multiple Ollama models to handle code generation requests through a hierarchical orchestration system. It provides a FastAPI backend and Streamlit web interface for interacting with local LLMs.

### Core Capabilities

- **Model Orchestration**: Routes tasks to appropriate models based on complexity
- **Distributed Inference**: Leverages SOLLOL for multi-node LLM execution
- **Hierarchical Memory**: Multi-tier caching system (Redis, SQLite, PostgreSQL, ChromaDB)
- **Workflow Management**: Prefect-based DAG orchestration for complex tasks
- **Web Interface**: Streamlit-based chat interface

## Architecture

### Components

```
hydra/
├── core/                    # Core functionality
│   ├── sollol_integration.py   # SOLLOL integration for distributed inference
│   ├── orchestrator.py         # Model selection and task routing
│   ├── memory.py              # Hierarchical memory system
│   ├── code_synthesis.py      # Code generation pipeline
│   └── tools.py               # Tool execution system
├── workflows/               # Task orchestration
│   └── dag_pipeline.py        # Prefect workflow definitions
├── db/                     # Database connections
│   └── connections.py         # Multi-tier database management
├── ui/                     # User interface
│   └── terminal.py            # Streamlit chat interface
└── main.py                 # FastAPI server

Dependencies:
- SOLLOL: Distributed LLM load balancing and node discovery
- Ollama: Local LLM runtime
```

### Model Hierarchy

The system uses a lightweight-to-heavyweight model selection strategy:

- **Light Orchestrator**: `qwen3:1.7b` - Fast task classification
- **Heavy Orchestrator**: `qwen3:14b` - Complex task decomposition
- **Worker Models**: User-configured models for specific tasks

### Memory Tiers

1. **L1 (Redis)**: Hot cache for immediate access
2. **L2 (SQLite)**: Recent data storage
3. **L3 (PostgreSQL)**: Persistent long-term storage
4. **L4 (ChromaDB)**: Vector embeddings for semantic search

## Installation

### Prerequisites

- Python 3.8+
- Ollama installed and running
- PostgreSQL (optional, for persistent storage)
- Redis (optional, for caching)
- 16GB+ RAM recommended
- 20GB+ disk space for models

### Setup

```bash
# Clone repository
git clone https://github.com/BenevolentJoker-JohnL/hydra.git
cd hydra

# Install Python dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your database credentials and SOLLOL settings

# Pull required Ollama models
ollama pull qwen3:1.7b
ollama pull qwen3:14b
ollama pull llama3.2:latest
```

### Database Setup (Optional)

For full functionality, set up PostgreSQL and Redis:

```bash
# PostgreSQL
sudo apt install postgresql
# Create database (see create_db.sql)

# Redis
sudo apt install redis-server
sudo systemctl start redis
```

**Note**: System will function with SQLite-only if PostgreSQL/Redis are unavailable.

## Usage

### Start API Server

```bash
python main.py api
# Server starts at http://localhost:8001
```

### Start Web UI

```bash
python main.py ui
# UI starts at http://localhost:8501
```

### API Example

```python
import requests

response = requests.post('http://localhost:8001/generate', json={
    'prompt': 'Create a Python function to calculate fibonacci numbers',
    'temperature': 0.7,
    'max_tokens': 2048
})

print(response.json())
```

### System Status

```bash
curl http://localhost:8001/health
```

## Configuration

### Environment Variables

Key settings in `.env`:

```bash
# SOLLOL Configuration
SOLLOL_DISCOVERY_ENABLED=true    # Auto-discover Ollama nodes
SOLLOL_DISCOVERY_TIMEOUT=10      # Node discovery timeout (seconds)
SOLLOL_VRAM_MONITORING=true      # Enable GPU monitoring
SOLLOL_DASHBOARD_ENABLED=true    # Enable monitoring dashboard
SOLLOL_DASHBOARD_PORT=8080       # Dashboard port

# Database Configuration
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=hydra
REDIS_HOST=localhost
REDIS_PORT=6379
```

### Model Configuration

Edit `config/models.yaml` to customize model selection:

```yaml
orchestrator:
  light:
    model: qwen3:1.7b
  heavy:
    model: qwen3:14b

embedding:
  model: mxbai-embed-large

default:
  model: llama3.2:latest
```

## Distributed Setup

Hydra uses SOLLOL for distributed inference across multiple nodes.

### Single Node (Default)

Works out of the box with local Ollama installation.

### Multi-Node Setup

1. **Install Ollama on all nodes**
2. **Configure network access** (see SOLLOL documentation)
3. **Enable SOLLOL discovery** in `.env`
4. **Start Hydra** - It will automatically discover and use available nodes

SOLLOL handles:
- Automatic node discovery on local network
- Load balancing across nodes
- Health monitoring and failover
- VRAM-aware routing (when GPUs available)

See [SOLLOL Integration Guide](SOLLOL_Integration_Guide.md) for details.

## Development

### Project Structure

- `core/` - Core orchestration, memory, and integration logic
- `db/` - Database connection management
- `workflows/` - Prefect DAG definitions
- `models/` - Model-specific implementations
- `ui/` - Streamlit interface components
- `tests/` - Test suite

### Running Tests

```bash
pytest tests/
```

### Code Style

Project uses:
- Black for formatting
- Pylint for linting
- Type hints for clarity

## Limitations

- **Model Quality**: Output quality depends on the capabilities of local models
- **Resource Requirements**: Larger models (13B+) require significant RAM
- **Network Dependency**: Multi-node setups require stable network connectivity
- **Database Optional**: System degrades gracefully without PostgreSQL/Redis

## Troubleshooting

### "Connection refused" errors

Ensure Ollama is running:
```bash
systemctl status ollama
```

### Out of memory errors

Use smaller models or reduce context length:
```yaml
orchestrator:
  light:
    model: qwen3:0.6b  # Smaller model
```

### Slow response times

Check SOLLOL dashboard for node health:
```bash
# Dashboard at http://localhost:8080
```

## Contributing

Contributions welcome. Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## License

MIT License - See LICENSE file for details

## Acknowledgments

- Built on [SOLLOL](https://github.com/BenevolentJoker-JohnL/SOLLOL) for distributed inference
- Uses [Ollama](https://ollama.ai/) for local LLM execution
- Inspired by the need for local, privacy-focused AI development tools
