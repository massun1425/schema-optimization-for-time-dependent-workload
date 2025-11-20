"""
Experiment Runner Component

Manages the execution of optimization experiments.
"""

import streamlit as st
import subprocess
import threading
import queue
import time
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Callable
import sys

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


class ExperimentRunner:
    """Manages experiment execution and progress tracking"""
    
    def __init__(self):
        self.is_running = False
        self.current_phase = None
        self.current_algorithm = None
        self.progress = 0.0
        self.log_queue = queue.Queue()
        self.process = None
        self.thread = None
        
    def run_experiment(
        self,
        algorithms: List[str],
        storage_limit_mb: int,
        phases: Dict[str, bool],
        settings: Dict,
        on_progress: Optional[Callable] = None,
        on_complete: Optional[Callable] = None,
        on_error: Optional[Callable] = None
    ):
        """Run experiment in background thread
        
        Args:
            algorithms: List of algorithm names to run
            storage_limit_mb: Storage limit in MB
            phases: Dictionary of phase names to boolean (enabled/disabled)
            settings: Additional settings dictionary
            on_progress: Callback for progress updates
            on_complete: Callback for completion
            on_error: Callback for errors
        """
        if self.is_running:
            raise RuntimeError("Experiment is already running")
        
        self.is_running = True
        self.progress = 0.0
        
        # Start background thread
        self.thread = threading.Thread(
            target=self._run_experiment_thread,
            args=(algorithms, storage_limit_mb, phases, settings, on_progress, on_complete, on_error),
            daemon=True
        )
        self.thread.start()
        
    def _run_experiment_thread(
        self,
        algorithms: List[str],
        storage_limit_mb: int,
        phases: Dict[str, bool],
        settings: Dict,
        on_progress: Optional[Callable],
        on_complete: Optional[Callable],
        on_error: Optional[Callable]
    ):
        """Background thread for running experiment"""
        try:
            # Build command
            cmd = self._build_command(algorithms, storage_limit_mb, phases, settings)
            
            self.log_queue.put(f"[INFO] Starting experiment...\n")
            self.log_queue.put(f"[INFO] Algorithms: {', '.join(algorithms)}\n")
            self.log_queue.put(f"[INFO] Storage limit: {storage_limit_mb} MB\n")
            self.log_queue.put(f"[INFO] Enabled phases: {', '.join([k for k, v in phases.items() if v])}\n")
            self.log_queue.put(f"[DEBUG] Command: {' '.join(cmd)}\n")
            
            # Run subprocess
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=str(project_root)
            )
            
            # Stream output
            for line in iter(self.process.stdout.readline, ''):
                if line:
                    self.log_queue.put(line)
                    self._parse_progress(line)
                    if on_progress:
                        on_progress(self.progress, self.current_phase, self.current_algorithm)
            
            # Wait for completion
            return_code = self.process.wait()
            
            if return_code == 0:
                self.log_queue.put("[INFO] Experiment completed successfully\n")
                if on_complete:
                    on_complete()
            else:
                error_msg = f"Experiment failed with return code {return_code}"
                self.log_queue.put(f"[ERROR] {error_msg}\n")
                if on_error:
                    on_error(error_msg)
                    
        except Exception as e:
            error_msg = f"Exception during experiment: {str(e)}"
            self.log_queue.put(f"[ERROR] {error_msg}\n")
            if on_error:
                on_error(error_msg)
        finally:
            self.is_running = False
            self.process = None
            
    def _build_command(
        self,
        algorithms: List[str],
        storage_limit_mb: int,
        phases: Dict[str, bool],
        settings: Dict
    ) -> List[str]:
        """Build command line arguments for run_experiment.py"""
        cmd = [
            sys.executable,
            str(project_root / "scripts" / "run_experiment.py"),
            "--algorithms"
        ] + algorithms
        
        # Add enabled phases using --phases flag
        enabled_phases = [phase_name for phase_name, enabled in phases.items() if enabled]
        if enabled_phases:
            cmd.append("--phases")
            cmd.extend(enabled_phases)
        
        # Add other settings
        if settings.get('output_dir'):
            cmd.extend(["--output", settings['output_dir']])
            
        if settings.get('verbose'):
            cmd.append("--verbose")
            
        return cmd
    
    def _parse_progress(self, line: str):
        """Parse log line to extract progress information"""
        # Parse algorithm
        if "Running ILP:" in line:
            self.current_algorithm = line.split("Running ILP:")[1].strip()
            
        # Parse phase
        phase_markers = {
            "Parsing queries": "query_parsing",
            "Running ILP optimization": "optimization",
            "Generating SQL": "sql_generation",
            "Creating MVs": "mv_creation",
            "Rewriting queries": "query_rewriting",
            "Running benchmark": "benchmark"
        }
        
        for marker, phase in phase_markers.items():
            if marker in line:
                self.current_phase = phase
                break
        
        # Parse progress percentage if available
        if "%" in line:
            try:
                # Extract percentage
                parts = line.split("%")
                for part in parts[:-1]:
                    tokens = part.split()
                    if tokens:
                        pct = float(tokens[-1])
                        self.progress = pct
                        break
            except (ValueError, IndexError):
                pass
                
    def stop_experiment(self):
        """Stop running experiment"""
        if self.process:
            self.process.terminate()
            self.log_queue.put("[INFO] Experiment stopped by user\n")
            self.is_running = False
            
    def get_logs(self, max_lines: int = 100) -> List[str]:
        """Get recent log lines
        
        Args:
            max_lines: Maximum number of lines to return
            
        Returns:
            List of log lines
        """
        logs = []
        try:
            while not self.log_queue.empty() and len(logs) < max_lines:
                try:
                    logs.append(self.log_queue.get_nowait())
                except queue.Empty:
                    break
        except Exception as e:
            logs.append(f"[ERROR] Failed to get logs: {str(e)}\n")
        return logs
    
    def get_status(self) -> Dict:
        """Get current experiment status
        
        Returns:
            Dictionary with status information
        """
        return {
            'is_running': self.is_running,
            'current_phase': self.current_phase,
            'current_algorithm': self.current_algorithm,
            'progress': self.progress
        }
