# Quick Setup Guide

## Single Node Setup (5 minutes)

For development or testing on a single machine.

### 1. Install Dependencies

```bash
cd hydra

# Install Python packages
pip install -r requirements.txt

# Install Ollama (if not already installed)
curl -fsSL https://ollama.ai/install.sh | sh
```

### 2. Pull Required Models

```bash
# Minimum required models
ollama pull qwen3:1.7b    # Light orchestrator (~1GB)
ollama pull qwen3:14b     # Heavy orchestrator (~9GB)
ollama pull llama3.2      # Default worker model (~2GB)
```

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env if you want to customize ports or enable databases
```

**Default configuration works for single-node setup.** No editing needed unless you want:
- PostgreSQL integration
- Redis caching
- Custom ports

### 4. Start the System

```bash
# Start API server
python main.py api
```

In another terminal:
```bash
# Start web interface
python main.py ui
```

### 5. Access Interfaces

- **Web UI**: http://localhost:8501
- **API**: http://localhost:8001
- **SOLLOL Dashboard**: http://localhost:8080 (if enabled)

---

## Multi-Node Setup (15 minutes)

For distributed inference across multiple machines on the same network.

### Prerequisites

- 2+ machines on the same local network (e.g., 10.9.66.x subnet)
- Ollama installed on each machine
- Network connectivity between nodes

### 1. On Each Worker Node

```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Configure Ollama to listen on network (not just localhost)
sudo systemctl edit ollama

# Add these lines:
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"

# Save and restart
sudo systemctl daemon-reload
sudo systemctl restart ollama

# Open firewall
sudo ufw allow 11434/tcp

# Pull models (divide models across nodes to save disk space)
ollama pull qwen3:1.7b
ollama pull llama3.2
```

### 2. On Coordinator Node

```bash
cd hydra

# Install dependencies
pip install -r requirements.txt

# Configure for distributed mode
cp .env.example .env

# Edit .env and set:
# SOLLOL_DISCOVERY_ENABLED=true
# SOLLOL_VRAM_MONITORING=true
# SOLLOL_DASHBOARD_ENABLED=true
```

### 3. Start Coordinator

```bash
python main.py api
```

The system will:
1. Scan the local network for Ollama nodes
2. Auto-discover available nodes
3. Display discovered nodes in the logs

Example output:
```
🚀 Initializing Hydra system with SOLLOL...
📊 Discovered 3 Ollama nodes
  - 10.9.66.154:11434 (healthy)
  - 10.9.66.250:11434 (healthy)
  - 10.9.66.90:11434 (healthy)
🎨 SOLLOL Dashboard: http://localhost:8080
📡 Hydra API: http://localhost:8001
```

### 4. Verify Distribution

Check the SOLLOL dashboard at http://localhost:8080 to see:
- All discovered nodes
- Model availability per node
- Resource usage
- Request routing

---

## Verification

### Test API

```bash
curl -X POST http://localhost:8001/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Write a Python function to reverse a string",
    "temperature": 0.7
  }'
```

### Test Web UI

1. Open http://localhost:8501
2. Enter a prompt in the chat interface
3. Submit and wait for response

### Check System Health

```bash
curl http://localhost:8001/health
```

Should return:
```json
{
  "status": "healthy",
  "components": {
    "database": { ... },
    "ollama": {
      "healthy_hosts": 3
    },
    "distributed": { ... }
  }
}
```

---

## Troubleshooting

### No nodes discovered

**Check Ollama is accessible:**
```bash
curl http://10.9.66.154:11434/api/tags
```

**Check firewall:**
```bash
sudo ufw status
sudo ufw allow 11434/tcp
```

### "Connection refused" errors

**Ensure Ollama is running:**
```bash
systemctl status ollama
sudo systemctl start ollama
```

### Slow responses

**Check node health:**
- Visit SOLLOL dashboard: http://localhost:8080
- Look for unhealthy nodes or high load

**Use smaller models:**
- `qwen3:0.6b` instead of `qwen3:1.7b`
- Reduce max_tokens in requests

### Out of memory

**Reduce batch size** or use smaller models:
```yaml
# In config/models.yaml
orchestrator:
  light:
    model: qwen3:0.6b
```

---

## Next Steps

- Read the full [README](README.md) for detailed documentation
- Check [SOLLOL Integration Guide](SOLLOL_INTEGRATION_COMPLETE.md) for advanced distributed setup
- Explore the API endpoints at http://localhost:8001/docs (FastAPI automatic docs)
- Customize model selection in `config/models.yaml`

---

## Resource Requirements

### Single Node

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| RAM | 8GB | 16GB+ |
| CPU | 4 cores | 8+ cores |
| Disk | 15GB | 30GB |
| Models | 2-3 small models | 5+ varied models |

### Multi-Node (3 nodes)

| Per Node | Minimum | Recommended |
|----------|---------|-------------|
| RAM | 6GB | 12GB+ |
| CPU | 4 cores | 6+ cores |
| Disk | 10GB | 20GB |
| Network | 100Mbps | 1Gbps |

---

## Support

For issues or questions:
1. Check the [README](README.md)
2. Review [Troubleshooting](README.md#troubleshooting)
3. Open an issue on GitHub
