# 🐉 Hydra Distributed Setup - Simple Guide

## What Is This?
Hydra lets you use multiple computers to run AI models together. Think of it like having multiple helpers working on the same task - one computer might be good at big tasks (GPU), others handle smaller tasks (CPU).

---

## 🚀 Super Quick Start (Just Copy & Paste!)

### On Your Main Computer:
```bash
# 1. Start the main brain (coordinator)
cd ~/hydra
python main.py api

# That's it! Keep this running.
```

### On Each Helper Computer:
```bash
# 1. Get the setup script
cd ~
git clone https://github.com/yourname/hydra.git
cd hydra/scripts

# 2. Run automatic setup (this does EVERYTHING)
./deploy_node.sh --auto --coordinator http://MAIN-COMPUTER-IP:8001

# Replace MAIN-COMPUTER-IP with your main computer's address
# Example: ./deploy_node.sh --auto --coordinator http://192.168.1.100:8001

# 3. Make Ollama accessible over network (IMPORTANT!)
# The script tries to do this, but if it doesn't work:
export OLLAMA_HOST=0.0.0.0:11434
sudo systemctl restart ollama
```

**Done!** Your computers are now working together! 🎉

---

## 📖 Step-by-Step Guide (If Auto-Setup Doesn't Work)

### Step 1: Setup Main Computer

This is the "boss" computer that tells others what to do.

```bash
# 1. Get Hydra
git clone https://github.com/yourname/hydra.git
cd hydra

# 2. Install what it needs
pip install -r requirements.txt

# 3. Setup database (just copy-paste these)
sudo apt-get install postgresql redis-server
sudo -u postgres createuser hydra
sudo -u postgres createdb hydra_db
sudo -u postgres psql -c "ALTER USER hydra PASSWORD 'hydra123';"

# 4. Create settings file
echo "DATABASE_URL=postgresql://hydra:hydra123@localhost/hydra_db
REDIS_URL=redis://localhost:6379
COORDINATOR_PORT=8001" > .env

# 5. Start it!
python main.py api
```

### Step 2: Setup Helper Computers

Do this on each computer you want to help:

```bash
# 1. Get to the scripts folder
cd ~/hydra/scripts

# 2. Run the setup menu
./deploy_node.sh

# You'll see a menu - just type '1' and press Enter

# 3. After setup completes, it asks:
#    "What would you like to do? (6/0):"
#    Type '6' to start the helper immediately
#    OR
#    Type '0' to exit and start it later
```

---

## 🏗️ How It Actually Works

### The Architecture:
```
Main Computer (Boss)
    ├── API Server (port 8001) - Coordinates everything
    └── Connects directly to:
        ├── Helper 1's Ollama (port 11434) - Runs models
        ├── Helper 2's Ollama (port 11434) - Runs models  
        └── Helper 3's Ollama (port 11434) - Runs models

Node Agents (port 8002) just monitor health - they DON'T run models!
```

**Important**: Ollama needs to be accessible over the network, not just localhost!

---

## 🤔 Common Problems & Fixes

### "Constant port cycling" or "No available Ollama hosts"
This means Ollama isn't accessible over the network. Fix it:
```bash
# On each helper computer:
export OLLAMA_HOST=0.0.0.0:11434
sudo systemctl restart ollama

# Verify it's working:
netstat -tln | grep 11434
# Should show: 0.0.0.0:11434 (NOT 127.0.0.1:11434)

# Test from main computer:
curl http://HELPER-IP:11434/api/tags
```

### "I don't know my computer's IP address"
```bash
# On Linux/Mac:
ip addr show | grep inet

# Look for something like: 192.168.1.XXX
# That's your IP!
```

### "Connection refused" or "Can't connect"
```bash
# On helper: Check if Ollama is listening on network
netstat -tln | grep 11434
# Should show 0.0.0.0:11434

# If it shows 127.0.0.1:11434, Ollama is local-only!
# Fix with:
export OLLAMA_HOST=0.0.0.0:11434
sudo systemctl restart ollama

# On main computer, check if it's running:
curl http://localhost:8001/health

# If not working, restart:
cd ~/hydra
python main.py api
```

### "Out of memory" errors
Your computer doesn't have enough RAM for big models. The system will automatically use smaller models instead!

### "Python not found"
```bash
# Install Python first:
sudo apt-get update
sudo apt-get install python3 python3-pip
```

### "Firewall blocking connection"
```bash
# On helper computers, allow Ollama:
sudo ufw allow 11434

# On main computer, allow API:
sudo ufw allow 8001
```

---

## 🎮 How to Use It

Once everything is running:

### Check if it's working:
```bash
# On main computer:
curl http://localhost:8001/nodes

# You should see your helper computers listed!
```

### Watch what's happening:
```bash
# See live monitoring:
cd ~/hydra/scripts
python monitor_cluster.py

# You'll see a cool dashboard showing all computers
```

### Test it:
```bash
# In your Hydra app, just use it normally!
# The system automatically picks the best computer for each task
```

---

## 🏠 What Computer Do I Need?

### Main Computer (Boss):
- 8GB RAM minimum
- Regular CPU is fine
- Needs to stay on

### Helper Computers:
- **For small models**: 4GB RAM (tinyllama, phi)
- **For medium models**: 8GB RAM (qwen 7B)
- **For big models**: 16GB+ RAM (qwen 14B)
- GPU helps but not required!

---

## 🔧 Troubleshooting Port Cycling

If you see logs constantly trying different ports/hosts:
```
WARNING  | No available Ollama hosts, waiting...
WARNING  | Host http://192.168.1.100:11434 health check failed
```

**This means Ollama isn't properly configured for network access!**

### Quick Fix:
```bash
# 1. On each helper, make Ollama network-accessible:
sudo tee /etc/systemd/system/ollama.service.d/override.conf <<EOF
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
EOF

sudo systemctl daemon-reload
sudo systemctl restart ollama

# 2. On main computer, update .env with actual IPs:
echo "CPU_NODE_1_HOST=192.168.1.101" >> .env
echo "CPU_NODE_2_HOST=192.168.1.102" >> .env
# (Use real IPs of your helpers)

# 3. Restart main API:
python main.py api
```

---

## 🎯 Quick Commands Cheat Sheet

```bash
# On Main Computer:
python main.py api                    # Start main server
curl http://localhost:8001/health     # Check if working
curl http://localhost:8001/nodes      # See all helpers

# On Helper Computer:
./deploy_node.sh                      # Setup menu
systemctl status ollama               # Check Ollama (the important one!)
systemctl status hydra-node           # Check monitor agent
journalctl -u ollama -f               # See what Ollama is doing
netstat -tln | grep 11434             # Check if Ollama is network-accessible

# Testing Connection (from main to helper):
curl http://HELPER-IP:11434/api/tags  # Should list models

# Monitoring:
python scripts/monitor_cluster.py     # Watch everything
python scripts/benchmark_cluster.py --quick  # Test speed
```

---

## 💡 Tips

1. **Start Small**: Try with just 2 computers first
2. **Use Ethernet**: WiFi works but cable is faster
3. **Same Network**: All computers should be on the same network
4. **Leave Running**: The main computer needs to stay on
5. **Auto-Recovery**: If a helper crashes, others keep working!

---

## 🆘 Need Help?

If stuck, try:
1. Turn it off and on again (seriously!)
2. Run the setup script again with `--auto`
3. Check logs: `journalctl -u hydra-node -n 50`
4. Make sure firewall isn't blocking:
   ```bash
   sudo ufw allow 8001  # On main
   sudo ufw allow 8002  # On helpers
   ```

---

## 🎉 Success Looks Like:

When everything works, you'll see:
- Main computer says: "Hydra system initialized successfully"
- Helper computers say: "Node agent initialized"
- Monitor shows all computers as "Healthy"
- Models run without "out of memory" errors

**That's it! You now have multiple computers working as one AI brain!** 🧠✨