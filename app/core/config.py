# app/core/config.py
from pathlib import Path
import yaml

CONFIG_PATH = Path("config.yaml")


def load_config() -> dict:
    """Lataa järjestelmäasetukset config.yaml-tiedostosta."""
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


CONFIG = load_config()

# Polkumääritykset
WORKSPACE_PATH = Path(CONFIG.get("paths", {}).get("workspace", "data/workspace"))
WORKSPACE_PATH.mkdir(parents=True, exist_ok=True)