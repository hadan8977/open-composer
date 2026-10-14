"""Read retained public evidence, not prices or strategy outcomes."""

import hashlib
import json
import re
import resource
import time
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

P = Path(__file__).resolve().parents[1]
ROOT = Path.cwd()
OLD = P.parent.parent / "martin-luk-usic-20261013"


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        if tag in ("p", "h1", "h2", "h3", "h4", "h5", "li", "div", "br"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        if tag in ("p", "li"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def bind(path):
    raw = path.read_bytes()
    return dict(
        path=str(path.relative_to(ROOT)), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()
    )


def main():
    start = time.process_time()
    inputs = {
        "guest2024": OLD / "sources/guest2024-original.html",
        "study2026": P.parent
        / "public-decision-replay/study-figure-source/authored_short_study_html.bin",
    }
    result = []
    for key, path in inputs.items():
        parser = Text()
        parser.feed(path.read_text())
        lines = [re.sub(r"\s+", " ", x).strip() for x in "".join(parser.parts).splitlines()]
        lines = [x for x in lines if x]
        out = P / "sources" / (key + ".txt")
        out.write_text("\n".join(f"P{i:04}: {x}" for i, x in enumerate(lines)) + "\n")
        result.append(dict(id=key, input=bind(path), normalized=bind(out)))
    transcript = []
    for path in sorted((OLD / "sources").glob("*.json")):
        obj = json.loads(path.read_text())
        content = (
            obj
            if isinstance(obj, str)
            else obj.get("response", "")
            if isinstance(obj, dict)
            else ""
        )
        if "Transcript of +969%" not in content:
            continue
        # A response can contain other pages after its transcript. Retain source
        # identity and line numbers; never merge two different pages as one.
        chunks = re.split(r"\n-{20,}\n", content)
        for chunk in chunks:
            if chunk.startswith("Transcript of +969%"):
                transcript.append(dict(source=bind(path), text=chunk))
    out = P / "sources/interview-retained-passages.json"
    out.write_text(json.dumps(transcript, ensure_ascii=False, indent=2) + "\n")
    result.append(
        dict(
            id="interview", normalized=bind(out), complete_video_review=False, auto_transcript=True
        )
    )
    report = dict(
        at_utc=datetime.now(UTC).isoformat(),
        sources=result,
        CPU=time.process_time() - start,
        max_RSS_KiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        market_requests=0,
        new_price_processing=False,
        economic_execution=False,
    )
    (P / "sources/preparation-receipt.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
