from __future__ import annotations

import time

from .engine import Engine


def make_server(config):
    from fastmcp import FastMCP

    engine = Engine(config)
    server = FastMCP("general-agent-benchmarks")

    @server.tool()
    def list_benchmarks() -> list[dict]:
        """List configured benchmark catalogs and whether their task indices are installed."""
        return engine.catalog()

    @server.tool()
    def list_tasks(
        benchmark: str, query: str = "", variant: str | None = None, offset: int = 0, limit: int = 20
    ) -> dict:
        """Search task IDs and tags; paginate without exposing answers or rubrics."""
        return engine.list_tasks(benchmark, query, variant, offset, limit)

    @server.tool()
    def get_task(benchmark: str, task_id: str, variant: str | None = None) -> dict:
        """Read the public problem, artifact requirements and missing setup items."""
        return engine.get_task(benchmark, task_id, variant)

    @server.tool()
    def start_run(benchmark: str, task_id: str, variant: str | None = None) -> dict:
        """Prepare a fresh attempt using only the selected task's public files."""
        return engine.start(benchmark, task_id, variant)

    @server.tool()
    def read_file(run_id: str, path: str = ".", offset: int = 0, limit: int = 16000) -> dict:
        """Read a UTF-8 file or list a directory inside this run's workspace."""
        return engine.read_file(run_id, path, offset, limit)

    @server.tool()
    def write_file(run_id: str, path: str, content: str) -> dict:
        """Write a text artifact relative to /workspace; paths cannot escape the run."""
        return engine.write_file(run_id, path, content)

    @server.tool()
    def execute_python(run_id: str, code: str, timeout: int = 60) -> dict:
        """Run Python in the task's network-disabled Docker sandbox; files persist in /workspace."""
        return engine.execute(run_id, code, timeout)

    @server.tool()
    def submit_run(run_id: str) -> dict:
        """Freeze the submission and automatically start its official evaluator. Poll run_status for feedback."""
        return engine.submit(run_id)

    @server.tool()
    def run_status(run_id: str, wait_seconds: int = 0) -> dict:
        """Get progress or feedback. Optionally wait up to 30 seconds for an evaluation result."""
        deadline = time.monotonic() + max(0, min(wait_seconds, 30))
        while True:
            result = engine.status(run_id)
            if result["status"] not in {"submitted", "evaluating"} or time.monotonic() >= deadline:
                return result
            time.sleep(0.5)

    return server


def serve(config):
    make_server(config).run(transport="stdio")
