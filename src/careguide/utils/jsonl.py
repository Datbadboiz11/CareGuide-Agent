from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

SchemaT = TypeVar("SchemaT", bound=BaseModel)


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:

    jsonl_path = Path(path)
    rows: list[dict[str, Any]] = []

    with jsonl_path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{jsonl_path}:{line_number}: invalid JSON: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{jsonl_path}:{line_number}: expected a JSON object")
            rows.append(row)

    return rows


def load_jsonl_as(path: str | Path, schema: type[SchemaT]) -> list[SchemaT]:

    jsonl_path = Path(path)
    items: list[SchemaT] = []

    for line_number, row in enumerate(read_jsonl(jsonl_path), start=1):
        try:
            items.append(schema.model_validate(row))
        except ValidationError as exc:
            raise ValueError(f"{jsonl_path}:{line_number}: schema validation failed\n{exc}") from exc

    return items
