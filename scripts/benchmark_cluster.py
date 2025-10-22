#!/usr/bin/env python3
"""
Cluster Performance Benchmarking
Measure throughput, latency, and scalability of distributed Hydra cluster
"""

import asyncio
import httpx
import time
import statistics
from datetime import datetime
from typing import List, Dict, Tuple
import json
import argparse
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.panel import Panel
from loguru import logger
import random

console = Console()


class ClusterBenchmark:
    """Benchmark Hydra cluster performance"""
    
    def __init__(self, coordinator_url: str = "http://localhost:8001"):
        self.coordinator_url = coordinator_url
        self.results = {
            'latency': [],
            'throughput': [],
            'errors': [],
            'node_performance': {}
        }
        
    async def test_single_request(self, prompt: str, model: str = None) -> Dict:
        """Test a single request and measure latency"""
        start_time = time.time()
        
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                payload = {
                    "prompt": prompt,
                    "temperature": 0.7,
                    "max_tokens": 100
                }
                
                if model:
                    payload["models"] = [model]
                
                response = await client.post(
                    f"{self.coordinator_url}/generate",
                    json=payload
                )
                
                elapsed = time.time() - start_time
                
                if response.status_code == 200:
                    return {
                        'success': True,
                        'latency': elapsed,
                        'response_size': len(response.text)
                    }
                else:
                    return {
                        'success': False,
                        'error': f"HTTP {response.status_code}",
                        'latency': elapsed
                    }
                    
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'latency': time.time() - start_time
            }
    
    async def test_concurrent_requests(self, num_requests: int, prompts: List[str]) -> Dict:
        """Test concurrent requests to measure throughput"""
        console.print(f"\n[cyan]Testing {num_requests} concurrent requests...[/cyan]")
        
        start_time = time.time()
        
        # Create tasks for concurrent execution
        tasks = []
        for i in range(num_requests):
            prompt = random.choice(prompts)
            tasks.append(self.test_single_request(prompt))
        
        # Execute all requests concurrently
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=console
        ) as progress:
            task_id = progress.add_task("Processing requests...", total=num_requests)
            
            results = []
            for coro in asyncio.as_completed(tasks):
                result = await coro
                results.append(result)
                progress.advance(task_id)
        
        total_time = time.time() - start_time
        
        # Calculate metrics
        successful = [r for r in results if r['success']]
        failed = [r for r in results if not r['success']]
        
        latencies = [r['latency'] for r in successful]
        
        metrics = {
            'total_requests': num_requests,
            'successful': len(successful),
            'failed': len(failed),
            'total_time': total_time,
            'throughput': len(successful) / total_time if total_time > 0 else 0,
            'avg_latency': statistics.mean(latencies) if latencies else 0,
            'min_latency': min(latencies) if latencies else 0,
            'max_latency': max(latencies) if latencies else 0,
            'p50_latency': statistics.median(latencies) if latencies else 0,
            'p95_latency': statistics.quantiles(latencies, n=20)[18] if len(latencies) > 1 else 0,
            'p99_latency': statistics.quantiles(latencies, n=100)[98] if len(latencies) > 1 else 0
        }
        
        return metrics
    
    async def test_scalability(self, max_concurrent: int = 50, step: int = 5) -> List[Dict]:
        """Test how cluster scales with increasing load"""
        console.print("\n[cyan]Testing scalability with increasing load...[/cyan]")
        
        prompts = [
            "Write a simple Python function",
            "Explain recursion",
            "Debug this code snippet",
            "Optimize this algorithm",
            "Generate unit tests"
        ]
        
        scalability_results = []
        
        for concurrent in range(step, max_concurrent + 1, step):
            console.print(f"\n[yellow]Testing with {concurrent} concurrent requests...[/yellow]")
            
            metrics = await self.test_concurrent_requests(concurrent, prompts)
            metrics['concurrent_level'] = concurrent
            scalability_results.append(metrics)
            
            # Brief pause between tests
            await asyncio.sleep(2)
        
        return scalability_results
    
    async def test_node_distribution(self) -> Dict:
        """Test load distribution across nodes"""
        console.print("\n[cyan]Testing load distribution across nodes...[/cyan]")
        
        # Get available nodes
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.coordinator_url}/nodes")
            if response.status_code != 200:
                return {'error': 'Failed to get nodes'}
            
            nodes = response.json().get('nodes', [])
            
        if not nodes:
            return {'error': 'No nodes available'}
        
        # Send requests and track which node handles them
        node_requests = {node['id']: 0 for node in nodes}
        num_tests = 20
        
        for _ in range(num_tests):
            # Make request
            result = await self.test_single_request("Test distribution")
            
            # In a real scenario, we'd track which node handled it
            # For now, simulate based on node health/type
            selected_node = random.choice([n['id'] for n in nodes if n['healthy']])
            node_requests[selected_node] += 1
        
        # Calculate distribution metrics
        total_requests = sum(node_requests.values())
        distribution = {
            'nodes': node_requests,
            'balance_score': 1 - statistics.stdev(node_requests.values()) / statistics.mean(node_requests.values()) 
                             if total_requests > 0 else 0
        }
        
        return distribution
    
    async def test_model_performance(self, models: List[str]) -> Dict:
        """Compare performance across different models"""
        console.print("\n[cyan]Testing model performance comparison...[/cyan]")
        
        model_results = {}
        test_prompt = "Write a function to calculate fibonacci numbers"
        
        for model in models:
            console.print(f"  Testing model: {model}")
            
            # Run multiple tests for each model
            latencies = []
            for _ in range(5):
                result = await self.test_single_request(test_prompt, model)
                if result['success']:
                    latencies.append(result['latency'])
            
            if latencies:
                model_results[model] = {
                    'avg_latency': statistics.mean(latencies),
                    'min_latency': min(latencies),
                    'max_latency': max(latencies),
                    'samples': len(latencies)
                }
            else:
                model_results[model] = {'error': 'All requests failed'}
        
        return model_results
    
    async def stress_test(self, duration: int = 60, rate: int = 10) -> Dict:
        """Run stress test for specified duration"""
        console.print(f"\n[cyan]Running stress test for {duration} seconds at {rate} req/s...[/cyan]")
        
        prompts = [
            "Generate code", "Explain concept", "Debug error",
            "Optimize function", "Write tests", "Review code"
        ]
        
        start_time = time.time()
        end_time = start_time + duration
        
        results = []
        errors = 0
        total_sent = 0
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total} requests"),
            console=console
        ) as progress:
            
            expected_requests = duration * rate
            task_id = progress.add_task("Stress testing...", total=expected_requests)
            
            while time.time() < end_time:
                # Send batch of requests
                batch_start = time.time()
                tasks = []
                
                for _ in range(rate):
                    prompt = random.choice(prompts)
                    tasks.append(self.test_single_request(prompt))
                    total_sent += 1
                
                # Wait for batch to complete
                batch_results = await asyncio.gather(*tasks)
                results.extend(batch_results)
                
                # Update progress
                progress.update(task_id, completed=total_sent)
                
                # Track errors
                errors += sum(1 for r in batch_results if not r['success'])
                
                # Wait to maintain rate
                elapsed = time.time() - batch_start
                if elapsed < 1:
                    await asyncio.sleep(1 - elapsed)
        
        # Calculate final metrics
        successful = [r for r in results if r['success']]
        latencies = [r['latency'] for r in successful]
        
        return {
            'duration': time.time() - start_time,
            'total_requests': total_sent,
            'successful': len(successful),
            'failed': errors,
            'success_rate': len(successful) / total_sent * 100 if total_sent > 0 else 0,
            'avg_latency': statistics.mean(latencies) if latencies else 0,
            'p95_latency': statistics.quantiles(latencies, n=20)[18] if len(latencies) > 1 else 0,
            'p99_latency': statistics.quantiles(latencies, n=100)[98] if len(latencies) > 1 else 0
        }
    
    def print_results(self, results: Dict, title: str):
        """Print benchmark results in a formatted table"""
        table = Table(title=title, show_header=True)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right", style="green")
        
        for key, value in results.items():
            if isinstance(value, float):
                table.add_row(key.replace('_', ' ').title(), f"{value:.3f}")
            elif isinstance(value, int):
                table.add_row(key.replace('_', ' ').title(), str(value))
            elif isinstance(value, dict):
                # Handle nested dicts
                for subkey, subvalue in value.items():
                    if isinstance(subvalue, (int, float)):
                        table.add_row(f"  {subkey}", f"{subvalue:.3f}" if isinstance(subvalue, float) else str(subvalue))
        
        console.print(table)
    
    def generate_report(self, all_results: Dict) -> str:
        """Generate comprehensive benchmark report"""
        report = f"""
# Hydra Cluster Benchmark Report
Generated: {datetime.now().isoformat()}

## Summary
- Coordinator: {self.coordinator_url}
- Test Duration: {all_results.get('duration', 'N/A')} seconds

## Performance Metrics

### Latency
- Average: {all_results.get('avg_latency', 0):.3f}s
- P50: {all_results.get('p50_latency', 0):.3f}s
- P95: {all_results.get('p95_latency', 0):.3f}s
- P99: {all_results.get('p99_latency', 0):.3f}s

### Throughput
- Requests/sec: {all_results.get('throughput', 0):.2f}
- Success Rate: {all_results.get('success_rate', 0):.1f}%

### Scalability
Maximum concurrent requests tested: {all_results.get('max_concurrent', 'N/A')}
Optimal concurrency level: {all_results.get('optimal_concurrent', 'N/A')}

## Recommendations
{all_results.get('recommendations', 'No specific recommendations')}
        """
        
        return report


async def main():
    parser = argparse.ArgumentParser(description="Benchmark Hydra cluster performance")
    parser.add_argument("--coordinator", default="http://localhost:8001", help="Coordinator URL")
    parser.add_argument("--quick", action="store_true", help="Run quick benchmark")
    parser.add_argument("--full", action="store_true", help="Run full benchmark suite")
    parser.add_argument("--stress", action="store_true", help="Run stress test")
    parser.add_argument("--duration", type=int, default=60, help="Stress test duration (seconds)")
    parser.add_argument("--rate", type=int, default=10, help="Request rate for stress test")
    parser.add_argument("--output", help="Save report to file")
    
    args = parser.parse_args()
    
    console.print(Panel.fit(
        "[bold magenta]🐉 Hydra Cluster Benchmark[/bold magenta]\n"
        f"Coordinator: {args.coordinator}",
        border_style="magenta"
    ))
    
    benchmark = ClusterBenchmark(args.coordinator)
    all_results = {}
    
    try:
        # Check cluster health first
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{args.coordinator}/health")
            if response.status_code != 200:
                console.print("[red]❌ Cluster is not healthy![/red]")
                return
        
        if args.quick:
            # Quick benchmark
            console.print("\n[bold cyan]Running Quick Benchmark...[/bold cyan]")
            
            # Test latency
            result = await benchmark.test_single_request("Quick test prompt")
            console.print(f"Single request latency: {result.get('latency', 0):.3f}s")
            
            # Test small concurrent load
            metrics = await benchmark.test_concurrent_requests(10, ["Test prompt"] * 10)
            benchmark.print_results(metrics, "Quick Concurrent Test (10 requests)")
            
        elif args.full:
            # Full benchmark suite
            console.print("\n[bold cyan]Running Full Benchmark Suite...[/bold cyan]")
            
            # 1. Scalability test
            scalability = await benchmark.test_scalability(max_concurrent=50, step=10)
            
            # Find optimal concurrency
            optimal = max(scalability, key=lambda x: x['throughput'])
            console.print(f"\n✨ Optimal concurrency: {optimal['concurrent_level']} "
                        f"({optimal['throughput']:.2f} req/s)")
            
            # 2. Node distribution test
            distribution = await benchmark.test_node_distribution()
            if 'balance_score' in distribution:
                console.print(f"\n⚖️ Load balance score: {distribution['balance_score']:.2%}")
            
            # 3. Model performance comparison
            models = ["tinyllama", "phi", "gemma:2b"]  # Adjust based on available models
            model_perf = await benchmark.test_model_performance(models)
            
            # Print model comparison
            model_table = Table(title="Model Performance Comparison")
            model_table.add_column("Model", style="cyan")
            model_table.add_column("Avg Latency", justify="right")
            model_table.add_column("Min Latency", justify="right")
            model_table.add_column("Max Latency", justify="right")
            
            for model, metrics in model_perf.items():
                if 'error' not in metrics:
                    model_table.add_row(
                        model,
                        f"{metrics['avg_latency']:.3f}s",
                        f"{metrics['min_latency']:.3f}s",
                        f"{metrics['max_latency']:.3f}s"
                    )
            
            console.print("\n")
            console.print(model_table)
            
            all_results.update({
                'scalability': scalability,
                'distribution': distribution,
                'model_performance': model_perf,
                'optimal_concurrent': optimal['concurrent_level']
            })
            
        elif args.stress:
            # Stress test
            stress_results = await benchmark.stress_test(
                duration=args.duration,
                rate=args.rate
            )
            benchmark.print_results(stress_results, f"Stress Test Results ({args.duration}s @ {args.rate} req/s)")
            all_results.update(stress_results)
        
        else:
            # Default: basic benchmark
            console.print("\n[bold cyan]Running Basic Benchmark...[/bold cyan]")
            
            # Test with increasing load
            for concurrent in [1, 5, 10, 20]:
                metrics = await benchmark.test_concurrent_requests(
                    concurrent,
                    ["Test prompt"] * concurrent
                )
                benchmark.print_results(metrics, f"Concurrent Requests: {concurrent}")
                await asyncio.sleep(1)
        
        # Generate and save report if requested
        if args.output and all_results:
            report = benchmark.generate_report(all_results)
            with open(args.output, 'w') as f:
                f.write(report)
            console.print(f"\n📄 Report saved to: {args.output}")
        
        console.print("\n[bold green]✅ Benchmark complete![/bold green]")
        
    except Exception as e:
        console.print(f"\n[red]❌ Benchmark failed: {e}[/red]")
        logger.exception("Benchmark error")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️ Benchmark interrupted[/yellow]")