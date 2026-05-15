from __future__ import annotations

import csv
import json
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
PDF_DIR = ROOT / "pdfs"
TEXT_DIR = ROOT / "extracted_text"

PAPERS = [
    {
        "key": "AlphaCrafter",
        "arxiv_id": "2605.05580",
        "topic": "LLM Agent 与多智能体交易系统",
        "image_refs": "Image #6-7",
        "confidence": "high",
    },
    {
        "key": "TrustTrade",
        "arxiv_id": "2603.22567",
        "topic": "LLM Agent 与多智能体交易系统",
        "image_refs": "Image #8",
        "confidence": "high",
    },
    {
        "key": "BlindTrade",
        "arxiv_id": "2603.17692",
        "topic": "LLM Agent 与多智能体交易系统",
        "image_refs": "Image #9",
        "confidence": "high",
    },
    {
        "key": "Expert Investment Teams",
        "arxiv_id": "2602.23330",
        "topic": "LLM Agent 与多智能体交易系统",
        "image_refs": "Image #6, #11-12",
        "confidence": "medium",
    },
    {
        "key": "HiveMind",
        "arxiv_id": "2512.06432",
        "topic": "LLM Agent 与多智能体交易系统",
        "image_refs": "Image #11-12",
        "confidence": "medium",
    },
    {
        "key": "OOM-RL",
        "arxiv_id": "2604.11477",
        "topic": "LLM Agent 与多智能体交易系统",
        "image_refs": "Image #6, #12",
        "confidence": "medium",
    },
    {
        "key": "SNAPO",
        "arxiv_id": "2605.06570",
        "topic": "强化学习组合优化与交易",
        "image_refs": "Image #15-16, #18",
        "confidence": "high",
    },
    {
        "key": "MetaRL-GBWM",
        "arxiv_id": "2605.02300",
        "topic": "强化学习组合优化与交易",
        "image_refs": "Image #16-17, #18-19",
        "confidence": "high",
    },
    {
        "key": "MACE / Realistic Market Impact",
        "arxiv_id": "2603.29086",
        "topic": "强化学习组合优化与交易",
        "image_refs": "Image #17, #19",
        "confidence": "high",
    },
    {
        "key": "SBCA",
        "arxiv_id": "2605.01384",
        "topic": "强化学习组合优化与交易",
        "image_refs": "Image #19-20",
        "confidence": "medium",
    },
    {
        "key": "FactorEngine",
        "arxiv_id": "2603.16365",
        "topic": "自动化因子挖掘与 Alpha 发现",
        "image_refs": "Image #23-24",
        "confidence": "high",
    },
    {
        "key": "Hubble",
        "arxiv_id": "2604.09601",
        "topic": "自动化因子挖掘与 Alpha 发现",
        "image_refs": "Image #24-25",
        "confidence": "high",
    },
    {
        "key": "SEMF",
        "arxiv_id": "2603.27321",
        "topic": "多模态金融预测与另类数据",
        "image_refs": "Image #27-30",
        "confidence": "high",
    },
    {
        "key": "Uni-FinLLM",
        "arxiv_id": "2601.02677",
        "topic": "多模态金融预测与另类数据",
        "image_refs": "Image #28-30",
        "confidence": "high",
    },
    {
        "key": "History Rhymes",
        "arxiv_id": "2511.09754",
        "topic": "多模态金融预测与另类数据",
        "image_refs": "Image #28-30",
        "confidence": "high",
    },
    {
        "key": "Acoustic Camouflage",
        "arxiv_id": "2604.14619",
        "topic": "多模态金融预测与另类数据",
        "image_refs": "Image #31",
        "confidence": "medium",
    },
    {
        "key": "PolyBench",
        "arxiv_id": "2604.14199",
        "topic": "评估基准与可靠性研究",
        "image_refs": "Image #32-33",
        "confidence": "high",
    },
    {
        "key": "QuantCode-Bench",
        "arxiv_id": "2604.15151",
        "topic": "评估基准与可靠性研究",
        "image_refs": "Image #33",
        "confidence": "high",
    },
    {
        "key": "Reliable Evaluation",
        "arxiv_id": "2603.27539",
        "topic": "评估基准与可靠性研究",
        "image_refs": "Image #34-36",
        "confidence": "high",
    },
]


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def fetch_arxiv_metadata(ids: list[str]) -> dict[str, dict[str, object]]:
    url = "https://export.arxiv.org/api/query"
    response = requests.get(url, params={"id_list": ",".join(ids)}, timeout=60)
    response.raise_for_status()
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom",
    }
    root = ET.fromstring(response.text)
    items: dict[str, dict[str, object]] = {}
    for entry in root.findall("atom:entry", ns):
        raw_id = entry.findtext("atom:id", default="", namespaces=ns).rsplit("/", 1)[-1]
        arxiv_id = raw_id.split("v", 1)[0]
        authors = [
            node.findtext("atom:name", default="", namespaces=ns).strip()
            for node in entry.findall("atom:author", ns)
        ]
        categories = [node.attrib.get("term", "") for node in entry.findall("atom:category", ns)]
        pdf_url = ""
        abs_url = ""
        for link in entry.findall("atom:link", ns):
            if link.attrib.get("title") == "pdf":
                pdf_url = link.attrib.get("href", "")
            if link.attrib.get("rel") == "alternate":
                abs_url = link.attrib.get("href", "")
        items[arxiv_id] = {
            "arxiv_id": arxiv_id,
            "title": " ".join(entry.findtext("atom:title", default="", namespaces=ns).split()),
            "authors": authors,
            "published": entry.findtext("atom:published", default="", namespaces=ns)[:10],
            "updated": entry.findtext("atom:updated", default="", namespaces=ns)[:10],
            "abstract": " ".join(entry.findtext("atom:summary", default="", namespaces=ns).split()),
            "categories": categories,
            "abs_url": abs_url or f"https://arxiv.org/abs/{arxiv_id}",
            "pdf_url": pdf_url or f"https://arxiv.org/pdf/{arxiv_id}",
        }
    return items


def download_pdf(meta: dict[str, object], path: Path) -> str:
    if path.exists() and path.stat().st_size > 20_000:
        return "downloaded"
    response = requests.get(str(meta["pdf_url"]), timeout=120)
    response.raise_for_status()
    path.write_bytes(response.content)
    return "downloaded" if path.stat().st_size > 20_000 else "small_or_failed"


def extract_text(pdf_path: Path, text_path: Path) -> str:
    if text_path.exists() and text_path.stat().st_size > 2_000:
        return "extracted"
    reader = PdfReader(str(pdf_path))
    chunks = []
    for page in reader.pages:
        try:
            chunks.append(page.extract_text() or "")
        except Exception as exc:  # pragma: no cover - best effort source extraction
            chunks.append(f"\n[page extraction failed: {exc}]\n")
    text_path.write_text(
        "\n\n".join(chunks).encode("utf-8", errors="replace").decode("utf-8"),
        encoding="utf-8",
    )
    return "extracted" if text_path.stat().st_size > 2_000 else "weak_extract"


def main() -> None:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    ids = [paper["arxiv_id"] for paper in PAPERS]
    metadata = fetch_arxiv_metadata(ids)
    rows = []
    for paper in PAPERS:
        arxiv_id = paper["arxiv_id"]
        meta = metadata.get(arxiv_id, {})
        if not meta:
            meta = {
                "arxiv_id": arxiv_id,
                "title": paper["key"],
                "authors": [],
                "published": "",
                "updated": "",
                "abstract": "",
                "categories": [],
                "abs_url": f"https://arxiv.org/abs/{arxiv_id}",
                "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
            }
        slug = slugify(f"{paper['key']}-{arxiv_id}")
        pdf_path = PDF_DIR / f"{slug}.pdf"
        text_path = TEXT_DIR / f"{slug}.txt"
        try:
            pdf_status = download_pdf(meta, pdf_path)
            time.sleep(0.5)
        except Exception as exc:
            pdf_status = f"failed: {exc}"
        try:
            text_status = extract_text(pdf_path, text_path) if pdf_path.exists() else "no_pdf"
        except Exception as exc:
            text_status = f"failed: {exc}"
        row = {
            **paper,
            **meta,
            "authors": "; ".join(meta.get("authors", [])),
            "categories": "; ".join(meta.get("categories", [])),
            "pdf_file": str(pdf_path.relative_to(ROOT)) if pdf_path.exists() else "",
            "text_file": str(text_path.relative_to(ROOT)) if text_path.exists() else "",
            "pdf_status": pdf_status,
            "text_status": text_status,
        }
        rows.append(row)

    (ROOT / "metadata.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    fields = [
        "key",
        "title",
        "topic",
        "arxiv_id",
        "authors",
        "published",
        "updated",
        "abs_url",
        "pdf_url",
        "pdf_file",
        "text_file",
        "pdf_status",
        "text_status",
        "image_refs",
        "confidence",
        "categories",
    ]
    with (ROOT / "paper_inventory.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})
    print(f"Collected {len(rows)} papers into {ROOT}")


if __name__ == "__main__":
    main()
