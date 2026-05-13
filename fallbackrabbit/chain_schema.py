"""Chain schema — load and validate chain/outage YAML/JSON configs."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from .models import Chain, SimulatedOutage


def load_chain(path: str | Path) -> Chain:
    """Load and validate a chain config from YAML or JSON.

    Args:
        path: Path to the chain config file.

    Returns:
        A validated Chain instance.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        ValueError: If the file content fails validation.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Chain config not found: {path}")

    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)

    if data is None:
        raise ValueError(f"Empty config file: {path}")

    try:
        return Chain.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"Invalid chain config in {path}:\n{exc}") from exc


def load_outage_scenario(path: str | Path) -> list[SimulatedOutage]:
    """Load and validate an outage scenario from YAML or JSON.

    Args:
        path: Path to the outage config file.

    Returns:
        A list of validated SimulatedOutage instances.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        ValueError: If the file content fails validation.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Outage config not found: {path}")

    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)

    if data is None:
        raise ValueError(f"Empty config file: {path}")

    outages_raw = data.get("outages", data)
    if not isinstance(outages_raw, list):
        raise ValueError(f"Expected 'outages' list in {path}, got {type(outages_raw).__name__}")

    try:
        return [SimulatedOutage.model_validate(item) for item in outages_raw]
    except ValidationError as exc:
        raise ValueError(f"Invalid outage config in {path}:\n{exc}") from exc
