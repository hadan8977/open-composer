"""Step 13 Track L: quant + LLM news factor/decision pipeline.

Owned by the Track L executor this round (see
``docs/plan-step-13-recent-high-return-ml-and-llm-tracks-2026-09-09.zh.md``
section 6's file-ownership table). Submodules:

- ``collector``: Alpaca News (Benzinga) PIT packet collection.
- ``extract`` (Wave L1): LLM extraction-only event tagging.
- ``features`` (Wave L2): PIT daily news feature table.
"""

from __future__ import annotations
