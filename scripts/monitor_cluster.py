#!/usr/bin/env python3
"""
Cluster Health Monitoring Script
Real-time monitoring of distributed Hydra cluster
"""

import asyncio
import httpx
import sys
import os
from datetime import datetime, timedelta
from typing import Dict, List
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.text import Text
import argparse
from loguru import logger

console = Console()


class ClusterMonitor:
    """Monitor Hydra cluster health and performance"""
    
    def __init__(self, coordinator_url: str = "http://localhost:8001"):
        self.coordinator_url = coordinator_url
        self.nodes = {}
        self.cluster_stats = {}
        self.last_update = None
        self.alerts = []
        
    async def fetch_cluster_status(self) -> Dict:
        """Fetch current cluster status"""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                # Get cluster stats
                stats_response = await client.get(f"{self.coordinator_url}/stats")
                if stats_response.status_code == 200:
                    self.cluster_stats = stats_response.json()
                
                # Get nodes list
                nodes_response = await client.get(f"{self.coordinator_url}/nodes")
                if nodes_response.status_code == 200:
                    nodes_data = nodes_response.json()
                    self.nodes = {
                        node['id']: node 
                        for node in nodes_data.get('nodes', [])
                    }
                
                self.last_update = datetime.now()
                return {"status": "connected", "nodes": len(self.nodes)}
                
        except Exception as e:
            self.add_alert(f"❌ Connection failed: {e}", "error")
            return {"status": "disconnected", "error": str(e)}
    
    def add_alert(self, message: str, level: str = "info"):
        """Add alert to the list"""
        self.alerts.append({
            "time": datetime.now(),
            "message": message,
            "level": level
        })
        # Keep only last 10 alerts
        self.alerts = self.alerts[-10:]
    
    def check_node_health(self, node: Dict):
        """Check individual node health and generate alerts"""
        node_id = node['id']
        
        # Check if node is unhealthy
        if not node.get('healthy', False):
            self.add_alert(f"⚠️ Node {node_id} is unhealthy", "warning")
        
        # Check high CPU usage
        cpu_percent = node.get('cpu_percent', 0)
        if cpu_percent > 80:
            self.add_alert(f"🔥 High CPU on {node_id}: {cpu_percent:.1f}%", "warning")
        
        # Check low memory
        mem_available = node.get('memory_available', 0)
        if mem_available < 2:
            self.add_alert(f"💾 Low memory on {node_id}: {mem_available:.1f}GB", "warning")
        
        # Check stale heartbeat
        last_heartbeat = node.get('last_heartbeat')
        if last_heartbeat:
            heartbeat_time = datetime.fromisoformat(last_heartbeat)
            time_since = (datetime.now() - heartbeat_time).total_seconds()
            if time_since > 120:
                self.add_alert(f"💔 No heartbeat from {node_id} for {time_since:.0f}s", "error")
    
    def create_nodes_table(self) -> Table:
        """Create table showing node status"""
        table = Table(title="🖥️ Connected Worker Nodes", expand=True)
        
        table.add_column("Node ID", style="cyan")
        table.add_column("IP Address", style="yellow")
        table.add_column("Type", style="magenta")
        table.add_column("Status", style="green")
        table.add_column("CPU %", justify="right")
        table.add_column("Memory", justify="right")
        table.add_column("Tasks", justify="right")
        table.add_column("Models Loaded", style="blue")
        
        for node_id, node in self.nodes.items():
            # Determine status color
            if node.get('healthy'):
                status = Text("✅ Healthy", style="green")
            else:
                status = Text("❌ Unhealthy", style="red")
            
            # Format CPU usage with color
            cpu_percent = node.get('cpu_percent', 0)
            cpu_color = "green" if cpu_percent < 50 else "yellow" if cpu_percent < 80 else "red"
            cpu_text = Text(f"{cpu_percent:.1f}%", style=cpu_color)
            
            # Format memory
            mem_available = node.get('memory_available', 0)
            mem_color = "green" if mem_available > 4 else "yellow" if mem_available > 2 else "red"
            mem_text = Text(f"{mem_available:.1f}GB", style=mem_color)
            
            # Get models list
            models = node.get('active_models', [])
            models_str = ", ".join(models) if models else "None"
            if len(models_str) > 30:
                models_str = models_str[:27] + "..."
            
            table.add_row(
                node_id,
                node.get('host', 'unknown'),
                node.get('type', 'unknown'),
                status,
                cpu_text,
                mem_text,
                str(node.get('active_tasks', 0)),
                models_str
            )
        
        return table
    
    def create_cluster_summary(self) -> Panel:
        """Create cluster summary panel"""
        cluster = self.cluster_stats.get('cluster', {})
        
        summary_text = f"""
[bold cyan]Cluster Overview[/bold cyan]
═══════════════════════════

Total Nodes:    {cluster.get('total_nodes', 0)}
Healthy Nodes:  [green]{cluster.get('healthy_nodes', 0)}[/green]
GPU Nodes:      {cluster.get('gpu_nodes', 0)}
CPU Nodes:      {cluster.get('cpu_nodes', 0)}

Active Models:  {cluster.get('active_models', 0)}
Cache Size:     {cluster.get('cache_size', 0)} items

Last Update:    {self.last_update.strftime('%H:%M:%S') if self.last_update else 'Never'}
        """
        
        return Panel(summary_text, title="📊 Statistics", border_style="blue")
    
    def create_alerts_panel(self) -> Panel:
        """Create alerts panel"""
        if not self.alerts:
            alerts_text = "[dim]No alerts[/dim]"
        else:
            alerts_text = ""
            for alert in self.alerts[-5:]:  # Show last 5
                time_str = alert['time'].strftime('%H:%M:%S')
                level_color = {
                    'info': 'cyan',
                    'warning': 'yellow', 
                    'error': 'red'
                }.get(alert['level'], 'white')
                
                alerts_text += f"[dim]{time_str}[/dim] [{level_color}]{alert['message']}[/{level_color}]\n"
        
        return Panel(alerts_text.strip(), title="🚨 Alerts", border_style="yellow")
    
    def create_performance_panel(self) -> Panel:
        """Create performance metrics panel"""
        load_balancer = self.cluster_stats.get('load_balancer', {})
        memory = self.cluster_stats.get('memory', {})
        
        perf_text = f"""
[bold cyan]Performance Metrics[/bold cyan]
═══════════════════════════

[yellow]Load Balancer:[/yellow]
Request Distribution:
"""
        
        # Show request counts per host
        request_counts = load_balancer.get('request_counts', {})
        if request_counts:
            for host, count in request_counts.items():
                host_short = host.split('://')[-1].split(':')[0]
                perf_text += f"  {host_short}: {count} requests\n"
        else:
            perf_text += "  [dim]No requests yet[/dim]\n"
        
        perf_text += f"""
[yellow]Memory Cache:[/yellow]
  Items: {memory.get('cache_items', 0)}
        """
        
        return Panel(perf_text.strip(), title="⚡ Performance", border_style="green")
    
    def create_dashboard_layout(self) -> Layout:
        """Create dashboard layout"""
        layout = Layout()
        
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=10)
        )
        
        layout["header"].update(
            Panel(
                Text("🐉 Hydra Cluster Monitor", justify="center", style="bold magenta"),
                border_style="magenta"
            )
        )
        
        # Split main into left and right
        layout["main"].split_row(
            Layout(name="left", ratio=2),
            Layout(name="right", ratio=1)
        )
        
        # Left side - nodes table
        layout["left"].update(self.create_nodes_table())
        
        # Right side - stats and alerts
        layout["right"].split_column(
            Layout(self.create_cluster_summary(), name="summary"),
            Layout(self.create_performance_panel(), name="performance")
        )
        
        # Footer - alerts
        layout["footer"].update(self.create_alerts_panel())
        
        return layout
    
    async def monitor_loop(self, refresh_interval: int = 5):
        """Main monitoring loop"""
        with Live(self.create_dashboard_layout(), refresh_per_second=1) as live:
            while True:
                try:
                    # Fetch latest status
                    status = await self.fetch_cluster_status()
                    
                    # Check for issues
                    if status['status'] == 'disconnected':
                        self.add_alert(f"Cannot connect to coordinator", "error")
                    else:
                        # Check each node's health
                        for node in self.nodes.values():
                            self.check_node_health(node)
                    
                    # Update display
                    live.update(self.create_dashboard_layout())
                    
                except Exception as e:
                    self.add_alert(f"Monitor error: {e}", "error")
                
                await asyncio.sleep(refresh_interval)


async def test_cluster(coordinator_url: str):
    """Test cluster functionality"""
    console.print("[bold cyan]🧪 Testing Cluster Functionality...[/bold cyan]\n")
    
    async with httpx.AsyncClient(timeout=10) as client:
        # Test 1: Health check
        console.print("1. Testing health endpoint...")
        try:
            response = await client.get(f"{coordinator_url}/health")
            if response.status_code == 200:
                console.print("   ✅ Health check passed", style="green")
            else:
                console.print(f"   ❌ Health check failed: {response.status_code}", style="red")
        except Exception as e:
            console.print(f"   ❌ Connection failed: {e}", style="red")
        
        # Test 2: List nodes
        console.print("\n2. Testing node listing...")
        try:
            response = await client.get(f"{coordinator_url}/nodes")
            if response.status_code == 200:
                nodes = response.json().get('nodes', [])
                console.print(f"   ✅ Found {len(nodes)} nodes", style="green")
                for node in nodes:
                    console.print(f"      - {node['id']} ({node['type']}) - {'Healthy' if node['healthy'] else 'Unhealthy'}")
            else:
                console.print(f"   ❌ Node listing failed: {response.status_code}", style="red")
        except Exception as e:
            console.print(f"   ❌ Failed to list nodes: {e}", style="red")
        
        # Test 3: Get cluster stats
        console.print("\n3. Testing cluster statistics...")
        try:
            response = await client.get(f"{coordinator_url}/stats")
            if response.status_code == 200:
                stats = response.json()
                cluster = stats.get('cluster', {})
                console.print(f"   ✅ Cluster has {cluster.get('healthy_nodes')}/{cluster.get('total_nodes')} healthy nodes", style="green")
            else:
                console.print(f"   ❌ Stats failed: {response.status_code}", style="red")
        except Exception as e:
            console.print(f"   ❌ Failed to get stats: {e}", style="red")
        
        # Test 4: Test model listing
        console.print("\n4. Testing model availability...")
        try:
            response = await client.get(f"{coordinator_url}/models")
            if response.status_code == 200:
                models = response.json()
                console.print(f"   ✅ Found {len(models)} models available", style="green")
                for model in models[:5]:  # Show first 5
                    console.print(f"      - {model.get('name')} on {model.get('host', 'unknown')}")
            else:
                console.print(f"   ❌ Model listing failed: {response.status_code}", style="red")
        except Exception as e:
            console.print(f"   ❌ Failed to list models: {e}", style="red")


async def main():
    parser = argparse.ArgumentParser(description="Monitor Hydra cluster health")
    parser.add_argument("--coordinator", default="http://localhost:8001", help="Coordinator URL")
    parser.add_argument("--refresh", type=int, default=5, help="Refresh interval in seconds")
    parser.add_argument("--test", action="store_true", help="Run cluster tests")
    
    args = parser.parse_args()
    
    if args.test:
        await test_cluster(args.coordinator)
    else:
        monitor = ClusterMonitor(args.coordinator)
        await monitor.monitor_loop(args.refresh)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n👋 Monitor stopped", style="yellow")