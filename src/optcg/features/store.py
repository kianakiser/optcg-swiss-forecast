"""Try feature storage with checked tournament CSVs, then compare the saved rows.

This small example goes into match_features_smoke, separate from future training
data. Supply all input history together. Historical result availability is still
unverified, even when a tournament is confirmed as completed today.
"""

import argparse
from getpass import getpass
import os
from pathlib import Path
import sys

import pandas as pd

from compute import compute_features
from prepare import read_matches


KEYS = ["tournament_id", "phase", "round", "table"]


def feature_frame(inputs):
    return prepare_frame(read_matches(inputs))


def prepare_frame(matches):
    frame = pd.DataFrame(compute_features(matches))
    # Midnight marks the date cutoff used for features, not publication time.
    frame["feature_date"] = pd.to_datetime(frame["date"], utc=True).astype("datetime64[us, UTC]")
    return frame


def verify_saved(expected, saved):
    if saved.duplicated(KEYS).any():
        raise ValueError("Hopsworks returned duplicate match keys")
    expected = expected.set_index(KEYS).sort_index()
    saved = saved.set_index(KEYS).sort_index().loc[:, expected.columns]
    saved["feature_date"] = pd.to_datetime(saved["feature_date"], utc=True)
    pd.testing.assert_frame_equal(expected, saved, check_dtype=False, rtol=1e-12, atol=1e-12)


def connect():
    key = os.environ.get("HOPSWORKS_API_KEY")
    if not key:
        if not sys.stdin.isatty():
            raise ValueError("Set HOPSWORKS_API_KEY for a non-interactive run")
        key = getpass("Hopsworks API key (hidden): ")
    if not key.strip():
        raise ValueError("A Hopsworks API key is required")

    import hopsworks

    return hopsworks.login(
        host="eu-west.cloud.hopsworks.ai",
        project="optcg_matchups",
        api_key_value=key,
        engine="python",
        hostname_verification=True,
    )


def publish_frame(project, frame, name="match_features_smoke"):
    group = project.get_feature_store().get_or_create_feature_group(
        name=name,
        version=1,
        description="Draft features from checked events. Earlier date cutoff; historical publication times unverified.",
        primary_key=KEYS,
        event_time="feature_date",
        online_enabled=False,
        time_travel_format="DELTA",
    )
    group.insert(frame, wait=True)
    verify_saved(frame, group.read())
    print(f"Verified {len(frame)} saved rows, including keys, labels and all feature values.")
    return group


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    args = parser.parse_args()
    frame = feature_frame(args.inputs)
    print(f"Prepared {len(frame)} rows for optcg_matchups / match_features_smoke v1")
    publish_frame(connect(), frame)


if __name__ == "__main__":
    main()
