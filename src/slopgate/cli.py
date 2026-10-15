"""SlopGate CLI interface."""

from __future__ import annotations

import argparse
import os
import platform
import sys
from importlib.metadata import PackageNotFoundError, version

from slopgate.config import get_settings


def check_version(pkg_name: str) -> str:
    """Return version string or NOT INSTALLED."""
    try:
        return version(pkg_name)
    except PackageNotFoundError:
        return "NOT INSTALLED"


def run_doctor() -> int:
    """Execute the doctor command to verify environment integrity."""
    settings = get_settings()
    python_exe = sys.executable
    is_venv = ".venv" in python_exe or hasattr(sys, "real_prefix") or (
        hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
    )

    print("=" * 60)
    print("  SlopGate Doctor — System & Environment Check")
    print("=" * 60)

    # 1. Python & Venv
    print("\n[Python Environment]")
    print(f"  Python Version:     {platform.python_version()}")
    print(f"  Executable Path:    {python_exe}")
    print(f"  Virtual Env Active: {'YES (Isolated)' if is_venv else 'NO (Warning: Global Python!)'}")

    # 2. System Hardware
    print("\n[Hardware Profile]")
    print(f"  OS Platform:        {platform.system()} {platform.release()} ({platform.machine()})")
    print(f"  Logical CPU Cores:  {os.cpu_count() or 'Unknown'}")
    print(f"  Configured Threads: {settings.decider_threads}")

    # 3. Environment Variables & Credentials (SAFE: values never leaked)
    print("\n[Configuration & Credentials]")
    for key, status in settings.doctor_summary().items():
        print(f"  {key:<28} {status}")

    # 4. Critical Dependencies
    print("\n[Dependency Status]")
    packages = [
        "torch",
        "strands-decider",
        "boto3",
        "pydantic",
        "pyyaml",
        "httpx",
        "scikit-learn",
        "rank-bm25",
        "pytest",
    ]
    for pkg in packages:
        status = check_version(pkg)
        indicator = "OK" if status != "NOT INSTALLED" else "MISSING"
        print(f"  {pkg:<20} {status:<18} [{indicator}]")

    print("\n" + "=" * 60)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        prog="slopgate",
        description="SlopGate: Local, confidence-gated issue and PR triage."
    )
    subparsers = parser.add_subparsers(dest="command", help="Sub-commands")

    # doctor command
    doctor_parser = subparsers.add_parser("doctor", help="Inspect environment, dependencies, and settings")

    # placeholder commands for later phases
    subparsers.add_parser("ingest", help="Ingest issues/PRs from GitHub or saved replay")
    subparsers.add_parser("run", help="Run background triage worker")
    subparsers.add_parser("review", help="Review and approve pending actions")
    subparsers.add_parser("backtest", help="Run offline calibration backtest")
    subparsers.add_parser("report", help="Generate receipts and calibration report")
    subparsers.add_parser("serve", help="Run local REST API server for Next.js dashboard")
    subparsers.add_parser("demo", help="Run end-to-end dry-run demo showcase")

    args = parser.parse_args(argv)

    if args.command == "doctor" or args.command is None:
        return run_doctor()

    print(f"Command '{args.command}' will be available in its respective implementation phase.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
