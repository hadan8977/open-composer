"""Retain the exact new ZIP as old compressed members plus literal new bytes.

No extraction/recompression or source semantics change. This preparation does
not unlink either ZIP. Release requires the separately reviewed receipt.
"""
import hashlib
import json
import os
import struct
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
OLD = ROOT / "data/raw/sec_xbrl/companyfacts.zip"
NEW = HERE.parent / "current-companyfacts-bulk/companyfacts.zip"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def offset(stream, member):
    stream.seek(member.header_offset)
    head = stream.read(30)
    assert head[:4] == b"PK\x03\x04"
    name, extra = struct.unpack_from("<HH", head, 26)
    return member.header_offset + 30 + name + extra


def main():
    retained = HERE / "retained-old-companyfacts.zip"
    literals = HERE / "current-zip-literals.bin"
    manifest = HERE / "exact-current-zip-delta.json"
    if retained.exists() or literals.exists() or manifest.exists():
        raise ValueError("retain the prior attempt; do not overwrite")
    original_sha, new_sha = sha(OLD), sha(NEW)
    os.link(OLD, retained)
    segments = []
    reused = 0
    digest = hashlib.sha256()
    with zipfile.ZipFile(OLD) as oz, zipfile.ZipFile(NEW) as nz, OLD.open("rb") as a, NEW.open("rb") as b, literals.open("xb") as out:
        previous = {i.filename: i for i in oz.infolist()}
        position = 0

        def literal(start, length):
            b.seek(start)
            literal_offset = out.tell()
            chunk_digest = hashlib.sha256()
            left = length
            while left:
                data = b.read(min(left, 1048576))
                if not data:
                    raise ValueError("truncated new ZIP")
                out.write(data)
                digest.update(data)
                chunk_digest.update(data)
                left -= len(data)
            if length:
                segments.append({"kind": "literal", "offset": literal_offset, "bytes": length, "sha256": chunk_digest.hexdigest()})

        for member in sorted(nz.infolist(), key=lambda i: i.header_offset):
            begin = offset(b, member)
            literal(position, begin - position)
            old = previous.get(member.filename)
            match = False
            if old and (old.CRC, old.compress_size, old.file_size) == (member.CRC, member.compress_size, member.file_size):
                old_begin = offset(a, old)
                a.seek(old_begin)
                b.seek(begin)
                left = member.compress_size
                sd = hashlib.sha256()
                match = True
                while left:
                    size = min(left, 1048576)
                    av, bv = a.read(size), b.read(size)
                    if len(av) != size or len(bv) != size or av != bv:
                        match = False
                        break
                    sd.update(av)
                    left -= size
                if match:
                    segments.append({"kind": "base", "offset": old_begin, "bytes": member.compress_size, "sha256": sd.hexdigest()})
                    a.seek(old_begin)
                    left = member.compress_size
                    while left:
                        data = a.read(min(left, 1048576))
                        digest.update(data)
                        left -= len(data)
                    reused += member.compress_size
            if not match:
                literal(begin, member.compress_size)
            position = begin + member.compress_size
        literal(position, NEW.stat().st_size - position)
    assert digest.hexdigest() == new_sha
    assert OLD.stat().st_ino == retained.stat().st_ino
    assert OLD.stat().st_size == retained.stat().st_size
    # Independent second pass through the retained representation, not NEW.
    reconstruction = hashlib.sha256()
    total = 0
    with retained.open("rb") as a, literals.open("rb") as b:
        for part in segments:
            stream = a if part["kind"] == "base" else b
            stream.seek(part["offset"])
            left = part["bytes"]
            sd = hashlib.sha256()
            while left:
                data = stream.read(min(left, 1048576))
                if not data:
                    raise ValueError("truncated retained segment")
                sd.update(data)
                reconstruction.update(data)
                total += len(data)
                left -= len(data)
            assert sd.hexdigest() == part["sha256"]
    assert total == NEW.stat().st_size and reconstruction.hexdigest() == new_sha
    result = {"original": {"path": str(NEW), "bytes": total, "sha256": new_sha}, "retained_base": {"path": str(retained), "bytes": retained.stat().st_size, "sha256": original_sha, "existing_inode_hardlink": True}, "literals": {"path": str(literals), "bytes": literals.stat().st_size, "sha256": sha(literals)}, "segments": segments, "reconstructed_exact_sha256": reconstruction.hexdigest(), "verified_reused_bytes": reused, "originals_unlinked": 0, "new_source_requests": 0, "unique_current_source_information_retained": True, "base_collector_uses_part_atomic_replace": True}
    manifest.write_text(json.dumps(result, indent=2) + "\n")
    print({k: result[k] for k in ["original", "literals", "verified_reused_bytes", "originals_unlinked"]})


if __name__ == "__main__":
    main()
