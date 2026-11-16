"""Platform experiment adapters: Google Ads ExperimentService, Meta adstudies, PostHog, and Tier 0 CSV."""

from __future__ import annotations

import pathlib
from typing import Any

from calculators import validate_json_schema


def build_platform_experiment_payload(
    experiment: dict[str, Any],
    schema_path: pathlib.Path | None = None,
) -> dict[str, Any]:
    """Translate validated experiment.schema.json contract into safe dry-run/PAUSED platform payload."""
    if schema_path is not None:
        import json

        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
        errs = validate_json_schema(experiment, schema, schema_path.parent)
        if errs:
            raise ValueError("Invalid experiment contract: " + "; ".join(errs))

    mode = experiment["platform_execution_mode"]
    exp_id = experiment["experiment_id"]

    if mode == "google_ads_validate_only":
        return {
            "platform": "google_ads",
            "service": "ExperimentService.MutateExperiments",
            "validate_only": True,
            "experiment": {
                "name": exp_id,
                "type": "SEARCH_CUSTOM",
                "status": "SETUP",
                "description": experiment["hypothesis"],
                "arms": [
                    {"control": True, "traffic_split_percent": 50},
                    {"control": False, "traffic_split_percent": 50},
                ],
            },
            "disproof_condition": experiment["disproof_condition"],
        }

    if mode == "meta_paused_study":
        return {
            "platform": "meta_ads",
            "endpoint": "adstudies",
            "status": "PAUSED",
            "study": {
                "name": exp_id,
                "type": "SPLIT_TEST",
                "description": experiment["hypothesis"],
                "cells": [
                    {"name": "control", "treatment_percentage": 50, "adset_status": "PAUSED"},
                    {"name": "variant", "treatment_percentage": 50, "adset_status": "PAUSED"},
                ],
            },
            "disproof_condition": experiment["disproof_condition"],
        }

    if mode == "posthog_flag":
        return {
            "platform": "posthog",
            "resource": "feature_flag_experiment",
            "active": False,
            "key": exp_id,
            "multivariate": {
                "variants": [
                    {"key": "control", "rollout_percentage": 50},
                    {"key": "test", "rollout_percentage": 50},
                ]
            },
            "disproof_condition": experiment["disproof_condition"],
        }

    return {
        "platform": mode,
        "manual_checklist": True,
        "experiment_id": exp_id,
        "min_runtime_days": experiment["min_runtime_days"],
        "target_sample_size": experiment["target_sample_size"],
        "disproof_condition": experiment["disproof_condition"],
    }
