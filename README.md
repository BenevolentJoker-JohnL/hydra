# 🐉 Hydra - Intelligent Code Synthesis System

A distributed, multi-model orchestrated code synthesis system that combines multiple LLMs to match or surpass the capabilities of leading AI coding assistants.

## Features

- **Multi-Model Orchestration**: Leverages 20+ open-source models with intelligent routing
- **Hierarchical Memory System**: 4-tier memory architecture (Redis → SQLite → PostgreSQL → ChromaDB)
- **Distributed Computing**: Load balancing across GPU and CPU nodes
- **DAG Workflows**: Prefect-based orchestration for complex tasks
- **Code Synthesis Pipeline**: Combines perspectives from multiple models for higher quality output
- **Web Interface**: Claude-like chat interface built with Streamlit

## Architecture

### Model Orchestration
- **Light Orchestrator**: qwen3:1.7b for simple task routing
- **Heavy Orchestrator**: qwen3:14b for complex task decomposition
- **Code Models**: Pool of 14+ specialized coding models
- **Specialized Models**: Dedicated models for math, reasoning, and JSON operations

### Memory Tiers
1. **L1 Cache** (Redis): Hot data, immediate access
2. **L2 Cache** (SQLite): Recent data, fast access  
3. **L3 Storage** (PostgreSQL): Persistent storage
4. **L4 Archive** (ChromaDB): Vector embeddings for semantic search

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/hydra.git
cd hydra
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

4. Install and configure Ollama on all nodes with required models

5. Set up databases:
- PostgreSQL
- Redis
- ChromaDB will auto-initialize
- SQLite will auto-create

## Usage

### Run API Server
```bash
python main.py api
```

### Run Web UI
```bash
python main.py ui
```

### API Example
```python
import requests

response = requests.post('http://localhost:8000/generate', json={
    'prompt': 'Create a Python function to calculate fibonacci numbers',
    'temperature': 0.7
})

print(response.json()['synthesized_code'])
```

## Configuration

Edit `config/models.yaml` to customize model selection and parameters.

## Node Setup

Configure your compute nodes in `.env`:
- 1 GPU node (primary)
- 3 CPU nodes (distributed workers)

## Contributing

Pull requests welcome! Please ensure all tests pass and follow the existing code style.

## License

MIT