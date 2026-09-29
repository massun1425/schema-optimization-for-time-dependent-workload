#!/usr/bin/env python3
"""
PostgreSQL Executor - Docker/Local switching helper

Switchable via the environment variable MV_USE_DOCKER=true/false or the --use-docker/--use-local flags
"""

import os
import subprocess
from typing import Optional


class PostgresExecutor:
    """Wrapper class for executing PostgreSQL commands.
    
    Uses either Docker or a local psql.
    
    Usage:
        executor = PostgresExecutor(use_docker=True)
        result = executor.run_psql_command("SELECT 1;", database="imdbload")
    """
    
    def __init__(
        self, 
        use_docker: Optional[bool] = None, 
        container_name: str = "mv_postgres",
        default_user: str = "postgres",
        default_password: str = ""
    ):
        """Initialize.
        
        Args:
            use_docker: Whether to use Docker. If None, the environment variable is consulted
            container_name: Docker container name
            default_user: Default PostgreSQL user
            default_password: Default password
        """
        if use_docker is None:
            # Read from the environment variable (default True = use Docker)
            env_value = os.environ.get("MV_USE_DOCKER", "true").lower()
            self.use_docker = env_value in ("true", "1", "yes")
        else:
            self.use_docker = use_docker
        
        self.container_name = container_name
        self.default_user = default_user
        self.default_password = default_password
    
    def _build_psql_command(
        self,
        database: str,
        user: Optional[str] = None,
        extra_args: Optional[list] = None
    ) -> list:
        """Build the psql command.
        
        Args:
            database: Database name
            user: User name (default_user if omitted)
            extra_args: List of additional arguments
            
        Returns:
            List of command arguments
        """
        user = user or self.default_user
        extra_args = extra_args or []
        
        if self.use_docker:
            cmd = [
                "docker", "exec", "-i", self.container_name,
                "psql", "-U", user, "-d", database
            ] + extra_args
        else:
            cmd = ["psql", "-U", user, "-d", database] + extra_args
        
        return cmd
    
    def run_psql_command(
        self,
        sql: str,
        database: str,
        user: Optional[str] = None,
        capture_output: bool = True,
        check: bool = True,
        extra_args: Optional[list] = None,
        env: Optional[dict] = None
    ) -> subprocess.CompletedProcess:
        """Execute an SQL command.
        
        Args:
            sql: SQL statement to execute
            database: Database name
            user: User name
            capture_output: Whether to capture the output
            check: Whether to raise an exception on error
            extra_args: Additional psql arguments
            env: Environment variables (PGPASSWORD is set if omitted)
            
        Returns:
            subprocess.CompletedProcess
        """
        cmd = self._build_psql_command(database, user, extra_args)
        cmd.extend(["-c", sql])
        
        # Set environment variables (PGPASSWORD is needed only for local execution)
        if env is None:
            env = {**os.environ}
            if not self.use_docker:
                env["PGPASSWORD"] = self.default_password
        
        return subprocess.run(
            cmd,
            capture_output=capture_output,
            text=True,
            check=check,
            encoding='utf-8',
            errors='replace',
            env=env
        )
    
    def run_psql_commands(
        self,
        sql_commands: list,
        database: str,
        user: Optional[str] = None,
        capture_output: bool = True,
        check: bool = True,
        extra_args: Optional[list] = None
    ) -> subprocess.CompletedProcess:
        """Execute multiple SQL commands sequentially.
        
        Args:
            sql_commands: List of SQL statements to execute
            database: Database name
            user: User name
            capture_output: Whether to capture the output
            check: Whether to raise an exception on error
            extra_args: Additional psql arguments
            
        Returns:
            subprocess.CompletedProcess (result of the last command)
        """
        base_extra_args = extra_args or []
        cmd = self._build_psql_command(database, user, base_extra_args)
        
        # Add each SQL command with the -c option
        for sql in sql_commands:
            cmd.extend(["-c", sql])
        
        env = {**os.environ}
        if not self.use_docker:
            env["PGPASSWORD"] = self.default_password
        
        return subprocess.run(
            cmd,
            capture_output=capture_output,
            text=True,
            check=check,
            encoding='utf-8',
            errors='replace',
            env=env
        )
    
    def run_explain_json(
        self,
        query_sql: str,
        database: str,
        user: Optional[str] = None,
        set_options: Optional[list] = None
    ) -> subprocess.CompletedProcess:
        """Execute EXPLAIN JSON.
        
        Args:
            query_sql: SQL whose query plan is retrieved
            database: Database name
            user: User name
            set_options: List of SET statements to execute beforehand
            
        Returns:
            subprocess.CompletedProcess
        """
        explain_sql = f"EXPLAIN (FORMAT JSON, COSTS TRUE, VERBOSE FALSE) {query_sql}"
        
        sql_commands = []
        if set_options:
            sql_commands.extend(set_options)
        sql_commands.append(explain_sql)
        
        return self.run_psql_commands(
            sql_commands,
            database,
            user,
            extra_args=["-t", "-A"]
        )
    
    def get_mode_description(self) -> str:
        """Get a description of the current mode"""
        if self.use_docker:
            return f"Docker ({self.container_name})"
        else:
            return "Local psql"


def get_executor_from_args(args) -> PostgresExecutor:
    """Create an Executor from argparse arguments.
    
    Args:
        args: argparse.Namespace object (with a use_docker attribute)
        
    Returns:
        PostgresExecutor
    """
    use_docker = getattr(args, 'use_docker', None)
    return PostgresExecutor(use_docker=use_docker)


def add_docker_args(parser):
    """Add Docker-related arguments to an argparser.
    
    Args:
        parser: argparse.ArgumentParser
    """
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        '--use-docker',
        action='store_true',
        dest='use_docker',
        default=None,
        help='Run psql via Docker (default; can be changed with the MV_USE_DOCKER environment variable)'
    )
    group.add_argument(
        '--use-local',
        action='store_false',
        dest='use_docker',
        help='Use the local psql'
    )
