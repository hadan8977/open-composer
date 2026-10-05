source: https://huggingface.co/sahil007123/kronos-nse-1d
fetched_utc: 2026-10-04T18:41:33Z
bytes_raw: 130513

sahil007123/kronos-nse-1d · Hugging Face

		Kronos-NSE-1d — a fine-tune that improved calibration and produced no alpha

Kronos-small and Kronos-Tokenizer-base fine-tuned on NSE (India) daily equity
bars, evaluated for one-day-ahead cross-sectional ranking skill.

This model does not predict Indian equity returns. It is published as a
documented negative result together with a real, measured calibration
improvement. Do not trade it.

		Headline

pretrained Kronos-small
this fine-tune

Rank-IC (1d, 100 sessions)
−0.0116
−0.0114

IC t-statistic
−0.54
−0.50

Directional hit rate
50.25%
51.57%

Forecast dispersion ÷ realised
3.61×
1.85×

Forecasts implying >±10% in a day
11.82%
2.93%

Long/short decile spread
0.046%
0.139%

Fine-tuning roughly halved forecast dispersion and cut impossible
one-day forecasts by 75%. It did not create ranking skill: the
information coefficient is statistically indistinguishable from zero, and
marginally negative.

For scale, the decile spread of 0.139% sits an order of magnitude below the
~10 bps round-trip cost of trading NSE equities, so it is not tradeable even
if it were real.

		The baseline beat it

A 12-1 momentum signal, measured on the identical 100 sessions at the
identical horizon:

signal
rank-IC
t
permutation control

12-1 momentum
+0.0376
+3.51
+0.0003

this model
−0.0114
−0.50
—

A decades-old, six-line ranking rule outperforms the fine-tuned foundation
model by a wide and statistically significant margin. That comparison is the
most useful thing in this card.

(Momentum's own skill decays: +0.0596 over 2015-2019 versus +0.0290 over
2023-2026. And in a cost-aware backtest over 2023-2026 a concentrated
top-10 momentum book returned 7.78% CAGR net against 20.46% for simply
holding the universe equal-weighted. A positive IC is necessary for a
tradeable strategy, not sufficient.)

		Evaluation

Held-out window: 2026-01-01 → 2026-07-30, 100 sessions, never seen in training.

Universe: top 80 by 60-day median turnover, re-formed each session.

Observations: 7,465 forecasts per variant.

Metric: cross-sectional Spearman rank-IC of predicted vs realised
next-session close-to-close return, aggregated as a t-statistic over
sessions.

Sampling: 1-day horizon on daily dates, so windows do not overlap and
the t-statistic is not inflated.

Four variants were evaluated. None showed skill:

variant
rank-IC
t
dispersion
impossible

pretrained Kronos-small
−0.0116
−0.54
3.61×
11.82%

fine-tuned, 4y raw (this model)
−0.0114
−0.50
1.85×
2.93%

fine-tuned, 15y corporate-action-adjusted
+0.0021
+0.09
10.19×
56.61%

fine-tuned, 15y, frozen tokenizer
−0.0315
−2.05
4.85×
17.86%

The 15-year variant, despite four times the data and corporate-action
adjustment, regressed calibration badly. Freezing the tokenizer recovered
about half of that, implicating tokenizer/predictor mismatch as a partial
cause — the tokenizer received far more adaptation than the predictor.

The frozen-tokenizer arm's t of −2.05 is the only |t| above 2 in the study.
It should not be believed: it is the fourth of four variants tested, where a
|t| > 2 arises by chance roughly 18% of the time, and no prior hypothesis
predicted negative skill.

		Training

Base: NeoQuasar/Kronos-small (predictor), NeoQuasar/Kronos-Tokenizer-base

Data: NSE daily bars, ~300 symbols by liquidity, 2022-09 → 2025-06 targets

Windows: 174,645 (90-bar lookback, 10-bar horizon)

Schedule: tokenizer 3 epochs, then predictor against it; AdamW,
lr 2e-4 / 4e-5, batch 16, grad-clip 3.0, MPS

Checkpoint selection: best validation loss. The predictor's validation
loss turned after epoch 1 and epochs 2-3 were discarded — on a corpus
five times larger the same thing happened, so this is not a data-volume
limitation.

Normalisation: statistics from the lookback segment only, never the
predicted segment.

		Usage

from huggingface_hub import snapshot_download
from model import Kronos, KronosTokenizer, KronosPredictor  # upstream Kronos repo

path = snapshot_download("Sahilsingh0808/kronos-nse-1d")
tokenizer = KronosTokenizer.from_pretrained(f"{path}/tokenizer").eval()
predictor = Kronos.from_pretrained(f"{path}/predictor").eval()
kp = KronosPredictor(predictor, tokenizer, max_context=512)

.eval() matters: from_pretrained leaves these modules in train mode, where
a non-zero attention dropout reaches scaled_dot_product_attention — an
outright error on MPS, and silent noise in every forecast elsewhere.

Sample at temperature 0.6, not 1.0. At 1.0 the pretrained model's forecast
spread measured 3.95× realised volatility with 12.6% impossible forecasts.

		Intended use

Research into financial time-series foundation models; a calibration
reference; a reproducible negative result for anyone evaluating whether to
fine-tune Kronos on a new equity market.

		Out of scope

Trading, investment decisions, or any use where the output is treated as a
return forecast. The model has no measured predictive skill. It is not
investment advice.

		Limitations

Evaluated on one market (NSE), one horizon (1 day), one window (100
sessions of 2026). 100 sessions is enough to reject a large effect, not to
rule out a small one — detecting an IC of 0.02 at |t| = 2 would need
roughly 400 sessions.

The training corpus was not corporate-action adjusted, so split and
bonus gaps appear as price crashes. The adjusted 15-year variant fixed that
and performed worse, so this is not the binding constraint, but it is a real
defect in this checkpoint.

Training universe is liquidity-ranked, biased toward large caps.

One market regime: 2022-2026 Indian equities were broadly rising.

		Citation

@misc{kronos_nse_1d_2026,
  title  = {Kronos-NSE-1d: fine-tuning a financial foundation model on Indian
            equities improves calibration but not predictive skill},
  author = {Sahil Singh},
  year   = {2026},
  note   = {Negative result. Rank-IC -0.0114 (t -0.50) over 100 held-out
            sessions; a 12-1 momentum baseline scored +0.0376 (t +3.51) on
            identical terms.},
  url    = {https://huggingface.co/Sahilsingh0808/kronos-nse-1d}
}

Downloads last month 

- 
Downloads are not tracked for this model. How to track 

 Inference Providers NEW 

 Time Series Forecasting 
This model isn't deployed by any Inference Provider. 🙋  Ask for provider support 

 Model tree for sahil007123/kronos-nse-1d 

Base model 
 NeoQuasar/Kronos-Tokenizer-base

 Finetuned (3) 

this model