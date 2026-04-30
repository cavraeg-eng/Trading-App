"""Release validation runner for backend, frontend, smoke, and secret checks."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent


SECRET_PATTERNS = {
    "private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "aws access key": re.compile(r"\b(A3T[A-Z0-9]|AKIA|ASIA)[A-Z0-9]{16}\b"),
    "credential assignment": re.compile(
        r"(?i)\b(api[_-]?key|secret(?:[_-]?key)?|api[_-]?token|access[_-]?token|password)\b"
        r"\s*[:=]\s*[\"']?(?!your_|example|changeme|placeholder|dummy|test_|settings\.|os\.getenv|env\.|$)"
        r"[A-Za-z0-9_./+=:-]{16,}[\"']?"
    ),
}

SECRET_SCAN_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".md",
    ".txt",
    ".env",
    ".example",
}

EXPECTED_IGNORED_PATHS = [
    ".env",
    ".env.local",
    "data/trading_bot.db",
    "logs/release.log",
    "models/model.pt",
    "frontend/dist/index.html",
    "frontend/coverage/lcov.info",
    "playwright-report/index.html",
    "test-results/results.json",
    "release-validation-results.md",
    "oanda_credentials.json",
]


class CheckResult:
    def __init__(self, name: str, ok: bool, detail: str = "") -> None:
        self.name = name
        self.ok = ok
        self.detail = detail


def run_command(name: str, command: list[str], cwd: Path = ROOT) -> CheckResult:
    print(f"\n==> {name}")
    print("$ " + " ".join(command))
    completed = subprocess.run(command, cwd=cwd)
    return CheckResult(name, completed.returncode == 0, f"exit code {completed.returncode}")


def git_files() -> list[Path]:
    completed = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [ROOT / line for line in completed.stdout.splitlines() if line.strip()]


def is_text_candidate(path: Path) -> bool:
    if path.name == "package-lock.json":
        return False
    suffixes = path.suffixes
    if path.suffix in SECRET_SCAN_SUFFIXES:
        return True
    return any(suffix in SECRET_SCAN_SUFFIXES for suffix in suffixes)


def security_check() -> CheckResult:
    print("\n==> Security and artifact hygiene")
    failures: list[str] = []

    tracked_files = git_files()
    tracked_relative_paths = {str(path.relative_to(ROOT)) for path in tracked_files}
    untracked_ignored_source = subprocess.run(
        ["git", "ls-files", "--others", "--ignored", "--exclude-standard", "trading_bot"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    for relative in untracked_ignored_source.stdout.splitlines():
        if Path(relative).suffix in {".py", ".pyi"} and relative not in tracked_relative_paths:
            failures.append(f"Python source under trading_bot is ignored/untracked: {relative}")

    tracked_artifacts = [
        relative
        for path in tracked_files
        for relative in [str(path.relative_to(ROOT))]
        for parts in [Path(relative).parts]
        if path.name == ".env"
        or parts[0] in {"data", "logs", "models"}
        or path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".sqlite", ".db", ".pt"}
    ]
    if tracked_artifacts:
        failures.append("Tracked local artifact(s): " + ", ".join(tracked_artifacts))

    for ignored_path in EXPECTED_IGNORED_PATHS:
        completed = subprocess.run(
            ["git", "check-ignore", "-q", ignored_path],
            cwd=ROOT,
        )
        if completed.returncode != 0:
            failures.append(f"Expected ignored path is not ignored: {ignored_path}")

    for path in tracked_files:
        relative = str(path.relative_to(ROOT))
        if not path.exists() or not path.is_file() or not is_text_candidate(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                failures.append(f"Potential {label} in {relative}")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return CheckResult("Security and artifact hygiene", False, f"{len(failures)} failure(s)")

    print("PASS: no tracked local artifacts, ignore rules cover release outputs, no secret patterns found")
    return CheckResult("Security and artifact hygiene", True)


def smoke_check() -> CheckResult:
    print("\n==> API smoke checks")
    try:
        from fastapi.testclient import TestClient

        import trading_bot.api.server as api_server

        endpoints = [
            ("GET", "/api/health", {200}),
            ("GET", "/api/settings", {200}),
            ("GET", "/api/broker/list", {200}),
            ("GET", "/api/broker/active", {200}),
        ]
        with tempfile.TemporaryDirectory(prefix="release-smoke-") as temp_dir:
            db_path = Path(temp_dir) / "trading_bot.db"
            previous_db_path = os.environ.get("TRADING_BOT_DB_PATH")
            try:
                os.environ["TRADING_BOT_DB_PATH"] = str(db_path)
                if api_server.get_api_db_path() != db_path:
                    return CheckResult("API smoke checks", False, "TRADING_BOT_DB_PATH override failed")
                with TestClient(api_server.app) as client:
                    failures = []
                    for method, path, expected_statuses in endpoints:
                        response = client.request(method, path)
                        if response.status_code not in expected_statuses:
                            failures.append(f"{method} {path} returned {response.status_code}")
                        else:
                            print(f"PASS: {method} {path} -> {response.status_code}")
            finally:
                if previous_db_path is None:
                    os.environ.pop("TRADING_BOT_DB_PATH", None)
                else:
                    os.environ["TRADING_BOT_DB_PATH"] = previous_db_path
        if failures:
            for failure in failures:
                print(f"FAIL: {failure}")
            return CheckResult("API smoke checks", False, f"{len(failures)} failure(s)")
        return CheckResult("API smoke checks", True)
    except Exception as exc:
        print(f"FAIL: smoke checks could not run: {exc}")
        return CheckResult("API smoke checks", False, str(exc))


def backend_check(full: bool) -> CheckResult:
    targets = ["trading_bot/tests"]
    if not full:
        targets = [
            "trading_bot/tests/test_trade_ledger.py",
            "trading_bot/tests/test_broker_manager.py",
            "trading_bot/tests/test_oanda_broker.py",
            "trading_bot/tests/test_automation_safety.py",
        ]
    return run_command("Backend tests", [sys.executable, "-m", "pytest", *targets])


def frontend_check() -> CheckResult:
    frontend_dir = ROOT / "frontend"
    if not (frontend_dir / "node_modules").exists():
        return CheckResult(
            "Frontend build",
            False,
            "frontend/node_modules is missing; run `cd frontend && npm ci` first",
        )
    return run_command("Frontend build", ["npm", "run", "build"], cwd=frontend_dir)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run release validation checks.")
    parser.add_argument("--backend", action="store_true", help="Run backend pytest checks.")
    parser.add_argument("--frontend", action="store_true", help="Run frontend build checks.")
    parser.add_argument("--security", action="store_true", help="Run secret and artifact hygiene checks.")
    parser.add_argument("--smoke", action="store_true", help="Run read-only API smoke checks.")
    parser.add_argument("--full-backend", action="store_true", help="Run the full backend test suite.")
    return parser.parse_args()


def main() -> int:
    os.environ.setdefault("TRADING_MODE", "paper")
    args = parse_args()
    selected = args.backend or args.full_backend or args.frontend or args.security or args.smoke

    results: list[CheckResult] = []
    if args.security or not selected:
        results.append(security_check())
    if args.backend or args.full_backend or not selected:
        results.append(backend_check(args.full_backend))
    if args.frontend or not selected:
        results.append(frontend_check())
    if args.smoke or not selected:
        results.append(smoke_check())

    print("\n==> Release validation summary")
    for result in results:
        status = "PASS" if result.ok else "FAIL"
        detail = f" ({result.detail})" if result.detail else ""
        print(f"{status}: {result.name}{detail}")

    return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())