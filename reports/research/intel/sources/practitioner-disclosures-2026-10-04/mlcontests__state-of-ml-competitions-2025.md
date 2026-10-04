# mlcontests__state-of-ml-competitions-2025
URL: https://mlcontests.com/state-of-machine-learning-competitions-2025/
Fetched: 2026-10-04 18:19 UTC (text only, tags stripped)

The State of Machine Learning Competitions

The State of
Machine Learning Competitions 
2025 Edition 
We analysed trends across hundreds of machine learning competitions that took place in 2025. 
This report highlights the techniques used in winning solutions.

 A Jolt ML Publication 

Highlights 
Bigger training budgets than ever before: winning solutions trained on up to 512 NVIDIA H100 GPUs.
Transformers finally dethrone convolutional neural nets (CNNs) in computer vision competitions.
Qwen dominates language competitions in a continuing shift to decoder models.
“AutoML” and tabular foundation models prove competitive, though GBDTs remain the tabular data standard. 

 ML Competitions Landscape 

More than 390 machine learning competitions took place in 2025, across 30+ platforms,
with a total prize pool of over $16m. These competitions included multi-million-dollar government-funded competitions,
grand challenges like the AI Mathematical Olympiad, and research competitions at ML or computer vision
conferences.1

This report starts with a brief overview of the landscape of competition platforms.
For a dissection of the approaches used by competition winners in 2025, skip ahead
to winning solutions.

 Platforms 

Kaggle remains by far the platform with the most users; it ran the most competitions in 2025, as well as
having the largest total prize pool.2
Tianchi is the second-largest platform by all three of these metrics.
Codabench hosted the third-most competitions in 2025, and its user count more than doubled over the year,
a year in which multiple platforms saw 30%+ user growth and Zindi became the sixth platform to have over 100,000 users.

 2025 Platform Comparison 

 Load Chart 

 Overview of Top Competition Platforms 

PlatformLaunchedUsers3CompetitionsTotal prize money4
AIcrowd 2017394k+13$93,000
Antigranular 20223k+1$5,000
Bitgrit201735k+52$6,000
Codabench202349k+45$248,000
CodaLab201311$21,000
CrunchDAO 202111k+66$300,000
DrivenData 2014125k+4$360,000
EvalAI201740k+34$74,000
Grand Challenge 2010125k+44$76,000
Kaggle 201029m+68$3,668,000
Signate201480k+74$25,000
Solafune 20202$24,000
Synapse201330k+7$7,000
ThinkOnward 20228k+3$80,000
Tianchi20141.4m851$1,028,000
Trustii 20202k+2$46,000
Zindi 2018100k+28$226,000
Other66$9,862,000
 Other platforms 

Competitions in the “Other” bucket in 2025 include:

DARPA’s AI Cyber Challenge

The VN2 Inventory Planning Challenge, hosted on DataSource

Waymo’s annual Open Dataset Challenges.

Various ongoing competitions related to the Vesuvius Challenge

Two ML kernel challenges hosted by GPU Mode in collaboration with AMD

Two competitions hosted on the Pond platform

Dozens of other independent competitions hosted on single-purpose websites

The open-source platform CodaLab is being sunset, and fully replaced by its newer sibling Codabench.9
Codabench is also open-source, developed by the same team, who host a free-to-use instance of the platform.

The other main open-source self-service competitions platform, EvalAI, appears to be introducing hosting fees for the
first time, with its website stating it is “transitioning to a paid plan for hosting challenges”.10

At the same time, Kaggle’s free-to-use self-service “Community Competitions” now allow organisers to offer prizes up to
$10k. Of the 68 Kaggle competitions in our 2025 dataset, 34 were Community competitions.

As well as growing by another seven million users, Kaggle’s product saw more significant features added in 2025 than
in previous years.
New features include
Benchmarks (ongoing leaderboards aimed at comparing frontier models’ performance on standardised tasks),
Game Arena
(player-vs-player tournaments, pitting models against each other in settings like chess, poker, or Werewolf),
and Writeups (long-form blog posts, including for competition solutions).
Kaggle’s progression system — which sets incentives and determines the criteria for becoming a Kaggle “Master” or
“Grandmaster” — also saw a
significant overhaul in 2025.

Other platforms also added features in 2025 — Zindi added
multi-metric evaluation
and new types of competitions, while the open-source Codabench added
numerous quality-of-life features
for competition participants and hosts.

Hugging Face’s Competitions product had its last commit in October 2024,
and the product lead left the company at the beginning of 2025. It still hosted two competitions in 2025, with a total
prize pool of $16k.

DrivenData published a review of
what happens after competitions have concluded, including several case studies detailing
real-world systems deployment, research publications, and hiring decisions based on competition submissions.

 Prizes & Participation 

The largest prize pool in 2025 was $8.5m, for the final round of DARPA’s
AI Cyber Challenge.

The number of competitions with prize pools of $100k or greater has grown consistently in the past four years; we
found 23 such competitions in 2025, up from 18 in 2024.

While the prize pool distribution is usually skewed towards first place
(with the first-placed winner awarded the largest portion of the pool), this year, some judging-panel-evaluated
competitions awarded equal prizes to each of the winners. For example, in the
OpenAI gpt-oss-20b red-teaming challenge,
each of the top ten teams received a $50k prize.

 Prize pool 

 Load Chart 

In general, the competitions with larger prize pools drew more competitors. Aside from the obvious direct draw of the
prize money, competitions with large prizes — especially those posed as ‘grand challenges’ with $1m+ prize pools
conditional on absolute performance — may be embraced as significant milestones by the broader machine learning community.
One example of this is the ARC Prize — since its million-dollar grand prize relaunch in 2024,11 its public
leaderboard is now often used as a yardstick for reasoning performance on new frontier models,12 as well
as being a core research topic for startups (including
Tufa Labs,
Poetiq,
Basis,
Agemo
and Giotto.ai).

The second
AIMO progress prize
had a guaranteed prize pool of over half a million dollars, with an additional $1.6m available conditional on
performance, and drew entries from over 2,200 teams.
The
CIBMTR hematopoietic cell transplantation survival rate prediction
competition, with a $50k prize pool, drew submissions from over 3,000 teams.

Direct community engagement can also attract a large pool of qualified competitors. The
GPU Mode Discord community, which started as a reading group for a parallel
programming book in 2024,
has since grown to over 24,000 members, and hosted two $150k AMD GPU kernel inference competitions in 2025.
The first competition received submissions from
more than 160 teams, a notable amount for an independently-hosted competition.
Alongside competitions, GPU Mode also hosts a lecture series related to kernel development and large language models.

 Leaderboard entries 

 Load Chart 

The most popular competition we found in 2025 was
Jane Street’s Real-Time Market Data Forecasting
competition, with over 3,700 teams taking part and a $120k prize pool.
The median number of teams per competition in our dataset is 36, and the mean is 351.

Many of the competitions at the lower end of this scale are part of competition tracks at conferences,
which are often targeted at researchers within a specific niche rather than the general competitions community.

 Winning Solutions 

To track tools and techniques used by competition winners, we analysed the #1-ranked solution for as many of the
competitions in 2025 as we could,13 and gathered information on programming languages, packages, model architectures, and
computational resources.

Almost all winning teams used Python as the main programming language for their solutions, in line with previous years.
The one exception we found was Kaggle’s
Efficient Chess competition,
for which the winner used C as their primary language, alongside Rust and Python.

The packages listed below represent the key Python packages that make up competition winners’ toolkit.

 Python Packages 

 Core 
 numpy 
 scipy 
 scikit-learn models, transforms, metrics 
 matplotlib low-level plotting 
 seaborn higher-level plotting 

 Deep Learning 
 torch deep learning core 
 pytorch-lightning batteries-included deep learning 
 einops tensor ops with Einstein notation 
 torchmetrics common metrics/loss functions 🆕 

 Tabular 
 -- dataframes -- 
 pandas 
 polars 
 -- gradient-boosted decision trees -- 
 lightgbm 
 xgboost 
 catboost 

 autogluon AutoML on dataframes 

 Vision 
 -- core vision algorithms -- 
 opencv-python 
 torchvision 
 Pillow 
 scikit-image 

 albumentations image augmentations 
 timm pre-trained models 
 monai healthcare imaging 🆕 

 NLP 
 transformers tools for pre-trained models 
 peft parameter-efficient fine-tuning 
 trl reinforcement learning 
 unsloth efficient training/inference 🆕 
 vllm efficient inference 🆕 
 sentence-transformers embedding models 

 Audio 
 librosa music and audio analysis 🆕 
 torchaudio audio/signal processing 🆕 
 jiwer speech-to-text evaluation 🆕 

 Performance and Efficiency 
 joblib parallelisation 
 numba jit compilation 
 onnxruntime fast inference 🆕 
 tensorrt fast NVIDIA GPU inference 🆕 

 Other 
 optuna hyperparameter optimisation 
 datasets loading data 
 huggingface_hub public datasets and models 
 wandb experiment tracking 
 shapely planar geometry 
 onnx model compatibility 🆕 
 hydra config management 🆕 
 tqdm progress bar 
 rich rich text CLI 
 loguru better logging 

 New Additions: Highlights 

librosa is a package for music and audio analysis. It was used in several
audio-focused competitions, mainly for its audio transforms including normalisation and pitch shifting.

monai, the Medical Open Network for Artificial Intelligence, provides a framework
for deep learning in healthcare imaging, built on top of PyTorch. It was used by the winners of several
healthcare-related competitions, including the team that won Kaggle’s
CryoET Object Identification
competition.

torchmetrics provides implementations of over 100 metrics in PyTorch.

onnx is an open format for machine learning interoperability, and
onnxruntime is a cross-platform inference and training accelerator,
developed by Microsoft.
Models can be converted to the ONNX standard from many other frameworks (including PyTorch). Winning solutions using the
ONNX Runtime mostly used it to make model inference more efficient.

hydra is a configuration management framework. Working on ML competitions often
involves running many experiments, and hydra is designed to make it easy to maintain configuration and manage overrides,
whether through configuration files or command line arguments.

unsloth is a library focused on efficient LLM fine-tuning. Built on top of
PyTorch, it enables faster training with lower memory use through a variety of optimisations, including custom GPU
kernels. It can also be used to speed up inference.

vLLM is a library for LLM inference and serving, including features like
batching, quantisation, speculative decoding, and optimised cuda kernels.

autogluon is an AutoML library that aims to build powerful ensembles, making
use of many other modelling libraries, and combines these with bagging and stack-ensembling to maximise predictive
power without manual hyperparameter tuning. It was used for tabular prediction in two winning solutions.

 Deep Learning 

 Deep Learning Libraries 

PyTorch remains the dominant deep learning framework; we found 44 winning solutions using PyTorch and only 1 using TensorFlow.

Of the solutions using PyTorch, 9 also used the higher-level PyTorch Lightning library, which provides additional
ready-to-use wrappers for training loops, data preparation, and other components. For examples of how PyTorch Lightning
was used, see the winning solutions for Zindi’s
Côte d’Ivoire Byte-Sized Agriculture Challenge
or the Vesuvius First Title Prize.

The one winning solution we found using TensorFlow was for the
Geology Forecast Challenge,
a community competition on Kaggle,
where the winner used TensorFlow’s higher-level Keras API.

Despite its popularity in other domains14 we didn’t find any winners using JAX to design or
train their models. Even for the Lux AI Season 3 competition, where
the environment was implemented in JAX, the winning solution used PyTorch.

One winning solution used the Rust-based
bullet framework to train a small neural net for evaluating chess positions.

 Load Chart 

 DataFrames 

DataFrames remain a two-bear race: 61 of the analysed winning solutions used Pandas, and 5 used Polars.

Of the 5 that used Polars, two used it minimally for IO, two used a mix of Polars and Pandas (e.g. some team members
used Pandas, some Polars), and one used Polars as its primary DataFrame
library with Pandas only for interfacing with other machine learning libraries.

For more analysis of Polars use in solutions, see the 2024
and 2023 editions of this report.

 Tabular Data 

Gradient-boosted decision trees (GBDTs) remain the go-to
tabular competition winner’s modelling tool,
sometimes as part of an ensemble alongside neural nets.

Among winning solutions that used GBDTs, XGBoost and LightGBM were most popular this year, with 14 uses each. We
found 8 winning solutions using CatBoost.
Although part of the choice of library is likely due to familiarity, some winners
explicitly stated that they experimented with all three of these libraries, and found significant performance
differences between the different libraries on their dataset.15

AutoGluon was used for tabular prediction in two winning solutions.
Most notably, the winner of Kaggle’s Open Polymer Prediction 2025 competition used AutoGluon as part of an ensemble,
and noted that AutoGluon “was able to beat an ensemble of XGBoost, LightGBM, and TabM models [tuned with] Optuna”, while
using only a fraction of the training budget.16

For the first time, we also saw a tabular foundation model (TabPFN) used, by the
winners of DrivenData’s
PREPARE challenge. The winning team used TabPFN to generate features that were fed into GBDT models.

We also found
one winning solution
using the TabM tabular deep learning model to predict transplant survival rates in a Kaggle competition. Their solution
used TabM as part of an ensemble of models, including GBDTs and a combination of k-nearest-neighbours and graph neural nets.

 Computer Vision 

 Computer Vision Architectures 

For the first time, Transformer-based architectures outnumbered those based on convolutional neural networks (CNNs)
among winning solutions.

 Load Chart 

The most popular Transformer-based architectures included ViT (often DinoV2) and Swin Transformer for image
classification, regression, or segmentation tasks, and Qwen-VL models for image-to-text tasks.

The most popular CNN-based architectures included YOLOv8 and YOLO11 for object detection, and ResNet and
EfficientNet for other tasks.

 Audio 

Audio competitions in 2025 included tasks related to speech recognition, animal species identification from audio clips,
student literacy assessment from audio clips, and dementia screening using acoustic biomarkers from voice recordings.

In four of the five competitions where the audio included human speech, the winners fine-tuned versions of
OpenAI’s Transformer-based Whisper model.
The fifth
used Meta’s W2v-BERT 2.0, based on Conformers, a Transformer/CNN hybrid architecture.

The winner of the
BirdCLEF+ 2025
species identification competition used a mixture of CNN-based models, each with sound-event-detection heads based on
those in a top solution to the 2021 edition of this competition.

 Natural Language Processing 

The ongoing shift from encoder models (like DeBERTa) to decoder models (generative LLMs)
like Llama/Mistral/Gemma/Qwen/DeepSeek
continued in 2025.17

Alibaba’s Qwen was the clear winner among open LLMs in 2025. Almost all of the winning solutions we found
for competitions with a text-processing element involved either a Qwen2.5 model, a Qwen3 model, or both.
We found limited use among winners of other open LLM models.

The winners of all three of the Kaggle competitions with large conditional grand prizes used Qwen models: the winner of the
Konwinski prize used Qwen2.5-Coder-32B,
the winner of the
AIMO progress prize 2 used Qwen2.5-14B,
and the winner of ARC Prize 2025 used Qwen3-4B (as well as other models for synthetic data generation).

We found only one winning team that made use of a BERT-style encoder model. The solution to the
Open Polymer Prediction
competition made use of both CodeBERT and ModernBERT, with full fine-tuning.

Weight quantisation was common among winning NLP solutions, particularly at inference time. Partial fine-tuning using
LoRA was also common, though some teams opted to do full fine-tuning, requiring larger compute budgets.
See last year’s report for more detail on
LoRA and quantisation.

We found three winning solutions using Unsloth for efficient fine-tuning and
inference of transformer-based neural nets implemented in PyTorch. Two of these used test-time fine-tuning, where the
compute constraints of the evaluation environment made efficiency essential.
Four winning solutions used vLLM for efficient LLM inference.

 Compute and Hardware 

There was a shift towards more compute-intensive solutions this year, and we found at least three instances where
multi-node corporate or university-owned clusters were used to train competition-winning solutions.

Nonetheless, there were winning teams at the other end of the spectrum, using (mostly free) cloud notebook services
for training. Nine used Kaggle Notebooks, one used Google Colab’s Free tier, and one used Google Colab’s Pro tier.
Kaggle’s Notebooks generally come with older GPU or TPU hardware, though certain recent Kaggle competitions have
allowed participants to use newer L4 or H100 GPUs.

We also found six winners using personal hardware, and three using rented cloud servers. For the majority of winning
solutions we analysed, we were unable to identify whether the training hardware was owned or rented.

 Hardware Used by Winners 

 Load Chart 

NVIDIA’s H100 finally dethroned the older A100 as the most-commonly-used GPU among winning solutions.
All the winning solutions we found were trained either on NVIDIA GPUs or exclusively on CPUs.18
We did not find any winning teams using AMD GPUs or Google TPUs for training.

 Accelerator Models 

 Load Chart 

Along with the H100, an NVIDIA Hopper generation GPU, first released in 2022, we also saw two of the new NVIDIA Blackwell
generation GPU models being used for training winning solutions: the RTX 5090 and the RTX Pro 6000 Blackwell, both
released in 2025.

Some winning solutions were trained on GPUs released almost a decade ago. In particular,
the NVIDIA T4 and P100, which are
both still available in Kaggle’s notebook environments, were used to train several winning solutions.

 Compare cloud GPU providers 

Use our comparison tool to compare prices for thousands of configurations across dozens of cloud providers.
Bare metal and virtual machines. On-demand, spot, and reserved instances. 

 Compare now → 
Multi-node setups

For the first time this year, we saw several multi-node training setups.
The winners of the WSDM Cup
and ARC Prize 2025 both used four 8xH100 nodes for
training,
a team from Meta used 128 of the older V100 GPUs for their winning solution to the Algonauts Challenge,
and the winners of the
second AI Mathematical Olympiad Progress Prize
used 512 H100 GPUs for training. To quote their write-up, “training lasted 48 hours on 512 H100 (yes, 512!)”.

 Training Budgets 

 Load Chart 

Budgets

While the majority of winning solutions would have cost under $100 to train using on-demand cloud compute,19
some winning solutions used much greater computational resources.

At the high end, 512 H100s were used for 48 hours of training,20
with an estimated on-demand cost of over $60k.21
The second-highest (with a cost estimate of just over $2.5k) used 32 H100s for 27 hours and 8 H100s for 24 hours,22
for ARC Prize 2025.
Both of these teams were made up entirely of NVIDIA employees.23
These training budgets are much larger than those used for competition-winning solutions in previous years
(although still several orders of magnitude below the training budgets for frontier models).

The largest training budget we found in 2024 was around $500, and in 2025 at least four competition winners
exceeded that, including the two NVIDIA teams mentioned above.

[…] my solution cost about $700 in cloud compute costs to develop and run.
This is in line with other top solutions,
but I’m hoping this competition is an outlier in this regard or we’ll have very few competitors going for top spots soon - not to mention the environmental impact.

Jeroen Cottaar, second place in Yale/UNC-CH Geophysical Waveform Inversion

 Top Solutions 

This section highlights a few of 2025’s most innovative or widely-applicable winning solutions.
 Efficient Chess AI Challenge (Linmiao Xu) 

This competition required building a chess agent under tight CPU and memory constraints. Xu’s winning solution paired
the Cfish chess engine with a neural net for position evaluation,
trained using the Rust-based chess neural net framework bullet.
The neural net used an NNUE architecture; a type of incrementally-updatable neural net developed for
sparse binary input spaces with minimal input changes between inference passes.24
This approach, which also used carefully-considered quantisation and compression, beat over 1,000 other teams in
a highly resource-constrained environment.

-> Read the full solution write-up here

“Research tends to look towards larger models, so it was nice to work on tiny models that were very fast to train. As it turns out, neural networks compressible to ~20kb are both significantly faster and stronger than all human knowledge on evaluating chess positions built up over decades!”

Linmiao Xu, winner of the Efficient Chess AI Challenge
 Agile Community Rules Classification (Guanshuo Xu) 

The Jigsaw Agile Community Rules Classification competition had an unusual feature: each
data row included positive and negative examples
— comments which do/do not violate the given moderation rule —
as additional inputs that could be used by competitors’ models.25
Xu’s winning solution generated additional training data from these examples and used that for fine-tuning —
all within the Kaggle competition evaluation environment intended for
inference, and within the 12-hour time limit. Using an ensemble of 6 LLMs (with up to 14 billion parameters each)
within these constraints required switching from PyTorch to Unsloth, a framework
for fast, efficient model training and inference, built on top of PyTorch,
as well as a few other optimisations for both training and inference.

-> Read the full solution write-up here

“Initially, I used vanilla transformers + pytorch code, which works great[…] However, I couldn’t scale beyond 7B models due to memory limitations. Later, I switched to Unsloth, which is much more memory-efficient — it can easily fit a 14B model within 16GB of GPU memory.”

Winner of the Jigsaw Agile Community Rules Classification competition
 Geophysical Waveform Inversion (Harshit Sheoran) 

This was a “prediction” competition, where participants submit their predictions for the test data, as opposed to a
(now more common) “code” competition, where participants submit code that will generate predictions on the
private test set.
The core task in the competition: given the output (seismic data) of a physics simulation, predict the
input (subsurface velocity maps).

Sheoran’s success on this problem came both from
improvements in model architecture and creating
a positive feedback loop between data generation and model training.

After building a model to predict the simulation input, Sheoran iteratively trained this model
by running the simulation forward to get the matching output for each ‘predicted input’.
These newly-labelled (simulation output, simulation input) pairs were then added to the training set for the next
epoch, and the process would repeat.

-> Read the full solution write-up here
 ARC Prize 2025 (Team NVARC) 

In the second iteration of the annual ARC Prize competition, NVIDIA’s Team NVARC built on the winning solution to the
previous iteration (Franzen et al., 2025), as well as the Tiny Relational Model (TRM) architecture
that won the best paper award (Jolicoeur-Martineau, 2025),
and combined that with a multi-stage synthetic data
generation pipeline with hundreds of thousands of synthetic samples.
They achieved a score of 24.03 on the private test set; a lead of almost 50% over second-place’s 16.53.
Their write-up also describes the outcome of some experiments they conducted after the end of the competition.

-> Read the full solution write-up here
 AI Mathematical Olympiad Progress Prize 2 (Team NemoSkills) 

The winning solution
to the second AIMO progress prize used large-scale synthetic data, tool-integrated reasoning,
model merging, significant inference optimisations, and
the largest compute budget
of any
winning solution in 2025. The team published their synthetic training data, as well as a paper
(Moshkov et al., 2025)
describing their approach in more detail.

-> Read the full solution write-up here

For inference optimization, we implemented a pipeline combining TensorRT-LLM conversion with FP8 quantization,
achieving 1.5x speedup over BF16. ReDrafter, a speculative decoding technique developed by Apple,
was used for a further 1.8x speedup.
Our serving system features dynamic batching with early stopping and a time-buffering strategy which allocates
compute resources efficiently.

Inference optimisations in NemoSKills’ AIMO 2 Solution

 Team Demographics 

More than half of the winning teams we found in 2025 were made up of just one person, for the third year in a row.
Teams of more than five were rare.

 Winning Team Sizes 

 Load Chart 

Over half of the winning teams we found were categorised as ‘first-time winners’, with no members who had already won a
competition on the same platform.

 Repeat Winners 

 Load Chart 

As mentioned in the previous sections, two of the most significant Kaggle competitions of 2025 — ARC Prize 2025 and
AIMO Progress Prize 2 — were won by teams of NVIDIA employees, including members of their “KGMON” Kaggle Grandmasters
Of NVIDIA group. This group makes up more than 10% of the current top-50-ranked Kaggle users.26

Some of the members of this group published an article titled
The Kaggle Grandmasters Playbook
in September 2025, giving an accessible introduction to seven techniques, including stacking and pseudo-labelling.

 Trends 

 Academia 

Kaggle published a position paper at the International Conference on Machine Learning (ICML),
making the case for competitions as the gold standard for empirical rigour in Generative AI evaluation.

Empirical evaluation in Generative AI is at a crisis point […]
It is now time for the field to view AI Competitions as the gold standard for empirical rigor in GenAI evaluation,
and to harness and harvest their results with according value.

Kaggle’s position paper at ICML 2025 (Sculley et al., 2025)
 NeurIPS 

The 2025 conference on Neural Information Processing Systems, NeurIPS, marked the tenth year of its official
competitions track.
In this edition, the conference accepted 18 official competitions, with a total prize pool of $270k.
Four of the competitions were hosted on Kaggle,
three on Codabench, and three on EvalAI.

The NeurIPS 2025 competition with the most prize money was the Google Code Golf Championship,
hosted on Kaggle, which had a $100k prize pool and attracted over 1,100 teams. The competition involved writing the
shortest possible programs to solve ARC Prize problems from the ARC-AGI-1 dataset.
Other NeurIPS 2025 competitions included problems related to weather forecasting, exoplanet signal extraction,
robotics and control, and various aspects of LLMs.

 NeurIPS Competitions 

 Load Chart 

 Other conferences 

Most of the competitions at the International Conference on Medical Image Computing and Computer Assisted Intervention
(MICCAI) were hosted on the Grand Challenge platform.
Computer vision workshop competitions at the International Conference on Computer Vision (ICCV)
and the Conference on Computer Vision and Pattern Recognition (CVPR) were mostly hosted on
CodaLab or EvalAI.27

 EurIPS: a new European conference 

In December 2025, the first edition of a Europe-based NeurIPS offshoot, EurIPS, took place in Copenhagen.

 Read our EurIPS coverage → 

 Multi-Year Competitions 

Some updates on ambitious competitions with multi-year agendas. Many of these have headline
grand prizes, often $1m+, paid out when a certain performance milestone is achieved, in addition to guaranteed prizes given out
to top performing teams in each iteration of the competition.

In the second progress prize of the AI Mathematical Olympiad (AIMO),
the winning team took home just over a quarter of a million dollars.
With a score of 34/50 on the private test set, they improved on the high score of 29 in the first progress prize,
despite significantly increased problem difficulty, but they were still a long way short of the 47/50 needed to unlock
the $1.5m+ grand prize.
The
third AIMO progress prize,
with harder problems and a similar conditional prize structure, is currently ongoing.
It ends in April 2026, and at the time of writing nine teams on the public leaderboard have a score of 44/50 — just
three points short of the grand prize level.28

The finals for DARPA’s AI Cyber Challenge
took place at DEF CON 33 in August, with Team Atlanta taking home the $4m prize for first place.
Their write-up can be found on their website.

In the first edition of the Konwinski Prize, the winner took home a $50k prize
for resolving 8% of the GitHub issues in the test set.
Additional prizes would have been unlocked at 10% increments, starting from 30%, up to the 90% success rate required for
the $800k+ top prize.
The winner,
who had a significant lead over others on the leaderboard, credits context management as one of the most important
components of their solution.
The top five teams’ solutions all used either Qwen or DeepSeek models in their solution.

No one reached the 90% success rate for the top prize. The first place winner resolved 8%.
Given the extreme nature of this challenge, this wasn’t a surprise and we consider this a great first step.
We hope that over time that someone will receive the $1M prize.

Konwinski Prize Competition Host, Kaggle

The Vesuvius Challenge paid out close to $100k across multiple prizes in 2025, most notably the
$60k first title prize for reading the title and author
of one of the scrolls non-invasively. Other progress on their research agenda in 2025 included
the first letters in scroll 4 being read.

ARC Prize 2025 concluded with the leading solution reaching 24% on the ARC-AGI-2 private evaluation set, at a cost of
approximately $0.20/task. At the time of writing, the best closed model with a similar cost (Gemini 3 Flash Preview)
achieves 33.6%, and the overall best (closed model) solution achieves 84.6% with a cost of around $14/task.29
The winning team took home $25k. A score of 85% was needed to unlock the additional $700k grand prize.

After the conclusion of ARC Prize 2025, the ARC Prize team published a
blog post
and comprehensive
technical report
with a summary of the results and approaches taken by successful
teams. The organisers identified “refinement loops” as the defining theme of 2025, stating that methods incorporating
weight-space refinement loops “are now achieving competitive performance with remarkably small networks
(7M parameters).”

The winning solution incorporated a Tiny Reasoning Model, as
described in the paper which won ARC Prize 2025’s best paper award and received significant
attention from the broader machine learning community (Jolicoeur-Martineau, 2025).

The organisers aim to make it harder for systems to overfit to ARC problems in the third version of the ARC dataset,
ARC-AGI-3, the first to feature dynamic game-like environments, with
ARC Prize 2026 launching March 25, 2026.30

 Looking Ahead 

Despite the previous claims of “Kaggle grandmaster-level” autonomous agents,
noted last year,
we have yet to see any publications demonstrating successful use of these agents in live competitions.
The advent of improved code generation models and harnesses, as well as evolutionary approaches like
AlphaEvolve (Novikov et al., 2025), may accelerate progress in this area.

 About This Report 

 About ML Contests 

For over six years now, ML Contests has provided a competition directory and shared insights
on trends in machine learning competitions. To receive occasional updates with content like this report,
subscribe to our mailing list or RSS feed.

If you enjoyed reading this report, you might like the previous editions.

 About Jolt 

ML Contests is part of Jolt, an online magazine for ML researchers and
practitioners.

Jolt publishes long-read technical articles, as well as updates and reporting from
major machine learning conferences.

 Acknowledgements 

Thank you to Mia Van Petegem, Peter Carlens, Alex Cross, and James Mundy, for helpful feedback on drafts of this report.

Thank you to the teams at AIcrowd, Antigranular, CrunchDAO, DrivenData, Grand Challenge, Kaggle, Solafune, ThinkOnward,
Trustii, and Zindi, for providing data on their competitions and winning solutions.

Thank you to the competition winners who took the time to answer our questions by email or questionnaire:
Kea Kohv,
Harshit Sheoran,
James Day,
Darius Moruri,
TonyK,
Levi Harris,
Chigozie Nkwocha,
Julius Mwangi M.,
Benson Wainaina,
Duke Kojo Kongo,
and
Naoto Suzuki.

Lastly, thank you to the maintainers of the open source projects we made use of in conducting our research and
producing this page: Astro, Chart.js, Linguist, pipreqs, and nbconvert.

 Methodology 

Data was gathered from correspondence with competition platforms, organisers, and winners, as well as from public online sources.

The following criteria were applied for inclusion. Each competition must:

have a total available prize pool of at least $1,000 in cash or liquid cryptocurrency, or be an official competition at a top machine learning or robotics conference with a dedicated competitions track (such as NeurIPS, MICCAI, or ICRA)

have ended between 1 January 2025 and 31 December 2025 (inclusive).

Where available, we used data provided by each competition platform, describing their own competitions, as a starting point.
Ten platforms were able to provide us with this data.

We did not receive this data from all platforms, and in these cases we gathered the data from their website.
Notably, this applied to CodaLab, Codabench, and EvalAI (three ‘self-service’ platforms where competition organisers can
create their own competitions with minimal to no intervention from the platform team).
For these platforms, we did our best to collect complete data and filter out irrelevant competitions
(such as ones used for class assignments or draft competitions which never ended up running).

Our filter for conference-related competitions was narrower than in previous years. In previous years, any competition
affiliated with a machine learning or robotics conference was automatically eligible (including those at competition
workshops). This resulted in us including a large number of competitions which had very few submissions, and about which
public information was limited and hard to track down. This year we only included conference-related competitions if they were part
of an official competitions track, and only those at “top conferences” — i.e. those with an A or A*
ICORE ranking. Other conference-related competitions which meet the $1k
minimum prize pool threshold were still included.

We were not able to collect full data for all platforms, especially those — like Tianchi and Signate — where English is not the primary language of the platform.
It is likely that there are additional competition platforms as yet unknown to us.
Please contact us if you know of any that are missing.

When counting a “number of competitions” for purposes such as prize pool distribution, or popularity of programming languages, we generally use the following definition:
If a competition is made up of several tracks, each with separate leaderboards and separate prize pools, then each track counts as its own competition.
If a competition is made up of multiple sub-tasks which are all measured together on one main leaderboard for one prize pool, they count together as one competition.
There are some exceptions.6

For the purposes of this report, we consider a “competition winner” to be the #1-placed team in a competition as defined above.
We are aware that other valid usages of the term exist, with their own advantages — for example, anyone winning a Gold/Silver/Bronze medal, or anyone winning a prize in a competition.
For ease of analysis and in order to avoid double-counting, we exclusively consider #1-placed teams in this report when aggregating statistics on “winning solutions” or “competition winners”,
and make occasional reference to other solutions.

Compiling the Python packages section in the winning toolkit involved some editorial choices.
In general, we list packages which were either used in several winning solutions, or instrumental in the success of at
least one winning solution.

The number of users for each platform is sourced from the platform directly, where possible.
Some platforms list their user numbers publicly on their website.
Most other platforms shared their user numbers with us via email.
Solafune chose not to disclose their user numbers.
User numbers for Signate, Tianchi, and Bitgrit are more than a year old, as we did not receive updates on their user numbers before publication of this report and were unable to find more recent public information.
 List of packages 
 [
 ('numpy', 62),
 ('pandas', 61),
 ('torch', 44),
 ('tqdm', 43),
 ('matplotlib', 34),
 ('sklearn', 33),
 ('scipy', 32),
 ('transformers', 25),
 ('torchvision', 16),
 ('seaborn', 16),
 ('cv2', 15),
 ('pil', 15),
 ('xgboost', 14),
 ('lightgbm', 14),
 ('timm', 13),
 ('requests', 12),
 ('yaml', 12),
 ('wandb', 11),
 ('huggingface_hub', 9),
 ('datasets', 9),
 ('pytorch_lightning', 9),
 ('peft', 9),
 ('catboost', 8),
 ('joblib', 8),
 ('setuptools', 8),
 ('albumentations', 8),
 ('skimage', 7),
 ('ipython', 7),
 ('einops', 6),
 ('librosa', 6),
 ('optuna', 6),
 ('monai', 6),
 ('onnxruntime', 6),
 ('rich', 6),
 ('torchmetrics', 6),
 ('polars', 6),
 ('simpleitk', 5),
 ('omegaconf', 5),
 ('pydantic', 5),
 ('accelerate', 4),
 ('vllm', 4),
 ('onnx', 4),
 ('mmengine', 4),
 ('safetensors', 4),
 ('xformers', 4),
 ('shap', 4),
 ('kagglehub', 4),
 ('evaluate', 4),
 ('packaging', 4),
 ('hydra', 4),
 ('soundfile', 3),
 ('pkg_resources', 3),
 ('click', 3),
 ('nibabel', 3),
 ('psutil', 3),
 ('mmcv', 3),
 ('plotly', 3),
 ('shapely', 3),
 ('numba', 3),
 ('geopandas', 3),
 ('tabulate', 3),
 ('bitsandbytes', 3),
 ('torchaudio', 3),
 ('unsloth', 3),
 ('tensorrt', 3),
 ('loguru', 3),
 ('jiwer', 3),
 ('pycocotools', 3)
] 

 Attribution 
For attribution in academic contexts, please cite this work asCarlens, H, "State of Machine Learning Competitions in 2025", ML Contests, 2026.

BibTeX citation@article{
carlens2026state,
author = {Carlens, Harald},
title = {State of Machine Learning Competitions in 2025},
journal = {ML Contests},
year = {2026},
note = {https://mlcontests.com/state-of-machine-learning-competitions-2025},
}

 Footnotes 
 Footnotes 

These counts include only official conference competitions, or those with a prize pool of at least $1k.
Inclusion criteria this year were more restrictive than in previous years. See methodology for more details. ↩

Part of the growth in Kaggle’s competitions as measured by this report is the
introduction of prize money for Kaggle’s free self-service “Community Competitions”, which was not possible before October 2024.
“As of today, community competition hosts can offer a prize pool of up to $10,000 USD in their competitions” — Kaggle blog post ↩

For the following platforms, user numbers were taken from their public websites on 2 Feb 2026: Kaggle, EvalAI, AIcrowd, Codabench, Zindi. ↩

The number of competitions and total prize money amounts are for competitions that ended in 2025. Prize money figures include only cash and liquid cryptocurrency. Travel grants and other types of prizes are excluded. Amounts are approximate — currency conversion is done at data collection time, and amounts are rounded to the nearest $1,000 USD. See Methodology for more details. ↩

User numbers for Bitgrit are as of March 2024. We reached out to the team at Bitgrit for updated information but did not get a response. ↩

CrunchDAO’s DataCrunch, which runs
continuously with prizes paid out monthly, is counted as one competition here. ↩ ↩2

“More than 80,000 high-level human resources are participating, including excellent data scientists at major companies and students majoring in the AI field. (as of February 2023)”. Source: Signate’s website, translated from Japanese using Google Translate on 3rd of February 2026. ↩

Tianchi user numbers are from April 2024. ↩

“As announced early last year, the CodaLab instance has been phased out for
hosting new competitions and for handling submissions on existing
competitions. As of September 2025, the creation of new competitions has
been disabled. Submissions processing has now been fully stopped as of
January 20th, 2026.
If you are a competition organizer and would like to continue accepting
submissions for your competition, you can migrate it to CodaBench, which is
now our main and actively supported platform. CodaBench supports CodaLab
bundles and provides equivalent—and extended—functionality”
(Email from the Codalab and Codabench team to their mailing list, 20 Jan 2026) ↩

A notice on EvalAI’s site reads: “Update: EvalAI is transitioning to a paid plan for hosting challenges and is sunsetting support for code-upload and static code-upload challenges. “ ↩

ARC was initially run on Kaggle in 2020 as the Abstraction and Reasoning Challenge, with $20k
in prizes, and was relaunched as the $1m+ ARC prize in 2024. ↩

For example, OpenAI worked with the ARC Prize team
to benchmark a version of their o3 model before release. ↩

For this analysis, we used winning solutions’ code where it was publicly available. When
solution code was unavailable, we gathered information either from write-ups or from communication with the winning
teams. For this section of the report, we consider only competitions where performance is a key criterion,
excluding competitions without a numeric success metric. ↩

For example, JAX’s success in statistical modelling. In this October 2025
blog post by Bob Carpenter,
co-founder of the popular probabilistic programming language Stan, he notes that “For high end applications, Stan is
slowly, but surely, being replaced by JAX.” ↩

For example,
the winner
of the March Machine Learning Mania competition stated that they found XGBoost to perform much better than CatBoost and
LightGBM.
The winner
of FlightRank 2025 stated that “XGBoost consistently performed best, with LightGBM adding useful diversity; CatBoost underperformed.” ↩

“AutoGluon’s “best” quality preset with a 2 hour limit for each property was able to beat an ensemble of XGBoost,
LightGBM, and TabM models that I tuned with Optuna and ~20x that amount of compute (not counting data preprocessing tuning,
which was in the ballpark of ~1 day per downstream prediction library I paired it with,
or all the other models I tried before settling on XGB + LGBM + TabM for the relatively manual ensemble).” — James Day, winner of Open Polymer Prediction 2025 ↩

We have commented on earlier phases of this shift in previous years. ↩

CPU-based training was common for gradient-boosted tree models, even though these do generally support GPU-based training. ↩

In fact, many winning solutions were trained at effectively zero marginal cost using free cloud
notebooks or personal devices. ↩

Interestingly, the
third-place finisher
in this competition did not do any training or fine-tuning at all, and scored 30/50 on the private test
set compared to the winners’ 34/50. ↩

We estimated approximate training budgets by combining reported hardware, training time, and median on-demand
cloud compute prices.
Prices are sourced from our cloud-gpus.com comparison page data.
For CPU instances, a nominal cost of 5 cents/h was used. These costs do not reflect actual spend in most
cases, but are intended as an approximate way to compare total computational resources used during training. ↩

This compute estimate includes only final model training, not synthetic data generation.
The total number of H100-hours used for their final solution is higher than this, but we do not have an estimate of how
much higher. ↩

While we have not explicitly confirmed this, it is our understanding that NVIDIA provides compute
resources to some of their employees for use in competitions. ↩

NNUE stands for Efficiently Updatable Neural Network. Initially developed for computer Shogi, it was
adopted by the Stockfish chess engine in 2020. For more on NNUE and chess, see
this introductory article,
or this more technical overview. ↩

The two moderation rules included in the training dataset were “No legal advice: Do not offer or request legal advice.”
and “No Advertising: Spam, referral links, unsolicited advertising, and promotional content are not allowed”. The test
dataset included an unspecified number of additional rules. ↩

See top-ranked NVIDIA Kagglers and KGMON. ↩

We included fewer of these in our data collection than last year, since our eligibility
criteria changed. ↩

With the assumption that a solution with a public leaderboard score of 44/50 would also have a
private leaderboard score of 44/50, which it may not. ↩

While generally comparable, it’s worth noting that the Kaggle competition was evaluated on the
private test set, whereas evaluations for closed models are run on the “semi-private” test set, where there remains
a higher risk of leakage because test examples are exposed to model APIs.
Cost vs score graphs for ARC-AGI-1 and ARC-AGI-2 can be found on the ARC Prize Leaderboard. ↩

See the ARC organisers’ comments on Overfitting on Knowledge. ↩

 References 

Alyaev, S., Blaser, N., Fedorov, A., & Kuvaev, I. (2025). Geology Forecast Challenge. https://kaggle.com/competitions/geology-forecast-challenge-open

Carlens, H. (2024). State of Competitive Machine Learning in 2023. ML Contests Research.

Carlens, H. (2025). State of Machine Learning Competitions in 2024. ML Contests Research.

Chollet, F., Knoop, M., Kamradt, G., & Landers, B. (2026). ARC Prize 2025: Technical Report. https://arxiv.org/abs/2601.10904

Chollet, F., Knoop, M., Kamradt, G., Reade, W., & Howard, A. (2025). ARC Prize 2025. https://kaggle.com/competitions/arc-prize-2025

Desai, M., Zhang, Y., Holbrook, R., O’Neil, K., & Demkin, M. (2024). Jane Street Real-Time Market Data Forecasting. https://kaggle.com/competitions/jane-street-real-time-market-data-forecasting

Deshpande, T., Akdemir, D., Reade, W., Chow, A., Demkin, M., & Bolon, Y.-T. (2024). CIBMTR - Equity in post-HCT Survival Predictions. https://kaggle.com/competitions/equity-post-HCT-survival-predictions

Doerschuk-Tiberi, B., Howard, A., Demkin, M., Cukierski, W., & Sculley, D. (2024). FIDE & Google Efficient Chess AI Challenge. https://kaggle.com/competitions/fide-google-efficiency-chess-ai-challenge

Franzen, D., Disselhoff, J., & Hartmann, D. (2025). Product of Experts with LLMs: Boosting Performance on ARC Is a Matter of Perspective. https://arxiv.org/abs/2505.07859

Frieder, S., Bealing, S., Nikolaiev, A., Smith, G. C., Buzzard, K., Gowers, T., Liu, P. J., Loh, P.-S., Mackey, L., de Moura, L., Roberts, D., Sculley, D., Tao, T., Balduzzi, D., Coyle, S., Gerko, A., Holbrook, R., Howard, A., & Markets, X. (2024). AI Mathematical Olympiad - Progress Prize 2. https://kaggle.com/competitions/ai-mathematical-olympiad-progress-prize-2

Frieder, S., Bealing, S., Vonderlind, P., Li, S., Nikolaiev, A., Smith, G. C., Buzzard, K., Gowers, T., Liu, P. J., Loh, P.-S., Mackey, L., de Moura, L., Roberts, D., Sculley, D., Tao, T., Balduzzi, D., Coyle, S., Gerko, A., Holbrook, R., … Markets, X. (2025). AI Mathematical Olympiad - Progress Prize 3. https://kaggle.com/competitions/ai-mathematical-olympiad-progress-prize-3

Gang Liu, & Cruz, M. (2025). NeurIPS - Open Polymer Prediction 2025. https://kaggle.com/competitions/neurips-open-polymer-prediction-2025

Harrington, K., Paraan, M., Cheng, A., Ermel, U. H., Kandel, S., Kimanius, D., Montabana, E., Peck, A., Schwartz, J., Serwas, D., Siems, H., Wang, F., Yu, Y., Zhao, Z., Zheng, S., Reade, W., Demkin, M., Maitland, K., McCarthy, D., … Carragher, B. (2024). CZII - CryoET Object Identification. https://kaggle.com/competitions/czii-cryo-et-object-identification

Harris, L., & Chen, T. (2026). A Space-Time Transformer for Precipitation Nowcasting. https://arxiv.org/abs/2511.11090

Jolicoeur-Martineau, A. (2025). Less is More: Recursive Reasoning with Tiny Networks. https://arxiv.org/abs/2510.04871

Klinck, H., Cañas, J. S., Demkin, M., Dane, S., Kahl, S., & Denton, T. (2025). BirdCLEF+ 2025. https://kaggle.com/competitions/birdclef-2025

Konwinski, A., Rytting, C., Shaw, J. F. A., Dane, S., Reade, W., & Demkin, M. (2024). Konwinski Prize. https://kaggle.com/competitions/konwinski-prize

lin Wei-Chiang, Frick, E., Dunlap, L., Angelopoulos, A., Gonzalez, J. E., Stoica, I., Dane, S., Demkin, M., & Keating, N. (2024). WSDM Cup - Multilingual Chatbot Arena. https://kaggle.com/competitions/wsdm-cup-multilingual-chatbot-arena

Lin, Y., Lu, L., Reade, W., Howard, A., Cruz, M., Chow, A., & Inversion, Y.-U. D.-D. F. W. (2025). Yale/UNC-CH - Geophysical Waveform Inversion. https://kaggle.com/competitions/waveform-inversion

Moffitt, M. D., Thakkar, D., Burnell, R., Firat, O., Reade, W., Dane, S., & Howard, A. (2025). NeurIPS 2025 - Google Code Golf Championship. https://kaggle.com/competitions/google-code-golf-2025

Moshkov, I., Hanley, D., Sorokin, I., Toshniwal, S., Henkel, C., Schifferer, B., Du, W., & Gitman, I. (2025). AIMO-2 Winning Solution: Building State-of-the-Art Mathematical Reasoning Models with OpenMathReasoning dataset. https://arxiv.org/abs/2504.16891

Novikov, A., Vũ, N., Eisenberger, M., Dupont, E., Huang, P.-S., Wagner, A. Z., Shirobokov, S., Kozlovskii, B., Ruiz, F. J. R., Mehrabian, A., Kumar, M. P., See, A., Chaudhuri, S., Holland, G., Davies, A., Nowozin, S., Kohli, P., & Balog, M. (2025). AlphaEvolve: A coding agent for scientific and algorithmic discovery. https://arxiv.org/abs/2506.13131

Sculley, D., Cukierski, W., Culliton, P., Dane, S., Demkin, M. M., Holbrook, R., Howard, A., Mooney, P. T., Reade, W., Risdal, M., & Keating, N. (2025). Position: AI Competitions Provide the Gold Standard for Empirical Rigor in GenAI Evaluation. Forty-Second International Conference on Machine Learning Position Paper Track. https://openreview.net/forum?id=Rxd2TpV6Eg

Sculley, D., Marks, S., & Howard, A. (2025). Red‑Teaming Challenge - OpenAI gpt-oss-20b. https://kaggle.com/competitions/openai-gpt-oss-20b-red-teaming

Sorensen, J., Santos, L. D., Vasserman, L., Cruz, M., Acosta, T., & Reade, W. (2025). Jigsaw - Agile Community Rules Classification. https://kaggle.com/competitions/jigsaw-agile-community-rules

Tao, S., Kumar, A., Doerschuk-Tiberi, B., Pan, I., Howard, A., & Su, H. (2024). NeurIPS 2024 - Lux AI Season 3. https://kaggle.com/competitions/lux-ai-season-3

Umuganda, D. (2025). Kinyarwanda Automatic Speech Recognition Track A. https://kaggle.com/competitions/kinyarwanda-automatic-speech-recognition-track-a

Franzen, D., Disselhoff, J., & Hartmann, D. (2025). Product of Experts with LLMs: Boosting Performance on ARC Is a Matter of Perspective. https://arxiv.org/abs/2505.07859
Jolicoeur-Martineau, A. (2025). Less is More: Recursive Reasoning with Tiny Networks. https://arxiv.org/abs/2510.04871
Moshkov, I., Hanley, D., Sorokin, I., Toshniwal, S., Henkel, C., Schifferer, B., Du, W., & Gitman, I. (2025). AIMO-2 Winning Solution: Building State-of-the-Art Mathematical Reasoning Models with OpenMathReasoning dataset. https://arxiv.org/abs/2504.16891
Sculley, D., Cukierski, W., Culliton, P., Dane, S., Demkin, M. M., Holbrook, R., Howard, A., Mooney, P. T., Reade, W., Risdal, M., & Keating, N. (2025). Position: AI Competitions Provide the Gold Standard for Empirical Rigor in GenAI Evaluation. Forty-Second International Conference on Machine Learning Position Paper Track. https://openreview.net/forum?id=Rxd2TpV6Eg
Jolicoeur-Martineau, A. (2025). Less is More: Recursive Reasoning with Tiny Networks. https://arxiv.org/abs/2510.04871
Novikov, A., Vũ, N., Eisenberger, M., Dupont, E., Huang, P.-S., Wagner, A. Z., Shirobokov, S., Kozlovskii, B., Ruiz, F. J. R., Mehrabian, A., Kumar, M. P., See, A., Chaudhuri, S., Holland, G., Davies, A., Nowozin, S., Kohli, P., & Balog, M. (2025). AlphaEvolve: A coding agent for scientific and algorithmic discovery. https://arxiv.org/abs/2506.13131
Deshpande, T., Akdemir, D., Reade, W., Chow, A., Demkin, M., & Bolon, Y.-T. (2024). CIBMTR - Equity in post-HCT Survival Predictions. https://kaggle.com/competitions/equity-post-HCT-survival-predictions
Sculley, D., Marks, S., & Howard, A. (2025). Red‑Teaming Challenge - OpenAI gpt-oss-20b. https://kaggle.com/competitions/openai-gpt-oss-20b-red-teaming
Frieder, S., Bealing, S., Nikolaiev, A., Smith, G. C., Buzzard, K., Gowers, T., Liu, P. J., Loh, P.-S., Mackey, L., de Moura, L., Roberts, D., Sculley, D., Tao, T., Balduzzi, D., Coyle, S., Gerko, A., Holbrook, R., Howard, A., & Markets, X. (2024). AI Mathematical Olympiad - Progress Prize 2. https://kaggle.com/competitions/ai-mathematical-olympiad-progress-prize-2
Desai, M., Zhang, Y., Holbrook, R., O’Neil, K., & Demkin, M. (2024). Jane Street Real-Time Market Data Forecasting. https://kaggle.com/competitions/jane-street-real-time-market-data-forecasting
Doerschuk-Tiberi, B., Howard, A., Demkin, M., Cukierski, W., & Sculley, D. (2024). FIDE & Google Efficient Chess AI Challenge. https://kaggle.com/competitions/fide-google-efficiency-chess-ai-challenge
Harrington, K., Paraan, M., Cheng, A., Ermel, U. H., Kandel, S., Kimanius, D., Montabana, E., Peck, A., Schwartz, J., Serwas, D., Siems, H., Wang, F., Yu, Y., Zhao, Z., Zheng, S., Reade, W., Demkin, M., Maitland, K., McCarthy, D., … Carragher, B. (2024). CZII - CryoET Object Identification. https://kaggle.com/competitions/czii-cryo-et-object-identification
Carlens, H. (2024). State of Competitive Machine Learning in 2023. ML Contests Research.
Carlens, H. (2025). State of Machine Learning Competitions in 2024. ML Contests Research.
Alyaev, S., Blaser, N., Fedorov, A., & Kuvaev, I. (2025). Geology Forecast Challenge. https://kaggle.com/competitions/geology-forecast-challenge-open
Tao, S., Kumar, A., Doerschuk-Tiberi, B., Pan, I., Howard, A., & Su, H. (2024). NeurIPS 2024 - Lux AI Season 3. https://kaggle.com/competitions/lux-ai-season-3
Umuganda, D. (2025). Kinyarwanda Automatic Speech Recognition Track A. https://kaggle.com/competitions/kinyarwanda-automatic-speech-recognition-track-a
Klinck, H., Cañas, J. S., Demkin, M., Dane, S., Kahl, S., & Denton, T. (2025). BirdCLEF+ 2025. https://kaggle.com/competitions/birdclef-2025
Konwinski, A., Rytting, C., Shaw, J. F. A., Dane, S., Reade, W., & Demkin, M. (2024). Konwinski Prize. https://kaggle.com/competitions/konwinski-prize
Chollet, F., Knoop, M., Kamradt, G., Reade, W., & Howard, A. (2025). ARC Prize 2025. https://kaggle.com/competitions/arc-prize-2025
Gang Liu, & Cruz, M. (2025). NeurIPS - Open Polymer Prediction 2025. https://kaggle.com/competitions/neurips-open-polymer-prediction-2025
lin Wei-Chiang, Frick, E., Dunlap, L., Angelopoulos, A., Gonzalez, J. E., Stoica, I., Dane, S., Demkin, M., & Keating, N. (2024). WSDM Cup - Multilingual Chatbot Arena. https://kaggle.com/competitions/wsdm-cup-multilingual-chatbot-arena
Sorensen, J., Santos, L. D., Vasserman, L., Cruz, M., Acosta, T., & Reade, W. (2025). Jigsaw - Agile Community Rules Classification. https://kaggle.com/competitions/jigsaw-agile-community-rules
Lin, Y., Lu, L., Reade, W., Howard, A., Cruz, M., Chow, A., & Inversion, Y.-U. D.-D. F. W. (2025). Yale/UNC-CH - Geophysical Waveform Inversion. https://kaggle.com/competitions/waveform-inversion
Moffitt, M. D., Thakkar, D., Burnell, R., Firat, O., Reade, W., Dane, S., & Howard, A. (2025). NeurIPS 2025 - Google Code Golf Championship. https://kaggle.com/competitions/google-code-golf-2025
Chollet, F., Knoop, M., Kamradt, G., & Landers, B. (2026). ARC Prize 2025: Technical Report. https://arxiv.org/abs/2601.10904
Harris, L., & Chen, T. (2026). A Space-Time Transformer for Precipitation Nowcasting. https://arxiv.org/abs/2511.11090
Frieder, S., Bealing, S., Vonderlind, P., Li, S., Nikolaiev, A., Smith, G. C., Buzzard, K., Gowers, T., Liu, P. J., Loh, P.-S., Mackey, L., de Moura, L., Roberts, D., Sculley, D., Tao, T., Balduzzi, D., Coyle, S., Gerko, A., Holbrook, R., … Markets, X. (2025). AI Mathematical Olympiad - Progress Prize 3. https://kaggle.com/competitions/ai-mathematical-olympiad-progress-prize-3