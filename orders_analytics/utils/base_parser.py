from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from orders_analytics.utils.errors import reconcile_errors
from orders_analytics.utils.schema import canonicalize_rows, write_normalized_rows
from orders_analytics.utils.validation import (
    normalize_order_type,
    normalize_payment_type,
    validate_enum_fields,
    validate_delivery_fee,
    validate_required_fields,
    validate_tax_fields,
    validate_test_customer_names,
    validate_negative_fees,
    validate_order_datetime_iso,
)
from orders_analytics.utils.constants import ERRORS_PATH


@dataclass
class ParseStats:
    total_inputs: int = 0
    rows_parsed: int = 0
    rows_written: int = 0
    duplicates_removed: int = 0
    conflicts: List[Dict[str, object]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[Dict[str, str]] = field(default_factory=list)


class BaseParser:
    platform: str = ""
    provider: str = ""
    dedupe_key: str = "order_id"

    def __init__(
        self,
        input_path: Optional[str] = None,
        out_path: Optional[str] = None,
        **kwargs,
    ):
        self.input_path = input_path
        self.out_path = out_path
        self.stats = ParseStats()
        self.extra = kwargs

    def default_input_path(self) -> str:
        raise NotImplementedError

    def default_out_path(self) -> str:
        raise NotImplementedError

    def resolve_paths(self) -> Tuple[str, str]:
        input_path = self.input_path or self.default_input_path()
        out_path = self.out_path or self.default_out_path()
        return input_path, out_path

    def load_inputs(self, input_path: str):
        return input_path

    def parse_rows(self, inputs) -> List[Dict[str, str]]:
        raise NotImplementedError

    def pre_process(self, rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
        return rows

    def post_process(self, rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
        # Normalize "nan"/None-like values to empty strings for consistency.
        for row in rows:
            row["order_type"] = normalize_order_type(str(row.get("order_type") or ""))
            row["payment_type"] = normalize_payment_type(str(row.get("payment_type") or ""))
            if "customer_name" in row:
                row["customer_name"] = str(row.get("customer_name") or "").strip().title()
            for key, value in list(row.items()):
                if value is None:
                    row[key] = ""
                    continue
                if isinstance(value, float) and str(value).lower() == "nan":
                    row[key] = ""
                    continue
                if isinstance(value, str) and value.strip().lower() == "nan":
                    row[key] = ""
        for validator in (
            validate_required_fields,
            validate_enum_fields,
            validate_delivery_fee,
            validate_tax_fields,
            validate_test_customer_names,
            validate_negative_fees,
            validate_order_datetime_iso,
        ):
            rows, errors = validator(rows, source=self.resolve_paths()[1])
            if errors:
                self.stats.errors.extend(errors)
        return rows

    def validate(self, rows: List[Dict[str, str]]) -> List[str]:
        return []

    def drop_null_keys(self, rows: List[Dict[str, str]], key: str) -> List[Dict[str, str]]:
        filtered = []
        for row in rows:
            value = str(row.get(key) or "").strip()
            if value:
                filtered.append(row)
        return filtered

    def dedupe_rows(
        self, rows: List[Dict[str, str]], key_field: str
    ) -> Tuple[List[Dict[str, str]], List[Dict[str, Dict[str, str]]], int]:
        seen: Dict[str, Dict[str, str]] = {}
        conflicts_map: Dict[str, Dict[str, Dict[str, str]]] = {}
        duplicates_removed = 0
        for row in rows:
            key = str(row.get(key_field) or "").strip()
            if not key:
                seen_key = f"__missing__{len(seen)}"
                seen[seen_key] = row
                continue
            if key not in seen:
                seen[key] = row
                continue
            duplicates_removed += 1
            existing = seen[key]
            for field in set(existing.keys()).union(row.keys()):
                old = existing.get(field, "")
                new = row.get(field, "")
                if not old and new:
                    existing[field] = new
                    continue
                if old and new and old != new:
                    if key not in conflicts_map:
                        conflicts_map[key] = {}
                    if field not in conflicts_map[key]:
                        conflicts_map[key][field] = {"first": old, "other": new}
        conflicts = [
            {"order_id": key, "diffs": [{"field": f, **vals} for f, vals in fields.items()]}
            for key, fields in conflicts_map.items()
        ]
        return list(seen.values()), conflicts, duplicates_removed

    def run(self) -> ParseStats:
        """Standard parser flow: load → parse → pre/post → drop null ids → dedupe → validate → write."""
        input_path, out_path = self.resolve_paths()
        inputs = self.load_inputs(input_path)
        rows = self.parse_rows(inputs)
        self.stats.rows_parsed = len(rows)
        rows = self.pre_process(rows)
        rows = self.post_process(rows)
        rows = self.drop_null_keys(rows, self.dedupe_key)
        rows, conflicts, duplicates_removed = self.dedupe_rows(rows, self.dedupe_key)
        self.stats.conflicts = conflicts
        self.stats.duplicates_removed = duplicates_removed
        self.stats.warnings.extend(self.validate(rows))
        rows = canonicalize_rows(rows)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        write_normalized_rows(rows, out_path)
        reconcile_errors(self.stats.errors, ERRORS_PATH)
        self.stats.rows_written = len(rows)
        return self.stats
