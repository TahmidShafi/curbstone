"""Rule engine: loads, validates, and executes DQA SQL rules in DuckDB."""

from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import duckdb
import pandas as pd
import yaml

REQUIRED_KEYS = {
    "id",
    "version",
    "level",
    "description",
    "rationale",
    "threshold_basis",
    "severity",
    "sql",
}
VALID_LEVELS = {"submission", "enumerator_day"}
VALID_SEVERITIES = {"low", "medium", "high"}


def load_rules(rules_path: Union[str, Path]) -> List[Dict[str, Any]]:
    """Load and validate rules YAML file."""
    path = Path(rules_path)
    if not path.is_file():
        raise FileNotFoundError(f"Rules configuration file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if data is None:
        return []

    if not isinstance(data, list):
        raise ValueError(f"Rules YAML must contain a top-level list, got {type(data).__name__}")

    validate_rules(data)
    return data


def validate_rules(rules: List[Dict[str, Any]]) -> None:
    """Validate rule dictionary schema, mandatory keys, and id uniqueness."""
    seen_ids = set()
    for idx, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise ValueError(f"Rule at index {idx} must be a mapping, got {type(rule).__name__}")

        missing = REQUIRED_KEYS - set(rule.keys())
        if missing:
            rule_id_hint = rule.get("id", f"index_{idx}")
            raise ValueError(f"Rule '{rule_id_hint}' is missing required fields: {sorted(missing)}")

        rule_id = rule["id"]
        if not isinstance(rule_id, str) or not rule_id.strip():
            raise ValueError(f"Rule at index {idx} has invalid or empty id: {rule_id!r}")

        if rule_id in seen_ids:
            raise ValueError(f"Duplicate rule id detected: '{rule_id}'")
        seen_ids.add(rule_id)

        level = rule["level"]
        if level not in VALID_LEVELS:
            raise ValueError(
                f"Rule '{rule_id}' has invalid level '{level}'. Must be one of {sorted(VALID_LEVELS)}"
            )

        severity = rule["severity"]
        if severity not in VALID_SEVERITIES:
            raise ValueError(
                f"Rule '{rule_id}' has invalid severity '{severity}'. Must be one of {sorted(VALID_SEVERITIES)}"
            )

        sql = rule["sql"]
        if not isinstance(sql, str) or not sql.strip():
            raise ValueError(f"Rule '{rule_id}' has empty or invalid SQL statement")


def run_rules(
    submissions: Union[pd.DataFrame, str, Path],
    villages: Union[pd.DataFrame, str, Path],
    rules: Optional[List[Dict[str, Any]]] = None,
    rules_path: Optional[Union[str, Path]] = None,
) -> pd.DataFrame:
    """Execute all validated SQL rules against submissions and villages reference tables in DuckDB.
    
    Returns a unified long DataFrame with columns:
    ['unit_id', 'rule_id', 'value', 'level', 'severity']
    """
    if rules is None:
        if rules_path is None:
            rules_path = Path(__file__).resolve().parent.parent / "rules" / "rules.yaml"
        rules = load_rules(rules_path)
    else:
        validate_rules(rules)

    output_columns = ["unit_id", "rule_id", "value", "level", "severity"]
    if not rules:
        return pd.DataFrame(columns=output_columns)

    # In-memory DuckDB connection
    con = duckdb.connect(":memory:")

    # Register submissions table
    if isinstance(submissions, (str, Path)):
        sub_path = Path(submissions)
        if not sub_path.is_file():
            raise FileNotFoundError(f"Submissions file not found: {sub_path}")
        df_sub = pd.read_parquet(sub_path)
    else:
        df_sub = submissions

    # Guard: every start_time and end_time must end with '+06:00'
    if "start_time" in df_sub.columns:
        bad_start = ~df_sub["start_time"].astype(str).str.endswith("+06:00")
        if bad_start.any():
            raise ValueError(f"Every start_time must end with '+06:00', got: {df_sub.loc[bad_start, 'start_time'].iloc[0]!r}")
    if "end_time" in df_sub.columns:
        bad_end = ~df_sub["end_time"].astype(str).str.endswith("+06:00")
        if bad_end.any():
            raise ValueError(f"Every end_time must end with '+06:00', got: {df_sub.loc[bad_end, 'end_time'].iloc[0]!r}")

    # Canonical local-time derivation using shared rules/submissions_view.sql
    view_sql_path = Path(__file__).resolve().parent.parent / "rules" / "submissions_view.sql"
    if "start_local" in df_sub.columns and "end_local" in df_sub.columns:
        con.register("submissions", df_sub)
    elif "start_time" in df_sub.columns and "end_time" in df_sub.columns:
        con.register("_raw_submissions", df_sub)
        con.sql(view_sql_path.read_text(encoding="utf-8"))
    else:
        con.register("submissions", df_sub)

    # Register villages reference table
    if isinstance(villages, (str, Path)):
        vil_path = Path(villages)
        if not vil_path.is_file():
            raise FileNotFoundError(f"Villages reference file not found: {vil_path}")
        df_vil = pd.read_parquet(vil_path)
    else:
        df_vil = villages
    con.register("villages", df_vil)

    hits_list: List[pd.DataFrame] = []

    for rule in rules:
        rule_id = rule["id"]
        rule_sql = rule["sql"]
        level = rule["level"]
        severity = rule["severity"]

        try:
            res_df = con.sql(rule_sql).df()
        except Exception as e:
            raise RuntimeError(f"Error executing SQL for rule '{rule_id}': {e}") from e

        required_res_cols = {"unit_id", "rule_id", "value"}
        missing_cols = required_res_cols - set(res_df.columns)
        if missing_cols:
            raise ValueError(
                f"Rule '{rule_id}' query must return columns {sorted(required_res_cols)}, missing: {sorted(missing_cols)}"
            )

        if not res_df.empty:
            res_df = res_df[["unit_id", "rule_id", "value"]].copy()
            res_df["level"] = level
            res_df["severity"] = severity
            hits_list.append(res_df)

    if not hits_list:
        return pd.DataFrame(columns=output_columns)

    result_df = pd.concat(hits_list, ignore_index=True)
    return result_df

