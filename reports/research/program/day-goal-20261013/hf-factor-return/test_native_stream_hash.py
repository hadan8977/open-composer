import hashlib

from open_composer.research.market_component import _load_binding, _sha256_file


def test_stream_hash_matches_full_bytes_across_chunk_boundaries(tmp_path):
    path = tmp_path / "payload.bin"
    value = bytes(range(256)) * 8201 + b"last byte"
    path.write_bytes(value)
    assert _sha256_file(path) == hashlib.sha256(value).hexdigest()


def test_binding_json_and_hash_mismatch_keep_existing_semantics(tmp_path):
    path = tmp_path / "packet.json"
    path.write_text('{"hello":42}')
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    blocked = []
    assert _load_binding(tmp_path, dict(path="packet.json", sha256=expected), "test", blocked) == {
        "hello": 42
    }
    assert blocked == []
    assert (
        _load_binding(tmp_path, dict(path="packet.json", sha256="wrong"), "test", blocked) is None
    )
    assert blocked == ["market_component_test_binding_invalid"]
