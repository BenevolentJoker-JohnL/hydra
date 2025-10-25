#!/usr/bin/env python3
"""
Hydra System Diagnostics Tool

This tool helps distinguish between SOLLOL-Hydra issues and Hydra application issues.
It checks the state of both systems and provides actionable recommendations.

Usage:
    python hydra_diagnostics.py
    python hydra_diagnostics.py --verbose
"""

import sys
import os
from pathlib import Path
from typing import Dict, List, Tuple
import subprocess

class Colors:
    """Terminal color codes"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_header(text: str):
    """Print a formatted header"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text:^70}{Colors.END}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.END}\n")


def print_status(status: str, message: str):
    """Print a status message with color"""
    if status == "OK":
        color = Colors.GREEN
        symbol = "✓"
    elif status == "WARNING":
        color = Colors.YELLOW
        symbol = "⚠"
    elif status == "ERROR":
        color = Colors.RED
        symbol = "✗"
    else:
        color = Colors.CYAN
        symbol = "ℹ"

    print(f"{color}{symbol} {message}{Colors.END}")


def check_sollol_installation() -> Tuple[str, Dict]:
    """Check SOLLOL/SOLLOL-Hydra installation"""
    results = {
        "sollol_installed": False,
        "sollol_hydra_installed": False,
        "sollol_version": None,
        "sollol_location": None,
        "package_name": None
    }

    try:
        # Check if sollol module can be imported
        import sollol
        results["sollol_installed"] = True
        results["sollol_version"] = getattr(sollol, '__version__', 'unknown')
        results["sollol_location"] = sollol.__file__

        # Check which package is installed
        pip_output = subprocess.run(
            ['pip', 'show', 'sollol-hydra'],
            capture_output=True,
            text=True
        )

        if pip_output.returncode == 0:
            results["sollol_hydra_installed"] = True
            results["package_name"] = "sollol-hydra"
            return "OK", results

        pip_output = subprocess.run(
            ['pip', 'show', 'sollol'],
            capture_output=True,
            text=True
        )

        if pip_output.returncode == 0:
            results["package_name"] = "sollol"
            return "WARNING", results

        return "ERROR", results

    except ImportError:
        return "ERROR", results


def check_hydra_structure() -> Tuple[str, Dict]:
    """Check Hydra project structure"""
    results = {
        "root_exists": False,
        "core_exists": False,
        "main_py_exists": False,
        "app_py_exists": False,
        "config_exists": False,
        "missing_files": []
    }

    hydra_root = Path("/home/joker/hydra")

    if not hydra_root.exists():
        return "ERROR", results

    results["root_exists"] = True

    # Check critical files/directories
    critical_paths = {
        "core_exists": hydra_root / "core",
        "main_py_exists": hydra_root / "main.py",
        "app_py_exists": hydra_root / "app.py",
        "config_exists": hydra_root / "config"
    }

    for key, path in critical_paths.items():
        if path.exists():
            results[key] = True
        else:
            results["missing_files"].append(str(path))

    # Determine overall status
    if all([results["core_exists"], results["main_py_exists"], results["app_py_exists"]]):
        return "OK", results
    elif results["core_exists"] and results["main_py_exists"]:
        return "WARNING", results
    else:
        return "ERROR", results


def check_sollol_hydra_integration() -> Tuple[str, Dict]:
    """Check integration between SOLLOL and Hydra"""
    results = {
        "integration_file_exists": False,
        "integration_imports": False,
        "sollol_pool_available": False,
        "dashboard_available": False,
        "resource_monitoring": False,
        "nodes_discovered": 0,
        "nodes_info": []
    }

    hydra_root = Path("/home/joker/hydra")
    integration_file = hydra_root / "core" / "sollol_integration.py"

    if not integration_file.exists():
        return "ERROR", results

    results["integration_file_exists"] = True

    try:
        # Test imports
        from sollol import OllamaPool, UnifiedDashboard
        results["sollol_pool_available"] = True
        results["dashboard_available"] = True
        results["integration_imports"] = True

        # Try to get resource information
        try:
            pool = OllamaPool.auto_configure()
            if hasattr(pool, 'nodes') and pool.nodes:
                results["resource_monitoring"] = True
                results["nodes_discovered"] = len(pool.nodes)

                # Get node resource info
                for node in pool.nodes[:5]:  # Limit to 5 nodes for display
                    node_info = {
                        'host': getattr(node, 'host', 'unknown'),
                        'port': getattr(node, 'port', 11434),
                        'healthy': getattr(node, 'is_healthy', False),
                        'gpu': getattr(node, 'gpu_available', False),
                        'vram_available_mb': getattr(node, 'vram_available', 0),
                        'vram_total_mb': getattr(node, 'vram_total', 0),
                    }
                    results["nodes_info"].append(node_info)
        except Exception as e:
            pass  # Resource monitoring is optional

        return "OK", results
    except ImportError as e:
        return "ERROR", results


def check_dependencies() -> Tuple[str, Dict]:
    """Check Python dependencies"""
    results = {
        "streamlit": False,
        "fastapi": False,
        "ollama": False,
        "redis": False,
        "prefect": False,
        "missing": []
    }

    required_packages = {
        "streamlit": "streamlit",
        "fastapi": "fastapi",
        "ollama": "ollama",
        "redis": "redis",
        "prefect": "prefect"
    }

    for key, package in required_packages.items():
        try:
            __import__(package)
            results[key] = True
        except ImportError:
            results["missing"].append(package)

    if len(results["missing"]) == 0:
        return "OK", results
    elif len(results["missing"]) <= 2:
        return "WARNING", results
    else:
        return "ERROR", results


def check_ollama_service() -> Tuple[str, Dict]:
    """Check if Ollama service is running"""
    results = {
        "running": False,
        "models_available": False,
        "model_count": 0
    }

    try:
        output = subprocess.run(
            ['ollama', 'list'],
            capture_output=True,
            text=True,
            timeout=5
        )

        if output.returncode == 0:
            results["running"] = True
            # Count models (subtract 1 for header line)
            model_count = len(output.stdout.strip().split('\n')) - 1
            results["model_count"] = max(0, model_count)
            results["models_available"] = model_count > 0
            return "OK" if results["models_available"] else "WARNING", results

        return "ERROR", results
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "ERROR", results


def diagnose_issue(error_type: str, error_msg: str) -> str:
    """Provide diagnosis based on error type"""

    sollol_keywords = [
        "OllamaPool", "UnifiedDashboard", "sollol", "distributed",
        "discovery", "load_balancer", "node discovery"
    ]

    hydra_keywords = [
        "ModelOrchestrator", "HierarchicalMemory", "code_generation",
        "orchestrator", "memory", "workflow"
    ]

    prefect_keywords = [
        "prefect", "flow", "task", "dag_pipeline", "workflow"
    ]

    streamlit_keywords = [
        "streamlit", "st.session_state", "st.", "app.py"
    ]

    # Check keywords
    error_lower = f"{error_type} {error_msg}".lower()

    if any(keyword.lower() in error_lower for keyword in sollol_keywords):
        return "SOLLOL-HYDRA"
    elif any(keyword.lower() in error_lower for keyword in prefect_keywords):
        return "PREFECT/WORKFLOW"
    elif any(keyword.lower() in error_lower for keyword in streamlit_keywords):
        return "HYDRA-UI"
    elif any(keyword.lower() in error_lower for keyword in hydra_keywords):
        return "HYDRA-CORE"
    else:
        return "UNKNOWN"


def provide_recommendations(checks: Dict[str, Tuple[str, Dict]]):
    """Provide recommendations based on check results"""
    print_header("RECOMMENDATIONS")

    sollol_status, sollol_data = checks["sollol"]
    hydra_status, hydra_data = checks["hydra"]
    integration_status, integration_data = checks["integration"]
    deps_status, deps_data = checks["dependencies"]
    ollama_status, ollama_data = checks["ollama"]

    recommendations = []

    # SOLLOL issues
    if not sollol_data["sollol_hydra_installed"]:
        recommendations.append({
            "level": "ERROR",
            "area": "SOLLOL-HYDRA",
            "issue": "sollol-hydra package not installed",
            "fix": "cd /home/joker/SOLLOL-Hydra && pip install --user --no-build-isolation -e ."
        })

    # Hydra structure issues
    if hydra_data["missing_files"]:
        recommendations.append({
            "level": "WARNING",
            "area": "HYDRA",
            "issue": f"Missing files: {', '.join(hydra_data['missing_files'])}",
            "fix": "Check git status and restore missing files"
        })

    # Integration issues
    if not integration_data["integration_imports"]:
        recommendations.append({
            "level": "ERROR",
            "area": "SOLLOL-HYDRA",
            "issue": "Cannot import SOLLOL components",
            "fix": "Reinstall sollol-hydra or check /home/joker/SOLLOL-Hydra/src/sollol/__init__.py"
        })

    # Dependency issues
    if deps_data["missing"]:
        recommendations.append({
            "level": "WARNING",
            "area": "DEPENDENCIES",
            "issue": f"Missing packages: {', '.join(deps_data['missing'])}",
            "fix": f"pip install {' '.join(deps_data['missing'])}"
        })

    # Ollama issues
    if not ollama_data["running"]:
        recommendations.append({
            "level": "ERROR",
            "area": "OLLAMA",
            "issue": "Ollama service not running",
            "fix": "systemctl start ollama or run ollama serve"
        })
    elif not ollama_data["models_available"]:
        recommendations.append({
            "level": "WARNING",
            "area": "OLLAMA",
            "issue": "No models installed",
            "fix": "ollama pull qwen3:1.7b && ollama pull qwen3:14b && ollama pull llama3.2"
        })

    # Print recommendations
    if not recommendations:
        print_status("OK", "All systems operational! No recommendations.")
    else:
        for rec in recommendations:
            print(f"\n{Colors.BOLD}[{rec['area']}]{Colors.END}")
            print_status(rec['level'], f"Issue: {rec['issue']}")
            print(f"  {Colors.CYAN}Fix: {rec['fix']}{Colors.END}")


def main():
    """Main diagnostic routine"""
    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    print_header("HYDRA SYSTEM DIAGNOSTICS")

    # Run checks
    checks = {
        "sollol": check_sollol_installation(),
        "hydra": check_hydra_structure(),
        "integration": check_sollol_hydra_integration(),
        "dependencies": check_dependencies(),
        "ollama": check_ollama_service()
    }

    # Display results
    print_header("SYSTEM STATUS")

    # SOLLOL check
    sollol_status, sollol_data = checks["sollol"]
    print(f"{Colors.BOLD}SOLLOL-HYDRA:{Colors.END}")
    if sollol_data["sollol_hydra_installed"]:
        print_status("OK", f"sollol-hydra {sollol_data['sollol_version']} installed")
        print(f"  Location: {sollol_data['sollol_location']}")
    elif sollol_data["sollol_installed"]:
        print_status("WARNING", f"Using regular sollol (not sollol-hydra)")
        print(f"  Location: {sollol_data['sollol_location']}")
    else:
        print_status("ERROR", "SOLLOL not installed")

    # Hydra check
    hydra_status, hydra_data = checks["hydra"]
    print(f"\n{Colors.BOLD}HYDRA PROJECT:{Colors.END}")
    if hydra_status == "OK":
        print_status("OK", "All critical files present")
    elif hydra_status == "WARNING":
        print_status("WARNING", f"Some files missing: {len(hydra_data['missing_files'])} files")
    else:
        print_status("ERROR", "Critical files missing")

    # Integration check
    integration_status, integration_data = checks["integration"]
    print(f"\n{Colors.BOLD}INTEGRATION:{Colors.END}")
    if integration_status == "OK":
        print_status("OK", "SOLLOL integration working")
        if integration_data["resource_monitoring"]:
            print(f"  {Colors.CYAN}Nodes discovered: {integration_data['nodes_discovered']}{Colors.END}")
            if integration_data["nodes_info"]:
                print(f"  {Colors.CYAN}Resource monitoring:{Colors.END}")
                for node in integration_data["nodes_info"]:
                    status = "✓" if node['healthy'] else "✗"
                    gpu_label = "GPU" if node['gpu'] else "CPU"
                    vram_gb = node['vram_available_mb'] / 1024
                    print(f"    {status} {node['host']}:{node['port']} ({gpu_label}) - {vram_gb:.1f}GB VRAM available")
    else:
        print_status("ERROR", "Integration issues detected")

    # Dependencies check
    deps_status, deps_data = checks["dependencies"]
    print(f"\n{Colors.BOLD}DEPENDENCIES:{Colors.END}")
    if deps_status == "OK":
        print_status("OK", "All required packages installed")
    elif deps_status == "WARNING":
        print_status("WARNING", f"Missing: {', '.join(deps_data['missing'])}")
    else:
        print_status("ERROR", f"Multiple missing packages: {', '.join(deps_data['missing'])}")

    # Ollama check
    ollama_status, ollama_data = checks["ollama"]
    print(f"\n{Colors.BOLD}OLLAMA:{Colors.END}")
    if ollama_status == "OK":
        print_status("OK", f"Running with {ollama_data['model_count']} models")
    elif ollama_status == "WARNING":
        print_status("WARNING", "Running but no models installed")
    else:
        print_status("ERROR", "Ollama service not running")

    # Provide recommendations
    provide_recommendations(checks)

    # Overall status
    print_header("OVERALL STATUS")

    all_ok = all(status in ["OK", "WARNING"] for status, _ in checks.values())
    critical_errors = sum(1 for status, _ in checks.values() if status == "ERROR")

    if all_ok and critical_errors == 0:
        print_status("OK", "System is healthy and ready to run")
        print(f"\n{Colors.GREEN}You can start Hydra with: streamlit run app.py{Colors.END}")
    elif critical_errors <= 1:
        print_status("WARNING", f"{critical_errors} critical issue(s) found - review recommendations")
    else:
        print_status("ERROR", f"{critical_errors} critical issues found - address before running")

    print()


if __name__ == "__main__":
    main()
