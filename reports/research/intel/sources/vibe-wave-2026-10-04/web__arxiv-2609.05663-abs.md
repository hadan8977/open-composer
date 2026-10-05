<!-- source: https://export.arxiv.org/api/query?id_list=2609.05663 ; fetched 2026-10-04T18:47Z ; truncated False -->
<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" xmlns:arxiv="http://arxiv.org/schemas/atom" xmlns="http://www.w3.org/2005/Atom">
  <id>https://arxiv.org/api/R3XJNYRRl6P9kJh0sxwTm96bsHk</id>
  <title>arXiv Query: search_query=&amp;id_list=2609.05663&amp;start=0&amp;max_results=10</title>
  <updated>2026-10-04T18:47:23Z</updated>
  <link href="https://arxiv.org/api/query?search_query=&amp;start=0&amp;max_results=10&amp;id_list=2609.05663" type="application/atom+xml"/>
  <opensearch:itemsPerPage>10</opensearch:itemsPerPage>
  <opensearch:totalResults>1</opensearch:totalResults>
  <opensearch:startIndex>0</opensearch:startIndex>
  <entry>
    <id>http://arxiv.org/abs/2609.05663v1</id>
    <title>What LLM Trading Agents Actually Do in Production: A Six-Month, Population-Scale Record from Two Fleets</title>
    <updated>2026-09-04T18:56:31Z</updated>
    <link href="https://arxiv.org/abs/2609.05663v1" rel="alternate" type="text/html"/>
    <link href="https://arxiv.org/pdf/2609.05663v1" rel="related" type="application/pdf" title="pdf"/>
    <summary>We present a continuous, population-scale measurement record of autonomous language-model trading agents operating in production across two systems with one design lineage: DX Terminal Pro (3,505 user-funded vaults trading real ETH in Base memecoin markets for 21 days, February to March 2026) and the DXAP live alpha fleet (500 to 599 user-created agents all-history, 91 to 117 concurrently active, trading Hyperliquid perpetuals, June to August 2026). The record spans roughly six months, 7.5M single-model invocations with about 300K onchain actions, and a further 231,638 multi-tool turns producing 14,596 fills. Four findings carry the paper. First, the operating layer determines behavior more than anything written in strategy text: a risk slider explains leverage (+0.425 per level), agent fixed effects absorb 60% of variance, and a leaderboard render boundary causally routes selection (regression discontinuity 1.75x at the top-3 cut). Second, sizing is volatility-blind: median leverage is 5.0x in every volatility sextile, and one posture-slider cell (11% of the book) holds 62% of liquidations. Third, agents capture almost none of the upside they reach: 43.2% of positions saw at least +300 bps of favorable excursion within 24h, yet 49.3% of those closed with a negative trade return; a mechanical bracket recovers +39.0 bps per position. Fourth, neither fleet shows a directional edge. The DXAP fleet is not profitable and trails a matched Hyperliquid retail benchmark (41% vs. 50% roundtrip win rate). A paired-replay league of frontier models on 416 captured production scenarios finds decision quality statistically indistinguishable at this horizon, while choice stability differs sharply across model families. Every headline survives day-clustered inference, permutation nulls, and a common-fee restatement; the paper closes with a 17-rule methodology canon bought with our own retractions.</summary>
    <category term="cs.AI" scheme="http://arxiv.org/schemas/atom"/>
    <category term="cs.CE" scheme="http://arxiv.org/schemas/atom"/>
    <category term="cs.MA" scheme="http://arxiv.org/schemas/atom"/>
    <published>2026-09-04T18:56:31Z</published>
    <arxiv:comment>17 pages, 8 figures, 3 tables. Artifacts, figures, and aggregate data: https://github.com/ProjectDXAI/continuous-record-llm-trading-agents</arxiv:comment>
    <arxiv:primary_category term="cs.AI"/>
    <author>
      <name>T. J. Barton</name>
    </author>
    <author>
      <name>Chris Constantakis</name>
    </author>
    <author>
      <name>Patti Hauseman</name>
    </author>
    <author>
      <name>Annie Mous</name>
    </author>
    <author>
      <name>Alaska Hoffman</name>
    </author>
    <author>
      <name>Brian Bergeron</name>
    </author>
    <author>
      <name>Hunter Goodreau</name>
    </author>
  </entry>
</feed>
