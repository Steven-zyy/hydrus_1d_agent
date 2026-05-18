"""Tests for hydrus_agent.run_manifest."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

import pytest

from hydrus_agent.run_manifest import (
    MANIFEST_SCHEMA_VERSION,
    RUN_MANIFEST_FILENAME,
    build_run_manifest,
    collect_environment,
    discover_input_files,
    discover_output_files,
    write_run_manifest,
    write_run_manifest_for_pipeline,
)


# --- Fixtures ------------------------------------------------------------


def _make_run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "case_test"
    (run_dir / "hydrus_project").mkdir(parents=True)
    (run_dir / "outputs").mkdir()
    (run_dir / "logs").mkdir()
    (run_dir / "figures").mkdir()
    return run_dir


def _write(path: Path, content: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _baseline_summary(run_dir: Path) -> dict:
    return {
        "case_id": "case_test",
        "run_dir": str(run_dir),
        "started_at": "2026-05-18T10:00:00",
        "finished_at": "2026-05-18T10:00:05",
        "execution_status": "completed",
        "hydrus_numerical_status": "converged",
        "qc_status": "passed",
        "overall_status": "ok",
    }


# --- collect_environment -------------------------------------------------


def test_collect_environment_has_minimum_keys():
    env = collect_environment()
    for key in (
        "python_version",
        "python_implementation",
        "platform",
        "system",
        "hydrus_agent_version",
        "git_commit",
    ):
        assert key in env
    assert env["python_version"] and env["python_version"] != "unknown"
    assert env["hydrus_agent_version"] == "0.6.0"
    # git_commit is either None or a 40-char hex string.
    if env["git_commit"] is not None:
        assert re.fullmatch(r"[0-9a-f]{40}", env["git_commit"])


def test_collect_environment_no_git_available(monkeypatch):
    monkeypatch.setattr("hydrus_agent.run_manifest.shutil.which", lambda _: None)
    env = collect_environment()
    assert env["git_commit"] is None


def test_collect_environment_git_subprocess_failure(monkeypatch):
    monkeypatch.setattr(
        "hydrus_agent.run_manifest.shutil.which", lambda _: "/usr/bin/git"
    )

    def _raise(*_a, **_kw):
        raise OSError("boom")

    monkeypatch.setattr("hydrus_agent.run_manifest.subprocess.run", _raise)
    env = collect_environment()
    assert env["git_commit"] is None


def test_collect_environment_git_nonzero_returncode(monkeypatch):
    monkeypatch.setattr(
        "hydrus_agent.run_manifest.shutil.which", lambda _: "/usr/bin/git"
    )

    class _Proc:
        returncode = 128
        stdout = ""
        stderr = "not a git repo"

    monkeypatch.setattr(
        "hydrus_agent.run_manifest.subprocess.run",
        lambda *a, **kw: _Proc(),
    )
    assert collect_environment()["git_commit"] is None


# --- discover_input_files ------------------------------------------------


def test_discover_input_files_finds_known_filenames_case_insensitive(tmp_path):
    run_dir = _make_run_dir(tmp_path)
    _write(run_dir / "config.json", '{"a": 1}')
    _write(run_dir / "hydrus_project" / "selector.in", "S")
    _write(run_dir / "hydrus_project" / "PROFILE.DAT", "P")
    _write(run_dir / "hydrus_project" / "Atmosph.In", "A")
    _write(run_dir / "hydrus_project" / "LEVEL_01.DIR", "L")

    entries = discover_input_files(run_dir)
    paths = {e["path"] for e in entries}
    assert "config.json" in paths
    assert "hydrus_project/selector.in" in paths
    assert "hydrus_project/PROFILE.DAT" in paths
    assert "hydrus_project/Atmosph.In" in paths
    assert "hydrus_project/LEVEL_01.DIR" in paths
    for entry in entries:
        assert entry["sha256"] and len(entry["sha256"]) == 64
        assert entry["size_bytes"] >= 1


def test_discover_input_files_picks_up_general_in_dat_dir_extensions(tmp_path):
    run_dir = _make_run_dir(tmp_path)
    _write(run_dir / "hydrus_project" / "custom.in", "x")
    _write(run_dir / "hydrus_project" / "extra.DAT", "x")
    _write(run_dir / "hydrus_project" / "Balance.out", "y")  # excluded
    _write(run_dir / "hydrus_project" / "Error.msg", "z")  # excluded

    paths = {e["path"] for e in discover_input_files(run_dir)}
    assert "hydrus_project/custom.in" in paths
    assert "hydrus_project/extra.DAT" in paths
    assert "hydrus_project/Balance.out" not in paths
    assert "hydrus_project/Error.msg" not in paths


def test_discover_input_files_stable_hash(tmp_path):
    run_dir = _make_run_dir(tmp_path)
    _write(run_dir / "hydrus_project" / "SELECTOR.IN", "hello")
    [entry] = discover_input_files(run_dir)
    assert entry["sha256"] == _sha256_text("hello")


def test_discover_input_files_skips_missing_hydrus_project(tmp_path):
    run_dir = tmp_path / "empty"
    run_dir.mkdir()
    assert discover_input_files(run_dir) == []


def test_discover_input_files_no_duplicates_when_known_and_extension_match(tmp_path):
    run_dir = _make_run_dir(tmp_path)
    _write(run_dir / "hydrus_project" / "SELECTOR.IN", "s")
    entries = discover_input_files(run_dir)
    rels = [e["path"] for e in entries]
    assert rels.count("hydrus_project/SELECTOR.IN") == 1


# --- discover_output_files -----------------------------------------------


def test_discover_output_files_lists_known_categories(tmp_path):
    run_dir = _make_run_dir(tmp_path)
    _write(run_dir / "hydrus_project" / "Balance.out", "b")
    _write(run_dir / "hydrus_project" / "T_Level.OUT", "t")
    _write(run_dir / "hydrus_project" / "Error.msg", "err")
    _write(run_dir / "outputs" / "qc_summary.json", "{}")
    _write(run_dir / "report.md", "# report")
    _write(run_dir / "figures" / "storage_vs_time.png", "png")
    _write(run_dir / "logs" / "hydrus_run.log", "log")

    entries = discover_output_files(run_dir)
    paths = {e["path"] for e in entries}
    assert "hydrus_project/Balance.out" in paths
    assert "hydrus_project/T_Level.OUT" in paths
    assert "hydrus_project/Error.msg" in paths
    assert "outputs/qc_summary.json" in paths
    assert "report.md" in paths
    assert "figures/storage_vs_time.png" in paths
    assert "logs/hydrus_run.log" in paths
    for entry in entries:
        assert "sha256" not in entry
        assert entry["size_bytes"] >= 1


def test_discover_output_files_skips_when_nothing_present(tmp_path):
    run_dir = _make_run_dir(tmp_path)
    assert discover_output_files(run_dir) == []


# --- build_run_manifest --------------------------------------------------


def test_build_run_manifest_happy_path(tmp_path):
    run_dir = _make_run_dir(tmp_path)
    config_path = tmp_path / "config.json"
    _write(config_path, '{"case_id": "case_test"}')
    _write(run_dir / "config.json", '{"case_id": "case_test"}')
    _write(run_dir / "hydrus_project" / "SELECTOR.IN", "s")
    _write(run_dir / "hydrus_project" / "Balance.out", "b")
    _write(run_dir / "report.md", "report")

    summary = _baseline_summary(run_dir)
    manifest = build_run_manifest(
        summary=summary,
        run_dir=run_dir,
        config_path=config_path,
        hydrus_launch_mode="argv",
    )

    assert manifest["schema_version"] == MANIFEST_SCHEMA_VERSION
    assert manifest["case_id"] == "case_test"
    assert manifest["run_dir"] == str(run_dir)
    assert manifest["config"]["path"] == str(config_path)
    assert manifest["config"]["content_hash_sha256"] == _sha256_text(
        '{"case_id": "case_test"}'
    )
    assert manifest["hydrus"]["launch_mode"] == "argv"
    assert "executable_path" in manifest["hydrus"]
    assert "executable_exists" in manifest["hydrus"]
    assert manifest["timestamps"]["started_at"] == summary["started_at"]
    assert manifest["timestamps"]["finished_at"] == summary["finished_at"]
    assert manifest["timestamps"]["manifest_written_at"].endswith("+00:00")
    assert manifest["reliability"]["overall_status"] == "ok"
    assert any(e["path"].endswith("SELECTOR.IN") for e in manifest["inputs"])
    assert any(e["path"].endswith("Balance.out") for e in manifest["outputs"])


def test_build_run_manifest_missing_optional_metadata(tmp_path):
    run_dir = _make_run_dir(tmp_path)
    summary = {
        "case_id": "case_test",
        # started_at / finished_at deliberately absent
        "execution_status": "failed_process",
        "hydrus_numerical_status": "unknown",
        "qc_status": "not_run",
        "overall_status": "failed",
    }
    manifest = build_run_manifest(
        summary=summary,
        run_dir=run_dir,
        config_path=None,
        hydrus_launch_mode=None,
    )
    assert manifest["schema_version"] == 1
    assert manifest["config"] == {
        "path": None,
        "absolute_path": None,
        "content_hash_sha256": None,
    }
    assert manifest["hydrus"]["launch_mode"] is None
    assert manifest["timestamps"]["started_at"] is None
    assert manifest["timestamps"]["finished_at"] is None
    assert manifest["timestamps"]["manifest_written_at"]
    assert manifest["inputs"] == []
    assert manifest["outputs"] == []
    assert manifest["reliability"]["overall_status"] == "failed"


def test_build_run_manifest_with_missing_config_file(tmp_path):
    run_dir = _make_run_dir(tmp_path)
    nonexistent = tmp_path / "does_not_exist.json"
    manifest = build_run_manifest(
        summary=_baseline_summary(run_dir),
        run_dir=run_dir,
        config_path=nonexistent,
        hydrus_launch_mode="argv",
    )
    assert manifest["config"]["path"] == str(nonexistent)
    assert manifest["config"]["content_hash_sha256"] is None


# --- write_run_manifest / write_run_manifest_for_pipeline ----------------


def test_write_run_manifest_round_trip(tmp_path):
    run_dir = _make_run_dir(tmp_path)
    manifest = build_run_manifest(
        summary=_baseline_summary(run_dir),
        run_dir=run_dir,
        config_path=None,
        hydrus_launch_mode="argv",
    )
    written = write_run_manifest(manifest, run_dir)
    assert written == run_dir / RUN_MANIFEST_FILENAME
    assert written.is_file()
    loaded = json.loads(written.read_text(encoding="utf-8"))
    assert loaded == manifest


def test_write_run_manifest_for_pipeline_returns_none_on_missing_dir(tmp_path):
    nowhere = tmp_path / "no_such_dir"
    result = write_run_manifest_for_pipeline(
        summary={"case_id": "x"},
        run_dir=nowhere,
        config_path=None,
        hydrus_launch_mode=None,
    )
    assert result is None


def test_write_run_manifest_for_pipeline_swallows_errors(tmp_path, monkeypatch):
    run_dir = _make_run_dir(tmp_path)

    def _boom(**_kw):
        raise RuntimeError("synthetic")

    monkeypatch.setattr("hydrus_agent.run_manifest.build_run_manifest", _boom)
    # Must not raise even though the builder explodes.
    result = write_run_manifest_for_pipeline(
        summary=_baseline_summary(run_dir),
        run_dir=run_dir,
        config_path=None,
        hydrus_launch_mode="argv",
    )
    assert result is None
    assert not (run_dir / RUN_MANIFEST_FILENAME).exists()
