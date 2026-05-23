# Open Composer Prompt Templates

Prompt templates for `source=llm_feature` factors are research inputs. They are hashed
automatically during `oc feature materialize`; changing the file changes the cache key.

Backtests never call an LLM directly. They replay materialized packets from
`reports/features/{strategy}/{factor}/packets.jsonl`.
