from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from dsse.config import AppConfig, MODEL_DIR, save_config, try_load_config
from dsse.db import DatabaseManager
from dsse.scenario_loader import list_cases

console = Console()

MODEL_CATALOG = {
    "mistral-small": "mistralai/Mistral-Small-3.1-24B-Instruct-2503",
    "qwen-2.5": "Qwen/Qwen2.5-7B-Instruct",
    "llama-3.3": "meta-llama/Llama-3.3-70B-Instruct",
    "none": None,
}


def _prompt_index(prompt: str, size: int) -> int:
    while True:
        choice = typer.prompt(prompt, type=int)
        if 1 <= choice <= size:
            return choice - 1
        console.print(f"Select a number between 1 and {size}.")


def choose_model_interactively() -> tuple[str, str | None]:
    console.print("Choose AI model\n")
    options = [
        ("mistral-small", "Mistral Small 3.1", "Best balance for extraction, reasoning, and drafting"),
        ("qwen-2.5", "Qwen 2.5 7B", "Faster and lighter"),
        ("llama-3.3", "Llama 3.3 70B", "Stronger but heavier"),
        ("none", "Deterministic only", "No AI drafting or extraction"),
    ]
    for idx, (_, label, desc) in enumerate(options, start=1):
        console.print(f"{idx}) {label}\n   {desc}")
    key, _, _ = options[_prompt_index("Select", len(options))]
    return key, MODEL_CATALOG[key]


def download_model(model_key: str, hf_repo: str | None) -> str:
    target = MODEL_DIR / model_key
    target.mkdir(parents=True, exist_ok=True)
    manifest = target / "manifest.txt"
    if manifest.exists():
        return str(target)
    if hf_repo is None:
        manifest.write_text("deterministic mode\n", encoding="utf-8")
        return str(target)
    try:
        from huggingface_hub import snapshot_download

        snapshot_download(repo_id=hf_repo, local_dir=target, local_dir_use_symlinks=False, allow_patterns=["*.json", "*.md", "tokenizer*", "*.txt"])
        manifest.write_text(f"downloaded from {hf_repo}\n", encoding="utf-8")
    except Exception:
        manifest.write_text(f"placeholder for {hf_repo}\n", encoding="utf-8")
    return str(target)


def _bundled_sample_case_available() -> bool:
    return "strategic-multi-lane-deadlock" in list_cases()


def _render_pgvector_fallback(message: str) -> None:
    console.print(message)
    console.print(
        "pgvector will be disabled for now. DSSE setup will continue in PostgreSQL-only mode.\n"
        "To enable semantic vectors later, install the pgvector extension on the PostgreSQL server and rerun setup."
    )


def run_interactive_setup(seed_case: bool = True) -> AppConfig:
    cfg, cfg_error = try_load_config()
    if cfg_error:
        console.print(f"Ignoring broken local config and starting clean setup.\n{cfg_error}\n")

    model_key, hf_repo = choose_model_interactively()
    console.print(f"\nSelected model\n{model_key}\n")
    model_dir = download_model(model_key, hf_repo)
    console.print(f"Model ready at {model_dir}\n")

    dsn = typer.prompt("Enter PostgreSQL connection string", default=cfg.postgres_dsn or "postgresql://user:password@localhost:5432/dsse")
    db = DatabaseManager(dsn)
    dsn_check = db.validate_dsn()
    if not dsn_check.ok:
        raise typer.BadParameter(dsn_check.message)

    console.print("Checking database connection...")
    connection_check = db.test_connection()
    console.print(connection_check.message)
    if not connection_check.ok:
        raise typer.Exit(code=1)

    console.print("Running schema migrations...")
    schema_check = db.ensure_schema()
    console.print(schema_check.message)
    if not schema_check.ok:
        raise typer.Exit(code=1)

    use_pgvector = typer.confirm("Enable pgvector semantic layer?", default=False)
    if use_pgvector:
        vector_check = db.ensure_pgvector()
        if vector_check.ok:
            console.print(vector_check.message)
        else:
            _render_pgvector_fallback(vector_check.message)
            use_pgvector = False

    expose_sample_case = typer.confirm("Expose bundled sample case in this setup?", default=seed_case)
    case_seeded = expose_sample_case and _bundled_sample_case_available()
    if expose_sample_case and not case_seeded:
        console.print("Bundled sample case was requested but is not available in this installation.")

    cfg.model_name = model_key
    cfg.model_source = hf_repo
    cfg.postgres_dsn = dsn
    cfg.use_pgvector = use_pgvector
    cfg.case_seeded = case_seeded
    save_config(cfg)
    return cfg
