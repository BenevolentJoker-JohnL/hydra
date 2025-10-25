# SOLLOL-Hydra Integration Guide

## Overview

**sollol-hydra** is a specialized fork of SOLLOL optimized for Hydra. It provides distributed LLM orchestration while maintaining compatibility with Hydra's architecture.

## Key Differences

### Package Structure

| Aspect | Regular SOLLOL | sollol-hydra |
|--------|---------------|---------------|
| **Package Name** | `sollol` | `sollol-hydra` |
| **Version** | 0.9.52 | 0.9.58+hydra |
| **Location** | `/home/joker/SOLLOL` | `/home/joker/SOLLOL-Hydra` |
| **Import** | `import sollol` | `import sollol` (same) |
| **CLI Command** | `sollol` | `sollol-hydra` |

### Installation

```bash
# Install sollol-hydra (recommended for Hydra)
cd /home/joker/SOLLOL-Hydra
pip install --user --no-build-isolation -e .

# Verify installation
pip show sollol-hydra
python -c "import sollol; print(sollol.__version__)"
```

## Troubleshooting Guide

### Using the Diagnostic Tool

The `hydra_diagnostics.py` tool helps identify whether issues are:
- SOLLOL-Hydra related (distributed orchestration)
- Hydra-Core related (model orchestration, memory)
- Hydra-UI related (Streamlit interface)
- Prefect/Workflow related (task pipelines)

```bash
# Run diagnostics
python hydra_diagnostics.py

# With verbose output
python hydra_diagnostics.py --verbose
```

### Common Issues & Solutions

#### 1. Wrong SOLLOL Package Installed

**Symptoms:**
- `pip show sollol` shows version 0.9.52 from `/home/joker/SOLLOL`
- Integration errors with Hydra

**Solution:**
```bash
pip uninstall sollol -y
cd /home/joker/SOLLOL-Hydra
pip install --user --no-build-isolation -e .
```

#### 2. Import Errors

**SOLLOL-Hydra Issue:**
```python
from sollol import OllamaPool  # ImportError
```

**Solution:**
```bash
# Reinstall sollol-hydra
cd /home/joker/SOLLOL-Hydra
pip install --user --no-build-isolation -e .
```

**Hydra Issue:**
```python
from core.orchestrator import ModelOrchestrator  # ImportError
```

**Solution:**
```bash
# Check if in hydra directory
cd /home/joker/hydra
# Verify files exist
python hydra_diagnostics.py
```

#### 3. Prefect/Workflow Errors

**Symptoms:**
- Errors mentioning `flow`, `task`, `dag_pipeline`
- Version conflicts with `griffe`

**This is a Hydra workflow issue, not SOLLOL-Hydra.**

**Solution:**
The workflow pipeline is optional. Hydra uses the orchestrator directly when workflows are unavailable.

```bash
# Update Prefect if needed
pip install prefect==2.20.10 --upgrade
```

#### 4. Streamlit UI Errors

**Symptoms:**
- Errors from `app.py` or `ui/` modules
- `st.session_state` errors

**This is a Hydra-UI issue, not SOLLOL-Hydra.**

**Solution:**
```bash
# Kill existing Streamlit processes
pkill -f streamlit

# Restart
streamlit run app.py
```

## Diagnostic Flowchart

```
Error Occurs
     |
     v
Run: python hydra_diagnostics.py
     |
     v
Check Tool Output
     |
     ├─> "SOLLOL-HYDRA" → SOLLOL-Hydra issue
     │   - Check /home/joker/SOLLOL-Hydra
     │   - Reinstall sollol-hydra
     │   - Check core/sollol_integration.py
     |
     ├─> "HYDRA-CORE" → Hydra orchestration issue
     │   - Check core/orchestrator.py
     │   - Check core/memory.py
     │   - Check db/connections.py
     |
     ├─> "HYDRA-UI" → Streamlit interface issue
     │   - Check app.py
     │   - Check ui/ modules
     │   - Restart Streamlit
     |
     ├─> "PREFECT/WORKFLOW" → Workflow pipeline issue
     │   - Check workflows/dag_pipeline.py
     │   - Update Prefect
     │   - Workflow is optional, can be disabled
     |
     └─> "DEPENDENCIES" → Missing packages
         - Install missing packages
         - Check requirements.txt
```

## Error Keywords Reference

### SOLLOL-Hydra Errors
- `OllamaPool`
- `UnifiedDashboard`
- `sollol`
- `distributed`
- `discovery`
- `load_balancer`
- `node discovery`

### Hydra-Core Errors
- `ModelOrchestrator`
- `HierarchicalMemory`
- `code_generation`
- `orchestrator`
- `memory tier`
- `db_manager`

### Hydra-UI Errors
- `streamlit`
- `st.session_state`
- `app.py`
- `render_*` (UI functions)

### Workflow Errors
- `prefect`
- `flow`
- `task`
- `dag_pipeline`
- `workflow`
- `griffe` (Prefect dependency)

## Quick Reference

### Check SOLLOL-Hydra Status
```bash
pip show sollol-hydra
python -c "import sollol; print(f'{sollol.__version__} @ {sollol.__file__}')"
```

### Verify Integration
```bash
python -c "from sollol import OllamaPool, UnifiedDashboard; print('OK')"
```

### Run Full Diagnostics
```bash
python hydra_diagnostics.py
```

### Start Hydra
```bash
# UI only
streamlit run app.py

# API server
python main.py api

# Both (in separate terminals)
python main.py api  # Terminal 1
python main.py ui   # Terminal 2
```

## Development Workflow

### 1. Making Changes to SOLLOL-Hydra

```bash
cd /home/joker/SOLLOL-Hydra

# Make your changes to src/sollol/

# No reinstall needed (using -e editable mode)
# Changes are immediately available

# Test
python hydra_diagnostics.py
```

### 2. Making Changes to Hydra

```bash
cd /home/joker/hydra

# Make your changes to core/, ui/, etc.

# Restart services
pkill -f streamlit  # If UI is running
streamlit run app.py

# Or restart API
# pkill -f "python main.py api"
# python main.py api
```

### 3. Testing Integration

```bash
# Always run diagnostics after changes
python hydra_diagnostics.py

# Test imports
python -c "from core.sollol_integration import SOLLOLIntegration; print('OK')"

# Test Hydra startup
streamlit run app.py
```

## Architecture

```
┌─────────────────────────────────────────┐
│             Hydra Application            │
│  ┌────────────────────────────────────┐ │
│  │   UI Layer (app.py, ui/)           │ │
│  └────────────┬───────────────────────┘ │
│               │                          │
│  ┌────────────▼───────────────────────┐ │
│  │   Core (orchestrator, memory)      │ │
│  │   ┌──────────────────────────────┐ │ │
│  │   │ core/sollol_integration.py   │ │ │
│  │   │  (Integration Layer)         │ │ │
│  │   └──────────┬───────────────────┘ │ │
│  └──────────────┼─────────────────────┘ │
└─────────────────┼───────────────────────┘
                  │
                  │ import sollol
                  │
┌─────────────────▼───────────────────────┐
│         SOLLOL-Hydra Package             │
│  /home/joker/SOLLOL-Hydra/src/sollol    │
│  ┌────────────────────────────────────┐ │
│  │   OllamaPool (Load Balancer)       │ │
│  │   UnifiedDashboard (Monitoring)    │ │
│  │   Node Discovery                   │ │
│  │   Distributed Orchestration        │ │
│  └────────────────────────────────────┘ │
└──────────────────────────────────────────┘
```

## Summary

- **sollol-hydra** is installed as a separate package from regular sollol
- Use `python hydra_diagnostics.py` to identify issue source
- SOLLOL-Hydra handles distributed orchestration
- Hydra handles model selection, memory, and UI
- The integration layer (`core/sollol_integration.py`) connects them
- Most errors can be categorized by keyword matching

For issues, always start with the diagnostic tool to determine whether the problem is in SOLLOL-Hydra or Hydra itself.
