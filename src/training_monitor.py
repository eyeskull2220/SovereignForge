# SovereignForge Training Monitor - Enhanced GPU Training Progress Display
# Beautiful real-time monitoring with progress bars and GPU metrics

import time
import threading
import psutil
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import logging
from dataclasses import dataclass, field
from collections import defaultdict
import json
import os

# Rich UI components
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.progress import (
    Progress, SpinnerColumn, BarColumn, TextColumn,
    TimeRemainingColumn, TimeElapsedColumn, MofNCompleteColumn
)
from rich.columns import Columns
from rich.layout import Layout
from rich.align import Align
from rich.style import Style

# GPU monitoring
try:
    import GPUtil
    from pynvml import nvmlInit, nvmlDeviceGetUtilizationRates, nvmlDeviceGetHandleByIndex
    GPU_MONITORING_AVAILABLE = True
except ImportError:
    GPU_MONITORING_AVAILABLE = False

logger = logging.getLogger(__name__)

@dataclass
class TrainingMetrics:
    """Real-time training metrics"""
    epoch: int = 0
    total_epochs: int = 0
    batch: int = 0
    total_batches: int = 0
    loss: float = 0.0
    accuracy: float = 0.0
    learning_rate: float = 0.0
    gpu_memory_used: int = 0
    gpu_memory_total: int = 0
    gpu_utilization: float = 0.0
    gpu_temperature: float = 0.0
    epoch_time: float = 0.0
    eta_seconds: float = 0.0
    start_time: datetime = field(default_factory=datetime.now)

@dataclass
class PairProgress:
    """Progress tracking for individual trading pairs"""
    pair: str
    status: str = "waiting"  # waiting, training, validating, completed, error
    progress: float = 0.0
    current_epoch: int = 0
    total_epochs: int = 0
    best_accuracy: float = 0.0
    current_loss: float = 0.0
    eta: str = "00:00:00"
    start_time: Optional[datetime] = None
    last_update: datetime = field(default_factory=datetime.now)

class GPUTrainingMonitor:
    """Beautiful real-time GPU training monitor with progress bars"""

    def __init__(self, pairs: List[str], total_epochs: int = 50):
        self.pairs = pairs
        self.total_epochs = total_epochs
        self.console = Console()

        # Initialize progress tracking
        self.pair_progress = {}
        for pair in pairs:
            self.pair_progress[pair] = PairProgress(
                pair=pair,
                total_epochs=total_epochs
            )

        # Global training state
        self.global_metrics = TrainingMetrics(total_epochs=total_epochs)
        self.training_active = False
        self.monitor_thread = None
        self.display_active = False

        # Progress bars
        self.main_progress = None
        self.pair_progress_bars = {}

        # GPU monitoring
        self.gpu_history = []
        self.system_history = []

        # Initialize GPU monitoring if available
        if GPU_MONITORING_AVAILABLE:
            try:
                nvmlInit()
                self.gpu_available = True
            except:
                self.gpu_available = False
        else:
            self.gpu_available = False

    def start_monitoring(self):
        """Start the training monitor"""
        if self.training_active:
            return

        self.training_active = True
        self.global_metrics.start_time = datetime.now()

        # Start monitoring thread
        self.monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitor_thread.start()

        logger.info("GPU Training Monitor started")

    def stop_monitoring(self):
        """Stop the training monitor"""
        self.training_active = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5.0)
        logger.info("GPU Training Monitor stopped")

    def create_display(self) -> Layout:
        """Create the main monitoring display"""
        layout = Layout()

        # Split into sections
        layout.split(
            Layout(name="header", size=3),
            Layout(name="main", ratio=3),
            Layout(name="footer", size=4)
        )

        # Header with title and global stats
        layout["header"].update(self._create_header_panel())

        # Main content with progress bars and GPU stats
        layout["main"].split_row(
            Layout(name="progress", ratio=2),
            Layout(name="gpu_stats", ratio=1)
        )

        layout["main"]["progress"].update(self._create_progress_panel())
        layout["main"]["gpu_stats"].update(self._create_gpu_panel())

        # Footer with system info and controls
        layout["footer"].update(self._create_footer_panel())

        return layout

    def _create_header_panel(self) -> Panel:
        """Create header panel with training overview"""
        elapsed = datetime.now() - self.global_metrics.start_time
        elapsed_str = f"{elapsed.seconds // 3600:02d}:{(elapsed.seconds % 3600) // 60:02d}:{elapsed.seconds % 60:02d}"

        header_text = f"""
[bold blue]🤖 SovereignForge GPU Training Monitor[/bold blue]
[green]⏱️  Elapsed: {elapsed_str}[/green] | [yellow]📊 Epoch: {self.global_metrics.epoch}/{self.global_metrics.total_epochs}[/yellow]
[cyan]🎯 Pairs: {len(self.pairs)}[/cyan] | [magenta]🚀 Active: {sum(1 for p in self.pair_progress.values() if p.status == 'training')}[/magenta]
        """.strip()

        return Panel(
            Align.center(header_text),
            title="[bold]Training Overview[/bold]",
            border_style="blue"
        )

    def _create_progress_panel(self) -> Panel:
        """Create progress bars panel for all pairs"""
        table = Table(show_header=True, header_style="bold magenta", show_edge=False)
        table.add_column("Pair", style="cyan", width=12)
        table.add_column("Status", style="green", width=10)
        table.add_column("Progress", width=20)
        table.add_column("Epoch", style="yellow", width=8)
        table.add_column("Loss", style="red", width=8)
        table.add_column("Acc", style="green", width=8)
        table.add_column("ETA", style="blue", width=10)

        for pair, progress in self.pair_progress.items():
            # Create progress bar
            progress_bar = self._create_pair_progress_bar(progress)

            # Status with color coding
            status_text = self._format_status(progress.status)

            # Format metrics
            loss_text = ".4f" if progress.current_loss > 0 else "--"
            acc_text = ".1f" if progress.best_accuracy > 0 else "--"

            table.add_row(
                f"[bold]{pair}[/bold]",
                status_text,
                progress_bar,
                f"{progress.current_epoch}/{progress.total_epochs}",
                loss_text,
                acc_text,
                progress.eta
            )

        return Panel(
            table,
            title="[bold]Pair Training Progress[/bold]",
            border_style="green"
        )

    def _create_pair_progress_bar(self, progress: PairProgress) -> str:
        """Create a mini progress bar for a pair"""
        if progress.status == "completed":
            return "[green]██████████[/green]"
        elif progress.status == "error":
            return "[red]██████████[/red]"
        elif progress.status == "training":
            filled = int(progress.progress * 10)
            empty = 10 - filled
            return f"[green]{'█' * filled}[/green][dim]{'█' * empty}[/dim]"
        else:
            return "[dim]██████████[/dim]"

    def _format_status(self, status: str) -> str:
        """Format status with appropriate colors"""
        status_map = {
            "waiting": "[dim]⏳ Waiting[/dim]",
            "training": "[green]🚀 Training[/green]",
            "validating": "[yellow]🔍 Validating[/yellow]",
            "completed": "[bold green]✅ Completed[/bold green]",
            "error": "[bold red]❌ Error[/bold red]"
        }
        return status_map.get(status, f"[dim]{status}[/dim]")

    def _create_gpu_panel(self) -> Panel:
        """Create GPU monitoring panel"""
        if not self.gpu_available:
            return Panel(
                "[dim]GPU monitoring not available\nInstall pynvml for GPU stats[/dim]",
                title="[bold]GPU Status[/bold]",
                border_style="yellow"
            )

        try:
            # Get current GPU stats
            gpu = GPUtil.getGPUs()[0] if GPUtil.getGPUs() else None
            if not gpu:
                return Panel("[dim]No GPU detected[/dim]", title="[bold]GPU Status[/bold]")

            # Memory usage bar
            mem_percent = (gpu.memoryUsed / gpu.memoryTotal) * 100
            mem_bar = self._create_memory_bar(mem_percent)

            # Temperature with color coding
            temp_color = "green"
            if gpu.temperature > 80:
                temp_color = "red"
            elif gpu.temperature > 70:
                temp_color = "yellow"

            gpu_info = f"""
[bold]GPU: {gpu.name}[/bold]
[cyan]Memory:[/cyan] {gpu.memoryUsed:.0f}MB / {gpu.memoryTotal:.0f}MB
{mem_bar}
[cyan]Utilization:[/cyan] {gpu.load*100:.1f}%
[{temp_color}]Temperature:[/{temp_color}] {gpu.temperature}°C
[cyan]Power:[/cyan] {gpu.powerDraw:.1f}W / {gpu.powerLimit:.1f}W
            """.strip()

            return Panel(
                gpu_info,
                title="[bold]GPU Status[/bold]",
                border_style="magenta"
            )

        except Exception as e:
            return Panel(
                f"[red]GPU monitoring error: {str(e)}[/red]",
                title="[bold]GPU Status[/bold]",
                border_style="red"
            )

    def _create_memory_bar(self, percentage: float) -> str:
        """Create a memory usage bar"""
        filled = int(percentage / 10)
        bar = "█" * filled + "░" * (10 - filled)

        color = "green"
        if percentage > 90:
            color = "red"
        elif percentage > 75:
            color = "yellow"

        return f"[{color}]{bar}[/{color}] ({percentage:.1f}%)"

    def _create_footer_panel(self) -> Panel:
        """Create footer panel with system info and controls"""
        # System stats
        cpu_percent = psutil.cpu_percent()
        memory = psutil.virtual_memory()
        memory_percent = memory.percent

        # Training stats
        active_pairs = sum(1 for p in self.pair_progress.values() if p.status == 'training')
        completed_pairs = sum(1 for p in self.pair_progress.values() if p.status == 'completed')
        error_pairs = sum(1 for p in self.pair_progress.values() if p.status == 'error')

        footer_text = f"""
[dim]System: CPU {cpu_percent:.1f}% | RAM {memory_percent:.1f}%[/dim]
[dim]Training: {active_pairs} active | {completed_pairs} completed | {error_pairs} errors[/dim]
[dim]Press Ctrl+C to stop monitoring | ESC to exit[/dim]
        """.strip()

        return Panel(
            Align.center(footer_text),
            title="[bold]System Status[/bold]",
            border_style="dim"
        )

    def _monitoring_loop(self):
        """Main monitoring loop"""
        while self.training_active:
            try:
                # Update GPU history
                self._update_gpu_history()

                # Update system history
                self._update_system_history()

                # Update ETAs for active pairs
                self._update_etas()

                time.sleep(2.0)  # Update every 2 seconds

            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")
                time.sleep(5.0)

    def _update_gpu_history(self):
        """Update GPU metrics history"""
        if not self.gpu_available:
            return

        try:
            gpu = GPUtil.getGPUs()[0] if GPUtil.getGPUs() else None
            if gpu:
                self.gpu_history.append({
                    'timestamp': datetime.now(),
                    'utilization': gpu.load * 100,
                    'memory_used': gpu.memoryUsed,
                    'memory_total': gpu.memoryTotal,
                    'temperature': gpu.temperature,
                    'power_draw': gpu.powerDraw
                })

                # Keep last 100 readings
                if len(self.gpu_history) > 100:
                    self.gpu_history.pop(0)

        except Exception as e:
            logger.debug(f"GPU history update error: {e}")

    def _update_system_history(self):
        """Update system metrics history"""
        try:
            memory = psutil.virtual_memory()
            self.system_history.append({
                'timestamp': datetime.now(),
                'cpu_percent': psutil.cpu_percent(),
                'memory_percent': memory.percent,
                'memory_used': memory.used / (1024**3),  # GB
                'memory_total': memory.total / (1024**3)   # GB
            })

            # Keep last 100 readings
            if len(self.system_history) > 100:
                self.system_history.pop(0)

        except Exception as e:
            logger.debug(f"System history update error: {e}")

    def _update_etas(self):
        """Update ETA calculations for active pairs"""
        now = datetime.now()

        for pair, progress in self.pair_progress.items():
            if progress.status == 'training' and progress.start_time:
                elapsed = now - progress.start_time
                elapsed_seconds = elapsed.total_seconds()

                if progress.current_epoch > 0:
                    avg_epoch_time = elapsed_seconds / progress.current_epoch
                    remaining_epochs = progress.total_epochs - progress.current_epoch
                    eta_seconds = avg_epoch_time * remaining_epochs

                    # Format ETA
                    eta_td = timedelta(seconds=int(eta_seconds))
                    progress.eta = f"{eta_td.seconds // 3600:02d}:{(eta_td.seconds % 3600) // 60:02d}:{eta_td.seconds % 60:02d}"
                else:
                    progress.eta = "--:--:--"

    def update_pair_progress(self, pair: str, status: str, progress: float = 0.0,
                           current_epoch: int = 0, loss: float = 0.0, accuracy: float = 0.0):
        """Update progress for a specific pair"""
        if pair not in self.pair_progress:
            return

        progress_obj = self.pair_progress[pair]
        progress_obj.status = status
        progress_obj.progress = progress
        progress_obj.current_epoch = current_epoch
        progress_obj.current_loss = loss
        progress_obj.last_update = datetime.now()

        if accuracy > progress_obj.best_accuracy:
            progress_obj.best_accuracy = accuracy

        if status == 'training' and progress_obj.start_time is None:
            progress_obj.start_time = datetime.now()

        # Update global metrics
        self._update_global_metrics()

    def _update_global_metrics(self):
        """Update global training metrics"""
        active_pairs = [p for p in self.pair_progress.values() if p.status == 'training']
        if active_pairs:
            # Average metrics across active pairs
            avg_loss = sum(p.current_loss for p in active_pairs) / len(active_pairs)
            avg_accuracy = sum(p.best_accuracy for p in active_pairs) / len(active_pairs)

            self.global_metrics.loss = avg_loss
            self.global_metrics.accuracy = avg_accuracy

            # Estimate current epoch (average across pairs)
            avg_epoch = sum(p.current_epoch for p in active_pairs) / len(active_pairs)
            self.global_metrics.epoch = int(avg_epoch)

    def display_monitor(self):
        """Display the live monitoring interface"""
        if self.display_active:
            return

        self.display_active = True

        try:
            with Live(self.create_display(), refresh_per_second=2, screen=True) as live:
                while self.training_active and self.display_active:
                    live.update(self.create_display())
                    time.sleep(1.0)

        except KeyboardInterrupt:
            self.display_active = False
        except Exception as e:
            logger.error(f"Display error: {e}")
            self.display_active = False

    def get_training_summary(self) -> Dict[str, Any]:
        """Get comprehensive training summary"""
        completed_pairs = sum(1 for p in self.pair_progress.values() if p.status == 'completed')
        error_pairs = sum(1 for p in self.pair_progress.values() if p.status == 'error')
        active_pairs = sum(1 for p in self.pair_progress.values() if p.status == 'training')

        total_time = datetime.now() - self.global_metrics.start_time

        return {
            'total_pairs': len(self.pairs),
            'completed_pairs': completed_pairs,
            'error_pairs': error_pairs,
            'active_pairs': active_pairs,
            'total_time_seconds': total_time.total_seconds(),
            'average_accuracy': self.global_metrics.accuracy,
            'final_loss': self.global_metrics.loss,
            'gpu_available': self.gpu_available,
            'pair_details': {
                pair: {
                    'status': progress.status,
                    'best_accuracy': progress.best_accuracy,
                    'final_loss': progress.current_loss,
                    'epochs_completed': progress.current_epoch,
                    'total_time': (progress.last_update - progress.start_time).total_seconds() if progress.start_time else 0
                }
                for pair, progress in self.pair_progress.items()
            }
        }

    def save_monitoring_data(self, filename: str = None):
        """Save monitoring data to file"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"training_monitor_{timestamp}.json"

        data = {
            'summary': self.get_training_summary(),
            'gpu_history': self.gpu_history,
            'system_history': self.system_history,
            'pair_progress': {
                pair: {
                    'status': progress.status,
                    'progress': progress.progress,
                    'current_epoch': progress.current_epoch,
                    'best_accuracy': progress.best_accuracy,
                    'current_loss': progress.current_loss,
                    'eta': progress.eta,
                    'start_time': progress.start_time.isoformat() if progress.start_time else None,
                    'last_update': progress.last_update.isoformat()
                }
                for pair, progress in self.pair_progress.items()
            }
        }

        with open(filename, 'w') as f:
            json.dump(data, f, indent=2, default=str)

        logger.info(f"Monitoring data saved to {filename}")

# Utility functions for easy integration

def create_training_monitor(pairs: List[str], epochs: int = 50) -> GPUTrainingMonitor:
    """Create and initialize a training monitor"""
    monitor = GPUTrainingMonitor(pairs, epochs)
    monitor.start_monitoring()
    return monitor

def display_training_monitor(monitor: GPUTrainingMonitor):
    """Display the training monitor interface"""
    monitor.display_monitor()

# Example usage
if __name__ == "__main__":
    # Example with 7 pairs
    pairs = ['BTC/USDT', 'ETH/USDT', 'XRP/USDT', 'XLM/USDT', 'HBAR/USDT', 'ALGO/USDT', 'ADA/USDT']
    monitor = create_training_monitor(pairs, epochs=50)

    # Simulate training progress
    import random

    for epoch in range(1, 51):
        for pair in pairs:
            # Simulate training progress
            progress = epoch / 50.0
            loss = 1.0 - (epoch / 50.0) + random.uniform(-0.1, 0.1)
            accuracy = 0.5 + (epoch / 50.0) * 0.4 + random.uniform(-0.05, 0.05)

            monitor.update_pair_progress(
                pair=pair,
                status='training',
                progress=progress,
                current_epoch=epoch,
                loss=max(0, loss),
                accuracy=min(1.0, max(0, accuracy))
            )

        time.sleep(0.5)  # Simulate training time

    # Mark some pairs as completed
    for pair in pairs[:3]:  # First 3 pairs complete
        monitor.update_pair_progress(pair, 'completed', 1.0, 50, 0.1, 0.85)

    # Display the monitor
    display_training_monitor(monitor)

    # Save monitoring data
    monitor.save_monitoring_data()

    monitor.stop_monitoring()