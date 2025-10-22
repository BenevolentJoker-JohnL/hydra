# 🚀 Quick Setup - 4 PC Cluster

## Your Setup
- **Main PC (Coordinator)**: 10.9.66.90 - Manages everything
- **Worker PC 1**: 10.9.66.154 - Runs models
- **Worker PC 2**: [Your IP] - Runs models
- **Worker PC 3**: [Your IP] - Runs models
- **Worker PC 4**: [Your IP] - Runs models

All PCs work together, sharing the load and running different models in parallel!

---

## Step 1: Start the Main PC (10.9.66.90)

```bash
# On the main PC (10.9.66.90):
cd ~/hydra/scripts
./host_node.sh quick

# Or if already set up, just start it:
./host_node.sh start
```

Keep this running! This is the brain that coordinates all workers.

---

## Step 2: Set Up Each Worker PC (One by One)

On each worker PC, run this ONE command:

```bash
# Quick deploy (already configured for 10.9.66.90):
cd ~/hydra/scripts
./deploy_node.sh --quick
```

That's it! The script will:
- Install Ollama
- Configure network access
- Connect to main PC at 10.9.66.90
- Start running automatically
- Models are pulled dynamically when needed!

**For Worker 1 (10.9.66.154):** Already done!
**For Worker 2:** Run the command above
**For Worker 3:** Run the command above  
**For Worker 4:** Run the command above

---

## How It Works

```
Main PC (10.9.66.90)
    ├── Receives requests
    ├── Picks best worker for each model
    └── Distributes work to:
        ├── Worker 1: Runs Model A
        ├── Worker 2: Runs Model B (parallel)
        ├── Worker 3: Runs Model C (parallel)
        └── Worker 4: Runs Model D (parallel)

All workers run different models AT THE SAME TIME!
```

---

## Check Everything is Working

### On Main PC:
```bash
# See all connected workers:
curl http://localhost:8001/nodes

# Monitor the cluster:
cd ~/hydra/scripts
python monitor_cluster.py
```

### On Any Worker:
```bash
# Check worker status:
curl http://localhost:8002/status

# See logs:
sudo journalctl -u hydra-node -f
```

---

## How Models Work (Automatic!)

**Models are loaded dynamically!** When the host requests a model:
1. Worker checks if it has the model
2. If not, downloads it automatically
3. Runs the model
4. Keeps it cached for next time

**No manual pulling needed!** Just request any model and workers will get it:

```python
# From main PC - workers auto-download as needed:
response = requests.post("http://localhost:8001/generate", json={
    "model": "llama2:7b",  # Worker downloads if needed
    "prompt": "Hello"
})
```

### Available Models (auto-downloaded when requested):
- **Small (4GB RAM)**: tinyllama, phi, gemma:2b
- **Medium (8GB RAM)**: llama2:7b, mistral:7b, qwen2.5:7b  
- **Large (16GB RAM)**: llama2:13b, qwen2.5:14b, mixtral:8x7b

---

## Tips for Best Performance

1. **Model Distribution**: Different workers can run different models
   - Worker 1: Small fast models (tinyllama, phi)
   - Worker 2: Code models (codellama, qwen-coder)
   - Worker 3: General models (llama2, mistral)
   - Worker 4: Large models (if enough RAM)

2. **The system automatically**:
   - Routes requests to the right worker
   - Balances load across all PCs
   - Falls back if a worker goes down
   - Runs models in parallel for speed

3. **If a worker disconnects**: Others keep working!

---

## Common Commands

### Start/Stop Worker:
```bash
sudo systemctl start hydra-node    # Start
sudo systemctl stop hydra-node     # Stop
sudo systemctl status hydra-node   # Check status
```

### Update Worker Code:
```bash
cd ~/hydra
git pull
cd scripts
./deploy_node.sh --quick
```

### Test Parallel Processing:
```python
# From main PC, test multiple models at once:
import requests

# These all run IN PARALLEL on different workers!
requests.post("http://localhost:8001/generate", json={
    "model": "tinyllama",
    "prompt": "Hello"
})
requests.post("http://localhost:8001/generate", json={
    "model": "phi", 
    "prompt": "Write code"
})
requests.post("http://localhost:8001/generate", json={
    "model": "llama2:7b",
    "prompt": "Explain AI"
})
```

---

## Troubleshooting

### "Can't connect to coordinator"
```bash
# On worker, check coordinator is reachable:
ping 10.9.66.90
curl http://10.9.66.90:8001/health
```

### "Ollama not accessible"
```bash
# Make sure Ollama listens on network:
sudo systemctl restart ollama
netstat -tln | grep 11434  # Should show 0.0.0.0:11434
```

### "Out of memory"
The system automatically picks smaller models! Or manually pull smaller ones:
```bash
ollama pull tinyllama  # Smallest
ollama pull phi        # Still small
```

---

## 🎉 That's It!

Your 4 PCs are now working together as one powerful AI cluster! Each can run different models simultaneously, sharing the computational load.