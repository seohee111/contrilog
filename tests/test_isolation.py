"""Agent 쪽 코드/입력이 Ground Truth를 import·read 하지 않는지, 입력에 정답이 노출되지 않는지 검사."""

import ast
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

import contrilog
from contrilog.data_access import load_project_input
from contrilog.data_access.input_loader import InputPathError
from contrilog.data_access.paths import DATA_ROOT, INPUT_FILES
from contrilog.schemas import ClaimStatus, ContributionType, StagnationState

PKG = Path(contrilog.__file__).parent
PROJECT_ROOT = PKG.parent

# Ground Truth에 접근하면 안 되는 패키지/모듈
AGENT_SIDE = ["agent", "tools", "memory", "data_access", "simulation", "schemas"]
ALLOWED_GT_MODULE = PKG / "schemas" / "ground_truth.py"  # schema 정의 자체는 예외
FORBIDDEN_MODULES = ("contrilog.evaluation", "contrilog.schemas.ground_truth")


def _agent_side_files():
    for sub in AGENT_SIDE:
        for f in (PKG / sub).rglob("*.py"):
            if f != ALLOWED_GT_MODULE:
                yield f


def _imported_modules(tree: ast.AST, file: Path) -> list[str]:
    """절대/상대 import를 모두 절대 모듈 이름으로 풀어서 반환."""
    pkg_parts = ["contrilog", *file.relative_to(PKG).parent.parts]
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = pkg_parts[: len(pkg_parts) - node.level + 1]
                mod = ".".join(base + ([node.module] if node.module else []))
            else:
                mod = node.module or ""
            out.append(mod)
            out += [f"{mod}.{a.name}" for a in node.names]
        elif isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", "")) in (
            "import_module", "__import__"
        ):
            out += [a.value for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
    return out


def test_agent_side_code_does_not_import_ground_truth():
    files = list(_agent_side_files())
    assert files
    for f in files:
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for mod in _imported_modules(tree, f):
            assert not mod.startswith(FORBIDDEN_MODULES), f"{f.relative_to(PROJECT_ROOT)} imports {mod}"


def _docstring_nodes(tree: ast.AST) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                ids.add(id(first.value))
    return ids


def test_agent_side_code_does_not_reference_ground_truth_path():
    """코드 안의 문자열 리터럴(경로 등)에 정답 디렉터리 이름이 없어야 한다. docstring 설명은 제외."""
    for f in _agent_side_files():
        tree = ast.parse(f.read_text(encoding="utf-8"))
        docstrings = _docstring_nodes(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
                assert "ground_truth" not in node.value.lower(), f"{f.relative_to(PROJECT_ROOT)}: {node.value!r}"


def test_import_checker_catches_violations():
    """검사기 자체가 상대/절대/동적 import를 잡아내는지 확인."""
    fake = PKG / "agent" / "planner.py"
    src = (
        "from ..evaluation import ground_truth_loader\n"
        "from contrilog.schemas.ground_truth import GroundTruthBundle\n"
        "import importlib\nimportlib.import_module('contrilog.evaluation.paths')\n"
    )
    mods = _imported_modules(ast.parse(src), fake)
    hits = [m for m in mods if m.startswith(FORBIDDEN_MODULES)]
    assert {"contrilog.evaluation", "contrilog.schemas.ground_truth", "contrilog.evaluation.paths"} <= set(hits)


def test_importing_agent_side_does_not_load_ground_truth_modules():
    code = (
        "import sys\n"
        "import contrilog.agent, contrilog.tools, contrilog.memory, contrilog.schemas\n"
        "import contrilog.data_access, contrilog.data_access.integrity, contrilog.simulation\n"
        "from contrilog.data_access import load_project_input\n"
        "load_project_input('P001')\n"
        "bad = [m for m in sys.modules if m.startswith(('contrilog.evaluation', 'contrilog.schemas.ground_truth'))]\n"
        "print(bad); sys.exit(1 if bad else 0)\n"
    )
    r = subprocess.run([sys.executable, "-c", code], cwd=PROJECT_ROOT, capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT)})
    assert r.returncode == 0, r.stdout + r.stderr


def test_schemas_package_does_not_export_ground_truth():
    import contrilog.schemas as S

    assert not [n for n in dir(S) if n.startswith("GroundTruth")]


def test_input_loader_reads_only_input_files():
    """audit hook으로 load_project_input 실행 중 열린 파일을 모두 기록한다."""
    code = (
        "import sys, json\n"
        "opened = []\n"
        "sys.addaudithook(lambda ev, args: opened.append(str(args[0])) if ev == 'open' and isinstance(args[0], str) and args[0].endswith('.json') else None)\n"
        "from contrilog.data_access import load_project_input\n"
        "load_project_input('P001')\n"
        "print(json.dumps(opened))\n"
    )
    r = subprocess.run([sys.executable, "-c", code], cwd=PROJECT_ROOT, capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT)})
    assert r.returncode == 0, r.stderr
    import json

    opened = [Path(p).resolve() for p in json.loads(r.stdout.strip().splitlines()[-1])]
    input_root = (DATA_ROOT / "input" / "P001").resolve()
    assert {p.name for p in opened} == set(INPUT_FILES.values())
    for p in opened:
        assert p.is_relative_to(input_root), p


def test_input_loader_refuses_redirect_to_ground_truth(tmp_path):
    """input/P001 이 정답 디렉터리를 가리키는 심볼릭 링크여도 읽지 않아야 한다."""
    (tmp_path / "input").mkdir()
    os.symlink(DATA_ROOT / "ground_truth" / "P001", tmp_path / "input" / "P001")
    with pytest.raises(InputPathError):
        load_project_input("P001", data_root=tmp_path)
    with pytest.raises(InputPathError):
        load_project_input("../ground_truth/P001")


# ---- 입력 데이터에 정답이 노출되지 않는지 -------------------------------------

def _texts(root: Path):
    for f in sorted(root.rglob("*.json")):
        yield f, f.read_text(encoding="utf-8")


LEAK_TOKENS = (
    [e.value for e in ContributionType]
    + [e.value for e in ClaimStatus if e != ClaimStatus.PENDING_VERIFICATION]
    + [e.value for e in StagnationState]
)
LEAK_PATTERNS = [r"\bCASE\d{2}\b", r"\bCase\s?\d{2}\b", r"\bGTC?L?S?-\d{2}\b", "ground_truth", "expected", "정답"]


@pytest.mark.parametrize("subdir", ["input", "simulation"])
def test_input_and_simulation_do_not_contain_answer_labels(subdir):
    for f, text in _texts(DATA_ROOT / subdir):
        for tok in LEAK_TOKENS:
            assert not re.search(rf"\b{tok}\b", text), f"{f.name}: label token {tok}"
        for pat in LEAK_PATTERNS:
            assert not re.search(pat, text, flags=re.IGNORECASE), f"{f.name}: pattern {pat}"


def test_ground_truth_not_inside_input_tree():
    gt = (DATA_ROOT / "ground_truth").resolve()
    inp = (DATA_ROOT / "input").resolve()
    assert not gt.is_relative_to(inp) and not inp.is_relative_to(gt)
