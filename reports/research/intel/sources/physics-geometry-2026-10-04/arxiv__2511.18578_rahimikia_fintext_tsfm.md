source: https://arxiv.org/pdf/2511.18578
fetched_utc: 2026-10-04T18:41:31Z
bytes_raw: 3674344

Re(Visiting) Time Series Foundation Models in Finance

                                                                                         Eghbal Rahimikia*
                                                                  Alliance Manchester Business School, University of Manchester
                                                                              eghbal.rahimikia@manchester.ac.uk

                                                                                                 Hao Ni
arXiv:2511.18578v1 [q-fin.CP] 23 Nov 2025




                                                                 Department of Mathematics, University College London (UCL)
                                                                                     h.ni@ucl.ac.uk

                                                                                            Weiguan Wang
                                                                              School of Economics, Shanghai University
                                                                                      weiguanwang@shu.edu.cn

                                                                                             November 2025

                                                                                                 Abstract

                                                  Financial time series forecasting is vital for trading, portfolio optimization, and risk man-
                                                  agement but is difficult due to noisy, non-stationary, and heterogeneous data. Recent time
                                                  series foundation models (TSFMs), inspired by large language models, offer a new ap-
                                                  proach for learning generalizable temporal representations. This paper provides the first
                                                  comprehensive empirical evaluation of TSFMs in global financial markets using large-scale
                                                  daily excess-return data. We assess zero-shot inference, fine-tuning, and pre-training from
                                                  scratch against strong benchmarks. Off-the-shelf TSFMs perform poorly, while models
                                                  pre-trained on financial data deliver substantial forecasting and economic gains. Larger
                                                  datasets, synthetic data augmentation, and hyperparameter tuning further improve results.

                                            Keywords: Time Series Foundation Models, Transformer Models, Asset Return Predictability, Cross-
                                            Sectional Stock Returns, Transfer Learning
                                            JEL Classification: C53, C45, C63, G17




                                                 * Corresponding author.
                                                 The authors acknowledge the use of resources provided by the Isambard-AI National AI Research Resource (AIRR).
                                            Isambard-AI is operated by the University of Bristol and is funded by the UK Government’s Department for Science,
                                            Innovation and Technology (DSIT) via UK Research and Innovation; and the Science and Technology Facilities Council
                                            [ST/AIRR/I-A-I/1023]. The authors would also like to acknowledge the assistance provided by Research IT and the
                                            use of the Computational Shared Facility at The University of Manchester. This work also made use of the facilities of
                                            the N8 Centre of Excellence in Computationally Intensive Research (N8 CIR), funded by the N8 research partnership
                                            and EPSRC (Grant No. EP/T022167/1). The Centre is coordinated by the Universities of Durham, Manchester, and
                                            York. Hao Ni is supported by the EPSRC under the program grant EP/S026347/1 and the Alan Turing Institute under
                                            the EPSRC grant EP/N510129/1. Weiguan Wang appreciates the financial support by the National Natural Science
                                            Foundation of China (No. 72201158). This work is also supported by the Shanghai Technical Service Center of Science
                                            and Engineering Computing, Shanghai University. All models are available through our portal at FinText.ai and the
                                            Hugging Face repository at https://huggingface.co/FinText.
1       Introduction

Financial time series forecasting is a central problem in quantitative finance, underpinning trading,

portfolio construction, and risk management. Decades of research have produced a wide spectrum of

models, from classical econometric approaches (e.g., ARIMA, GARCH) to modern machine learning

(ML) models such as tree-based ensembles and deep neural networks. Yet reliable forecasting remains

difficult. Financial data are noisy, non-stationary, and heterogeneous across assets and horizons,

with low signal-to-noise ratios, regime shifts, and limited effective sample sizes for many instruments.

These properties complicate generalization and challenge the stability of out-of-sample performance

in dynamic markets.

    The success of large language models (LLMs) has popularized a pre-training and fine-tuning

paradigm for learning general-purpose representations that transfer across tasks and domains. This

paradigm has inspired the emergence of time series foundation models (TSFMs)1 , large pre-trained

architectures designed to learn universal temporal representations from vast and diverse time series cor-

pora. TSFMs aim to deliver competitive performance on previously unseen datasets in a zero-shot or

few-shot manner, while retaining strong in-domain accuracy after adaptation. Recent models illustrate

two dominant design philosophies: discrete tokenization with autoregressive decoding versus contin-

uous latent embeddings with regression-style objectives. Analogous to LLMs for text, the promise

of TSFMs lies in compressing generic temporal regularities (e.g., seasonality, volatility clustering,

long-memory features) into reusable representations that can be efficiently adapted to domain-specific

tasks.

    This paper presents the first comprehensive empirical study of TSFMs in global financial markets.

Using a large-scale panel of daily excess returns spanning 34 years across 94 countries, we evaluate

three TSFM regimes at the univariate level: (i) zero-shot inference with pre-trained weights, (ii) fine-

tuning on financial data, and (iii) pre-training from scratch on financial time series. We test these

approaches against a broad set of benchmarks, including linear models, ensemble models2 , and neural

networks. Our analysis leverages one of the largest datasets ever used for financial forecasting, com-

prising approximately two billion observations that enable model training at the international level

and testing across major markets, including the United States, Hong Kong, Taiwan, South Korea,

Germany, the United Kingdom, India, and Australia. This extensive coverage supports a rigorous

    1
      In Das et al. (2024), TimesFM is used as the abbreviation for time series foundation model. However, most of the
recent literature adopts TSFM as the standard abbreviation for time series foundation model. Accordingly, in this paper,
we use ‘TSFM’ as the generic term for time series foundation models, and reserve ‘TimesFM’ to refer to the specific
model of Das et al. (2024).
    2
      Throughout this study, ensemble models refer specifically to tree-based ensemble models.


                                                           1
evaluation of TSFMs and benchmark models, examining their robustness and generalizability across

diverse market structures and institutional environments. We assess model performance from both

statistical and economic perspectives, with statistical evaluation based on out-of-sample forecasting

metrics under an expanding-window design, and economic evaluation translating forecasts into port-

folio returns. By combining global data with more than three decades of daily observations, this study

provides robust evidence on the potential and limitations of TSFMs for financial forecasting.

   We begin by evaluating the performance of benchmark models in forecasting next-day excess re-

turns using historical return information. This evaluation is crucial, as it establishes the foundation for

assessing the predictive capacity of TSFMs. Nevertheless, such benchmarking is frequently overlooked

in the TSFM literature, where model comparisons are typically performed on generic datasets that

fail to capture the unique characteristics of financial time series. Across rolling estimation windows

of 5, 21, 252, and 512 trading days and from 2001 to 2023, ensemble models (CatBoost, XGBoost,

and LightGBM) consistently outperform linear benchmarks (OLS, Lasso, Ridge, Elastic Net, and

principal component regression (PCR)) and neural network architectures across standard forecast-

ing performance metrics. Specifically, when averaged across all window sizes, the linear regression

model attains an out-of-sample R2 of −0.47%, while the CatBoost model achieves −0.10% for all

U.S. stocks. The direction accuracies are all just above 51% for the four windows. Also, small-

capitalization firms exhibit greater predictability compared to large-capitalization firms. Portfolios

constructed from ensemble-based forecasts also yield higher annualized returns and Sharpe ratios,

alongside smaller drawdowns and more favorable higher-moment characteristics. Notably, CatBoost

delivers the strongest risk-adjusted performance, outperforming both linear and neural network coun-

terparts. The best-performing CatBoost model, in terms of the Sharpe ratio, achieves an annualized

return of 46.50% and a Sharpe ratio of 6.79 when using a window size of 252. These results are

derived from a long–short portfolio constructed using the model’s daily predicted excess returns and

rebalanced on a daily basis, without accounting for transaction costs.

   Turning to TSFMs, our empirical analysis focuses on two widely adopted TSFMs: Chronos (Ansari

et al., 2024) and TimesFM (Das et al., 2024). We begin by documenting that off-the-shelf pre-trained

TSFMs perform weakly in zero-shot forecasting of daily excess returns, underperforming strong en-

semble models such as CatBoost and LightGBM. For both Chronos and TimesFM families, their

performance gradually improves as the larger model and wider window size are used. The Chronos

(large) model with 512 past excess returns generates out-of-sample R2 of −1.37% and directional accu-

racy just above 51%, while the TimesFM (500M) model attains R2 of −2.80% and directional accuracy

just below 50%. However, across all window sizes, off-the-shelf pre-trained TSFMs deliver markedly

                                                    2
lower R2 than benchmarks. Also, the annualized returns of the long–short portfolios constructed using

Chronos (large) and TimesFM (500M), based on a window size of 512, decline to 20.17% and −1.47%,

respectively. Extending the analysis to twelve additional TSFM architectures yields generally simi-

lar results, reinforcing the robustness of these findings. Nonetheless, some evidence of generalization

emerges among TSFMs pre-trained on larger-scale datasets. Next, fine-tuning of these pre-trained

models on financial data yields limited improvements and fails to close the performance gap with

benchmarks. Most fine-tuned TSFM performance deteriorates, except for Chronos (large). However,

this improvement does not translate into economic gains. Furthermore, when focusing on goodness-of-

fit, fine-tuning TSFMs on financial data once again does not fully close the performance gap relative

to benchmark models.

   Subsequently, we pre-train the TSFMs from scratch for each year using only the financial data

available up to that point. This procedure ensures that the models are not exposed to information

from future periods, thereby preventing look-ahead bias, an issue that may arise when employing

off-the-shelf TSFMs. We find that TSFMs pre-trained from scratch achieve substantial gains in both

predictive accuracy and portfolio performance. Considering the Chronos (small) model, its R2 for

window size 5 increases substantially to −3.18% from −77.07%, and for window size 512, it increases

to −0.59% from −1.27%. However, even when pre-trained from scratch on financial data, TSFMs still

remain less effective in terms of goodness-of-fit than benchmark models. In terms of annualized return

and Sharpe ratio, the Chronos (small) model achieves 36.84% and 5.42, respectively, using a window

size of 512, while the TimesFM (20M) model attains 30.36% and 3.66 under the same conditions.

This highlights the importance of domain-specific pre-training and alignment with financial data.

Moreover, when comparing different window sizes, the results again indicate that the performance of

TSFM improves with longer windows, whereas the benchmark models perform relatively better over

shorter windows. For instance, the TimesFM (20M) model attains −18.22% annual return predicting

with only 5 past returns, while it attains 30.36% with a window size of 512. Furthermore, across all

model classes, including benchmark, zero-shot, fine-tuned, and pre-trained TSFMs, the long leg of the

portfolio consistently outperforms the short leg.

   Expanding the training universe from U.S. to global markets yields mixed results for the benchmark

models. The linear model gains an additional 0.43–0.60% R2 when expanding the dataset, turning

all R2 positive. Other benchmark models (Lasso, Ridge, and NN) also improve quite remarkably,

while the ensemble models (CatBoost, XGBoost, and LightGBM) deteriorate marginally. However,

the direction accuracies and portfolio performance mostly weaken for all models. When combined

with financial factors and synthetic data augmentation, TSFMs exhibit consistent improvements in

                                                    3
both statistical and economic outcomes, achieving higher accuracy and stronger risk-adjusted portfolio

returns. Specifically, the Chronos (small) model achieves the highest directional accuracy of 51.74%,

compared with 51.16% obtained by CatBoost using a window size of 512. The annualized return and

Sharpe ratio change to 41.89% and 6.78, respectively, compared with 47.25% and 6.46 achieved by

CatBoost under the same window size. Moreover, our analysis underscores the critical importance of

hyperparameter tuning: with appropriate optimization, TSFMs are capable of outperforming bench-

mark models even without scaling the dataset. Finally, examining performance over time shows that

both TSFMs and benchmark models experience gradual degradation in portfolio performance, reflect-

ing evolving market dynamics and rising efficiency. However, the decline is markedly slower and less

severe for TSFMs. We also extend the main empirical tests to seven major non-U.S. markets, where

we observe broadly consistent results with those obtained in the U.S.

   Taken together, the evidence shows that generic time series pre-training does not directly transfer

to financial domains, and that finance-native pre-training and data scaling are essential for realizing

the full potential of TSFMs in financial forecasting. In this sense, TSFMs represent a new class of

models for financial forecasting, combining the scalability and adaptability of foundation architectures

with domain-specific learning objectives. To advance future research and foster transparency and

reproducibility, we publicly release our models as open-source resources.


1.1   Related Work

Our paper contributes most directly to research on return prediction for stocks, particularly on how

historical returns can predict future performance. The momentum (Jegadeesh and Titman, 1993)

and reversal effects (Jegadeesh, 1990) are among the most prominent, constructed by sorting stocks

on past cumulative returns. Building signals from moving averages is another simple yet effective

approach. For instance, Brock et al. (1992) find strong support for moving-average and trading-range

break strategies. Neely et al. (2014) also show that technical indicators such as moving averages,

momentum, and volatility measures possess predictive power for the equity risk premium. Moskowitz

et al. (2012) document a time series momentum effect, showing that an asset’s own past excess re-

turns predict its future performance. Extending this evidence, Menkhoff et al. (2012) show that

currency momentum delivers high abnormal returns unexplained by standard risk factors, while As-

ness et al. (2013) find that value and momentum premia are pervasive across global asset classes

and linked to common risk sources.       Barroso and Santa-Clara (2015) highlight that momentum

strategies exhibit time-varying risk and occasional large crashes, but volatility scaling can improve

risk-adjusted performance. Gupta and Kelly (2018) demonstrate that momentum also exists among


                                                   4
factors themselves, referred to as factor momentum, which generates strong abnormal returns and com-

plements traditional momentum. Liu and Tsyvinski (2021) demonstrate that cryptocurrencies also

exhibit strong momentum driven by market-specific factors such as investor attention. More recently,

Ehsani and Linnainmaa (2022) show that momentum largely reflects factor timing: factor returns are

positively autocorrelated, this autocorrelation concentrates in the leading principal components, and

a factor-momentum strategy explains a substantial share of stock-level momentum.

   Building on this literature, subsequent research has explored alternative approaches for capturing

nonlinear and dynamic relationships in return predictability. Instead of relying on moving averages,

non-parametric regression techniques have been applied to examine the predictive power of technical

indicators constructed from price–volume information. For example, Lo et al. (2000) use kernel regres-

sions to model nonlinear dependencies between past prices and future returns. With the availability

of larger datasets and advances in computation, a new generation of ML and deep learning (DL)

models now learn nonlinear interactions and temporal dependencies directly from raw financial time

series, delivering strong out-of-sample forecasts when properly tuned. These studies typically employ

a multivariate framework that incorporates a broader set of exogenous variables to enhance predictive

accuracy. For instance, Gu et al. (2020) examine the predictive performance of various ML models

including regularized linear regressions, tree-based models, and neural networks, while Leippold et al.

(2022) conduct a similar analysis in the Chinese market. Extending this line of research, Chen et al.

(2024) show that DL architectures can capture complex nonlinear relations and interactions in asset

pricing. Li et al. (2025) demonstrate that ML models trained on a comprehensive universe of financial

signals achieve economically meaningful out-of-sample performance only when features are carefully

designed, and Kelly et al. (2025) propose new asset pricing models that embed Transformer archi-

tectures into the stochastic discount factor, enabling context-aware cross-asset information sharing

and yielding substantial reductions in pricing errors and improvements in out-of-sample Sharpe ratios.

Complementing these empirical advances, Kelly et al. (2024) provide a theoretical justification for the

superior performance of complex models, proving that out-of-sample forecast accuracy and portfolio

performance increase with model complexity when appropriate regularization is applied.3 Overall,

   3
      This claim has sparked debate. For example, Berk (2023) argues that the theoretical framework in Kelly et al. (2024)
is too narrow to be of practical use in financial economics and that its assumptions are inconsistent with equilibrium
asset pricing. Similarly, Buncic (2025) re-examines the empirical results and shows that the findings are largely driven by
modeling choices, notably the zero-intercept restriction and the aggregation method. Nagel (2025) demonstrates that, in
high-complexity ridgeless Random Fourier Features (RFF) settings with short training windows, the approach effectively
reproduces a volatility-timed momentum strategy rather than uncovering genuine predictive signals. In addition, Cartea
et al. (2025) develop a theoretical and empirical framework showing that when predictive features are measured with
noise, increasing model complexity can degrade out-of-sample R2 and portfolio Sharpe ratios, thereby highlighting a
‘limited virtue of complexity.’ In response to these critiques, Kelly and Malamud (2025) provide theoretical and empirical
clarifications, showing that the main findings of Kelly et al. (2024) remain robust and extending the analysis to include
limits to learning and the concept of ensemble complexity.


                                                            5
these studies show that ML models can successfully predict the cross-section of stock returns based on

historical data, particularly for small-cap stocks, thereby challenging the Efficient Market Hypothesis

(see also Martin and Nagel, 2022). We extend the existing literature by leveraging TSFMs to scale

models beyond previously tested limits and to analyze how higher levels of parameterization influence

asset pricing performance.

   Another emerging trend in financial ML is the development of domain-specific language models

tailored to financial text. One of the earliest and most influential examples is FinBERT (Huang

et al., 2023), a pre-trained model specifically adapted for finance that enhances information extrac-

tion and sentiment analysis within accounting and financial documents. Building on this direction,

Rahimikia and Drinkall (2024) develop domain-specific LLMs aimed at mitigating look-ahead bias and

demonstrate that targeted pre-training at smaller model scales can match or even outperform large

general-purpose models such as the LLaMA series in trading tasks. This line of research is further

advanced by He et al. (2025), who introduce chronologically consistent language models trained on

time-stamped data to ensure that only information available at each point in time is used. Their

findings indicate that look-ahead bias can be reduced while maintaining strong performance in both

language and financial prediction tasks. Together, these studies underscore the growing focus on tem-

porally aware and domain-adapted LLMs, a consideration that is equally important for TSFMs, whose

architectures are largely derived from LLM principles. Accordingly, ensuring temporal consistency and

domain alignment in TSFMs represents another key focus of this study.

   More recently, foundation and generative models have emerged as powerful approaches for time se-

ries forecasting. Foundation models are large Transformer-based architectures pre-trained on extensive

and heterogeneous collections of time series data to learn generalizable temporal representations that

can be transferred across different series and sampling frequencies with minimal fine-tuning. Inspired

by LLMs such as InstructGPT (Ouyang et al., 2022), LLaMA (Touvron et al., 2023), and DeepSeek

(Liu et al., 2024), these TSFMs adapt tokenization and embedding strategies originally developed for

text to the continuous, multivariate, and irregularly sampled nature of temporal data. Representative

examples include Chronos (Ansari et al., 2024), which applies discrete tokenization with a Transformer

backbone, and TimesFM (Das et al., 2024), which employs continuous embeddings and a decoder-only

design. Collectively, these architectures demonstrate strong cross-domain generalization and enable

zero-shot and few-shot forecasting capabilities across diverse temporal domains.

   In parallel, generative models such as generative adversarial networks (GANs) and diffusion mod-

els extend financial forecasting beyond point predictions to model the full conditional distribution of



                                                  6
returns. Notable examples include Quant GAN (Wiese et al., 2020), which generates realistic return

paths while preserving key statistical properties of financial data; Fin-GAN (Vuletić et al., 2024),

which incorporates economics-informed objectives for regime-aware scenario generation; Signature-

Wasserstein GANs (Liao et al., 2024), which leverage path signatures to reduce the min-max game to

supervised learning, enhancing the training stability; and FTS-Diffusion (Huang et al., 2024), which

models scale-invariant temporal patterns and enhances predictive robustness through data augmen-

tation. Moreover, TSFMs are inherently capable of simulating future trajectories and can thus be

viewed as conditional generative models. Together, these developments mark a paradigm shift from

traditional point estimation toward probabilistic forecasting. Despite these advances, empirical evalu-

ation of TSFMs and generative approaches in financial contexts remains limited. This study addresses

this gap by providing a comprehensive assessment of their applicability and performance in financial

forecasting, systematically benchmarking zero-shot, fine-tuned, and from-scratch pre-training regimes

of TSFMs across a large number of assets.

    The remainder of this paper is organized as follows. Section 2 introduces the core concepts under-

lying TSFMs, detailing their architectures and training paradigms. Section 3 outlines the proposed

methodology, including the modeling framework, evaluation metrics, and experimental setup. Sec-

tion 4 describes the data sources, cleaning procedures, and computational resources used to conduct

our experiments. Section 5 presents the main numerical findings, comparing benchmark models with

TSFMs across various configurations and data volumes. Finally, Section 6 summarizes the key insights,

discusses implications for future research, and concludes the study.



2     Time Series Foundation Models

We begin by introducing the fundamentals of LLMs in Section 2.1, which serve as the basis for TSFMs.

We then present two representative TSFMs, namely Chronos (Ansari et al., 2024) and TimesFM (Das

et al., 2024) in Section 2.2 and Section 2.3, respectively. We also describe ten additional TSFMs used

in our numerical experiments in Section D. For a comprehensive overview, readers are referred to Liang

et al. (2024), which categorizes TSFMs by their embedding design, architecture choice, pre-training

objective, and adaptation strategy.


2.1    Large Language Models

LLMs are powerful DL models that generate text by predicting the next word in a sequence based on

the context of preceding words. They operate on tokenized text inputs and produce text outputs, with



                                                  7
the Transformer architecture serving as their core building block. LLMs are typically trained using an

unsupervised learning objective on massive corpora, allowing them to capture rich linguistic patterns.

This enables them to perform a wide range of language tasks such as translation, summarization,

question answering, and content generation. Due to their versatility and generalization capabilities,

LLMs are often considered foundation models for natural language processing (NLP).


2.1.1   Tokenization

In language modeling, raw text data consists of sequences of words, which are typically represented as

tokens. Tokenization refers to the process of segmenting and mapping an input string into a sequence

of integer tokens (z1 , · · · , zT ), each drawn from a finite vocabulary V. This process is often conducted

by using subword (Kudo, 2018) or byte-pair encoding schemes (Sennrich et al., 2016). Tokens are

then mapped to continuous vector embeddings via a learned embedding matrix. Positional encodings

are added to preserve the order information that would otherwise be lost due to the permutation

invariance of the Transformer architecture.


2.1.2   Network Architecture: Transformer

The Transformer (Vaswani et al., 2017) is a sequence-to-sequence model based on the self-attention

mechanism. It maps an input sequence of embeddings to an output sequence of contextual repre-

sentation. Sequence modeling is achieved through stacked layers of self-attention and position-wise

feed-forward networks, each wrapped with residual connections and layer normalization. The core

building block of the Transformer is the multi-head self-attention (MHSA) module, in which each

attention head computes a weighted aggregation of input features based on their pairwise similarities.

Formally,


                                                  ˜
                        MHSA : RT ×d → RT ×d ;

                                     X 7→ O := Concat(head1 , . . . , headh ) W O ,                     (1)


where d and d˜ are the feature dimension of the input and output sequence, respectively, and T is the

time dimension. For head i ∈ {1, . . . , h}:


                                Qi = XWiQ ,    Ki = XWiK ,     Vi = XWiV ,                              (2)




                                                      8
where WiQ , WiK , WiV ∈ Rd×dk are learnable projection matrices. The attention output for head i is

given by:
                                                      Qi K ⊤
                                                            
                                     headi = Softmax √ i Vi ,                                         (3)
                                                         dk

where Vi ∈ RT ×dk and the Softmax operation is applied row-wise across the time dimension to yield

normalized attention weights. The output O is obtained by concatenating all heads across the feature
                                                                      ˜
dimension and applying the learnable matrix W O ∈ R(hdk )×d . The complete set of learnable param-

eters in the MHSA module is {WiQ , WiK , WiV }i∈{1,··· ,h} ∪ W O . Yu et al. (2025) analyze Transformers

for time series data through the lens of rank structure, showing that time series embeddings tend to

exhibit low-rank properties. This inherent structure makes attention layers more compact and com-

putationally efficient, providing insight into why Transformers can be effectively compressed for time

series forecasting.


2.1.3    Training and Inference

Given a sequence of tokens z1:T drawn from a vocabulary V, an LLM is typically optimized to maximize

the autoregressive log-likelihood:
                                               T
                                               X
                                         max         log pθ (zt |z<t ) ,                              (4)
                                          θ
                                               t=1

where z<t = (z1 , · · · , zt−1 ) and pθ denotes the conditional distribution of tokens, parametrized by θ.

In practice, this objective is equivalent to minimizing the cross-entropy loss, which is optimized using

stochastic gradient–based methods such as Adam (Kingma and Ba, 2015) or its variants.

   At inference time, the model rolls out forecasts autoregressively. As a generative probabilistic

model, the LLM simulates the next token based on the learned conditional distribution, appends it to

the sequence, and repeats until the desired horizon is reached. Consequently, one can estimate various

statistical properties of the predictive distribution, such as means, variances, or quantiles, by drawing

multiple samples via Monte Carlo simulation.


2.2     Chronos

Chronos (Ansari et al., 2024), proposed by Amazon, is one of the most popular foundation models for

time series. It closely follows the LLM architecture, differing primarily in the tokenization scheme,

which is adapted from textual data to handle continuous-valued time series inputs. Therefore, it is

possible to integrate a variety of LLM backbones within this framework, since the overall Transformer-

based architecture remains largely unchanged.




                                                        9
Tokenization.      Consider a time series x1:C+H = [x1 , ..., xC+H ], where the first C steps are the input

context used to predict the next H steps. To leverage the forecasting capacity of LLMs, Chronos

transforms the continuous real-valued observations x into discrete tokens through a two-step process:

(1) scaling and (2) quantization. Heterogeneous scaling across time series data makes model optimiza-

tion challenging. Hence, one needs to map the time series values into a suitable range for quantization

by mean scaling. A series is normalized by the mean of the absolute values from the historical context,

as defined by the following transformation: x̃ is given by x̃ = xi /s and s = C1 C
                                                                                P
                                                                                 i=1 |xi |.


   The scaled time series then needs to be mapped to a finite set of tokens, by means of quantization,

in order to be processed by LLMs. The quantization function q : R 7→ {1, 2, ..., B} assigns each value

x̃ to a bin, given by:                         
                                               
                                               
                                               
                                               
                                               1    if − ∞ ≤ x̃ < b1 ,
                                               
                                               
                                               
                                               
                                               2
                                                    if b1 ≤ x̃ < b2 ,
                                     q(x̃) =                                                           (5)
                                               ..
                                               
                                               
                                               
                                                .
                                               
                                               
                                               
                                               
                                               B
                                                    if bB−1 ≤ x̃ < ∞,

where (bi )i denote uniformly spaced bin edges. At inference time, each predicted token j is mapped

to its corresponding bin center d(j) = cj through dequantization, and then rescaled by s to obtain the

final forecast. The quantization–dequantization process constrains predictions within [c1 , cB ], which

corresponds to the range [−15s, 15s] in Chronos’s default configuration. The bin width is 30s/(B − 1),

implying that a large s reduces precision by grouping nearby values into the same token, whereas a

small s risks producing values outside the representable range.


Framework.       Similar to LLMs, Chronos adopts the cross-entropy loss function and a flexible Trans-

former backbone, which can be either encoder–decoder or decoder-only; in our experiments, we use

the T5 architecture (Raffel et al., 2020). Analogous to language models that generate text autore-

gressively, Chronos predicts future time series values by recursively sampling from the conditional

categorical distribution over tokenized observations. Each predicted token is then converted into a

real-valued number through a dequantization and rescaling process tailored for time series data. Be-

cause the model outputs a full probability distribution at each step, it enables probabilistic forecasting

and uncertainty quantification, which are particularly relevant in financial applications.




                                                      10
2.3   TimesFM

TimesFM (Das et al., 2024), proposed by Google, is another representative TSFM, differing from

Chronos primarily in its continuous representation and training objective. Whereas Chronos discretizes

time series data via scaling and quantization to produce tokenized sequences suitable for LLM-style

autoregressive modeling, TimesFM represents time series directly in a continuous latent space and is

optimized under a supervised regression loss. The model naturally extends to multivariate time series

and retains a strong connection to LLMs through its Transformer-based architecture.


Embedding.      Recall that x1:T is a d-dimensional time series of length T . Instead of tokenizing

each scalar observation, TimesFM partitions the input into a sequence of patches, where each patch

pi ∈ RL×d contains L consecutive time steps:


                     pi = [x(i−1)L+1 , x(i−1)L+2 , . . . , xiL ],   i = 1, . . . , M := T /L.        (6)


For simplicity, in Equation (6), we assume that T is an integer multiple of L; otherwise, the sequence

can be padded to satisfy this condition. This patching mechanism is analogous to the sliding-window

approach commonly used in time series analysis, allowing each patch to serve as a ‘token’ that captures

local temporal dependencies. Each patch defined on the non-overlapping time interval is encoded into

a continuous embedding using a residual network fϕ , typically implemented as a multilayer perceptron

(MLP):

                                           ei = fϕ (pi ),    ei ∈ Rh ,                               (7)

where h is the embedding dimension. To improve generalization across different context lengths,

TimesFM applies a random masking strategy that probabilistically omits certain patches, ensuring

the model encounters all possible prefix lengths during training. Note that the patch length of the

input and output sequences need not be identical.


Framework.      The resulting embeddings [e1 , . . . , eM ] are then passed through a stacked Transformer

decoder with causal self-attention, whereby the model attends only to preceding embeddings in the

sequence to predict an output in the future; this preserves the information flow in time series. The

model outputs a continuous forecast embedding p̂i+1 , which is mapped back to the time domain

through another residual network gψ :

                                                p̂i+1 = gψ (hi ),                                    (8)

where hi denotes the hidden state of the Transformer at step i.


                                                        11
    Unlike Chronos, which is trained with a cross-entropy loss over discrete tokens, TimesFM is opti-

mized directly on the continuous prediction error using the mean squared error (MSE) loss between

the observed output pi and the model-estimated p̂i at the forecasting horizon. During inference,

TimesFM supports multi-step forecasting through a rolling-window strategy, recursively feeding pre-

dicted patches back into the model to generate longer-horizon forecasts. This continuous formulation

eliminates the need for quantization or dequantization, allowing TimesFM to learn smooth represen-

tations and capture fine-grained temporal variations without discretization artifacts.



3       Methodology

3.1         Problem Setup

Under the probability space (Ω, F, P), consider a financial market consisting of M assets. Let S (i) :=
      
   (i)
  St      denote the price series of the ith asset, where T is the range of the time index on a daily
         t∈T
                                                                         (i)
basis and i ∈ {1, · · · , M } is the asset index. Let Dt                       denote the cash dividend (or other cash

distribution) paid by asset i between time t − 1 and t. The corresponding one-day return is defined
                  (i)     (i)    (i)
      (i)        St +Dt −St−1
by rt       :=            (i)          . Next, we compute each firm’s daily excess return by subtracting the daily
                        St−1
risk-free rate from its total daily return. The daily excess return for firm i on day t is therefore defined
      (i),ex        (i)         (d)            (i)                                                     (d)
as rt          = rt − rf,t , where rt                is the one-day return, including dividends, and rf,t is the daily

risk-free rate. We are interested in simulating the distribution of the next excess return of the ith
                                                                               (i)
asset, given the information of the asset up to time t, i.e., S1:t , or equivalently, the past excess return
                                (i),ex
series, denoted by r1:t                  .

    We further assume that the conditional law of one-step excess returns is identical across assets,
                 (i),ex     (i),ex
that is, P(rt+1 |r1:t                  = r) does not depend on i. This assumption implies a homogeneous market

structure where individual asset dynamics share a common recursive pattern. Under this setting,

a single conditional generator can be trained using pooled data from all assets and then applied

universally to simulate future returns for any asset. In practice, certain normalization of the return

series might be applied to ensure that this assumption is valid.

    Stochastic TSFM. Some TSFMs, such as Chronos, are conditional generative models capable of

sampling future return paths given past observations. Let Gθ : Z × RC → R denote a conditional

generative model parameterized by θ, where Z is the noise space and C is the length of the lagged

time series. The aim of Gθ is to approximate the conditional distribution of the next excess return of




                                                                  12
any arbitrary asset given the lagged values rt−C+1:t , i.e.,


                                             ex
                                     Gθ (Z, rt−C+1 , . . . , rtex ) ≈ P(rt+1
                                                                         ex
                                                                             |Ft ),                   (9)


where Ft denotes the sigma-algebra (information set) generated by the historical returns r1:t . Once

the generative model is trained, it can be used for various downstream tasks. For instance, one can

estimate the conditional expectation of the next excess return via Monte Carlo sampling, i.e.,

                                                N
                              ex            1 X           ex                            iid
                           E[rt+1 |Ft ] ≈       Gθ (Zn , rt−C+1 , . . . , rtex ),     Zn ∼ Z,        (10)
                                            N
                                               n=1


where N is the number of Monte Carlo samples and Zn is independently drawn from the noise vector

Z. Similarly, one can estimate the probability of an upward or downward movement of the next excess

return from the empirical distribution of the Monte Carlo samples.

   Deterministic TSFM. Deterministic TSFMs such as TimesFM directly output a point prediction

for the next return. When no distributional information is provided, the sign of this point estimate

is often used as a proxy for predicting the direction of the next movement. However, if the true

conditional distribution is asymmetric, the sign of the conditional mean may not correctly indicate

the most likely direction of return movement.


3.2     Time Series Foundation Models: Training and Inference

The TSFMs, described in Section 2, can be applied to the return-forecasting problem described above.

Based on the dataset used for training and model initialization, the TSFMs can be further categorized

into three types: (1) pre-trained models, (2) fine-tuned models, and (3) models pre-trained from

scratch. For our above return prediction task, we have the financial time series data, denoted by

Dfin = {S (i) }N
               i=1 .
                 fin




3.2.1    Pre-Trained Model (Zero-Shot Inference)

                       N
Let Dpre = {X (i) }i=1
                     pre
                         denote a large collection of heterogeneous time series datasets used for pre-

training. This pre-training dataset is massive, encompassing time series with diverse statistical char-

acteristics such as seasonality, autocorrelation, and volatility dynamics. Typically, Dpre has time series

from various domains, and also includes a large amount of synthetic time series. The model parame-

ters θpre are obtained by minimizing the loss function which is generic to time series of various kinds.

The pre-trained model Gθpre thus learns domain-agnostic temporal structures such as seasonality,

volatility clustering, and cross-asset dependencies. In zero-shot inference, Gθpre is directly applied to

                                                           13
a new dataset without parameter updates, leveraging its generalization ability to generate predictive

distributions across unseen domains. In our case, we apply Gθpre to Dfin for generating the future

return.


3.2.2     Fine-Tuned Model

Given a pre-trained initialization θpre , fine-tuning adapts the model to a specific downstream dataset

(e.g., Dfin in our case) by solving:


                                 θfin = arg min E(X,Y )∼Dfin L(Gθ (X), Y ) ,                        (11)
                                             θ



where L is a supervised loss tailored to the target objective (e.g., conditional return generation).

The pre-trained parameters may serve as a strong prior, accelerating convergence and enhancing

generalization when Dfin is relatively small. This transfer-learning setup balances domain-specific

adaptation with the preservation of foundational temporal knowledge. In our case, we adopt the
                                                                                   ex
original loss function used in the TSFM with training pairs defined as (X, Y ) = (rt−C+1:t    ex ) for
                                                                                           , rt+1

fine-tuning, and set all the model parameters trainable.


3.2.3     Models Pre-Trained from Scratch

Instead of using a pre-trained model for parameter initialization, model parameters are randomly

initialized, θ0 ∼ P0 , and trained solely on Dfin :


                                                                      ex          ex
                                                                                     
                        θscratch = arg min E(rt−C+1:t+1
                                              ex        )∼Dfin L Gθ (rt−C+1:t ), rt+1 ,             (12)
                                        θ



where L is the loss function of the TSFM. Pre-training from scratch typically requires larger datasets

and greater computational resources, as the model must learn temporal dependencies without any

prior knowledge. In our study, as the same loss function L is used for fine-tuning in Section 3.2.2,

the main difference between Section 3.2.3 and Section 3.2.2 lies in the parameter initialization. Pre-

training learns all parameters from scratch, whereas fine-tuning starts from a pre-trained model and,

in some applications, may update only the final layers while freezing earlier ones.


3.3     Evaluation Metrics

To evaluate different aspects of generative models for return prediction, we consider a range of test

metrics, grouped into two categories: (i) forecasting performance and (ii) portfolio performance.




                                                      14
3.3.1    Forecasting Performance Metrics

In our work, we focus on two forecasting performance metrics: (1) predicting the conditional mean of

future returns, and (2) predicting the probability of return direction (up or down). For the first metric,
                                             2
we employ the coefficient of determination (ROOS                                      2
                                                 ). In particular, our definition of ROOS follows the

out-of-sample metric used by Gu et al. (2020), defined as:

                                                          P       (i),ex       (i),ex 2
                                         2                  i,t (rt+1 − r̂t+1 )
                                        ROOS =1−               P         (i),ex 2
                                                                                        ,                                (13)
                                                                   i,t (rt+1 )


         (i),ex                                                                                       (i),ex
where rt+1        denotes the realized excess return of asset i at time t + 1, and r̂t+1                       represents the
                                                2
corresponding predicted value. This version of ROOS benchmarks forecasts against a naive prediction of

zero.4 Throughout this study, we report ROOS
                                         2   in percentage terms. For the second group of metrics, we

use classification accuracy (overall accuracy) and the macro-averaged F1 score5 as evaluation metrics

for the binary classification of return direction. In addition to overall classification accuracy, we

report upward accuracy and downward accuracy, which correspond respectively to cases where the

realized future return is positive or negative. All directional accuracy measures are likewise reported

in percentage terms.


3.3.2    Portfolio Performance Metrics

Following standard empirical asset pricing procedures for portfolio sorting, we translate the model’s

forecasts into an implementable long–short trading strategy. At the end of each trading day t, the
                                                                               (i),ex
model generates a one–day–ahead predicted excess return rbt+1                           for each stock i in the investable
                                                 (i),ex
universe. We then rank all stocks by rbt+1                and divide them into ten deciles. A zero-cost, equal-

weighted long–short portfolio is constructed by going long the top-decile stocks and short the bottom-

decile stocks. The portfolio is rebalanced daily.

                                                          LS } provides a direct, economically in-
   The realized long–short portfolio return time series {rt+1

terpretable measure of the model’s cross-sectional ranking performance. Significant positive returns

indicate that the model’s predicted-return ranking successfully identifies near-term winners and losers.

   4
      Gu et al. (2020) argue that using the historical mean as a baseline is inappropriate for individual stock returns,
because historical mean excess returns are extremely noisy and can make even weak models appear to perform well.
By contrast, benchmarking against zero avoids overstating predictive performance and provides a more stringent and
economically meaningful test of out-of-sample forecasting accuracy.
    5
      The macro-averaged F1 score is defined as the unweighted mean of the class-specific F1 scores, computed inde-
pendently for each class. It jointly accounts for precision, the proportion of correctly predicted positive (upward or
downward) excess return trends among all predicted positives, and recall, the proportion of correctly predicted positives
among all actual positives. This macro-averaging approach ensures balanced evaluation ofP directional forecasting perfor-
                                                                                            C   2 Precisionc ×Recallc
mance across both upward and downward excess return trends. Formally, macro-F1 = C1         c=1 Precisionc +Recallc , where
C denotes the number of classes (here, C = 2 for up and down excess return trends).


                                                              15
We report a comprehensive set of portfolio performance metrics that capture profitability, risk, and

distributional characteristics. Specifically, the annualized return, standard deviation, and Sharpe ratio

summarize mean performance and volatility-adjusted efficiency. The daily return (bps) provides a di-

rect measure of the average daily economic magnitude of the long–short strategy. To assess downside

risk, we include both the overall maximum drawdown (Max DD) and the largest single-day loss (Max

DD (1-day)). Finally, the skewness and kurtosis statistics describe the asymmetry and tail risk of the

portfolio return distribution. Annualized return, standard deviation, Max DD, and Max DD (1-day)

are reported in percentage terms.



4       Data and Computational Resources

4.1     Data Source

We construct a comprehensive panel of daily firm-level excess returns spanning 1990–2023 across 94

countries.6 The raw equity returns are adjusted for delisting effects, corporate actions, and market

conventions to produce a clean, consistent measure of daily stock performance net of the local risk-

free rate. Daily price and return information are obtained from two complementary sources. For the

U.S., all equity data originate from the Center for Research in Security Prices (CRSP) database. For

non-U.S. markets, we rely on Compustat global daily security files, which provide comparable firm

identifiers, prices, and share counts. When a security is available in both CRSP and Compustat, the

CRSP record is given priority because of its broader coverage of corporate actions, higher data quality,

and inclusion of delisting returns.

    Before computing excess returns, the daily data undergo a sequence of cleaning and harmonization

procedures. Only listings on the primary trading venue of each country are retained to avoid duplicate

records for cross-listed securities. Securities with nonpositive or missing prices are removed, and

returns outside a range of ±1000% are treated as data errors. Observations belonging to the bottom

five percent of the market capitalization distribution within each country-day are excluded to limit

the influence of microcaps, which often display irregular trading behavior and excessive volatility.

    When delisting information is available, the reported delisting return is incorporated on the final

trading day of the firm. In cases where a delisting is recorded but the associated return is missing, a

    6
     One methodological concern that may arise pertains to our choice of data frequency. While most prior empirical asset
pricing studies employ monthly excess returns and emphasize multivariate return predictability using macroeconomic or
firm-level variables, our analysis focuses on daily excess return forecasting. The use of daily data inherently limits the
analysis to a univariate setting, as most predictive factors are unavailable or unreliable at this frequency. This study
evaluates zero-shot and fine-tuning approaches and further examines the feasibility of pre-training TSFMs from scratch,
which requires a large number of observations. Monthly data do not provide a sufficiently large sample for this purpose;
therefore, we employ daily data to ensure the feasibility of the analysis.


                                                           16
                      Table 1: Cumulative Observations and Security Coverage

                                                        U.S.
                    Year    Observations      Securities     Year   Observations      Securities
                    2000        86.82           35.76        2012      133.62           48.40
                    2001        90.77           36.51        2013      137.73           49.57
                    2002        94.62           37.28        2014      141.91           50.84
                    2003        98.40           38.05        2015      146.15           52.01
                    2004       102.21           39.13        2016      150.40           53.02
                    2005       106.06           40.15        2017      154.61           54.19
                    2006       109.91           41.35        2018      158.85           55.38
                    2007       113.84           42.89        2019      163.12           56.46
                    2008       117.82           43.78        2020      167.47           57.87
                    2009       121.71           44.53        2021      172.10           60.71
                    2010       125.61           45.54        2022      176.96           62.25
                    2011       129.55           47.01
                                                    All Markets
                    Year    Observations      Securities     Year   Observations      Securities
                    2000       132.96           67.40        2012      299.14           129.36
                    2001       143.05           73.79        2013      317.02           134.83
                    2002       153.45           77.35        2014      334.59           141.18
                    2003       163.99           80.78        2015      352.77           147.31
                    2004       174.79           84.55        2016      371.48           154.04
                    2005       186.16           89.13        2017      390.82           160.93
                    2006       200.20           94.61        2018      410.77           167.67
                    2007       215.11           101.68       2019      430.88           174.17
                    2008       231.03           106.50       2020      451.73           182.25
                    2009       247.17           110.70       2021      473.75           194.19
                    2010       263.82           116.18       2022      496.89           204.09
                    2011       280.96           122.32

                  Note: This table presents the cumulative number of observations and unique
                  securities for the U.S. in the top panel, and for all markets combined in the
                  bottom panel. The years 2000 to 2022 represent individual years for which
                  separate models are trained. Observation counts are reported in millions,
                  and security counts in thousands.


return of −30% is assigned following the standard convention in the literature to mitigate survivorship

bias. To maintain consistency between CRSP and Compustat records, daily returns from Compustat

are winsorized using the CRSP return distribution as a benchmark. Specifically, Compustat returns

above the 99.9th percentile or below the 0.1st percentile of the corresponding CRSP distribution for

the same day are capped at those values. This ensures that extreme observations in international

markets do not distort the overall return distribution. Following data cleaning, excess returns are

computed as described in Section 3.1.

   Table 1 presents the cumulative number of observations (excess returns) and unique securities for

the U.S. in the top panel, and for all markets combined in the bottom panel.7 The years 2000 to

2022 represent individual years for which separate models are trained. The training data begin in

1990. Observation counts are reported in millions, and security counts in thousands. The 2022 models

employed the most extensive dataset, comprising a maximum of 176.96 million and 496.89 million

   7
    The complete list of country and region codes is provided in Table A.1. In total, we compile global data from 94
countries and regions to construct a single dataset for model training for each year from 2000 to 2022.


                                                        17
observations for the U.S. and global data, respectively. The corresponding securities counts were

62,250 for the U.S. and 204,090 for all markets combined.

   Figure A.1 reports the cumulative number of observations and unique securities for the U.S. market,

while Figure A.2 presents the corresponding values for the combined global sample. The light-shaded

region represents the sample period starting in 1990 (expanding window) used to train the predictive

models, while the dark-shaded region denotes the period from 2001 to 2022, during which the predictive

models are trained on a yearly basis. The data start in 1990 because of the lower quantity and quality

of data prior to that year, especially for global markets.8

   As another source of data, we use all factors from Jensen et al. (2023) (JKP factors), organized

into thirteen conceptual clusters that reflect distinct economic mechanisms. The main clusters include

‘Investment’, ‘Value’, ‘Low risk’, and ‘Quality’, which capture firms’ growth, valuation, risk, and prof-

itability characteristics. Other clusters such as ‘Seasonality’, ‘Profit growth’, ‘Leverage’, ‘Profitability’,

‘Momentum’, ‘Debt issuance’, ‘Accruals’, ‘Short-term reversal’, and ‘Size’ represent additional aspects

of firm behavior, including cyclical patterns, financial structure, and return dynamics. Together,

these 153 monthly factors proxy for underlying economic risks and behavioral patterns that shape

cross-sectional returns.

   Table 2 presents the annual observations and security coverage of the JKP factors. The top panel

reports data for the U.S., while the bottom panel aggregates data from all markets. As before, the

observation counts are reported in millions, and security counts in thousands. The 2022 models

employed the most extensive dataset, comprising a maximum of 456.62 million and 1434.05 million

observations for the U.S. and global data, respectively. The corresponding securities counts were 33,180

for the U.S. and 102,820 for all markets combined. The larger number of observations results from

generating up to 153 factors per security. Figure A.3 compares the cumulative number of observations

and unique securities between the excess return data, the JKP data, and the combined dataset. The

maximum number of observations for all data together (Total) recorded in 2022 corresponds to 1930.95

million observations and 135,990 securities.9

    8
      The annual breakdown of cross-market excess returns is presented in Table A.2 and Table A.3, accompanied by
the corresponding annual breakdown of cross-market securities shown in Table A.4 and Table A.5. The first two tables
present the cumulative number of valid excess return observations by year and market, with values scaled in millions.
The second two tables also present the number of securities by year and market, with values scaled in thousands. The
numbers are presented cumulatively, showing the number of unique securities present up to and including each year. It
is evident from all tables that in the early years, the number of available observations, particularly for global markets, is
limited and in many cases close to zero. The sample size increases progressively over time as data coverage improves.
    9
      The annual breakdown of JKP observations is presented in Table A.6 and Table A.7, accompanied by the cor-
responding annual breakdown of JKP securities shown in Table A.8 and Table A.9. The first two tables present the
cumulative number of valid JKP observations by year and market, with all values scaled in millions. The second two
tables present the number of securities used to construct the JKP factors, with values scaled in thousands. The higher
number of observations and securities for JKP factors over time is clearly observable in all figures.


                                                             18
Table 2: Cumulative Observations and Security Coverage (JKP Factors)

                                        U.S.
     Year    Observations     Securities     Year   Observations     Securities
     2000       282.76          25.60        2012      384.81          28.99
     2001       293.08          25.85        2013      391.92          29.30
     2002       302.70          26.08        2014      399.11          29.70
     2003       311.72          26.32        2015      406.39          30.00
     2004       320.51          26.69        2016      413.51          30.22
     2005       329.28          27.08        2017      420.51          30.51
     2006       337.93          27.45        2018      427.48          30.83
     2007       346.43          27.87        2019      434.45          31.11
     2008       354.69          28.09        2020      441.40          31.63
     2009       362.55          28.27        2021      448.76          32.84
     2010       370.15          28.51        2022      456.62          33.18
     2011       377.56          28.76
                                    All Markets
     Year    Observations     Securities     Year   Observations     Securities
     2000       397.02          50.50        2012      879.34           81.53
     2001       427.66          54.74        2013      929.82           83.53
     2002       459.73          56.75        2014      981.88           85.52
     2003       492.88          58.65        2015     1034.59           87.48
     2004       527.88          60.64        2016     1087.90           89.17
     2005       565.03          63.44        2017     1142.58           91.55
     2006       604.63          66.49        2018     1198.29           93.55
     2007       647.10          70.38        2019     1254.78           95.22
     2008       691.35          72.50        2020     1311.98           97.30
     2009       736.13          74.26        2021     1371.86          101.05
     2010       782.30          76.57        2022     1434.05          102.82
     2011       830.02          79.23

    Note: This table presents the cumulative number of observations and unique
    securities for the JKP factors, as defined in Jensen et al. (2023). The top
    panel reports data for the U.S., while the bottom panel aggregates data from
    all markets. The years 2000 to 2022 represent individual years for which sep-
    arate models are trained. Observation counts are reported in millions, and
    security counts in thousands.




                                        19
   Based on these three datasets, we define three corresponding groups of data for model training.

The first group contains only U.S. excess return data. The second extends this to include global excess

return data, encompassing both U.S. and global firms. The third further augments the global data by

incorporating the JKP factors. Throughout this study, we refer to these groups as U.S., global, and

JKP-augmented, respectively.10 Model estimation follows an expanding-window approach, with the

first model (for year 2000) trained on data starting in 1990, and one additional model estimated for

each subsequent year through 2022. Consequently, for each test conducted in this study, a total of 23

distinct training datasets are constructed. The dataset begins in 1990, as this year marks the point

from which both U.S. and international markets exhibit sufficiently reliable and comprehensive data

coverage.


4.2    Data Cleaning and Preprocessing

To ensure the integrity and comparability of the multi-asset return panel, and following the cleaning

procedures described in Section 4.1, we implement a series of additional data cleaning and prepro-

cessing steps to enhance data quality. These procedures serve to standardize the dataset prior to

conducting the empirical analysis. To mitigate the influence of extreme values, all daily excess returns

are winsorized symmetrically to the interval [−1, 1]:


                                       (i),ex                                          (i),ex 
                                      r̄t       = min 1, max(−1, rt                         ) .               (14)


The threshold is time-invariant and keeps more data than the usual 99% quantile cut used in empirical

research (Bali et al., 2016). This step curtails the leverage effect of outliers, which are common in

multi-asset environments, and stabilizes the subsequent cross-sectional imputations. After cleaning,

all firm-level series are merged into a unified annual panel,


                                                 (1),ex      (2),ex               (Mt ),ex 
                                      r̄tex = r̄t         , r̄t        , . . . , r̄t              ,           (15)


with dates ordered in ascending sequence, where Mt denotes the number of assets available at time

t and i ∈ {1, . . . , Mt } indexes assets. This ensures that all assets share a common calendar index,

allowing for synchronized cross-sectional analysis at the daily level.

   Missing excess returns are imputed within each country–day cross-section to preserve the institu-

tional structure of national markets. For each trading date t, if all firms’ returns from a country are

  10
     The data volumes of the U.S., global, and JKP-augmented datasets are also reported in Figure A.4, measured in
gigabytes (GB), reaching over 120 GB for the JKP-augmented data in 2022, which represents the largest dataset used.


                                                                  20
             Table 3: Summary of Annual Out-of-Sample Observations and Securities

                  Year    Observations      Securities     Year      Observations     Securities
                  2001      913,194           4,585        2013         735,737         3,308
                  2002      879,869           4,269        2014         749,785         3,346
                  2003      898,407           4,326        2015         728,878         3,285
                  2004      965,728           4,444        2016         722,053         3,349
                  2005      931,131           4,234        2017         731,544         3,360
                  2006      926,102           4,240        2018         721,802         3,271
                  2007      907,453           4,182        2019         697,442         3,233
                  2008      788,216           3,795        2020         700,507         3,363
                  2009      693,570           3,393        2021         783,312         3,583
                  2010      761,590           3,515        2022         716,029         3,398
                  2011      743,847           3,430        2023         738,169         3,705
                  2012      710,378           3,264       Overall     18,144,743       10,171

                 Note: This table reports the annual number of out-of-sample excess return ob-
                 servations and the count of unique securities for the U.S. market from 2001 to
                 2023. Excess returns are reported as raw observation counts, while the number
                 of securities represents distinct securities included each year. The overall num-
                 ber of securities in the last row represents the count of unique securities across
                 all years combined. The summary statistics are derived from CRSP data, with
                 the sample filtered to include only ordinary common shares, excluding preferred
                 stocks, funds, and other non-equity securities. The analysis is further restricted
                 to U.S. common stocks traded on major exchanges (NYSE, AMEX, and NAS-
                 DAQ) with a minimum share price of $5.


missing, the entire date is treated as missing (interpreted as a market-wide closure or holiday). Other-

wise, following Gu et al. (2020), missing values within that country are replaced by the cross-sectional

median of non-missing observations from that country on date t. Using the median instead of the

mean enhances robustness to heavy-tailed or skewed return distributions, especially during volatile

market conditions. The imputation is conducted independently across countries, respecting differences

in trading calendars and market microstructures.

   To avoid extrapolating excess returns beyond an asset’s listing period, we identify the first and

last valid trading dates for each asset, and any observations outside this interval are set to missing.

This boundary masking ensures that the imputation procedure only affects internal gaps (occasional

missing trades within the active period) and not structural absences such as pre-listing or post-delisting

intervals. Also, dates for which all asset excess returns are missing are removed from the panel. These

typically correspond to global holidays or systemic closures and thus contain no information relevant for

the cross-sectional analysis. This operation increases computational efficiency without any information

loss.


4.3     Sample and Model Sizes

To generate forecasts, each model is estimated using an expanding window that begins in 1990. Con-

sequently, the out-of-sample evaluation period spans from 2001 to 2023. The summary of annual

out-of-sample observations and securities is presented in Table 3. Two conditions are applied when



                                                         21
filtering the data. First, the sample includes only ordinary common shares, excluding preferred stocks,

funds, and other non-equity securities. Second, low-priced stocks trading below $5 are removed to

avoid distortions arising from illiquid or highly volatile penny stocks. The analysis is further restricted

to firms listed on the major U.S. exchanges, including the NYSE, AMEX, and NASDAQ, to ensure

data quality and consistency across actively traded and well-regulated markets. In total, all models,

including benchmark models, are tested on over 18 million daily excess returns and approximately

10,000 U.S. securities. This long time span and large sample of excess returns and securities ensure

reliable comparisons across all models.

   Having defined the sample used in the evaluation, we now summarize the relative complexity of

the forecasting models. To provide a clear picture of the differences in model size, Figure 1 presents

a plot of model parameter counts (log-scaled on the x-axis) against model categories (y-axis). Bubble

area is proportional to the true parameter count. Black bubbles denote benchmark models, while gray

bubbles denote TSFMs. TSFMs include Chronos (tiny, mini, small, base, and large)11 , and TimesFM

(with 8, 20, 200, and 500 million parameters). For models where the number of parameters depends

on the chosen input window size, we report the average number of parameters. For benchmark models

whose complexity depends on hyperparameter choices, we report the maximum possible number of

parameters for illustration. The pronounced difference in scale between TSFMs and the benchmark

models, which include conventional ML models, is evident. Reported TSFM sizes correspond to config-

urations employed in zero-shot inference, fine-tuning, and pre-training. TSFMs used for pre-training

are highlighted with black borders. We employ all available model sizes of Chronos and TimesFM

in both our zero-shot and fine-tuned experiments. However, due to computational constraints, we

restrict our pre-training experiments with Chronos to the tiny, mini, and small configurations, and

scale down TimesFM to versions containing approximately 8 million and 20 million parameters.12


4.4    Computational Resources

Inference, fine-tuning, and particularly the pre-training of TSFMs are computationally intensive pro-

cesses that necessitate access to large-scale, high-performance computing infrastructure. All model

development and experimental procedures in this study were executed on servers equipped with graph-
  11
      Chronos variants contain approximately 8M, 20M, 46M, 200M, and 710M parameters for the tiny, mini, small, base,
and large models, respectively.
   12
      TimesFM (200M) refers to the model released under the TimesFM 1 version, while TimesFM (500M) corresponds
to the model released under TimesFM 2. Our scaled-down TimesFM variants are derived from the TimesFM 2. Relative
to the original TimesFM 2 model configuration, which specifies 50 Transformer layers, 16 attention heads, 16 key–value
heads, a head dimension of 80, a hidden size of 1280, and an intermediate size of 5120, we proportionally reduced these
architectural hyperparameters to construct smaller variants. The 20M model employs 9 Transformer layers, 6 attention
heads, 6 key–value heads, a head dimension of 72, a hidden size of 432, and an intermediate size of 1248, whereas the
8M model uses 7 layers, 4 attention heads, 4 key–value heads, a head dimension of 66, a hidden size of 264, and an
intermediate size of 1024. All other settings remain consistent with the original TimesFM 2 specification.


                                                          22
                                            Figure 1: Comparative Model Complexity

                                 Chronos (Large)                                                                              709 M
                                TimesFM (500M)                                                                            500 M
                                  Chronos (Base)                                                                      201 M
                                TimesFM (200M)                                                                        200 M
                                 Chronos (Small)                                                               46 M
                                 TimesFM (20M)                                                              20 M
                                  Chronos (Mini)                                                            20 M
                                  TimesFM (8M)                                                         8M
                                  Chronos (Tiny)                                                       8M
                        Model

                                       CatBoost                                          512 K
                                       XGBoost                                       205 K
                                      LightGBM                                51 K
                                            PCR                             41 K
                                           NN-L                      6K
                                           NN-S                 2K
                                         Enet+H      199
                                      RIDGE+H        199
                                      LASSO+H        199
                                         OLS+H       199


                                               100         1K        10K    100K         1M          10M       100M       1B
                                                                     Number of Parameters (log scale)
                                                           Benchmark Models                  Time Series Foundation Models

       Note: This figure presents a plot of model parameter counts (log-scaled on the x-axis) against model cate-
       gories (y-axis). Bubble area is proportional to the true parameter count. Black bubbles denote benchmark
       models, while gray bubbles denote time series foundation models (TSFMs). Benchmark models include
       linear (OLS+H, LASSO+H, RIDGE+H, Elastic Net+H, and PCR), ensemble (XGBoost, CatBoost, and
       LightGBM), and neural network (NN-S and NN-L) models. ‘H’ indicates that the model is estimated us-
       ing the Huber loss. TSFMs include Chronos (tiny, mini, small, base, and large), and TimesFM (with 8,
       20, 200, and 500 million parameters). For models where the number of parameters depends on the chosen
       input window size, we report the average number of parameters. For benchmark models whose complexity
       depends on hyperparameter choices, we report the maximum possible number of parameters for illustration.
       Reported TSFM sizes correspond to configurations employed in zero-shot inference, fine-tuning, and pre-
       training. TSFMs used for pre-training are highlighted with black borders.


ics processing units (GPUs). In total, approximately 50,000 GPU hours were utilized across all stages.

This includes the pre-training of 396 Chronos models and 264 TimesFM models as part of this study. A

substantial portion of these computational resources was also allocated to large-scale inference experi-

ments, including extensive zero-shot evaluations across a diverse range of TSFMs. Benchmark models,

which rely primarily on central processing unit (CPU)-based computation, also required substantial

resources. Although precise usage was not recorded due to variation across servers, we estimate that

roughly 25,000 CPU hours were consumed for training and testing these benchmark models.

   The TSFM experiments were executed on multi-node servers equipped with NVIDIA GH200 Grace

Hopper GPUs, each integrating a Grace CPU with an H100 Tensor Core GPU. Each GPU featured 96

GB of high-bandwidth memory, supported by large shared CPU memory and high-speed interconnects

that enabled distributed and parallel computation. This configuration facilitated the efficient scaling of

large Transformer architectures and ensured stable throughput during extended training cycles.13 To

ensure experimental consistency, random number generators (RNGs) were initialized at the beginning

of all runs.
  13
     A detailed account of the computational infrastructure and its underlying technical aspects is provided in McIntosh-
Smith et al. (2024). Part of this research was also conducted using N8 Bede, which provides a broadly similar computa-
tional infrastructure.


                                                                           23
5        Numerical Results

As a preliminary step, we evaluate the performance of several benchmark models to identify the

best-performing one, which serves as the primary baseline for comparing TSFMs. This step ensures

that subsequent comparisons are both rigorous and realistic, moving beyond the general benchmarks

commonly used in the TSFM literature toward a more specialized set of models that better reflect

practical financial forecasting performance. Benchmark models include linear (OLS, Lasso, Ridge,

Elastic Net, and PCR), ensemble (XGBoost, CatBoost, and LightGBM), and neural network (NN-S

and NN-L)14 models. The selection of these models is motivated by several considerations. First, they

are widely employed in the existing literature and represent the main categories of models commonly

applied in financial forecasting tasks. Second, these models are computationally feasible to train given

the large sample size utilized in this study. Finally, the set includes several models, particularly en-

semble models, that are frequently recognized as among the best-performing techniques in forecasting

applications.15

    To generate forecasts, a distinct benchmark model is estimated for each year from 2000 to 2022.16

Each model is estimated using an expanding window that begins in 1990, and the model estimated

for year t is employed to produce forecasts for year t + 1. Consequently, the out-of-sample evaluation

period spans from 2001 to 2023. For the TSFMs, when pre-training or fine-tuning is performed,

the same expanding-window procedure is applied to maintain consistency and avoid look-ahead bias.

This approach yields 23 distinct models, each corresponding to one out-of-sample forecasting year.

In contrast, for zero-shot experiments using publicly available pre-trained TSFMs, a single model

is applied across all out-of-sample periods.17 All models are also evaluated with window sizes of

5, 21, 252, and 512 trading days to examine how the amount of historical information available to

each model influences its performance. The window sizes of 5, 21, and 252 trading days correspond

approximately to one week, one month, and one year of past excess returns, respectively. A window

size of 512 trading days is additionally included, as it is a commonly used maximum input length in
    14
      NN-S refers to a single-hidden-layer neural network with 8 hidden units, while NN-L denotes a similar architecture
comprising 32 hidden units. Further details are provided in Section C.
   15
      A detailed description of the benchmark models is provided in Section C. Also, Table C.1 presents the hyperparam-
eter settings for the benchmark models. The set of models is drawn from Gu et al. (2020) and Leippold et al. (2022),
subject to the additional requirement that they can be trained efficiently on the large-scale dataset employed in this
study. Also, hyperparameter tuning is performed only for the first year (2000), and the selected hyperparameters are
subsequently applied to the remaining years. This procedure ensures computational feasibility while enabling a fair
comparison across different classes of models. The key hyperparameters that were optimized are reported under ‘Tuned’,
while those held constant throughout the analysis are reported under ‘Fixed’.
   16
      Throughout this study, we use the terms ‘pre-training’ and ‘fine-tuning’ when referring to TSFMs, and the terms
‘training’ or ‘estimation’ when referring to other model classes.
   17
      This evaluation framework enables us to assess the generalization ability of publicly available TSFMs. However,
depending on the data used to pre-train these models, look-ahead bias may arise. To mitigate this concern, we develop
proprietary pre-trained models that explicitly exclude any such overlap, while retaining the zero-shot and fine-tuned
results from publicly available TSFMs for comparison.


                                                          24
many TSFMs. Finally, our work focuses on univariate return forecasting, benchmarking all TSFM

models on a univariate time series setting, although some recently proposed TSFMs are capable of

handling multivariate data.

   We present our empirical findings in Section 5.1, Section 5.2, and Section 5.3. In Section 5.1, both

the benchmark models and the TSFMs are trained exclusively on U.S. data. Section 5.2 broadens

the scope to a global context by training all models, including both benchmarks and TSFMs, on

an extensive dataset encompassing 94 countries. Finally, Section 5.3 evaluates the out-of-sample

performance of the benchmark models and TSFMs across seven major international markets, thereby

extending our analysis beyond the U.S. market.18


5.1     Results with U.S. Data

The initial set of results, presented in Section 5.1.1, reports the performance of benchmark models.

Moving to the TSFMs, we present numerical results from three distinct experiments. Following Sec-

tion 3.2.1, the first experiment employs pre-trained models released by their respective authors and

applies them directly in a zero-shot setting to forecast excess returns, as shown in Section 5.1.2. The

second experiment, described in Section 3.2.2 and reported in Section 5.1.3, fine-tunes these models

and provides the corresponding results. Section 5.1.4 extends the analysis by pre-training the models

from scratch and presenting the resulting performance. Finally, Section 5.1.5 provides a brief overview

of the training time comparison across models. For all models, only U.S. data is used. Also, unless

explicitly stated otherwise, all hyperparameters are kept consistent with those proposed by the original

authors.


5.1.1    Benchmark Results

Table 4 reports the forecasting performance results for the benchmark models. This table presents each

metric as a set of three values, ordered from top to bottom: full sample, top 25% of firms by market

capitalization (large-cap), and bottom 25% (small-cap) for various predictive models across different

window sizes (5, 21, 252, and 512 trading days). Metrics are first computed separately for each calendar

year using all stock-date observations within that year. The reported values represent the average of

these yearly statistics. Metrics include out-of-sample R2 (ROOS
                                                            2   ), overall directional accuracy, upward

and downward classification accuracy, and macro-averaged F1 score. Benchmark models include linear

(OLS, Lasso, Ridge, Elastic Net19 , and PCR), ensemble (XGBoost, CatBoost, and LightGBM), and

  18
      All pre-trained models from scratch are available through our portal at FinText.ai and the Hugging Face repository
at https://huggingface.co/FinText.
   19
      Throughout this study, the abbreviation Enet is employed to represent the Elastic Net model.


                                                          25
neural network (NN-S and NN-L) models. ‘H’ indicates that the model is estimated using the Huber

loss. ‘Overall Acc.’ denotes overall directional accuracy, ‘Up Acc.’ and ‘Down Acc.’ represent the

model’s accuracy in predicting upward and downward excess returns respectively, and ‘F1’ refers to

the macro-averaged F1 score.

   The results show that ensemble models, specifically XGBoost, CatBoost, and LightGBM, generally

achieve superior forecasting performance across window sizes compared with other models. These
                                2
ensemble models exhibit higher ROOS values and overall accuracy. For the largest window size (512),
                     2
CatBoost attains an ROOS of −0.03%, an overall prediction accuracy of 51.16%, and an F1 score

of 0.49. The only model that performs better in terms of directional accuracy is OLS; however, its
                         2
performance in terms of ROOS is lower than that of the ensemble models. For the best-performing

models, there is also a general trend indicating that these models exhibit better forecasting performance

for small-cap stocks compared to large-cap stocks. For the CatBoost model, averaged across all window

lengths, the out-of-sample R2 for small-cap stocks is 0.51%, compared with −0.37% for large-cap

stocks. The corresponding overall accuracy values are 52.29% and 50.76%, respectively, while the F1

scores are 0.52 and 0.47. A similar pattern, indicating stronger predictive performance for small-cap

stocks, is generally observed across the other models as well. This finding is consistent with the results

reported in Gu et al. (2020), Leippold et al. (2022), and Kelly et al. (2025). Also, neural network models

(NN-S and NN-L) produce mixed outcomes. NN-L performs moderately better than NN-S with longer

windows (except for 512 days), particularly in terms of directional accuracy, but still trails behind the

ensemble models. Overall, the results highlight that ensemble models provide the most reliable and

robust predictive performance. Across different window sizes, model performance generally improves

with longer estimation windows, indicating that incorporating more historical information enhances

predictive performance.20




  20
      We also report in Table B.1 the results of the modified Diebold–Mariano (DM) tests, following the approach of Gu
et al. (2020), which assess the statistical significance of out-of-sample forecasting performance differences among bench-
mark models. A positive and statistically significant DM statistic indicates that the model in the column outperforms
the model in the corresponding row. Consistent with the benchmark performance results, XGBoost, CatBoost, and
LightGBM exhibit significantly superior forecasting performance compared to traditional linear models such as OLS,
Lasso, Ridge, Elastic Net, and PCR across most window sizes. Neural network models (NN-S and NN-L) show mixed re-
sults, occasionally outperforming linear models but generally lagging behind the ensemble models. Among the ensemble
models, CatBoost and XGBoost most frequently deliver statistically significant improvements over competing models.
When also comparing performance across different window sizes for the same model, the results indicate that longer
estimation windows (252 and 512 days) generally lead to improved forecasting performance, particularly for nonlinear
and ensemble models, while shorter windows (5 and 21 days) yield more volatile and less reliable results.


                                                           26
                                                       Table 4: Benchmark Models - Forecasting Performance

     Model                  OLS+H                         LASSO+H                           RIDGE+H                          Enet+H                               PCR
 Window Size        5      21     252     512      5       21     252     512      5         21     252     512      5       21     252     512      5       21     252     512
                  -0.40   -0.41   -0.48   -0.57   -2.89   -1.42   -1.65   -1.81   -1.31     -1.35   -1.65   -1.79   -1.36   -1.36   -1.31   -1.09   -1.34   -1.24   -1.50   -2.70
     R2 OOS       -0.88   -0.88   -0.96   -1.07   -3.75   -2.12   -2.40   -2.58   -1.96     -2.00   -2.37   -2.51   -2.04   -2.04   -2.01   -1.75   -1.85   -1.73   -2.02   -3.56
                  0.31     0.30    0.26   0.19    -1.53   -0.36   -0.53   -0.67   -0.27     -0.31   -0.54   -0.67   -0.30   -0.29   -0.26   -0.13   -0.64   -0.59   -0.79   -1.54
                  51.92   51.93   51.86   51.82   51.34   51.24   51.15   51.18   51.24     51.27   51.27   51.32   51.22   51.28   51.15   51.12   50.99   50.92   50.90   51.04
  Overall Acc.    50.59   50.62   50.67   50.69   51.09   51.18   51.15   51.20   51.20     51.14   51.28   51.21   51.18   51.21   51.21   51.18   51.00   50.96   50.97   50.77
                  54.67   54.65   54.40   54.27   52.38   51.89   51.71   51.75   51.93     52.11   51.97   52.16   51.94   52.00   51.66   51.58   51.38   51.31   51.29   52.01
                  45.56   45.92   47.50   47.77   63.70   67.15   68.03   67.94   67.34     66.17   67.26   65.96   66.87   67.31   69.12   69.33   66.11   65.95   66.00   62.33
    Up Acc.       42.63   43.01   44.79   45.21   63.90   68.11   69.20   69.09   68.29     66.89   68.42   66.79   67.80   68.26   70.46   70.63   68.00   68.13   68.32   63.48
                  49.24   49.68   51.23   51.38   66.91   69.53   70.33   70.27   70.04     68.96   69.36   68.19   69.47   69.89   71.38   71.43   66.83   66.34   66.22   63.29
                  58.19   57.87   56.19   55.81   39.38   35.61   34.74   34.82   35.56     36.78   35.66   37.04   36.02   35.53   33.68   33.32   36.22   36.20   36.15   39.99
   Down Acc.      59.01   58.70   56.92   56.49   37.80   33.40   32.41   32.49   33.36     34.78   33.29   34.92   33.86   33.31   31.19   30.85   33.19   32.96   32.82   37.45
                  59.48   59.05   57.23   56.81   39.63   36.16   35.26   35.36   35.94     37.20   36.60   37.97   36.50   36.04   34.22   33.96   37.67   37.95   38.06   41.97
                  0.52    0.52    0.52    0.52    0.51    0.50    0.50    0.50    0.50      0.50    0.50    0.50    0.50    0.50    0.50    0.49    0.50    0.50    0.50    0.50
       F1         0.50    0.50    0.51    0.51    0.50    0.49    0.49    0.49    0.49      0.50    0.49    0.50    0.49    0.49    0.49    0.49    0.49    0.49    0.49    0.50
                  0.54    0.54    0.54    0.54    0.52    0.51    0.51    0.51    0.51      0.51    0.51    0.51    0.51    0.51    0.50    0.50    0.51    0.51    0.51    0.52

     Model                 XGBoost                         CatBoost                         LightGBM                           NN-S                            NN-L
 Window Size        5      21     252     512      5       21     252     512      5         21     252     512      5       21     252     512      5       21     252     512
                  -0.23    0.01   -0.09   -0.12   -0.25   -0.05   -0.03   -0.03   -0.22     -0.01   -0.08   -0.13   -3.10   -3.35   -1.91   -2.35   -3.36   -2.31   -2.29   -2.58
     R2 OOS       -0.44   -0.28   -0.33   -0.32   -0.50   -0.38   -0.32   -0.28   -0.43     -0.27   -0.31   -0.34   -4.48   -5.12   -2.54   -2.79   -5.13   -3.05   -2.82   -3.40
                  0.38     0.64    0.51   0.47     0.39   0.67    0.64    0.60    0.37      0.60     0.52   0.47    -1.95   -2.08   -0.97   -1.38   -2.04   -1.39   -1.36   -1.60
                  51.23   51.23   51.27   51.34   50.94   51.12   51.08   51.16   51.17     51.18   51.24   51.38   50.94   50.97   50.96   51.32   51.25   51.28   51.04   50.85
  Overall Acc.    50.90   51.01   51.15   51.22   50.70   50.74   50.80   50.95   50.95     51.01   51.13   51.20   50.52   50.54   50.81   50.98   50.48   51.04   50.35   50.30
                  52.52   52.44   52.31   52.46   51.96   52.48   52.33   52.39   52.34     52.30   52.34   52.59   51.94   52.06   51.74   52.33   52.79   52.24   52.34   52.05
                  68.63   69.44   70.53   69.42   68.96   67.82   66.87   69.14   69.61     70.05   70.05   68.14   48.28   46.43   62.42   56.89   46.58   59.45   53.18   49.67
    Up Acc.       71.26   73.96   76.27   74.88   72.05   72.97   71.06   74.39   72.42     74.80   75.86   73.46   48.02   45.96   62.93   56.89   46.08   59.20   51.97   48.62
                  67.39   66.84   67.79   66.86   68.00   65.11   64.65   66.07   68.76     67.93   67.49   66.00   49.13   47.59   63.69   58.32   47.64   60.17   55.50   51.40
                  33.97   33.15   32.25   33.36   33.14   34.60   35.59   33.37   32.95     32.53   32.73   34.73   53.19   55.28   39.64   45.35   55.32   42.51   49.16   52.30
   Down Acc.      29.26   26.65   24.64   26.09   28.11   27.25   29.59   26.24   28.21     25.86   25.10   27.61   52.60   54.98   37.84   44.22   54.81   41.45   49.15   52.32
                  38.91   39.27   38.28   39.22   37.42   41.01   41.24   39.87   37.41     38.10   38.67   40.28   54.21   55.94   41.04   46.46   56.49   44.37   49.53   52.93
                  0.49    0.49    0.49    0.49    0.49    0.49    0.50    0.49    0.49      0.49    0.49    0.49    0.43    0.43    0.47    0.48    0.44    0.45    0.48    0.47
       F1         0.47    0.46    0.46    0.46    0.47    0.47    0.48    0.47    0.47      0.47    0.47    0.47    0.41    0.41    0.46    0.46    0.42    0.44    0.46    0.45
                  0.51    0.51    0.51    0.51    0.51    0.52    0.52    0.51    0.51      0.51    0.51    0.51    0.44    0.45    0.49    0.50    0.46    0.47    0.50    0.49

Note: This table presents each metric as a set of three values, ordered from top to bottom: full sample, top 25% of firms by market capitalization (large-cap), and bottom
25% (small-cap) for various predictive models across different window sizes (5, 21, 252, and 512 trading days). Metrics are first computed separately for each calendar year
using all stock-date observations within that year. The reported values represent the average of these yearly statistics. Metrics include out-of-sample R2 (ROOS
                                                                                                                                                               2
                                                                                                                                                                   ), overall
directional accuracy, upward and downward classification accuracy, and macro-averaged F1 score. Benchmark models include linear (OLS, Lasso, Ridge, Elastic Net, and
PCR), ensemble (XGBoost, CatBoost, and LightGBM), and neural network (NN-S and NN-L) models. ‘Overall Acc.’ denotes overall directional accuracy, ‘Up Acc.’ and
‘Down Acc.’ represent the model’s accuracy in predicting upward and downward excess returns respectively, and ‘F1’ refers to the macro-averaged F1 score. ‘H’ indicates
that the model is estimated using the Huber loss.




                                                                                       27
                                                           Table 5: Benchmark Models - Portfolio Performance

     Model                      OLS+H                         LASSO+H                         RIDGE+H                           Enet+H                              PCR
   Window Size          5      21   252       512      5       21  252        512      5       21  252        512      5       21    252      512      5       21      252     512
                      45.32   45.71   45.91   45.34   44.83   43.67   43.84   43.78   44.93   44.48   44.79   44.30   44.29   44.31   44.30   43.83   30.17   29.50    28.59   33.39
 Annualized Return    29.15   29.40   29.34   28.86   28.82   27.97   28.10   28.06   28.86   28.80   28.48   28.24   28.53   28.49   28.48   28.11   19.33   19.23    18.31   21.64
                      16.17   16.31   16.57   16.48   16.01   15.70   15.73   15.72   16.07   15.68   16.30   16.06   15.76   15.82   15.82   15.72   10.83   10.27    10.28   11.75
                       9.32   9.34    9.34    9.31    9.25    8.99    9.00    9.06    9.22    9.24    9.36    9.35    9.18    9.17    9.14    9.01    8.36    8.24     8.13    8.47
 Standard Deviation   13.89   13.92   13.90   13.89   13.84   13.66   13.66   13.68   13.84   13.80   13.77   13.79   13.78   13.78   13.76   13.67   13.11   13.04    12.99   13.17
                      11.85   11.83   11.84   11.86   11.87   11.88   11.88   11.89   11.86   11.90   12.01   11.98   11.89   11.89   11.88   11.88   12.13   12.07    12.00   12.04
                       4.86   4.89    4.92    4.87    4.84    4.86    4.87    4.83    4.88    4.81    4.79    4.74    4.83    4.83    4.85    4.86    3.61    3.58     3.52    3.94
    Sharpe Ratio       2.10   2.11    2.11    2.08    2.08    2.05    2.06    2.05    2.09    2.09    2.07    2.05    2.07    2.07    2.07    2.06    1.47    1.47     1.41    1.64
                       1.37   1.38    1.40    1.39    1.35    1.32    1.32    1.32    1.36    1.32    1.36    1.34    1.33    1.33    1.33    1.32    0.89    0.85     0.86    0.98
                      17.98   18.14   18.22   17.99   17.79   17.33   17.40   17.37   17.83   17.65   17.77   17.58   17.58   17.58   17.58   17.39   11.97   11.71    11.34   13.25
 Daily Return (bps)   11.57   11.67   11.64   11.45   11.44   11.10   11.15   11.13   11.45   11.43   11.30   11.21   11.32   11.30   11.30   11.15   7.67    7.63     7.27    8.59
                       6.42   6.47    6.57    6.54    6.35    6.23     6.24   6.24    6.38    6.22    6.47    6.37    6.25    6.28    6.28    6.24    4.30    4.08     4.08    4.66
                      17.59   17.62   17.61   19.07   17.03   14.54   14.54   14.98   17.17   17.24   17.36   18.06   17.01   16.86   15.99   14.67   15.86   16.28    16.27   14.85
      Max DD          32.60   32.98   32.88   33.14   32.36   31.40   31.40   31.57   32.44   32.31   32.15   32.16   32.21   32.17   32.02   31.43   27.12   27.59    27.46   28.61
                      29.03   28.45   27.57   27.15   29.50   29.02   29.02   30.69   29.68   29.43   25.99   26.31   30.58   30.50   30.76   29.02   31.73   31.92    33.28   35.12
                       5.60   5.66    5.68    5.68    5.59    5.06    5.06    5.14    5.59    5.57    5.50    5.39    5.53    5.49    5.42    5.06    3.24    2.94     3.65    4.21
  Max DD (1-day)       8.74   8.79    8.77    8.76    8.75    8.40    8.40    8.44    8.77    8.75    8.64    8.50    8.68    8.69    8.62    8.40    7.45    7.16     7.59    7.85
                       5.11   5.08    4.94    4.95    5.25    5.48    5.48    5.47    5.23    5.31    5.19    5.30    5.33    5.29    5.33    5.48    4.64    4.88     4.92    6.13
                       1.30    1.31   1.26    1.29    1.26    1.12    1.13     1.10   1.21     1.21   1.11    1.12    1.20    1.19    1.16     1.13   0.87     0.87     0.78   0.81
        Skew          -0.09   -0.08   -0.10   -0.09   -0.11   -0.08   -0.07   -0.08   -0.11   -0.08   -0.10   -0.09   -0.10   -0.10   -0.09   -0.07   -0.01   -0.08    -0.10   -0.18
                       0.54    0.55   0.55    0.56    0.51    0.45    0.46     0.45   0.50     0.49   0.45    0.44    0.47    0.47    0.46     0.46   0.42     0.38     0.41   0.31
                      17.33   17.74   17.62   17.67   16.73   15.15   15.15   15.15   16.68   16.65   16.26   16.21   16.53   16.40   16.22   15.09   12.51   12.43    11.19   12.39
        Kurt          12.04   12.24   12.14   12.13   11.86   11.08   11.07   11.18   11.87   11.84   11.63   11.57   11.72   11.73   11.66   11.07   10.11   9.80     10.04   10.50
                       6.41   6.37    6.40    6.34    6.19    6.01     6.06   6.06    6.15    6.26    6.20    6.19    6.13    6.12    6.06    6.06    6.15    6.12     5.83    6.15

     Model                     XGBoost                         CatBoost                       LightGBM                           NN-S                            NN-L
   Window Size          5      21  252        512      5       21   252       512      5       21   252       512      5       21    252      512      5       21    252       512
                      44.47   46.86   47.69   47.40   42.54   46.52   46.50   47.25   43.61   45.93   46.49   46.52   40.59   42.62   40.15   40.11   44.04   42.97    40.84   38.82
 Annualized Return    27.16   28.86   30.13   30.06   26.58   28.26   29.00   29.22   26.74   28.52   29.53   29.68   27.33   27.45   25.45   25.53   28.37   27.66    26.12   24.87
                      17.31   18.00   17.56   17.34   15.95   18.26   17.50   18.03   16.87   17.41   16.96   16.83   13.26   15.17   14.70   14.58   15.67   15.31    14.73   13.95
                       7.68   7.17    8.14    8.30    7.40    6.86    6.85    7.31    7.72    7.51    8.22    8.40    9.29    9.19    8.97    8.93    9.22    9.29     8.84    8.87
 Standard Deviation   14.15   13.90   13.94   13.98   14.14   13.88   13.71   13.81   14.23   13.99   14.05   14.10   14.00   13.85   13.62   13.71   13.84   13.83    13.70   13.57
                      12.05   12.42   12.53   12.53   12.09   12.37   12.31   12.31   12.07   12.42   12.56   12.52   11.76   11.96   11.91   11.84   11.91   11.89    11.84   11.90
                       5.79   6.53    5.86    5.71    5.74    6.78    6.79    6.46    5.65    6.12    5.66    5.54    4.37    4.64    4.48    4.49    4.78    4.63     4.62    4.38
    Sharpe Ratio       1.92   2.08    2.16    2.15    1.88    2.04    2.12    2.12    1.88    2.04    2.10    2.11    1.95    1.98    1.87    1.86    2.05    2.00     1.91    1.83
                       1.44   1.45    1.40    1.38    1.32    1.48    1.42    1.46    1.40    1.40    1.35    1.34    1.13    1.27    1.23    1.23    1.32    1.29     1.24    1.17
                      17.65   18.59   18.92   18.81   16.88   18.46   18.45   18.75   17.31   18.23   18.45   18.46   16.11   16.91   15.93   15.92   17.48   17.05    16.21   15.41
 Daily Return (bps)   10.78   11.45   11.96   11.93   10.55   11.22   11.51   11.59   10.61   11.32   11.72   11.78   10.84   10.89   10.10   10.13   11.26   10.97    10.36   9.87
                       6.87   7.14    6.97    6.88    6.33    7.25     6.94   7.15    6.70    6.91    6.73    6.68    5.26    6.02    5.83    5.78    6.22    6.08     5.84    5.54
                      12.21   12.61   15.51   16.15   12.08   13.10   13.62   14.34   13.94   16.08   16.72   17.04   18.91   18.50   16.58   16.98   17.01   18.53    14.48   17.29
      Max DD          32.08   32.09   33.46   33.65   32.51   32.85   31.86   32.62   33.33   33.87   33.95   33.72   33.36   33.38   32.27   32.70   32.39   33.23    31.99   31.66
                      29.82   29.85   30.91   29.99   30.31   28.43   30.20   27.85   30.67   32.56   31.17   29.89   30.49   30.76   31.78   31.25   30.53   29.63    30.79   29.22
                       4.97   3.41    4.36    4.56    4.86    3.75    4.15    4.93    5.10    4.26    4.96    5.17    5.62    5.47    4.80    5.15    5.51    5.61     5.49    5.29
  Max DD (1-day)       8.56   8.06    8.23    8.19    8.28    8.21    8.19    8.19    8.59    8.33    8.28    8.32    8.81    8.54    8.21    8.37    8.67    8.80     8.67    8.32
                       5.51   4.74    5.63    5.12    5.56    4.49    5.03    5.27    5.66    5.36    5.56    5.52    6.31    5.53    4.98    5.28    5.58    5.63     5.18    5.19
                       1.81   2.10    1.57    1.48    2.24    2.19    2.25     1.72   1.80     1.74   1.58    1.56    1.31    1.31    1.20     1.67   1.24     1.37     1.27   1.36
        Skew          -0.05   0.01    -0.01   -0.03   -0.01   0.00    0.02    -0.05   -0.08   -0.06   -0.04   -0.04   -0.12   -0.15   -0.09   -0.00   -0.11   -0.11    -0.14   -0.13
                       0.35   0.36    0.33    0.36    0.35    0.38    0.38     0.36   0.33     0.35   0.32    0.32    0.48    0.51    0.51     0.52   0.52     0.53     0.45   0.49
                      26.84   28.34   21.08   19.97   33.34   31.81   32.72   26.79   27.33   25.88   22.98   22.46   17.34   16.69   15.43   20.70   16.54   17.36    17.32   17.86
        Kurt          11.44   11.51   12.13   11.98   11.62   12.31   12.53   12.56   11.37   12.17   12.26   12.20   11.96   11.61   11.69   12.29   11.45   11.68    11.98   11.78
                       6.15   5.21    5.70    5.64    6.17    5.16     5.40   5.53    6.36    5.81    5.94    5.84    7.07    6.62    6.16    6.23    6.76    6.69     6.04    6.51

Note: This table reports average yearly portfolio performance metrics across different rolling window sizes (5, 21, 252, and 512 trading days) for each model. Each cell displays
three values from top to bottom: long–short portfolio, long-only leg, and short-only leg. Metrics include annualized return, standard deviation, Sharpe ratio, daily return (in
basis points), maximum drawdown (Max DD), one-day maximum drawdown (Max DD (1-day)), skewness, and kurtosis of portfolio returns. Benchmark models include linear
(OLS, Lasso, Ridge, Elastic Net, and PCR), ensemble (XGBoost, CatBoost, and LightGBM), and neural network (NN-S and NN-L) models. Portfolios are formed using decile
sorting based on model forecasts, with equal weighting across stocks. ‘H’ indicates that the model is estimated using the Huber loss.


                                                                                      28
   Detailed results on portfolio performance can be found in Table 5. This table reports average

yearly portfolio performance metrics across different rolling window sizes for each model. Each cell

displays three values from top to bottom: long–short portfolio, long-only leg, and short-only leg. Met-

rics include annualized return, standard deviation, Sharpe ratio, daily return (in basis points), Max

DD, Max DD (1-day), skewness, and kurtosis of portfolio returns. Consistent with the results shown

in Table 4, the portfolio performance metrics indicate that ensemble models outperform both linear

and neural network models. Across all rolling window sizes, ensemble models, particularly CatBoost,

followed by XGBoost and LightGBM, achieve the highest annualized returns, Sharpe ratios, and daily

returns, showing that stronger predictive accuracy translates into higher portfolio profitability. These

models also exhibit moderate standard deviations, smaller maximum drawdowns, and more favorable

higher-moment characteristics, including positive skewness and lower kurtosis, which suggest improved

tail-risk management and more stable return distributions. In contrast, linear models deliver consis-

tent but moderate performance across metrics, while neural networks display higher volatility, deeper

drawdowns, and lower Sharpe ratios. The highest Sharpe ratio of 6.79 is achieved by CatBoost, exceed-

ing both the linear benchmarks (mean Sharpe ratio ≈ 4.61) and neural network models (mean Sharpe

ratio ≈ 4.55). The other ensemble models achieve maximum Sharpe ratios of 6.53 for XGBoost and

6.12 for LightGBM. Also, across all benchmark models and performance metrics, the long leg generally

outperforms the short leg. This pattern holds across window sizes and risk-adjusted measures. This

finding aligns with the results documented in Gu et al. (2020), Chen et al. (2024), and Leippold et al.

(2022). Overall, the metrics in Table 5 confirm that ensemble models, especially CatBoost, provide

the best balance between profitability, risk control, and return stability.21 Accordingly, CatBoost is

adopted as the benchmark model for the remainder of this study.


5.1.2    Zero-Shot Results

The central premise of TSFMs is that they can deliver competitive zero-shot performance across a

wide range of tasks and frequencies, paralleling the success of LLMs, which have demonstrated strong

zero-shot learning capabilities across diverse domains. TSFMs are designed to generalize to new tasks

without task-specific fine-tuning; however, whether this promise holds in complex, real-world settings

remains an open question. We evaluate this claim by employing TSFMs released by their respective

authors and assessing their zero-shot performance, with particular attention to whether their claimed


  21
     Table B.2 reports the annualized average returns of decile spread portfolios across models and window sizes. Decile
returns generally rise from low to high, with a few small non-monotonic steps. Ensemble models show the steepest
and most consistent gradients and typically the largest H–L spreads. Linear models also sort positively but with flatter
gradients, although PCR is notably weaker than the others. Neural networks deliver smaller spreads than ensembles and
most linear models, although they occasionally overlap in some window sizes.


                                                          29
generalization ability extends to the highly specialized and demanding task of daily excess return

forecasting. We begin our analysis by examining two TSFMs, Chronos (Ansari et al., 2024) and

TimesFM (Das et al., 2024), which are widely recognized as pioneering contributions to this domain.

Their architectures have provided the basis for numerous subsequent model developments.

   The zero-shot forecasting performance results in Table 6 show that TSFMs, including Chronos and

TimesFM, perform substantially worse than the benchmark model (CatBoost). Across all model sizes
                                                     2
and window lengths, TSFMs produce markedly negative ROOS values, often extremely negative for

smaller Chronos models and both TimesFM versions. The Chronos (small) variant attains the best
                                      2
performance among the TSFMs, with an ROOS of −1.27%, which remains substantially below the

benchmark models’ best value of −0.03% for the full sample. The two TimesFM variants exhibit even
                                               2
greater instability, yielding highly negative ROOS values across all windows, further highlighting the

severe zero-shot underperformance of TSFMs relative to the benchmark. Between TimesFM 1 and
                                         2
TimesFM 2, particularly with respect to ROOS , TimesFM 1 exhibits substantially weaker performance.

Although larger Chronos variants improve with longer windows, still, for many model configurations

their directional accuracy remains around or below 50%. TSFMs also exhibit asymmetric forecasting

behavior, occasionally overpredicting either upward or downward movements, a tendency that is also

observed in most of the benchmark models. TimesFM models display even more unstable and erratic
                                   2
performance, with highly negative ROOS values and below 50% directional accuracy. The weakness

of TSFMs is particularly evident at shorter window sizes, where these models consistently deliver the

most severe drops in predictive performance. Although their results improve with longer windows,

this recovery remains limited, suggesting that TSFMs are more capable of leveraging longer historical

contexts than shorter-term information. Also, results are mixed between small and large stocks,

with performance varying across models and window sizes. Nonetheless, the best-performing models

broadly mirror the benchmark’s small-stock advantage documented in Section 5.1.1.




                                                 30
                                                Table 6: Zero-Shot TSFMs - Forecasting Performance

     Model                  Benchmark                          Chronos (Tiny)                         Chronos (Mini)                          Chronos (Small)
 Window Size        5        21       252     512       5         21      252      512        5          21        252      512       5          21       252     512
                  -0.25     -0.05    -0.03    -0.03   -75.87     -8.34   -8.34     -1.77    -43.14      -11.60    -11.60   -0.75     -77.07     -13.04   -13.04   -1.27
     R2 OOS       -0.50     -0.38    -0.32    -0.28   -68.38     -8.27   -8.27     -2.50    -40.16       -9.68     -9.68   -1.13     -52.28      -8.01    -8.01   -1.34
                  0.39      0.67     0.64      0.60   -85.21     -8.87   -8.87     -1.15    -47.34      -13.96    -13.96   -0.40    -104.56     -18.68   -18.68   -1.16
                  50.94     51.12    51.08    51.16   48.39      49.31   49.31     50.46    48.60       49.32     49.32    50.54    48.54       49.50    49.50    50.99
  Overall Acc.    50.70     50.74    50.80    50.95   49.41      49.88   49.88     50.86    49.36       49.68     49.68    50.68    49.22       49.46    49.46    50.25
                  51.96     52.48    52.33    52.39   46.26      48.35   48.35     50.60    46.95       48.75     48.75    51.06    46.98       49.53    49.53    52.62
                  68.96     67.82    66.87    69.14   54.53      59.51   59.51     78.02    51.67       54.39     54.39    68.43    47.69       44.87    44.87    28.51
    Up Acc.       72.05     72.97    71.06    74.39   55.72      62.19   62.19     82.42    53.54       58.34     58.34    74.41    49.71       49.24    49.24    41.28
                  68.00     65.11    64.65    66.07   52.81      56.75   56.75     70.99    48.62       48.76     48.76    60.84    44.32       38.35    38.35    15.37
                  33.14     34.60    35.59    33.37   42.32      39.23   39.23     23.25    45.50       44.21     44.21    32.87    49.28       53.82    53.82    72.60
   Down Acc.      28.11     27.25    29.59    26.24   42.71      36.80   36.80     17.55    44.86       40.39     40.39    25.56    48.56       49.35    49.35    58.95
                  37.42     41.01    41.24    39.87   40.37      40.84   40.84     32.21    45.39       48.64     48.64    42.22    49.27       59.38    59.38    85.77
                   0.49      0.49    0.50     0.49    0.48       0.49    0.49      0.46      0.49        0.49     0.49     0.49      0.48        0.49    0.49     0.48
       F1          0.47      0.47    0.48     0.47    0.49       0.49    0.49      0.44      0.49        0.49     0.49     0.47      0.49        0.49    0.49     0.49
                   0.51      0.52    0.52     0.51    0.46       0.48    0.48      0.49      0.47        0.49     0.49     0.51      0.47        0.49    0.49     0.44

     Model                 Chronos (Base)                      Chronos (Large)                       TimesFM 1 (200M)                       TimesFM 2 (500M)
 Window Size        5        21       252     512       5         21      252      512        5          21        252      512       5          21       252     512
                  -57.59    -21.47   -21.47   -1.35   -46.86    -23.84   -23.84    -1.37   -1469.95    -5004.66   -2.3e4   -6.3e4   -27.96      -11.87   -3.86    -2.80
     R2 OOS       -38.80    -13.21   -13.21   -1.60   -35.50    -12.58   -12.58    -1.03    -610.92     -517.03   -2.1e4   -2.7e4   -27.27      -10.90   -3.79    -2.90
                  -78.52    -30.27   -30.27   -1.22   -60.60    -35.63   -35.63    -1.70   -3499.35    -9809.08   -3.1e4   -1.2e5   -29.93      -13.36   -3.96    -2.64
                  48.59     49.19    49.19    50.80   48.70      49.13   49.13     51.01    49.55       50.00     49.87    49.60    48.34       48.70    49.59    49.82
  Overall Acc.    49.42     49.61    49.61    49.86   49.58      49.91   49.91     50.61    50.24       49.86     49.62    49.74    49.25       49.44    49.69    50.01
                  46.84     48.45    48.45    52.61   46.94      47.85   47.85     52.46    48.53       50.15     50.24    49.36    46.34       47.18    49.72    49.94
                  53.94     52.98    52.98    24.55   59.70      64.13   64.13     49.60    73.64       49.94     45.46    54.59    50.14       52.74    52.16    56.11
    Up Acc.       55.68     56.87    56.87    30.55   61.30      66.96   66.96     59.93    73.80       49.14     44.42    53.29    52.65       56.01    56.30    61.13
                  51.04     47.24    47.24    21.48   57.24      60.71   60.71     37.29    73.55       51.27     47.35    56.82    46.21       48.61    47.40    50.53
                  43.27     45.31    45.31    76.18   37.85      34.35   34.35     52.04    26.02       50.01     54.08    44.72    46.46       44.56    46.81    43.44
   Down Acc.      42.75     41.76    41.76    69.42   37.20      31.87   31.87     40.19    25.68       50.51     54.86    46.00    45.49       42.28    42.34    38.02
                  43.02     49.33    49.33    80.34   37.70      36.35   36.35     66.00    26.26       49.15     52.79    42.75    46.38       45.81    51.66    49.31
                   0.48      0.49    0.49     0.47    0.48       0.48    0.48      0.50      0.47        0.50     0.50     0.49      0.48        0.48    0.49     0.49
       F1          0.49      0.49    0.49     0.47    0.49       0.48    0.48      0.49      0.47        0.50     0.49     0.49      0.49        0.49    0.49     0.49
                   0.47      0.48    0.48     0.47    0.47       0.47    0.47      0.51      0.46        0.50     0.50     0.49      0.46        0.47    0.49     0.50

Note: This table presents each metric as a set of three values, ordered from top to bottom: full sample, top 25% of firms by market capitalization (large-
cap), and bottom 25% (small-cap) for various predictive models across different window sizes (5, 21, 252, and 512 trading days). The benchmark model is
CatBoost, the best-performing model among the benchmarks. The time series foundation models (TSFMs) include Chronos (tiny, mini, small, base, and
large) and TimesFM (version 1 with 200 million and version 2 with 500 million parameters). Zero-shot inference is performed using the pre-trained models
released by the respective authors. Metrics are first computed separately for each calendar year using all stock-date observations within that year. The re-
ported values represent the average of these yearly statistics. Metrics include out-of-sample R2 (ROOS
                                                                                                   2
                                                                                                       ), overall directional accuracy, upward and downward
classification accuracy, and macro-averaged F1 score. ‘Overall Acc.’ denotes overall directional accuracy, ‘Up Acc.’ and ‘Down Acc.’ represent the model’s
accuracy in predicting upward and downward excess returns respectively, and ‘F1’ refers to the macro-averaged F1 score. Numbers exceeding four digits are
expressed in scientific notation for clarity.



                                                                                  31
                                                 Table 7: Zero-Shot TSFMs - Portfolio Performance

     Model                      Benchmark                          Chronos (Tiny)                      Chronos (Mini)                      Chronos (Small)
   Window Size          5        21   252         512       5         21    252       512       5        21     252       512       5         21     252      512
                      42.54     46.52    46.50    47.25   -37.07     -17.31    9.15   14.25   -32.85    -15.50   20.17   21.09    -36.73     -14.36   6.53    7.64
 Annualized Return    26.58     28.26    29.00    29.22   -12.51      -3.68    9.42   11.20    -9.23     -1.13   14.44   15.40    -12.20      -1.27   7.63    8.98
                      15.95     18.26    17.50    18.03   -24.56     -13.63   -0.27   3.05    -23.62    -14.37   5.73    5.69     -24.53     -13.10   -1.09   -1.34
                      7.40      6.86     6.85     7.31    8.11       6.07     5.42    5.28    8.00      6.69     5.44    5.57     8.13       6.79     7.56    8.14
 Standard Deviation   14.14     13.88    13.71    13.81   11.79      12.00    12.69   12.86   11.91     12.05    12.50   12.51    11.75      11.62    11.48   10.63
                      12.09     12.37    12.31    12.31   13.34      13.52    13.58   13.45   13.73     13.75    13.74   13.52    13.70      14.46    15.53   15.62
                       5.74      6.78    6.79     6.46    -4.57      -2.85     1.69   2.70    -4.10     -2.32    3.71     3.79    -4.52      -2.12    0.86    0.94
    Sharpe Ratio       1.88      2.04    2.12     2.12    -1.06      -0.31     0.74   0.87    -0.77     -0.09    1.16     1.23    -1.04      -0.11    0.66    0.84
                       1.32      1.48    1.42     1.46    -1.84      -1.01    -0.02   0.23    -1.72     -1.05    0.42     0.42    -1.79      -0.91    -0.07   -0.09
                      16.88     18.46    18.45    18.75   -14.71     -6.87     3.63   5.66    -13.03    -6.15    8.00     8.37    -14.57     -5.70    2.59    3.03
 Daily Return (bps)   10.55     11.22    11.51    11.59    -4.97     -1.46     3.74   4.45     -3.66    -0.45    5.73     6.11     -4.84     -0.50    3.03    3.56
                      6.33      7.25     6.94     7.15     -9.74     -5.41    -0.11   1.21     -9.37    -5.70    2.27     2.26     -9.73     -5.20    -0.43   -0.53
                      12.08     13.10    13.62    14.34   99.98      98.16    19.64   12.82   99.95     97.25    10.57   12.40    99.98      96.42    23.19   24.63
      Max DD          32.51     32.85    31.86    32.62   95.91      69.10    35.16   34.74   91.15     55.02    27.87   29.08    95.53      54.45    35.18   29.40
                      30.31     28.43    30.20    27.85   99.70      96.45    51.28   46.49   99.64     97.06    46.91   46.08    99.71      96.12    64.16   62.50
                       4.86      3.75    4.15     4.93    5.34       4.91     5.00    5.45    12.18     4.67     4.89    12.24    12.11      4.98     4.29    4.31
  Max DD (1-day)       8.28      8.21    8.19     8.19    6.31       6.85     6.96    6.98    7.23      6.55     6.85    6.64     6.78       6.82     7.06    6.64
                       5.56      4.49    5.03     5.27    7.84       7.68     7.60    7.40    11.65     7.99     7.87    11.65    11.65      7.81     7.25    6.64
                       2.24      2.19    2.25     1.72    -0.77      -1.11    -1.49   -1.36   -2.97     -0.81    -1.05   -7.78    -2.77      -1.12    -0.66   -0.50
        Skew           -0.01     0.00    0.02     -0.05   -0.41      -0.42    -0.46   -0.44   -0.44     -0.41    -0.43   -0.31    -0.47      -0.52    -0.53   -0.45
                       0.35      0.38    0.38     0.36    0.15       0.12      0.06   0.12    -0.29     0.17      0.12   -0.27    -0.26      0.03     0.04    0.10
                      33.34     31.81    32.72    26.79   14.18      20.52    19.51   20.58   67.69     18.09    17.60   266.68   61.70      15.74    7.27    7.09
        Kurt          11.62     12.31    12.53    12.56   5.66       6.45     5.47    5.74    6.34      5.08     5.24     5.64    5.99       6.18     6.17    7.73
                      6.17      5.16     5.40     5.53    11.65      9.70     9.22    9.81    15.73     10.44    8.75    13.62    15.40      8.06     5.93    5.32

     Model                     Chronos (Base)                      Chronos (Large)                   TimesFM 1 (200M)                   TimesFM 2 (500M)
   Window Size          5         21    252       512       5         21     252      512       5        21    252    512           5       21    252    512
                      -31.94    -16.69    7.37    14.35   -30.59     -17.40   9.89    20.17   -6.83     -1.83    -1.40   -4.85    -39.62     -33.33   -7.61   -1.47
 Annualized Return    -10.04     -2.99    8.21    13.50    -8.95      -3.05   8.82    13.13   -1.42     4.39      5.00   3.06     -13.04     -11.11   1.02    4.73
                      -21.90    -13.70   -0.84    0.85    -21.64     -14.35   1.07    7.04    -5.41     -6.22    -6.41   -7.91    -26.58     -22.22   -8.64   -6.19
                      7.65      6.74     8.31     8.52    7.66       6.90     7.62    6.91    6.40      9.48     5.06    5.33     9.52       9.23     8.55    7.95
 Standard Deviation   12.07     11.94    10.58    10.10   12.20      11.90    10.96   10.72   12.98     13.18    11.06   11.26    11.79      11.57    11.36   11.57
                      13.61     14.00    15.63    15.63   13.61      13.71    14.97   14.27   11.37     14.28    12.88   12.63    14.32      14.53    14.89   14.86
                       -4.18     -2.48    0.89    1.68    -3.99      -2.52    1.30    2.92    -1.07     -0.19    -0.28   -0.91    -4.16      -3.61    -0.89   -0.18
    Sharpe Ratio       -0.83     -0.25    0.78    1.34    -0.73      -0.26    0.80    1.22    -0.11     0.33      0.45   0.27     -1.11      -0.96    0.09    0.41
                       -1.61     -0.98   -0.05    0.05    -1.59      -1.05    0.07    0.49    -0.48     -0.44    -0.50   -0.63    -1.86      -1.53    -0.58   -0.42
                      -12.68     -6.62    2.92    5.69    -12.14     -6.91    3.92    8.00    -2.71     -0.73    -0.56   -1.93    -15.72     -13.23   -3.02   -0.58
 Daily Return (bps)    -3.98     -1.19    3.26    5.36     -3.55     -1.21    3.50    5.21    -0.56     1.74      1.99   1.22      -5.18      -4.41   0.41    1.88
                       -8.69     -5.44   -0.33    0.34     -8.59     -5.69    0.43    2.79    -2.15     -2.47    -2.54   -3.14    -10.55      -8.82   -3.43   -2.46
                      99.94     97.90    23.95    19.72   99.92      98.22    19.87   15.80   81.06     59.97    32.50   70.13    99.99      99.96    84.86   46.40
      Max DD          92.83     64.37    31.04    27.80   90.86      64.45    38.92   28.55   55.51     41.87    35.81   41.90    96.33      94.25    54.11   45.57
                      99.46     96.52    65.64    53.41   99.42      96.99    53.10   45.85   76.29     84.46    81.81   87.24    99.82      99.50    90.14   84.32
                       4.99      4.98    3.93     5.97    12.08      4.60     5.05    4.31    3.62      6.64     3.84     4.83    7.12       7.88     11.93   12.19
  Max DD (1-day)       6.99      6.44    6.18     6.01    6.97       6.39     5.63    5.42    6.92      7.88     5.59     5.66    7.85       6.71     6.29    6.28
                       8.34      8.17    7.42     6.25    11.65      7.72     7.53    6.21    6.02      7.79     7.15     7.86    9.23       9.22     11.65   11.65
                       -0.79     -0.97   -0.57    -0.54   -3.18      -1.03    -0.84   -0.72   -0.08     -0.43    -0.34   -0.14    -1.51      -1.68    -3.27   -3.91
        Skew           -0.43     -0.48   -0.52    -0.48   -0.41      -0.50    -0.55   -0.43   -0.30     -0.14    -0.43   -0.37    -0.59      -0.65    -0.66   -0.56
                       0.12      0.08     0.02    0.08    -0.30      0.12      0.08   0.15    0.37      -0.10     0.21   0.14     0.02       0.01     -0.30   -0.29
                      13.79     15.52    6.44     6.74    74.25      16.83    11.78   9.52    8.62      11.36    17.94   35.83    19.07      21.97    59.69   81.67
        Kurt          6.12      5.80     7.22     9.55    6.04       5.61     5.34    5.51    6.50      9.73     5.81    6.21     6.41       5.95     5.33    5.03
                      10.77     9.53     5.53     4.58    15.77      10.66    7.17    6.42    8.65      8.73     8.65    9.81     12.69      12.29    14.20   14.08

Note: This table reports average yearly portfolio performance metrics across different rolling window sizes (5, 21, 252, and 512 trading days) for each
model. The benchmark model is CatBoost, the best-performing model among the benchmarks. The time series foundation models (TSFMs) include
Chronos (tiny, mini, small, base, and large) and TimesFM (version 1 with 200 million and version 2 with 500 million parameters). Zero-shot inference
is performed using the pre-trained models released by the respective authors. Each cell displays three values from top to bottom: long–short portfolio,
long-only leg, and short-only leg. Metrics include annualized return, standard deviation, Sharpe ratio, daily return (in basis points), maximum drawdown
(Max DD), one-day maximum drawdown (Max DD (1-day)), skewness, and kurtosis of portfolio returns. Portfolios are formed using decile sorting based
on model forecasts, with equal weighting across stocks.


                                                                               32
   In terms of portfolio performance, the zero-shot forecasts generated by TSFMs do not translate

into economically meaningful trading strategies. As reported in Table 7, portfolios constructed using

TSFM signals deliver substantially lower annualized returns and Sharpe ratios relative to the bench-

mark model, and in many cases yield negative performance, particularly for smaller Chronos variants

and both TimesFM models. These portfolios are further characterized by higher volatility, larger

maximum drawdowns, and unfavorable higher-moment statistics (negative skewness and elevated kur-

tosis). While larger Chronos models exhibit marginal improvements when longer historical windows

are employed, their profitability remains well below those of the benchmark. Among all configura-

tions, the best-performing model is Chronos (large) with a 512-day window, yielding an annualized

return of 20.17% and a Sharpe ratio of 2.92, which are substantially lower than the 47.25% annualized

return and 6.46 Sharpe ratio reported for the benchmark model with the same window size. For the

two TimesFM variants, the strongest configuration is TimesFM 2 with a 512-day window, yielding an

annualized return of –1.47% and a Sharpe ratio of –0.18. Also, the relative performance of the long

and short legs is generally consistent with the benchmark results. Across models and window sizes,

the long leg tends to deliver higher performance than the short leg. Overall, unlike the benchmark

model whose forecasting accuracy translates into economically significant results, these TSFMs lack

the zero-shot generalization capability necessary for effective portfolio construction.22

   Figure 2 illustrates the cumulative log returns of long–short portfolios generated from model fore-

casts across different window sizes. Each panel shows how an initial investment evolves over time

when trading on TSFM signals, compared with the benchmark model and the market (S&P 500).

Shaded regions correspond to U.S. recession periods as identified by the National Bureau of Economic

Research (NBER). The benchmark produces steadily rising and stable cumulative return paths across

all window sizes, consistently outperforming the market. In contrast, portfolios constructed using

TSFM forecasts display flat or declining cumulative returns, with many TSFMs, particularly smaller

Chronos variants and both TimesFM versions, exhibiting persistent losses and sharp drawdowns. Even

the larger Chronos models show only slight improvements at longer window sizes and still fail to gen-

erate sustained positive returns. Overall, these results reinforce our previous findings and indicate

that TSFM-based forecasts do not yield profitable long–short trading strategies in a zero-shot setting,

in clear contrast to the benchmark portfolio.23
   22
      The full cross-sectional return distribution for zero-shot TSFMs is reported in Table B.3. While the benchmark
model produces a clear and monotonic spread in returns across deciles in Table B.2, TSFMs generally fail to generate
a stable ranking structure. In many cases, decile returns appear noisy or inverted, and the H–L spreads are small or
negative, particularly for smaller Chronos and TimesFM models. Even larger TSFM variants only exhibit weak and
inconsistent spread patterns, indicating limited ability to order stocks by expected returns in a zero-shot setting.
   23
      Figure B.1 presents the cumulative log returns of the long and short portfolio legs separately for each model. The
results are consistent with our previous conclusions: while the benchmark model delivers stable performance across the
long and short portfolio legs, TSFM-based portfolios exhibit limited economic value in the zero-shot setting.


                                                          33
      Figure 2: Cumulative Log Returns of Zero-Shot TSFMs: Long–Short Portfolios
                                                 Benchmark          Chronos (Mini)           Chronos (Base)       TimesFM (200M)
                                                 Market             Chronos (Small)          Chronos (Large)      TimesFM (500M)
                                                 Chronos (Tiny)
                                 15
                                      5 days
                                 10

                                  5

                                  0

                                −5

                                −10

                                −15
                                 15
                                      21 days
                                 10

                                  5
        Cumulative Log Return




                                  0

                                −5

                                −10

                                −15
                                 15
                                      252 days
                                 10

                                  5

                                  0

                                −5

                                −10

                                −15
                                 15
                                      512 days
                                 10

                                  5

                                  0

                                −5

                                −10

                                −15
                                   2000               2004        2008            2012            2016         2020          2024
                                                                                      Date

Note: This figure displays the cumulative log returns of long–short portfolios constructed using various
forecasting models over rolling windows of 5, 21, 252, and 512 trading days. The benchmark model is
CatBoost, the best-performing model among the benchmarks. The time series foundation models (TSFMs)
include Chronos (tiny, mini, small, base, and large) and TimesFM (version 1 with 200 million and version
2 with 500 million parameters). Zero-shot inference is performed using the pre-trained models released
by the respective authors. Each subplot corresponds to a specific horizon, as indicated by the text labels
in the upper-left corners. The benchmark model (CatBoost) is highlighted in black with bold lines. The
dashed black line represents the cumulative log return of the market (S&P 500). Shaded areas indicate
U.S. recession periods, as defined by the National Bureau of Economic Research (NBER). All portfolios are
equally weighted.




                                                                                      34
   As discussed earlier, one of the central claims motivating the development of TSFMs is their

purported ability to achieve strong zero-shot forecasting performance. However, the empirical results

presented thus far demonstrate that, at least in the case of Chronos and TimesFM, this claim does

not hold within the financial forecasting domain. While our analysis focuses on these two widely

used models, we extend the zero-shot evaluation to a broader set of TSFMs, encompassing all major

publicly available models and their respective size variants. This expanded analysis offers a more

comprehensive and representative assessment of how current TSFMs perform relative to established

benchmark models. Specifically, our evaluation includes Chronos-Bolt (tiny, mini, small, and base),

TimesFM 2.5, Moirai (small, base, and large) and Moirai 2 (Woo et al., 2024), Kairos (10M, 23M, and

50M parameters) (Feng et al., 2025), Moment (small, base, and large) (Goswami et al., 2024), Lag-

Llama (Rasul et al., 2023), TiRex (Auer et al., 2025), FlowState (Graf et al., 2025), TTM (Ekambaram

et al., 2024), Toto (Cohen et al., 2024), and Sundial (Liu et al., 2025). The forecasting performance

results are reported in Table B.4 and Table B.5, portfolio performance results in Table B.6 and

Table B.7, and spread portfolio performance results in Table B.8 and Table B.9.24

   The extended zero-shot evaluation across a diverse suite of TSFMs reveals pronounced heterogene-

ity in forecasting accuracy, robustness, and portfolio level performance. Forecasting performance vari-

ation appears strongly associated with model scale, with larger models generally delivering improved

accuracy. The most salient finding, however, concerns the pronounced weakness in goodness-of-fit, as
                               2
indicated by consistently low ROOS values across all evaluated TSFMs. In nearly all tested TSFMs,

these models underperform relative to the benchmark, underscoring persistent challenges in achieving

reliable goodness-of-fit. At the portfolio level, Toto demonstrates the strongest zero-shot performance,

followed by Lag-Llama, Sundial, and TiRex. The subsequent group of models, including Moirai 2,

TimesFM 2.5, and Moment (large), exhibit moderate performance among the TSFMs. The remaining

TSFMs can be classified as relatively weak performers.

   A comparison of forecasting performance indicates that, in terms of goodness-of-fit, even Toto
                                                          2
performs relatively poorly, yielding substantially lower ROOS values relative to the benchmark. In its
                                                     2
best-performing configuration, the model attains an ROOS of −114.18% for the 512-day window, which

is markedly worse than the benchmark model’s value of −0.03% for the same window size. Despite

    24
       Different TSFM architectures can generate outputs in fundamentally different ways, meaning that a consistent
aggregation approach is not always achievable. To ensure comparability across models, we adapt our procedure accord-
ingly: if the model provides multiple generated outputs, we use the mean; otherwise, we use the median, and if neither
is available, we use the model’s point forecasting. The number of generated samples for each model follows the proposed
configuration, with Chronos, Kairos, Sundial, and TTM producing 20 samples each, and Lag-Llama, Toto, and Moirai
producing 100 samples each, consistent with the values reported in the respective studies, except where computational
constraints required a proportional reduction. For TSFMs designed to generate a single output per forecast, only one
prediction is produced accordingly.


                                                          35
this, the model exhibits more balanced directional accuracy. For the same configuration, it attains

upward and downward accuracy rates of 55.59% and 45.81%, respectively, compared with 69.14% and

33.37% for the benchmark model. Consequently, it achieves a higher F1 score of 0.50, relative to

the benchmark model’s 0.49. Using a 512-day window, the benchmark’s long–short Sharpe is 6.46

(its peak occurs at 252 days with Sharpe 6.79), with standard deviation 7.31%, maximum drawdown

14.34%, skewness +1.72, and kurtosis 26.79. In comparison, Toto attains a slightly lower Sharpe of

6.22 but lower standard deviation 4.14% and maximum drawdown 8.96%. However, Toto’s return

distribution exhibits materially higher kurtosis (82.53) and negative skewness (−2.66), consistent

with heavier downside tails. Thus, relative to the benchmark, Toto trades lower typical variability

for greater exposure to rare but severe losses; it does not unambiguously dominate the benchmark

on a risk–return basis. The details of the pre-training datasets for the TSFMs are presented in

Table D.2, which highlights the substantial data volumes used by these models, particularly Toto with

approximately 2.3 trillion observations. The enhanced performance observed in TSFMs such as Toto

cannot be explained solely by architectural design improvements; it is more plausibly driven, at least

in part, by the scale of the pre-training data employed.

   Overall, the zero-shot evaluation reveals pronounced heterogeneity in performance across existing

TSFMs. While several models fail to generate meaningful predictive signals and perform close to

random, others achieve moderate accuracy and exhibit early signs of generalization, particularly when

longer window sizes are employed. Moreover, while TSFMs tend to display inferior performance in
          2
terms of ROOS compared to benchmark models, this pattern is not generally observed for directional
           2
accuracy. ROOS measures the calibration of point forecasts, which is a stringent criterion given the high

noise in daily excess returns. In contrast, portfolio performance depends primarily on discrimination,

that is, the ability to correctly capture the sign and cross-sectional ranking of excess returns. A model
                   2
may exhibit a low ROOS because its predicted values are biased or mis-scaled, yet still generate an

informative ordering of assets. When returns are sorted and a top-minus-bottom long–short portfolio

is constructed, even modest predictive advantages in ranking can accumulate into economically sig-

nificant Sharpe ratios. It is also noteworthy that, as presented in Table D.2, apart from a few TSFMs

pre-trained on Bitcoin price series, no directly related return data are utilized for pre-training. The

fact that some models can reach these levels of performance despite having limited or no exposure to

financial data during pre-training is noteworthy, as it suggests that generic time series representations

may already encode structural and temporal features transferable to complex financial forecasting

tasks. However, these mixed outcomes indicate that zero-shot performance alone may not fully cap-

ture the underlying potential of these models. Consequently, a systematic investigation involving both


                                                   36
fine-tuning and domain-adaptive pre-training is essential to assess whether currently low-performing

architectures such as Chronos and TimesFM can be improved to deliver more stable, consistent, and

economically meaningful performance.


5.1.3    Fine-Tuned Results

Although the primary appeal of TSFMs lies in their zero-shot performance, most studies also rec-

ommend fine-tuning as a secondary step to enhance predictive accuracy when zero-shot results are

suboptimal. This approach is consistent with evidence from LLMs, where fine-tuning has been shown

to improve performance on domain-specific tasks. Accordingly, in this study, we extend our analy-

sis by fine-tuning the Chronos and TimesFM models of varying sizes to investigate how this process

influences both forecasting and portfolio performance.

   As shown in Table 8, most fine-tuned Chronos variants and both TimesFM models continue to

exhibit weak out-of-sample fit, with overall accuracy hovering around 50%, similar to their zero-shot

counterparts in Table 6. The notable exception is Chronos (large), which, after fine-tuning, achieves
          2
positive ROOS   2
              (ROOS ≈ 0.46–0.48) across window sizes and market-caps. Nonetheless, there are some
                                   2
improvements, particularly in the ROOS values of TimesFM models and, in some cases, slight gains

in overall accuracy. Also, similar to the zero-shot setting, results after fine-tuning are mixed between

small-cap and large-cap stocks, though some models show a slight edge for small-cap stocks. For

portfolio results, the pattern is even clearer: relative to the zero-shot portfolio results in Table 7,

fine-tuning generally deteriorates performance, often reducing the Sharpe ratio and, in several cases,

reversing it from positive to negative values. Annualized returns for the fine-tuned TSFM portfolios

are mostly negative, with Sharpe ratios ranging from –3.34 to 0.07. Even for Chronos (large), the

improved forecasting metrics do not translate into competitive trading performance.25 The best-

performing configuration is the Chronos (large) model, which attains an annualized return of 0.23%

and a Sharpe ratio of 0.07, both far below the benchmark model’s 46.50% and 6.79 for the same

window size. Also, fine-tuned TSFMs show a similar pattern in which the long leg outperforms the

short leg. Figure 3 presents the cumulative log returns of long–short portfolios for fine-tuned TSFMs.

Compared with the results in Figure 2, the findings further confirm that fine-tuning generally degrades

the performance of TSFM across all window sizes, relative to the zero-shot setting.26

  25
      Table B.10 presents the results obtained after fine-tuning, while Table B.3 reports the spread portfolio performance
of the zero-shot TSFMs. Across Chronos and TimesFM and all window sizes, fine-tuning compresses the decile return
profile as lows rise, highs fall, and middle deciles bunch, most strongly at short horizons and still present at longer
horizons. This compression reduces portfolio profitability and risk-adjusted performance.
   26
      Figure B.2 displays the cumulative log returns of the long and short portfolio legs separately for each model. The
results are consistent with our previous findings, suggesting that fine-tuning the TSFMs does not lead to any improvement
in portfolio performance.


                                                           37
                                                      Table 8: Fine-Tuned TSFMs - Forecasting Performance

    Model                    Benchmark                            Chronos (Tiny)                           Chronos (Mini)                           Chronos (Small)
 Window Size         5         21     252     512         5         21       252       512        5          21       252       512        5          21       252       512
                   -0.25      -0.05   -0.03   -0.03     -284.11   -260.19   -204.18   -206.36   -562.12    -127.03    -75.19    -71.96   -288.93     -86.10   -58.67    -51.89
     R2 OOS        -0.50      -0.38   -0.32   -0.28     -286.65   -293.73   -282.37   -300.82   -565.51    -149.73   -115.26   -117.61   -268.75     -97.87   -78.13    -70.01
                   0.39       0.67    0.64    0.60      -290.49   -233.94   -140.04   -133.98   -578.10    -108.11    -47.08    -42.98   -322.05     -75.72   -42.58    -38.33
                   50.94     51.12    51.08   51.16      49.69     49.71    49.77      49.82    49.86       49.86    50.02     50.04     49.92       49.79    49.86     49.84
  Overall Acc.     50.70     50.74    50.80   50.95      50.53     50.83    50.92      50.95    50.55       50.81    50.81     50.80     50.40       50.78    50.82     50.76
                   51.96     52.48    52.33   52.39      48.60     48.30    48.45      48.54    49.05       48.81    49.32     49.38     49.46       48.65    48.79     48.79
                   68.96     67.82    66.87   69.14      76.67     87.92    90.35      90.30    72.87       84.18    79.70     78.87     67.87       85.31    84.45     82.83
    Up Acc.        72.05     72.97    71.06   74.39      77.47     89.46    94.07      94.42    74.20       87.64    87.99     87.85     70.13       88.00    88.76     86.77
                   68.00     65.11    64.65   66.07      75.25     84.75    83.13      82.36    70.44       77.63    66.92     65.45     63.72       80.14    77.32     76.23
                   33.14     34.60    35.59   33.37      23.35     12.34    10.09      10.20    27.17       16.25    21.01     21.90     32.25       15.03    16.02     17.57
   Down Acc.       28.11     27.25    29.59   26.24      22.48     10.52    5.93       5.60     25.68       12.35    12.10     12.25     29.72       11.97    11.30     13.27
                   37.42     41.01    41.24   39.87      24.80     15.68    17.37      18.19    29.63       22.89    33.55     35.03     36.44       20.31    23.10     24.11
                    0.49      0.49    0.50    0.49       0.46      0.42      0.40      0.40      0.47       0.43      0.45      0.46      0.48       0.43      0.43      0.44
       F1           0.47      0.47    0.48    0.47       0.46      0.41      0.38      0.38      0.47       0.42      0.42      0.42      0.48       0.42      0.42      0.42
                    0.51      0.52    0.52    0.51       0.46      0.42      0.43      0.43      0.47       0.45      0.48      0.48      0.49       0.44      0.45      0.46

    Model                  Chronos (Base)                         Chronos (Large)                         TimesFM 1 (200M)                         TimesFM 2 (500M)
 Window Size         5         21     252     512         5         21       252       512        5          21       252       512        5          21       252       512
                  -1507.22   -11.16   -4.81   -5.42      0.47      0.47      0.46      0.46     -30.17      -15.94    -5.30     -5.10    -532.65    -565.05   -176.49   -147.66
     R2 OOS       -1496.14   -11.72   -5.02   -5.74      0.46      0.45      0.45      0.45     -29.65      -14.56    -5.54     -5.63    -520.63    -561.43   -141.04   -124.07
                  -1548.14   -10.78   -4.67   -5.22      0.48      0.48      0.48      0.48     -32.07      -17.49    -5.18     -4.73    -568.61    -562.05   -178.58   -147.66
                   50.03     49.95    49.99   49.99      49.97     50.24    50.27      50.27    48.72       49.21    49.82     49.88     48.93       49.47    50.00     49.97
  Overall Acc.     50.00     50.19    49.84   49.94      49.98     49.85    49.82      49.79    49.28       49.78    50.23     50.19     49.41       50.00    50.38     50.29
                   50.14     49.64    50.10   49.95      50.02     50.86    50.98      50.98    47.34       48.19    49.38     49.44     47.82       48.59    49.56     49.53
                   49.62     58.73    43.83   48.48      49.72     36.13    35.33      35.02    50.95       56.60    59.55     59.89     47.30       55.10    57.48     57.58
    Up Acc.        50.66     59.56    41.55   46.29      50.37     36.72    36.89      36.41    53.11       59.11    61.65     62.52     49.37       57.45    59.77     60.01
                   47.75     57.32    47.21   51.18      48.71     35.53    33.22      33.17    47.67       54.09    57.84     57.49     44.31       52.64    55.43     55.66
                   50.22     41.31    55.96   51.35      50.01     63.85    64.72      65.02    46.44       41.99    40.56     40.34     50.32       43.67    42.62     42.46
   Down Acc.       49.12     40.38    58.39   53.61      49.30     63.26    63.06      63.53    45.10       39.93    38.55     37.56     49.10       41.74    40.41     39.97
                   51.94     42.67    52.62   48.73      50.85     64.38    66.71      66.75    46.97       43.07    42.11     42.49     50.83       44.84    44.37     44.09
                    0.49      0.50    0.50    0.50       0.49      0.49      0.49      0.49      0.49       0.49      0.49      0.49      0.48       0.47      0.48      0.48
       F1           0.49      0.50    0.49    0.50       0.49      0.49      0.48      0.48      0.49       0.49      0.49      0.49      0.48       0.48      0.48      0.48
                    0.49      0.49    0.50    0.50       0.49      0.49      0.49      0.49      0.47       0.48      0.49      0.49      0.46       0.47      0.48      0.47

Note: This table presents each metric as a set of three values, ordered from top to bottom: full sample, top 25% of firms by market capitalization (large-cap), and
bottom 25% (small-cap) for various predictive models across different window sizes (5, 21, 252, and 512 trading days). The benchmark model is CatBoost, the best-
performing model among the benchmarks. The time series foundation models (TSFMs) include Chronos (tiny, mini, small, base, and large) and TimesFM (version
1 with 200 million and version 2 with 500 million parameters). The models released by the respective authors are fine-tuned on an annual basis. Metrics are first
computed separately for each calendar year using all stock-date observations within that year. The reported values represent the average of these yearly statistics.
Metrics include out-of-sample R2 (ROOS2
                                          ), overall directional accuracy, upward and downward classification accuracy, and macro-averaged F1 score. ‘Overall Acc.’
denotes overall directional accuracy, ‘Up Acc.’ and ‘Down Acc.’ represent the model’s accuracy in predicting upward and downward excess returns respectively, and
‘F1’ refers to the macro-averaged F1 score.



                                                                                      38
                                               Table 9: Fine-Tuned TSFMs - Portfolio Performance

     Model                     Benchmark                         Chronos (Tiny)                      Chronos (Mini)                     Chronos (Small)
   Window Size          5      21    252         512      5       21     252        512       5         21    252      512       5         21     252      512
                      42.54    46.52   46.50    47.25    -3.43    -2.59   -2.46    -1.01    -3.34      -1.84   -0.32   -0.86   -2.87      -2.72    -1.36   -1.67
 Annualized Return    26.58    28.26   29.00    29.22    3.59      3.42   3.69     4.57      3.73       3.94   4.39     4.52    3.13       3.94    4.61     4.67
                      15.95    18.26   17.50    18.03    -7.01    -6.01   -6.15    -5.58    -7.07      -5.78   -4.71   -5.38   -6.00      -6.66    -5.97   -6.34
                      7.40     6.86    6.85      7.31    3.71     5.84    7.17     6.82     3.58      5.77     6.21     5.63   3.51       5.71     5.84     5.07
 Standard Deviation   14.14    13.88   13.71    13.81    13.74    14.73   14.79    14.41    13.64     14.65    14.48   13.99   13.47      14.42    14.12   13.63
                      12.09    12.37   12.31    12.31    11.77    10.12   8.79     8.80     11.55     10.09    9.56     9.64   11.37      10.06    9.67     9.79
                       5.74    6.78    6.79      6.46    -0.92    -0.44   -0.34    -0.15    -0.93      -0.32   -0.05   -0.15   -0.82      -0.48    -0.23   -0.33
    Sharpe Ratio       1.88    2.04    2.12      2.12    0.26      0.23   0.25     0.32      0.27       0.27   0.30     0.32    0.23       0.27    0.33     0.34
                       1.32    1.48    1.42      1.46    -0.60    -0.59   -0.70    -0.63    -0.61      -0.57   -0.49   -0.56   -0.53      -0.66    -0.62   -0.65
                      16.88    18.46   18.45    18.75    -1.36    -1.03   -0.97    -0.40    -1.32      -0.73   -0.13   -0.34   -1.14      -1.08    -0.54   -0.66
 Daily Return (bps)   10.55    11.22   11.51    11.59    1.42      1.36   1.46     1.81      1.48       1.56   1.74     1.79    1.24       1.56    1.83     1.85
                      6.33     7.25    6.94     7.15     -2.78    -2.38   -2.44    -2.21    -2.81      -2.29   -1.87   -2.13   -2.38      -2.64    -2.37   -2.51
                      12.08    13.10   13.62    14.34    56.25    52.31   52.83    35.19    55.21     44.49    28.12   27.81   50.94      50.14    31.62   38.69
      Max DD          32.51    32.85   31.86    32.62    43.19    41.73   43.97    42.05    42.14     41.51    40.52   41.40   44.79      42.37    42.41   37.93
                      30.31    28.43   30.20    27.85    83.96    79.55   78.45    76.23    84.08     78.12    72.25   75.02   79.97      81.08    77.73   79.76
                       4.86    3.75    4.15      4.93    5.06     2.07     3.20     2.32    2.14       2.37    3.04    3.50    1.45       6.79     6.95    2.60
  Max DD (1-day)       8.28    8.21    8.19      8.19    7.12     7.33     6.87     7.13    7.34       7.25    6.73    6.99    6.90       7.41     6.82    6.93
                       5.56    4.49    5.03      5.27    5.80     5.07     4.49     4.08    5.34       5.00    3.87    6.20    5.66       6.44     6.52    6.20
                       2.24    2.19    2.25      1.72    -1.63     0.20   0.19     0.21     -0.05       1.09   1.13     0.20    0.13      -0.96    -0.94    0.08
        Skew          -0.01    0.00    0.02     -0.05    -0.21    -0.13   -0.18    -0.18    -0.26      -0.15   -0.12   -0.20   -0.22      -0.18    -0.18   -0.21
                       0.35    0.38    0.38      0.36    0.24      0.45   0.63     0.68      0.30       0.44   0.62     0.36    0.36       0.19    0.26     0.28
                      33.34    31.81   32.72    26.79    40.29    3.72    3.25     2.95     4.62      18.07    17.92   7.02    2.98       24.64    24.78   4.55
        Kurt          11.62    12.31   12.53    12.56    6.45     5.97    4.70     4.86     6.88      6.00     5.35    5.42    6.51       6.03     5.19    5.68
                      6.17     5.16    5.40     5.53     7.94     8.93    10.64    10.44    7.83      8.18     7.81    8.66    8.31       10.20    10.17   9.56

     Model                    Chronos (Base)                     Chronos (Large)                  TimesFM 1 (200M)                   TimesFM 2 (500M)
   Window Size          5       21    252    512          5        21     252    512          5       21    252    512           5       21    252    512
                      -2.00    -0.61   -1.44    -1.03    -2.11    -0.69   0.23     -0.94    -32.08    -20.45   -1.73   -2.47   -28.72     -17.40   -2.44   -4.02
 Annualized Return     3.79    4.58    4.45      4.77    4.47      4.78   5.10     4.69      -9.94     -5.05   3.68     3.63    -7.94      -3.99   3.62     3.13
                      -5.79    -5.20   -5.89    -5.80    -6.57    -5.47   -4.87    -5.63    -22.14    -15.40   -5.41   -6.10   -20.78     -13.41   -6.06   -7.15
                      2.80     2.50    2.98      2.98    2.62     2.76    3.10     2.97     9.62      9.80     6.04     5.55   9.84       10.33    6.53     5.67
 Standard Deviation   12.59    12.99   11.34    11.15    12.39    11.99   11.85    11.74    11.79     11.64    12.54   12.45   10.81      10.97    12.12   12.04
                      12.87    12.17   12.22    11.93    12.53    12.60   11.62    11.66    14.24     14.51    12.01   11.70   14.52      14.60    11.98   11.66
                      -0.72    -0.25   -0.48    -0.35    -0.80    -0.25   0.07     -0.32    -3.34      -2.09   -0.29   -0.45   -2.92      -1.68    -0.37   -0.71
    Sharpe Ratio       0.30    0.35    0.39      0.43    0.36      0.40   0.43     0.40     -0.84      -0.43   0.29     0.29   -0.73      -0.36    0.30     0.26
                      -0.45    -0.43   -0.48    -0.49    -0.52    -0.43   -0.42    -0.48    -1.55      -1.06   -0.45   -0.52   -1.43      -0.92    -0.51   -0.61
                      -0.79    -0.24   -0.57    -0.41    -0.84    -0.28   0.09     -0.37    -12.73     -8.12   -0.69   -0.98   -11.40     -6.91    -0.97   -1.60
 Daily Return (bps)    1.50    1.82    1.77      1.89    1.77      1.90   2.02     1.86      -3.94     -2.00   1.46     1.44    -3.15     -1.58    1.44     1.24
                      -2.30    -2.06   -2.34    -2.30    -2.61    -2.17   -1.93    -2.23     -8.79     -6.11   -2.15   -2.42    -8.25     -5.32    -2.41   -2.84
                      42.03    16.90   28.74    21.45    42.76    20.85   12.22    21.40    99.94     99.16    50.50   49.32   99.88      98.33    56.73   63.01
      Max DD          44.33    41.18   37.91    41.15    42.81    39.57   37.87    40.26    92.55     77.16    55.79   54.16   87.92      69.97    41.25   40.59
                      81.53    78.51   79.68    79.34    83.02    80.12   77.33    79.02    99.49     97.69    81.64   79.98   99.32      96.41    83.81   83.49
                       1.12    1.09    5.12      5.59    1.13     1.54     1.00     5.97    7.96      12.01    3.02    6.53    8.00       12.01    3.73    6.53
  Max DD (1-day)       7.22    6.80    6.87      6.30    6.74     6.97     6.72     6.81    5.94      5.53     7.05    6.88    5.28       5.50     6.99    6.78
                       6.07    5.55    4.94      5.21    5.96     5.78     5.05     5.37    8.13      11.65    5.87    6.22    8.15       11.65    5.43    6.22
                       1.96    -0.01   -3.53    -4.81    -0.07    -0.52   9.30     -5.54    -1.60      -2.85   -0.35   -1.74   -1.30      -2.02    -0.26   -1.30
        Skew          -0.31    -0.23   -0.37    -0.39    -0.28    -0.39   -0.25    -0.36    -0.48      -0.56   -0.48   -0.45   -0.43      -0.40    -0.33   -0.33
                       0.20    0.29    0.27      0.25    0.24      0.23   0.34     0.27     -0.07      -0.45   0.16     0.15    0.04      -0.17    0.36     0.31
                      51.11    2.63    96.45    138.03   2.87     6.48    351.97   179.60   18.60     44.29    5.76    28.67   17.19      38.36    7.67    25.88
        Kurt          7.04     6.57    6.97      6.45    7.17     7.97     7.93     7.76    5.54      5.27     6.80     6.19   4.30       4.96     6.46    6.11
                      7.15     7.07    6.21      6.61    6.90     6.88     6.05     6.24    12.47     16.51    5.20     7.06   11.98      17.10    6.00    7.45

Note: This table reports average yearly portfolio performance metrics across different rolling window sizes (5, 21, 252, and 512 trading days) for each
model. The benchmark model is CatBoost, the best-performing model among the benchmarks. The time series foundation models (TSFMs) include
Chronos (tiny, mini, small, base, and large) and TimesFM (version 1 with 200 million and version 2 with 500 million parameters). The models released
by the respective authors are fine-tuned on an annual basis. Each cell displays three values from top to bottom: long–short portfolio, long-only leg,
and short-only leg. Metrics include annualized return, standard deviation, Sharpe ratio, daily return (in basis points), maximum drawdown (Max DD),
one-day maximum drawdown (Max DD (1-day)), skewness, and kurtosis of portfolio returns. Portfolios are formed using decile sorting based on model
forecasts, with equal weighting across stocks.


                                                                            39
5.1.4    Pre-Trained Results

The final test evaluates the performance of TSFMs when pre-trained entirely from scratch. In this

context, pre-training refers to the initialization of model parameters using large-scale U.S. excess

return data, consistent with the procedure applied to all benchmark models in Section 5.1.1. We

construct TSFMs following the Chronos and TimesFM architectures but pre-train them exclusively

on our proprietary excess return dataset. This design enables a controlled comparison between models

pre-trained on broad, cross-domain datasets and those trained solely on domain-specific financial data.

Through this experiment, we aim to determine whether pre-training on financial data enhances the

models’ ability to capture return dynamics, a challenge that most existing TSFMs have struggled

to address effectively, as evidenced by both the zero-shot results in Section 5.1.2 and the fine-tuned

results in Section 5.1.3.

   Table 10 reports the forecasting performance of TSFMs that have been pre-trained on U.S. excess

return data. A comparison of these results with the zero-shot results in Table 6 and the fine-tuned

results in Table 8 clearly shows that domain-specific pre-training leads to substantial improvements in

predictive accuracy, stability, and consistency across different window sizes. While zero-shot and fine-

tuned TSFMs exhibit limited forecasting ability, pre-trained models, especially Chronos, demonstrate

substantially better forecasting performance. Across all model specifications, and relative to the zero-

shot results, on average Chronos achieves 1.43% improvement in directional accuracy, and 20.57% in
 2
ROOS                                                         2
     . TimesFM demonstrates a decline in both out-of-sample ROOS and F1 score metrics; however,

it attains an improvement of up to 2.18% in directional accuracy.27 Also, the results align with the

benchmarks, showing a clear edge for small-cap stocks across models and window sizes. Although
                                                                                          2
a clear and consistent improvement is observed when moving from zero-shot and fine-tuned ROOS

results to pre-trained models, especially for Chronos, the performance gap relative to the benchmark

models remains substantial. The best-performing pre-trained TSFM is Chronos (small), which attains
    2
an ROOS of −0.59% for the 512-day window. In absolute terms, this is approximately 20 times lower
                            2
than the benchmark models’ ROOS of −0.03% for the same window size. Once again, this persistent

discrepancy highlights the inherent limitations of TSFMs in achieving accurate goodness-of-fit, which

stem from their architectural design rather than from the size or nature of the data used for pre-

training.28
  27
      The modified DM tests in Table B.11 corroborate our main findings. Across window sizes, the benchmark (CatBoost)
delivers consistently superior out-of-sample accuracy relative to all pre-trained TSFMs. Within the TSFMs, larger models
and longer windows generally help, with Chronos (small) tending to outperform Chronos (tiny) and Chronos (mini), and
TimesFM (20M) often improving on TimesFM (8M) at medium to long windows. Comparing TSFM families, pre-trained
Chronos variants typically outperform pre-trained TimesFM models at comparable window sizes.
   28
      To further examine the forecasting performance of the TSFMs, we visualize the predictive distributions produced
by different variants of the Chronos models. Figure B.4 presents 30-day-ahead interval forecasts (P10 –P90 ) of daily


                                                          40
     Figure 3: Cumulative Log Returns of Fine-Tuned TSFMs: Long–Short Portfolios
                                                 Benchmark    Chronos (Tiny)           Chronos (Small)   Chronos (Large)
                                                 Market       Chronos (Mini)           Chronos (Base)    TimesFM (200M)


                                 15
                                      5 days
                                 10

                                  5

                                  0

                                −5

                                −10

                                −15
                                 15
                                      21 days
                                 10

                                  5
        Cumulative Log Return




                                  0

                                −5

                                −10

                                −15
                                 15
                                      252 days
                                 10

                                  5

                                  0

                                −5

                                −10

                                −15
                                 15
                                      512 days
                                 10

                                  5

                                  0

                                −5

                                −10

                                −15
                                   2000           2004       2008              2012            2016      2020              2024
                                                                                Date

Note: This figure displays the cumulative log returns of long–short portfolios constructed using various
forecasting models over rolling windows of 5, 21, 252, and 512 trading days. The benchmark model is
CatBoost, the best-performing model among the benchmarks. The time series foundation models (TSFMs)
include Chronos (tiny, mini, small, base, and large) and TimesFM (version 1 with 200 million and version
2 with 500 million parameters). The models released by the respective authors are fine-tuned on an annual
basis. Each subplot corresponds to a specific horizon, as indicated by the text labels in the upper-left corners.
The benchmark model (CatBoost) is highlighted in black with bold lines. The dashed black line represents
the cumulative log return of the market (S&P 500). Shaded areas indicate U.S. recession periods, as defined
by the National Bureau of Economic Research (NBER). All portfolios are equally weighted.




                                                                               41
                           Table 10: Pre-Trained TSFMs - Forecasting Performance

     Model                   Benchmark                        Chronos (Tiny)                         Chronos (Mini)
 Window Size        5         21     252     512       5           21      252      512       5        21       252      512
                   -0.25     -0.05   -0.03   -0.03   -3.77     -1.09      -0.65    -0.61    -4.50     -1.26    -0.60    -0.61
     R2 OOS        -0.50     -0.38   -0.32   -0.28   -3.85     -1.24      -0.87    -0.89    -4.43     -1.54    -0.78    -0.83
                   0.39      0.67     0.64    0.60   -3.74     -0.83      -0.30    -0.24    -4.61     -0.87    -0.26    -0.23
                  50.94      51.12   51.08   51.16   50.32     50.65      51.27    51.32    50.24     50.57    51.31    51.34
  Overall Acc.    50.70      50.74   50.80   50.95   49.29     49.86      50.81    50.87    49.31     49.86    50.90    50.87
                  51.96      52.48   52.33   52.39   51.77     52.11      52.80    52.91    51.53     51.96    52.88    53.01
                  68.96      67.82   66.87   69.14   18.50     31.78      46.82    47.66    22.99     33.22    47.43    46.58
    Up Acc.       72.05      72.97   71.06   74.39   17.97     32.02      55.26    55.40    22.31     33.20    55.85    53.22
                  68.00      65.11   64.65   66.07   19.80     33.38      41.48    42.68    24.63     35.01    42.63    43.56
                  33.14      34.60   35.59   33.37   81.36     68.79      55.20    54.54    76.82     67.25    54.67    55.61
   Down Acc.      28.11      27.25   29.59   26.24   81.84     68.00      45.48    45.51    77.43     66.80    45.02    47.72
                  37.42      41.01   41.24   39.87   80.29     68.62      62.76    61.90    75.47     66.88    61.85    61.26
                   0.49      0.49    0.50    0.49    0.44          0.48   0.50     0.50     0.46       0.48    0.50     0.50
       F1          0.47      0.47    0.48    0.47    0.43          0.47   0.48     0.48     0.45       0.47    0.49     0.49
                   0.51      0.52    0.52    0.51    0.45          0.50   0.52     0.52     0.47       0.50    0.52     0.52

     Model                 Chronos (Small)                    TimesFM (8M)                           TimesFM (20M)
 Window Size        5         21     252     512       5           21      252      512       5        21       252      512
                   -3.18     -1.43   -0.65   -0.59   -33.01    -16.71     -22.64   -28.15   -35.12    -16.69   -13.83   -15.03
     R2 OOS        -3.17     -1.40   -0.92   -0.84   -32.39    -17.85     -25.75   -32.83   -32.93    -16.99   -15.66   -17.60
                   -3.20     -1.33   -0.17   -0.15   -35.65    -15.26     -20.82   -25.83   -39.67    -16.09   -12.37   -13.09
                  50.40      50.79   51.36   51.36   49.73     50.80      51.14    51.15    49.88     50.88    51.14    51.12
  Overall Acc.    49.58      50.08   50.86   50.84   49.20     49.94      50.20    50.26    49.84     50.66    50.95    50.98
                  51.65      52.27   53.12   53.20   50.19     52.28      52.82    52.78    49.77     51.53    51.82    51.82
                  26.10      36.59   45.39   45.96   39.75     34.48      34.98    35.52    49.57     54.82    57.46    57.60
    Up Acc.       25.60      37.04   52.00   51.52   41.50     36.12      36.26    36.80    51.06     55.89    57.98    58.45
                  27.57      37.76   42.72   43.93   37.11     32.77      34.21    34.48    47.46     54.05    57.70    57.38
                  73.85      64.36   56.85   56.35   59.15     66.32      66.39    65.84    49.34     46.20    44.34    44.14
   Down Acc.      74.16      63.16   48.97   49.52   56.93     63.98      64.48    64.00    47.46     44.04    42.74    42.26
                  72.89      65.01   62.33   61.38   61.48     69.11      68.59    68.22    51.17     48.71    46.17    46.44
                   0.47      0.49    0.50    0.50    0.47          0.45   0.43     0.43     0.47       0.47    0.45     0.45
       F1          0.46      0.48    0.49    0.49    0.47          0.45   0.42     0.43     0.47       0.46    0.45     0.45
                   0.48      0.51    0.52    0.52    0.47          0.46   0.44     0.44     0.47       0.47    0.46     0.46

Note: This table presents each metric as a set of three values, ordered from top to bottom: full sample, top 25% of
firms by market capitalization (large-cap), and bottom 25% (small-cap) for various predictive models across differ-
ent window sizes (5, 21, 252, and 512 trading days). The benchmark model is CatBoost, the best-performing model
among the benchmarks. The time series foundation models (TSFMs) include Chronos (tiny, mini, and small) and
TimesFM (with 8 million and 20 million parameters). The models are pre-trained from scratch using U.S. excess re-
turn data on an annual basis. Metrics are first computed separately for each calendar year using all stock-date obser-
vations within that year. The reported values represent the average of these yearly statistics. Metrics include out-of-
sample R2 (ROOS
              2
                   ), overall directional accuracy, upward and downward classification accuracy, and macro-averaged
F1 score. ‘Overall Acc.’ denotes overall directional accuracy, ‘Up Acc.’ and ‘Down Acc.’ represent the model’s accu-
racy in predicting upward and downward excess returns respectively, and ‘F1’ refers to the macro-averaged F1 score.




                                                              42
   Moving to portfolio performance results in Table 11, and in comparison with the zero-shot results

in Table 7 and the fine-tuned results in Table 9, a clear improvement in portfolio performance is

observed following domain-specific pre-training. The pre-trained TSFMs, particularly Chronos across

all model sizes, exhibit notably higher annualized returns and Sharpe ratios, especially at medium

and long window sizes. For instance, Chronos (tiny) achieves Sharpe ratios improving from 1.69 to

3.33 for the 252-day window size and from 2.70 to 4.10 for the 512-day window size, compared with

the zero-shot results. Similarly, Chronos (mini) improves from 3.71 to 4.05 at 252 days and from 3.79

to 4.54 at 512 days, while Chronos (small) increases from 0.86 to 4.89 and 0.94 to 5.42 for the same

respective window sizes, all relative to their zero-shot results. TimesFM models also benefit from

pre-training. TimesFM (8M) achieves Sharpe ratios improving from –0.89 to 2.86 for the 252-day

window size and from –0.18 to 3.23 for the 512-day window size, compared with its zero-shot results.

Similarly, TimesFM (20M) improves from –0.89 to 3.51 at 252 days and from –0.89 to 3.66 at 512 days,

both showing substantial gains relative to their zero-shot results. The changes in annualized returns

follow a similar pattern. Moreover, across many model configurations, particularly those with shorter

window sizes, the standard deviation of portfolio returns declines, and maximum drawdowns become

less severe. Among all TSFMs, the Chronos (small) model exhibits the strongest performance for a

window size of 512 days, generating an annualized return of 36.84%, a standard deviation of 6.79%,

and a Sharpe ratio of 5.42. Although these values remain below the corresponding benchmark values

of 47.25%, 7.31%, and 6.46, respectively, for the same window size, the model substantially narrows

the performance gap relative to both the zero-shot and fine-tuned TSFMs. Conversely, we observe a

marked improvement in both maximum drawdown and one-day maximum drawdown when moving

from the benchmark model to Chronos (Small). For the same window size, these metrics decline

from 18.75 and 14.34 to 9.01 and 6.59, respectively. Also, for the same window size, compared with

the benchmark (skew = 1.72, kurtosis = 26.79), the Chronos (small) model shows slightly negative

excess returns for selected U.S. stocks (AAPL and MSFT), generated using Chronos TSFMs. The left column displays
zero-shot forecasts from the publicly available Chronos model, the middle column shows forecasts based on a fine-tuned,
publicly available Chronos model, and the right column reports forecasts from a Chronos model pre-trained on global
excess returns. All models use the small configuration. The black lines represent realized excess returns, the shaded
blue regions denote 80% predictive intervals, and the dashed blue lines indicate the 10th and 90th percentile boundaries.
The vertical dotted line marks the forecast start date. The forecasting horizon spans 30 trading days, from September
19, 2025, to October 31, 2025. The estimation window comprises 512 trading days, covering the period from September
11, 2023, to September 18, 2025. Consistent with Section 5.1.2, the number of generated samples is fixed at 20. For
both AAPL and MSFT, the fine-tuned Chronos model appears systematically mis-centered: realized excess returns fall
outside the 80% predictive intervals. In contrast, the zero-shot variant produces slightly better forecasts, while the pre-
                                                                                                                       2
trained version tracks the realized return path more closely. This illustrates why TSFMs typically exhibit weak ROOS
performance. TSFM-based forecasts tend to align poorly with the realized magnitudes of excess returns, capturing
                                                                                                           2
primarily the directional movements rather than their exact values. This discrepancy leads to lower ROOS        relative to
the benchmarks, despite maintaining reasonably strong directional predictive power. This pattern is consistent with our
broader finding that domain-specific pre-training materially enhances forecast stability and directional accuracy, whereas
fine-tuning on the same dataset, as implemented here, does not. Nonetheless, we do not view fine-tuning as inherently
detrimental; more targeted approaches, such as using narrower, asset-specific datasets or optimized hyperparameter
configurations, may restore or even improve performance.


                                                            43
skew (–0.29) and lower yet still extreme kurtosis (20.43). This indicates a shift toward mild downside

asymmetry and somewhat reduced tail risk. Moreover, consistent with the benchmark, zero-shot, and

fine-tuned results, the pre-trained TSFMs also exhibit stronger performance for the long leg than for

the short leg.29

   Figure 4 displays the cumulative long–short returns of the pre-trained TSFMs. A comparison with

the zero-shot results in Figure 2 and the fine-tuned results in Figure 3 clearly demonstrates that pre-

trained TSFMs deliver substantially improved and more stable portfolio performance. The cumulative

return trajectories show that pre-training enables both Chronos and TimesFM models to generate

persistent positive excess returns over time, in contrast to the flatter or declining patterns observed in

the zero-shot and fine-tuned settings. The improvement is particularly pronounced at longer rolling

window sizes (252 and 512 days), where the pre-trained TSFMs display smoother upward trends.30

   Overall, these results confirm that domain-specific pre-training substantially strengthens TSFM-

based portfolio strategies, transforming previously weak or noisy return profiles into robust and eco-

nomically meaningful performance. These pre-trained TSFMs achieve better alignment between pre-

dictive performance and portfolio performance, yielding higher Sharpe ratios, lower drawdowns, and

more stable returns compared to their generic off-the-shelf pre-trained counterparts. This improvement

is also achieved with substantially smaller model sizes compared to the originally released pre-trained

models. Specifically, TimesFM 2 is scaled down from 500 million parameters to 8 million and 20

million parameter variants. In addition, our Chronos models include tiny, mini, and small variants,

with even the tiny variant outperforming the largest Chronos model released by the original authors,

despite the latter being pre-trained on a more diverse and substantially larger dataset. Another impor-

tant finding is that our pre-trained models generally outperform not only the Chronos and TimesFM

models released by their respective authors, but also the majority of other general-purpose models

evaluated in Section 5.1.2, despite differences in their architectures and pre-training datasets.

   This performance gap underscores the critical importance of pre-training context: exposure to

financial time series enables models to internalize domain-relevant statistical patterns that generic pre-

training fails to capture. Consequently, although the benchmark model still delivers the best overall


  29
      Table B.12 presents the spread portfolio performance of pre-trained TSFMs. A comparison with the zero-shot results
in Table B.3 and the fine-tuned results in Table B.10 shows that domain-specific pre-training substantially improves the
performance of TSFM-based portfolios. While zero-shot models exhibit weak or inconsistent return spreads, pre-trained
variants generate markedly stronger and more stable performance, particularly at longer window sizes. Although the
benchmark model continues to achieve the highest overall returns, pre-training significantly narrows the performance
gap.
   30
      Figure B.3 presents the cumulative log returns of the long and short portfolio legs for each model. The results are
consistent with our previous findings, indicating that pre-training the TSFMs substantially improves portfolio perfor-
mance in both the long and short portfolio legs when evaluated separately.


                                                           44
                            Table 11: Pre-Trained TSFMs - Portfolio Performance

     Model                      Benchmark                        Chronos (Tiny)                     Chronos (Mini)
   Window Size          5        21   252       512       5         21    252      512       5         21    252      512
                      42.54     46.52   46.50   47.25   -1.14     9.47     23.69   28.00   -0.70      9.84    27.55   31.63
 Annualized Return    26.58     28.26   29.00   29.22   6.33      11.63    19.41   21.82    7.31      11.76   21.01   23.80
                      15.95     18.26   17.50   18.03   -7.47     -2.17    4.27     