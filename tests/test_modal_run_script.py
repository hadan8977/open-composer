"""Pure-logic tests for scripts/modal_run.py: no network, no Modal calls."""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import modal_run as mr  # noqa: E402


def test_substitute_command_replaces_shard_and_nshards() -> None:
    argv = ["uv", "run", "python", "scripts/foo.py", "--shard", "{shard}", "--n", "{nshards}"]
    assert mr.substitute_command(argv, 2, 5) == [
        "uv",
        "run",
        "python",
        "scripts/foo.py",
        "--shard",
        "2",
        "--n",
        "5",
    ]


def test_substitute_command_leaves_plain_tokens_untouched() -> None:
    argv = ["uv", "run", "python", "scripts/foo.py"]
    assert mr.substitute_command(argv, 0, 1) == argv


def test_config_file_allowed_excludes_non_example_yaml() -> None:
    assert not mr.config_file_allowed(Path("config/giants_sweep/manifest.yaml"))
    assert mr.config_file_allowed(Path("config/notifications.yaml.example"))
    assert mr.config_file_allowed(Path("config/research-autonomy.json"))


def test_config_file_allowed_excludes_key_secret_token_named_files() -> None:
    assert not mr.config_file_allowed(Path("config/broker-secrets.json"))
    assert not mr.config_file_allowed(Path("config/api-token.example"))
    assert not mr.config_file_allowed(Path("config/private-key.pem"))


def test_iter_allowlisted_files_skips_pycache_and_config_yaml(tmp_path: Path) -> None:
    (tmp_path / "open_composer").mkdir()
    (tmp_path / "open_composer" / "mod.py").write_text("x = 1\n")
    pycache = tmp_path / "open_composer" / "__pycache__"
    pycache.mkdir()
    (pycache / "mod.cpython-311.pyc").write_bytes(b"\x00")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "manifest.yaml").write_text("a: 1\n")
    (tmp_path / "config" / "notifications.yaml.example").write_text("a: 1\n")
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "secret.json").write_text("{}")
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    (tmp_path / "uv.lock").write_text("")

    files = mr.iter_allowlisted_files(tmp_path)
    rels = {str(p.relative_to(tmp_path)) for p in files}

    assert "open_composer/mod.py" in rels
    assert not any("__pycache__" in r for r in rels)
    assert "config/manifest.yaml" not in rels
    assert "config/notifications.yaml.example" in rels
    assert not any(r.startswith("reports/") for r in rels)
    assert "pyproject.toml" in rels
    assert "uv.lock" in rels


def test_iter_allowlisted_files_includes_extra_dir(tmp_path: Path) -> None:
    (tmp_path / "extra_pkg").mkdir()
    (tmp_path / "extra_pkg" / "m.py").write_text("x = 1\n")
    files = mr.iter_allowlisted_files(tmp_path, extra_dirs=["extra_pkg"])
    rels = {str(p.relative_to(tmp_path)) for p in files}
    assert "extra_pkg/m.py" in rels


def test_scan_file_for_secrets_flags_assigned_literal(tmp_path: Path) -> None:
    f = tmp_path / "leak.py"
    f.write_text('APCA_API_KEY_ID = "AKIAABCDEFGH12345678"\n')
    violations = mr.scan_file_for_secrets(f)
    assert violations
    assert "APCA" in violations[0]


def test_scan_file_for_secrets_allows_naming_an_env_var(tmp_path: Path) -> None:
    f = tmp_path / "clean.py"
    f.write_text(
        "import os\n"
        'key = os.environ["ALPACA_API_KEY"]\n'
        "# remember to set DEEPSEEK_API_KEY before running\n"
    )
    assert mr.scan_file_for_secrets(f) == []


def test_scan_file_for_secrets_flags_private_key_header(tmp_path: Path) -> None:
    f = tmp_path / "id_rsa.py"
    f.write_text("BLOB = '''\n-----BEGIN RSA PRIVATE KEY-----\nMIIBOgIBAAJBAK...\n'''\n")
    violations = mr.scan_file_for_secrets(f)
    assert any("private key" in v for v in violations)


def test_scan_for_secrets_aborts_stage_code(tmp_path: Path) -> None:
    (tmp_path / "open_composer").mkdir()
    leaky = tmp_path / "open_composer" / "leaky.py"
    leaky.write_text('DEEPSEEK_API_KEY = "sk-abcd1234efgh5678ijkl"\n')
    files = [leaky]
    violations = mr.scan_for_secrets(files)
    assert violations


def test_scan_file_for_secrets_allows_readable_status_labels(tmp_path: Path) -> None:
    """Long lowercase snake_case labels containing a keyword substring (no
    digits, not a random-looking value) are status tags, not credentials --
    this is real code from the repo that must not block every Modal launch."""
    f = tmp_path / "labels.py"
    f.write_text(
        "\n".join(
            [
                'A = "alpaca_paper_sync"',
                'B = "alpaca_paper_only"',
                'C = "missing_api_key_fallback_to_deterministic"',
                'D = "immutable_alpaca_contract_snapshot"',
                "",
            ]
        )
    )
    assert mr.scan_file_for_secrets(f) == []


def test_private_key_header_ignores_the_scanners_own_source(tmp_path: Path) -> None:
    """The detector's own code/comments name '-----BEGIN' and 'PRIVATE KEY'
    without concatenating them into a real PEM header; must not self-flag."""
    f = tmp_path / "self_ref.py"
    f.write_text(
        "# `-----BEGIN` (private key headers) is never safe.\n"
        'if "-----BEGIN" in line and "PRIVATE KEY" in line.upper():\n'
        "    pass\n"
    )
    assert mr.scan_file_for_secrets(f) == []


def test_scan_dir_stat_matches_needs_sync(tmp_path: Path) -> None:
    d = tmp_path / "data" / "sip" / "daily"
    d.mkdir(parents=True)
    (d / "a.parquet").write_bytes(b"12345")
    stat = mr.scan_dir_stat(d)
    assert "a.parquet" in stat
    assert not mr.needs_sync(stat, stat)
    assert mr.needs_sync(stat, None)
    assert mr.needs_sync(stat, {"a.parquet": [1.0, 2.0]})


def test_needs_sync_detects_a_touched_file(tmp_path: Path) -> None:
    d = tmp_path / "data" / "x"
    d.mkdir(parents=True)
    f = d / "a.bin"
    f.write_bytes(b"abc")
    before = mr.scan_dir_stat(d)
    time.sleep(0.01)
    f.write_bytes(b"abcd")
    after = mr.scan_dir_stat(d)
    assert mr.needs_sync(after, before)


def test_manifest_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    assert mr.read_manifest(path) == {}
    mr.write_manifest({"data/x": {"a.bin": [3.0, 1.0]}}, path)
    assert mr.read_manifest(path) == {"data/x": {"a.bin": [3.0, 1.0]}}


def test_parse_args_splits_command_and_supports_fetch_to() -> None:
    ns, command = mr.parse_args(
        [
            "--job",
            "demo",
            "--cpu",
            "2",
            "--memory-gib",
            "4",
            "--timeout-min",
            "10",
            "--out",
            "reports/research/iterations/demo",
            "--fetch-to",
            "reports/research/control/scratch/demo",
            "--shards",
            "3",
            "--",
            "uv",
            "run",
            "python",
            "scripts/demo.py",
            "--shard",
            "{shard}",
        ]
    )
    assert ns.job == "demo"
    assert ns.shards == 3
    assert ns.fetch_to == "reports/research/control/scratch/demo"
    assert command == ["uv", "run", "python", "scripts/demo.py", "--shard", "{shard}"]


def test_parse_args_requires_double_dash_and_a_command() -> None:
    try:
        mr.parse_args(["--job", "demo"])
    except SystemExit:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected SystemExit without --")

    try:
        mr.parse_args(["--job", "demo", "--"])
    except SystemExit:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected SystemExit with an empty command")


def test_parse_args_rejects_shards_below_one() -> None:
    try:
        mr.parse_args(
            [
                "--job",
                "demo",
                "--cpu",
                "1",
                "--memory-gib",
                "1",
                "--timeout-min",
                "1",
                "--out",
                "x",
                "--shards",
                "0",
                "--",
                "true",
            ]
        )
    except SystemExit:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected SystemExit for --shards 0")
