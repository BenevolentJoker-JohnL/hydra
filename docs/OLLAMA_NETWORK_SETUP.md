# 🌐 Ollama Network Configuration

## The Problem
By default, Ollama only listens on localhost (127.0.0.1), meaning it can't be accessed from other computers. For distributed setup, we need to make Ollama accessible over the network.

## Quick Fix

### On Each Helper Computer:

#### Option 1: Environment Variable (Easiest)
```bash
# Set Ollama to listen on all network interfaces
export OLLAMA_HOST=0.0.0.0:11434

# Restart Ollama
systemctl restart ollama
```

#### Option 2: Systemd Service Configuration (Permanent)
```bash
# Edit the Ollama service
sudo systemctl edit ollama

# Add these lines:
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"

# Save and restart
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

#### Option 3: Direct Launch (Testing)
```bash
# Stop existing Ollama
sudo systemctl stop ollama

# Run with network access
OLLAMA_HOST=0.0.0.0:11434 ollama serve
```

## Verify It's Working

### On the Helper Computer:
```bash
# Check if Ollama is listening on all interfaces
netstat -tlnp | grep 11434
# Should show: 0.0.0.0:11434 (not 127.0.0.1:11434)
```

### From Main Computer:
```bash
# Test connection to helper
curl http://HELPER-IP:11434/api/tags
# Should return JSON with models list
```

## Security Warning ⚠️

Opening Ollama to the network means anyone on your network can use it! For home networks this is usually fine, but be careful on public/work networks.

### To Restrict Access (Optional):
```bash
# Only allow specific IPs (example for main computer at 192.168.1.100)
sudo ufw allow from 192.168.1.100 to any port 11434
sudo ufw deny 11434
```

## Architecture Clarification

```
Main Computer (Coordinator)
    │
    ├── Connects to → Helper 1 Ollama (port 11434)
    ├── Connects to → Helper 2 Ollama (port 11434)
    └── Connects to → Helper 3 Ollama (port 11434)

Node Agents (port 8002) are just for:
- Monitoring health
- Reporting status
- Managing models
- NOT for running inference
```

## Updated Setup Steps

### 1. On Each Helper:
```bash
# Configure Ollama for network access
echo 'OLLAMA_HOST=0.0.0.0:11434' | sudo tee -a /etc/environment
sudo systemctl restart ollama

# Verify it's accessible
curl http://localhost:11434/api/tags
```

### 2. On Main Computer (.env file):
```bash
# Update with actual helper IPs
CPU_NODE_1_HOST=192.168.1.101
CPU_NODE_2_HOST=192.168.1.102
CPU_NODE_3_HOST=192.168.1.103
```

### 3. Test Connection:
```bash
# From main computer
curl http://192.168.1.101:11434/api/tags
curl http://192.168.1.102:11434/api/tags
```

## Common Issues

### "Connection refused"
- Ollama not configured for network access
- Firewall blocking port 11434
- Wrong IP address

### "Timeout"
- Helper computer is off
- Network issue
- Ollama not running

### Fix Commands:
```bash
# On helper computer
sudo ufw allow 11434          # Open firewall
systemctl status ollama        # Check if running
journalctl -u ollama -f        # View logs
```