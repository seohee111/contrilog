import json

import pytest

from contrilog.data_access import load_project_input
from contrilog.data_access.paths import DATA_ROOT, INPUT_FILES, input_dir
from contrilog.evaluation.ground_truth_loader import load_ground_truth
from contrilog.evaluation.paths import GROUND_TRUTH_FILES, ground_truth_dir
from contrilog.simulation.loader import load_simulated_replies

PROJECT_ID = "P001"


@pytest.fixture(scope="session")
def project_input():
    return load_project_input(PROJECT_ID)


@pytest.fixture(scope="session")
def ground_truth():
    return load_ground_truth(PROJECT_ID)


@pytest.fixture(scope="session")
def replies():
    return load_simulated_replies(PROJECT_ID)


@pytest.fixture(scope="session")
def raw_input():
    base = input_dir(PROJECT_ID)
    return {k: json.loads((base / f).read_text(encoding="utf-8")) for k, f in INPUT_FILES.items()}


@pytest.fixture(scope="session")
def raw_ground_truth():
    base = ground_truth_dir(PROJECT_ID)
    return {k: json.loads((base / f).read_text(encoding="utf-8")) for k, f in GROUND_TRUTH_FILES.items()}


@pytest.fixture(scope="session")
def data_root():
    return DATA_ROOT
