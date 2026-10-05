source: https://arxiv.org/pdf/2007.05290
fetched_utc: 2026-10-04T18:46:41Z
bytes_raw: 846769

Temporally Correlated Task Scheduling for Sequence Learning


                                         Xueqing Wu 1 Lewen Wang 2 Yingce Xia 2 Weiqing Liu 2 Lijun Wu 2 Shufang Xie 2 Tao Qin 2 Tie-Yan Liu 2


                                                                  Abstract                                  neous machine translation, we need to begin translation
                                                                                                            before reading the complete source sequence. In this appli-
                                             Sequence learning has attracted much research                  cation, the generation of output sentence is k word behind
                                             attention from the machine learning community                  the source input, which is called wait-k strategy/task (Ma
                                             in recent years. In many applications, a sequence
arXiv:2007.05290v2 [cs.CL] 2 Jul 2021




                                                                                                            et al., 2019). Wait-k tasks with different k values are tem-
                                             learning task is usually associated with multiple              porally correlated. (2) Stock forecasting aims to predict the
                                             temporally correlated auxiliary tasks, which are               trend of stocks at some future day (Dai & Zhang, 2013).
                                             different in terms of how much input information               Tasks of predicting stock prices at different future days con-
                                             to use or which future step to predict. For exam-              stitute a set of temporally correlated tasks. Different from
                                             ple, (i) in simultaneous machine translation, one              general multi-task learning, the input and output data of
                                             can conduct translation under different latency                these temporally correlated tasks are highly overlapped, and
                                             (i.e., how many input words to read/wait before                only differ in how much future input to use when processing
                                             translation); (ii) in stock trend forecasting, one             the current input (e.g., how many future source words to read
                                             can predict the price of a stock in different future           to translate the current word in simultaneous translation) or
                                             days (e.g., tomorrow, the day after tomorrow).                 which future data to predict (e.g., the price movement of
                                             While it is clear that those temporally correlated             which future day to predict in stock trend forecasting).
                                             tasks can help each other, there is a very limited
                                             exploration on how to better leverage multiple                 Clearly, a given sequence learning task (denoted as the main
                                             auxiliary tasks to boost the performance of the                or target task) can be boosted by its temporally correlated
                                             main task. In this work, we introduce a learnable              tasks. Taking English-to-Vietnamese simultaneous trans-
                                             scheduler to sequence learning, which can adap-                lation as an example, assume the main task is wait-3, and
                                             tively select auxiliary tasks for training depending           the temporally correlated tasks are wait-1, 2, 3, · · · , 13. By
                                             on the model status and the current training data.             training a model on all those correlated tasks and evaluating
                                             The scheduler and the model for the main task                  the model on wait-3, we observe that the BLEU score is im-
                                             are jointly trained through bi-level optimization.             proved from 27.17 to 28.54. (BLEU (Papineni et al., 2002)
                                             Experiments show that our method significantly                 is a widely used accuracy metric in machine translation,
                                             improves the performance of simultaneous ma-                   the larger the better.) A similar phenomenon is observed
                                             chine translation and stock trend forecasting.                 in stock price forecasting. Improvements across various
                                                                                                            applications motivate us to explore how to leverage those
                                                                                                            temporally correlated tasks more effectively to improve per-
                                                                                                            formance on the main task.
                                        1. Introduction
                                                                                                            Given that there are usually multiple temporally correlated
                                        Sequence learning (Sutskever et al., 2014; Bahdanau et al.,
                                                                                                            tasks, the key challenge lies in which tasks to use and when
                                        2014) is an important problem in deep learning, which cov-
                                                                                                            to use them in the training process. In this work, we in-
                                        ers many applications including machine translation (Wu
                                                                                                            troduce a learnable task scheduler for sequence learning,
                                        et al., 2016; Vaswani et al., 2017), time series predic-
                                                                                                            which adaptively selects temporally correlated tasks during
                                        tion (Qin et al., 2017a; Zhang et al., 2017a), weather fore-
                                                                                                            the training process. The scheduler accesses the model sta-
                                        casting (Shi et al., 2015; Kim et al., 2017), etc. In real-world
                                                                                                            tus and the current training data (e.g., in current minibatch),
                                        applications, a sequence learning task is often associated
                                                                                                            and selects the best auxiliary task to help the training of the
                                        with multiple temporally correlated tasks: (1) In simulta-
                                                                                                            main task. The scheduler and the model for the main task
                                           1
                                             University of Science and Technology of China, Hefei, Anhui,   are jointly trained through bi-level optimization: the sched-
                                        China 2 Microsoft Research, Beijing, China. Correspondence to:      uler is trained to maximize the validation performance of the
                                        Yingce Xia <yingce.xia@microsoft.com>.                              model, and the model is trained to minimize the training loss
                                                                                                            guided by the scheduler. Experimental results on simulta-
                                        Proceedings of the 38 th International Conference on Machine
                                        Learning, PMLR 139, 2021. Copyright 2021 by the author(s).          neous machine translation and stock trend forecasting show
                                Temporally Correlated Task Scheduling for Sequence Learning

that such a task scheduler brings significant improvements.       that in conventional sequence learning where the complete
                                                                  source sequence is available, δT = ∞. In the extreme case
Our main contributions are three-fold:
                                                                  where no latency is allowed, δT = 0. Let fT denote the
(1) To the best of our knowledge, we are the first to formulate   model for task T , which generates the output sequentially.
and study the problem of leveraging temporally correlated         ỹ denotes the output sequence of fT based on x, and is
tasks for sequence learning.                                      initialized as an empty list. After processing xt conditioned
                                                                  on x≤t+δT = (x1 , x2 , · · · , xt+δT ), based on the processed
(2) We propose a new learning algorithm with a scheduler
                                                                  representations of xt , x≤t+δT , and the already generated ỹ,
to adaptively select the temporally correlated tasks to boost
                                                                  fT needs to make a decision ŷ = fT (xt , x≤t+δT , ỹ). The
the main task. The scheduler and the model of the main task
                                                                  decision could be to generate a single token, multiple tokens,
are jointly trained without additional supervision signals.
                                                                  or no token. After that, we append ŷ to the end of ỹ. We
(3) We empirically verify the effectiveness of our method.        repeat the above steps to process all tokens in x.
Experiments on four simultaneous translation tasks show
                                                                  (2) Predicting the future: Tasks in this category aim to
that our method improves wait-k baseline by 1 to 3 BLEU
                                                                  predict some future values for a given time series. Repre-
scores. Experiments on a stock price forecasting dataset
                                                                  sentative examples include stock trend forecasting (Dai &
show that our method can improve the baselines in terms of
                                                                  Zhang, 2013), where we want to predict the price trend of
Spearman’s rank correlation coefficient and prediction loss.
                                                                  an individual stock on some future days (e.g., tomorrow,
Our code for simultaneous translation task is at https:           the day after tomorrow, etc.) based on its historical prices,
//github.com/shirley-wu/simul-mt_                                 and weather forecasting (Shi et al., 2015; Kim et al., 2017),
temporally-correlated-task-scheduling,                            where we want to predict the weather of a city on a future
and the code for stock price forecasting is at                    day based on its historical weather.
https://github.com/microsoft/qlib/tree/
                                                                  Let x denote the input time series, and y = (y1 , y2 , · · · )
main/examples/benchmarks/TCTS.
                                                                  denote the output sequence, where yt is the value of the t-th
                                                                  future day/step. For a task T ∈ T , the goal is to predict
2. Problem Setup and Our Algorithm                                the value of the σT -th future day, i.e., ỹσT , where σT is a
                                                                  positive integer and varies across different tasks T .
 In this section, we first set up the problem of temporally
correlated task scheduling for sequence learning, and then        Each task has a different loss function `(x, y, T ), which is
present our algorithm. Finally, we discuss the connection         used to measure the distance between the predicted ỹ and
between our method and existing methods, and also provide         the groundtruth y (in the first class of tasks) or ỹσT and yσT
an intuition why our method works.                                (in the second class of tasks). Any task in T can be the main
                                                                  task, and the others are regarded as auxiliary tasks. In this
2.1. Problem Setup                                                work, our goal is to better leverage those auxiliary tasks to
                                                                  help the main task.
Let X and Y denote the input space and output space, and
let T = {T1 , · · · , T|T | } denote a set of temporally corre-
                                                                  2.2. Our Algorithm
lated tasks. Depending on applications, those tasks can be
temporally correlated in different ways. We categorize them       As aforementioned, our basic idea is to introduce a task
into two main classes and formalize them as follows.              scheduler, which adaptively selects an auxiliary training
                                                                  task to improve the performance of the main task. A basic
(1) Sequence processing with latency constraints: Tasks
                                                                  assumption of our algorithm is that the models for all tasks
in this category aim to process each token in an input
                                                                  in T can share parameters (except for a few individual parts
sequence, one by one sequentially, under certain latency
                                                                  like task embeddings), which is easy to satisfy in machine
constraints. Representative examples include simultaneous
                                                                  translation, stock trend forecasting, etc. Let f (x; θ) denote
translation (Ma et al., 2019), which targets at translating
                                                                  the model with parameter θ. Let ϕ(x, y, θ; ω) denote the
each source word without waiting for the end of the input
                                                                  task scheduler parameterized by ω, which outputs an auxil-
sentence, and streaming speech recognition (He et al., 2019),
                                                                  iary task in T conditioned on an input-output pair (x, y) and
which requires recognizing each word said by a speaker in
                                                                  the model f (· · · ; θ) of the main task. More specifically, we
real-time, etc.
                                                                  extract a low-dimensional feature Ix,y,θ to describe (x, y, θ)
Let x denote an input sequence and xt denotes its t-th to-        and use it as the actual input of the scheduler network ϕ.
ken. We focus on the setting where each token in x will be        For ease of reference, we will alternatively use ϕ(x, y, θ; ω)
sequentially processed. Each task T ∈ T is associated with        and ϕ(Ix,y,θ ; ω). ϕ can be different functions depending on
a non-negative integer δT , indicating that when processing       applications, which will be discussed in Section 3 and 4.
the token xt , how many additional tokens can be used. Note
                                             Temporally Correlated Task Scheduling for Sequence Learning

                                                                                  Algorithm 1 The optimization algorithm.
          (𝑥1 , 𝑦1 )                                  𝜃0                           1: Input: Training episode E; internal update iterations S; learn-
                                                                 𝐷v                   ing rate η1 of model f (· · · ; θ) ; learning rate η2 of the sched-
                               𝜔           𝑇𝑖1
                                                                                      uler ϕ(· · · ; ω); batch size B;
                                           Δ𝜃
                                                                                   2: for e ← 1 : E do
                                                                                   3:    Prepare a buffer to store states and actions: B = {};
          (𝑥2 , 𝑦2 )                                  𝜃1                           4:    for s ← 1 : S do
                               𝜔           𝑇𝑖2                                     5:       Sample a minibatch of data De,s from Dt with size B;
                                                                                   6:       For each (x, y) ∈ De,s , we sample a temporally corre-
                                           Δ𝜃                     Δ𝜔                        lated auxiliary task T according to the output distribu-
                                                                                            tion of ϕ(x, y, θ; ω), and get D̃ = {(x, y, T )} where
                                                      𝜃2
              ……




                                                                                            |D̃| = B;
                                                                                   7:       Add the inputs of ϕ (i.e., Ix,y,θ ) to B:
          (𝑥𝑆 , 𝑦𝑆 )                                 𝜃𝑆−1                                   B ← B ∪ {(Ix,y,θ , T )|(x, y, T ) ∈ D̃};
                               𝜔           𝑇𝑖𝑆                                     8:       Update model f :        P
                                                                                            θ ← θ − (η1 /B)∇θ (x,y,T )∈D̃ `(x, y, T ; θ);
                                           Δ𝜃                                      9:    end for
                                                      𝜃𝑆
                                                                                  10:    Calculate the validation performance as the reward: Re =
                                                                                         M(Dv ; θe,S );
                                                                                  11:    Update the scheduler:
                                                                                                            P
                                                                                         ω ← ω + η2 Re (I,T )∈B ∇ω log P (ϕ(I; ω) = T ).
Figure 1: The optimization workflow of one episode. The                           12: end for
solid lines and dashed lines represent the workflow of inner-                     13: Return: θ.
optimization (w.r.t. θ) and outer-optimization (w.r.t. ω)
respectively. At step s, with training data (xs , ys ), the sched-
uler ϕ(· · · ; ω) chooses a suitable task Tis (green solid lines)                 with any gradient-based optimizer like momentum SGD,
to update the model f (· · · ; θ) (blue solid lines). After S                     Adam (Kingma & Ba, 2015), etc. The outer loop (from
steps, we evaluate the model f on the validation set Dv and                       step 2 to step 11) aims to optimize ω. ϕ(x, y, θ; ω) can be
update the scheduler ϕ (green dashed lines).                                      regarded as a policy network, where the state is the feature
                                                                                  Ix,y,θ , the action is the choice of task T ∈ T , and the reward
                                                                                  is the validation performance Re (step 10). At the end of
Now we have two sets of parameters to learn from the data:                        each episode, we update ω using REINFORCE algorithm
ω in the scheduler ϕ and θ in the model f . Let Dt and                            (step 11). The workflow of one episode is shown in Figure 1.
Dv denote the training and validation sets respectively. We
formulate the training of f and ϕ as a bi-level optimiza-                         2.3. Discussion
tion (Sinha et al., 2017), which is
                                                                                  Our problem is related to several other learning settings.
 max M(Dv ; θ(ω));                 s.t.,                                    (1)   (1) In multi-task learning (Zhang & Yang, 2017) (briefly,
   ω
                        1           X                                             MTL), multiple tasks are jointly trained and mutually
θ(ω) = arg min                                   ET ∼ϕ(x,y,θ;ω) `(x, y, T ; θ).   boosted. In MTL, each task is treated equally, while in
               θ       |Dt |
                               (x,y)∼Dt
                                                                                  our setting, we focus on the main task.
In the above formulation, M(Dv ; θ(ω)) denotes the valida-                        (2) Transfer learning (Pan et al., 2010) also leverages auxil-
tion performance of the main task, and ` is the loss function                     iary tasks to boost a main task. Curriculum transfer learning
of data (x, y) on task T . Intuitively, we expect that the                        (briefly, CL) (Shao et al., 2018; Dong et al., 2017) is one
scheduler can select a good auxiliary task for each input-                        kind of transfer learning which schedules auxiliary tasks
output pair, so that eventually the validation performance of                     according to certain rules, e.g., from easy to difficult. Our
the model on the main task can be maximized.                                      problem can also be regarded as a special kind of transfer
                                                                                  learning, where the auxiliary tasks are temporally correlated
Following the common practice (Liu et al., 2019; Fan et al.,
                                                                                  with the main task. Our learning process is dynamically con-
2018), we optimize Eqn.(1) in an alternative way: We first
                                                                                  trolled by a scheduler rather than some pre-defined rules.
fix ω and optimize θ, and then fix θ and optimize ω using the
REINFORCE algorithm (Sutton & Barto, 2018). We repeat                             (3) Our method is also related to Different Data Selection
the process until convergence, as shown in Algorithm 1.                           (DDS) (Wang et al., 2020). Both our work and DDS train a
The training process consists of E episodes (i.e., the outer                      meta controller to improve the learning process on a given
loop), and each episode consists of S update iterations (i.e.,                    task via reinforcement learning. The main difference is
the inner loop). The inner loop (from step 4 to step 9)                           that DDS aims to better select training data from a dataset,
aims to optimize θ, where we can update the parameter                             while our work aims to better utilize temporally correlated
                                    Temporally Correlated Task Scheduling for Sequence Learning

tasks (and their corresponding data). Given a main task,                 and controllable latency, and has been used in speech-related
our method constructs and schedules a series of temporal                 simultaneous NMT (Zhang et al., 2019; Ren et al., 2020).
correlated tasks, while DDS works on the given task only.
                                                                         For adaptive strategies, Cho & Esipova (2016) proposed
Intuitively, training with temporally correlated auxiliary               wait-if-worse (WIW) and wait-if-diff (WID) methods which
tasks helps the main task for two reasons: (1) The temporally            generate a new target word if its probability does not de-
correlated tasks either share the same output with overlapped            crease (for WIW) or if the generated word is unchanged (for
inputs or the same input. Thus, joint training of them enables           WID) after reading a new source token. Grissom II et al.
shared representation learning, just like general multi-task             (2014) and Gu et al. (2017) used reinforcement learning to
training (MTL), and consequently improves the main task;                 train the read/write controller, while Zheng et al. (2019a)
(2) The x/y pairs from correlated tasks can be viewed as                 trained the controller in a supervised way. Alinejad et al.
noised augmentation of the training data for the main task,              (2018) added a “predict” operator to the controller so that
which helps the main task.                                               it can anticipate future source inputs. Zheng et al. (2019b)
                                                                         introduced a “delay” token into the target vocabulary indi-
3. Application to Simultaneous Translation                               cating that the model should read a new word. Monotonic
                                                                         infinite lookback attention (MILk) used a hard attention
3.1. Task Description                                                    model to determine when to read new tokens, and a soft
                                                                         attention model to perform translation (Arivazhagan et al.,
Simultaneous neural machine translation (briefly, NMT) has
                                                                         2019). Ma et al. (2020) introduced multi-head attention to
attracted much attention recently. In contrast to standard
                                                                         MILk and proposed monotonic multihead attention (MMA)
NMT, where the NMT system can access the full input
                                                                         with two variants: MMA-IL (Infinite Lookback) with higher
sentence, simultaneous NMT requires the model to conduct
                                                                         translation quality and greater computational overhead, and
translation before reading the full input sentence. In this
                                                                         MMA-H(ard) with higher computational efficiency. Be-
task, X and Y are collections of sentences in the source
                                                                         sides, Zheng et al. (2020a) extended wait-k to an adaptive
language and the target language. Wait-k (Ma et al., 2019) is
                                                                         strategy by training multiple wait-m models with different
a simple yet effective method in simultaneous NMT, where
                                                                         m’s and adaptively selecting a decoding strategy during in-
the translation is k words behind the source input. Formally,
                                                                         ference. Zheng et al. (2020b) explored a new setting, where
given a data pair (x, y) ∈ X × Y where the t-th token of
                                                                         at each timestep, the translation model over-generates the
x/y is xt /yt , when we read a prefix (x1 , x2 , · · · , xk ) (briefly
                                                                         target words and corrects them in a timely fashion.
denoted as x≤k ), we need to output the first target token
y1 ; when reading x≤k+1 , we should output y2 , etc. In
                                                                         3.3. Settings
comparison, for standard NMT, one can start translation
after reading all tokens in x. A larger k makes the task                 Datasets: For IWSLT’14 En→De, following (Edunov et al.,
easier and leads to better translation quality, but at the cost          2018), we split 7k sentences from the training corpus for
of a larger waiting time.                                                validation, and the test set is the concatenation of tst2010,
Under our framework, simultaneous translation belongs                    tst2011, tst2012, dev2010 and dev2012. For IWSLT’15
to the first class of tasks in Section 2.1. Let Tm denote                En→Vi, following (Ma et al., 2020), we use tst2012 as the
wait-m task, and δTm for task Tm is m − 1. Assuming                      validation set and tst2013 as the test set. For IWSLT’17
wait-k is the main task Tmain , then the temporally cor-                 En→Zh, we concatenate tst2013, tst2014 and tst2015 as the
related tasks T are wait-m with different m values, i.e.                 validation set and use tst2017 as the test set. For WMT’15
T = {T1 , T2 , · · · , TM }. In this work, we set M = 13. If             En→De, following (Ma et al., 2019; Arivazhagan et al.,
the scheduler ϕ assigns a task Tm (i.e., wait-m) to a data               2019), we use newstest2013 as the validation set and use
pair (x, y), the loss function on this task is:                          newstest2015 as the test set. More details about datasets can
                                                                         be found in Appendix C.1.
                      |y|
  `(x, y, Tm ; θ) =
                      X
                            log P (yt |y≤t−1 , x≤t+m−1 ; θ). (2)         Models: Following Ma et al. (2019), the translation model
                      t=1
                                                                         f is based on Transformer (Vaswani et al., 2017). However,
                                                                         different from Ma et al. (2019), we conduct incremental
3.2. Background                                                          encoding, so that when encoding each source token, the
                                                                         model can only attend to its previous tokens. The computa-
Previous work on simultaneous NMT can be categorized by                  tion complexity for encoding is O(L2x ) compared to O(L3x )
whether using a fixed decoding strategy or an adaptive one.              in Ma et al. (2019), where Lx is the length of the source
Fixed strategies use pre-defined rules to determine when to              sentence x. We find that our model is more efficient than Ma
read or to write a new token (Dalvi et al., 2018; Ma et al.,             et al. (2019) with little accuracy drop. Detailed formulation
2019). Wait-k is a representative method (Ma et al., 2019),              and empirical comparison are in Appendix B.
which achieves good results in terms of translation quality
                                Temporally Correlated Task Scheduling for Sequence Learning

For IWSLT En→Zh and En→Vi, we use the transformer                 En→Vi, we use multi-bleu.perl to evaluate BLEU
small model, where the embedding dimension, feed-forward          scores; for IWSLT’17 En→Zh and WMT’15 En→De, we
layer dimension, number of layers are 512, 1024 and 6 re-         use sacreBLEU to evaluate the detokenized BLEU scores.
spectively. For IWSLT En→De, we use the same archi-
tecture but change the embedding dimension into 256. For          3.4. Results and Analysis
WMT’15 En→De, we use the transformer big setting, where
the above three numbers are 1024, 4096 and 6 respectively.        We first compare our method with MTL, CL and wait-k ∗
The scheduler ϕ for each task is a multilayer perceptron          on IWSLT datasets. The BLEU-latency curves are shown in
(MLP) with one hidden layer and the tanh activation func-         Figure 2, and the BLEU scores of En→Vi are reported in
tion. The size of the hidden layer is 256.                        Table 1. For the wait-k ∗ , we also report the optimal training
                                                                  task (i.e., k ∗ ) for each main task wait-k . BLEU scores of
Input features of ϕ: The input of ϕ is a 7-dimension              all language pairs are left in Appendix D. Experiments on
vector with the following features: (1) the ratios be-            more heuristic baselines are in Appendix E.2.
tween the lengths of the source/target sentences to
the average source/target sentenceP     lengths in all train-
                                                                         29.0                                                                              29.0
ing data   (2 dimensions),  i.e., L  /(   x0 ∈X Lx /|X |) and
                                   x               0
      P                                                                  28.5                                                                              28.5
Ly /( y0 ∈Y Ly0 /|Y|); (2) the training loss over data (x, y)            28.0                                                                              28.0
                                                                         27.5                                                                              27.5
evaluated on the main task wait-k; (3) the average of histor-                                                                         Wait-k



                                                                  BLEU




                                                                                                                                                    BLEU
                                                                         27.0                                                                              27.0
ical training losses; (4) the validation loss of the previous            26.5
                                                                                                                                      Wait-k *             26.5
                                                                         26.0
                                                                                                                                      CL                   26.0
epoch; (5) the average of historical validation loss; (6) the                                                                         MTL
                                                                         25.5                                                         Ours                 25.5
ratio of current training step to the total training iteration.          25.0                                                                              25.0
                                                                                     0.65          0.70          0.75          0.80      0.85                         3       4       5       6            7        8       9       10
The ablation study of feature selection is in Appendix E.1.                                                       AP                                                                              AL

                                                                                (a) BLEU-AP, En→Vi.                                                               (b) BLEU-AL, En→Vi.
Choice of M: The validation performance M is the negative
validation loss with wait-k strategy. To stabilize training,             28                                                                                28
the reward for the e-th episode (step 10 of Algorithm 1) is              26                                                                                26
Re − Re−1 , where Re−1 is the validation performance M                   24                                                                                24
of the previous episode.
                                                                  BLEU




                                                                                                                                                    BLEU
                                                                         22                                                                                22

                                                                         20                                                                                20
Baselines: We implement the MTL and CL baselines dis-
                                                                         18                                                                                18
cussed in Section 2.3: (1) For MTL, each task is randomly
sampled. (2) For the curriculum transfer learning (briefly,                     0.60        0.65          0.70
                                                                                                                 AP
                                                                                                                        0.75      0.80       0.85                 2       3       4       5
                                                                                                                                                                                              AL
                                                                                                                                                                                                       6            7       8       9

CL), we start from the easiest task TM and gradually move
                                                                                (c) BLEU-AP, En→De.                                                             (d) BLEU-AL, En→De.
to the main task Tmain . For wait-k, we implement another
variant wait-k ∗ , where we train M baseline models on dif-
                                                                         24                                                                                24
ferent wait-m tasks (1 ≤ m ≤ M ), and pick the best
                                                                         22                                                                                22
model according to the validation performance on wait-k
task. Wait-k ∗ is expected to bring additional improvements              20                                                                                20
                                                                  BLEU




                                                                                                                                                    BLEU




as pointed out by Ma et al. (2019). After that, we com-                  18                                                                                18

pare with several adaptive methods, including Wait-if-Worse              16                                                                                16

(WIW), Wait-if-Diff (WID), MILk, MMA-IL and MMA-H                        14
                                                                                 0.60        0.65           0.70          0.75        0.80
                                                                                                                                                           14
                                                                                                                                                                      2       3       4       5                6        7       8
                                                                                                               AP                                                                             AL
(refer to Section 3.2 for a brief introduction). Finally, we
combine our method with Zheng et al. (2020a). We leave                          (e) BLEU-AP, En→Zh.                                                               (f) BLEU-AL, En→Zh.
the training details of all algorithms (optimizer, hyperpa-
rameter, etc) in Appendix C.2, and the details of baselines       Figure 2: Translation quality against latency metrics (AP
in Appendix C.3.                                                  and AL) on IWSLT tasks.
Evaluation: We use BLEU to measure the translation qual-
ity, and use Average Proportion (AP) and Average Lagging
                                                                                 k          wait-k                       wait-k∗ / k∗                           CL                MTL                              Ours
(AL) to evaluate the translation latency. AP measures the
average proportion of source symbols required for transla-                       1           25.14                          26.14 / 5                       26.01                 26.12                        27.03
                                                                                 3           27.17                          28.25 / 5                       26.37                 28.54                        29.01
tion, and AL measures the average number of delayed words                        5           28.29                          28.44 / 9                       27.97                 28.61                        28.91
(see Appendix A.1. for details). Following the common                            7           28.31                         28.38 / 13                       28.31                 28.77                        29.17
practice (Ma et al., 2019; 2020), we show the BLEU-AP                            9           28.39                          28.39 / 9                       28.31                 28.70                        29.06
and BLEU-AL curves to demonstrate the tradeoff between
quality and latency. For IWSLT’14 En→De and IWSLT’15                              Table 1: BLEU scores on IWSLT En→Vi task.
                                                       Temporally Correlated Task Scheduling for Sequence Learning

We have the following observations:                                                            Appendix D. When AL ≥ 5.0, our method outperforms all
                                                                                               baseline models, and when AL < 5.0, our method performs
(1) Generally, our method consistently performed the best
                                                                                               slightly worse than MMA-IL and MMA-H. A possible rea-
across different translation tasks in terms of both translation
                                                                                               son is that our method does not explicitly reduce the latency,
quality and controllable latency. As shown in Table 1, our
                                                                                               but focuses on improving performance under given latency
method achieves the highest BLEU scores among all base-
                                                                                               constraints.
lines. In Figure 2, the curve for our method (i.e., the red
one) is on the top in most cases, which indicates that given                                   We further compare and combine our method with Zheng
specific latency (e.g., AP or AL), we can achieve the best                                     et al. (2020a). We conduct experiments on two variants of
translation quality. The results of significance tests are left                                Zheng et al. (2020a), where the wait-m models are obtained
in Appendix D.                                                                                 through vanilla wait-k (denoted by “Zheng et al.”) and our
                                                                                               strategy respectively (denoted by “Zheng et al. + Ours”.
(2) MTL and CL can outperform the vanilla baseline, which
                                                                                               The BLEU-AL curves are shown in Figure 4(b), and the
demonstrates the effectiveness of leveraging the temporally
                                                                                               BLEU-AP curves are in Appendix D. We can see that: (1)
correlated tasks. However, the improvements are not consis-
                                                                                               our method catches up with Zheng et al. (2020a), which
tent, and it is hard to tell which baseline is better. CL slightly
                                                                                               is built upon 10 models in total (wait-1, 2, · · · , 10); (2) af-
outperforms MTL on En→De. However, on En→Zh, CL
                                                                                               ter combing our approach with Zheng et al. (2020a), the
performs better at lower latency while MTL performs better
                                                                                               performance can be further boosted, which shows that our
at higher latency. In comparison, the improvement brought
                                                                                               method is complementary to adaptive inference strategies
by our method is much more consistent.
                                                                                               like Zheng et al. (2020a).
(3) Wait-k ∗ also outperforms wait-k. Specifically, we notice
that the optimal training k ∗ is always larger than k for the
                                                                                                      29
main task. This is consistent with the observation in Ma                                              28                                                       29

et al. (2019). However, compared with CL and MTL, wait-                                               27
                                                                                                                                                               28
                                                                                                      26
k ∗ does not have a consistent advantage. This shows that the




                                                                                                                                                        BLEU
                                                                                               BLEU




                                                                                                      25
                                                                                                                                                               27               Wait-k
improvements of MTL, CL and our method is not due to the                                              24
                                                                                                      23
                                                                                                                                 Wait-k        MILk                             Ours
existence of some “best” task in T , and further demonstrates                                                                    Ours          WIW             26               Zheng et al.
                                                                                                      22                         MMA-IL        WID
                                                                                                                                 MMA-H                                          Zheng et al. + ours
the importance of adaptively using all auxiliary tasks.                                               21                                                       25
                                                                                                           2.5   5.0   7.5   10.0 12.5 15.0 17.5 20.0               4   6   8   10    12   14   16    18
                                                                                                                                AL                                               AL
The results on WMT’15 En→De, whose training corpus
                                                                                               (a) Comparison with several (b) Comparison and combina-
is larger, are shown in Figure 3. Wait-k ∗ , MTL and CL                                        adaptive methods.           tion with Zheng et al. (2020a).
do not bring much improvement compared to vanilla wait-
k. Our method consistently outperforms all baselines,
                                                                                               Figure 4: BLEU-AL comparison between our method and
which demonstrates the effectiveness of our method on
                                                                                               baselines on En→Vi.
large datasets. We further evaluate them on WMT’14 and
WMT’16 test sets and obtain similar conclusions (see Ap-
pendix D for details).                                                                         Computational overhead: To evaluate the additional compu-
                                                                                               tational overhead brought by our method, we compare the
                                                                                               training speed of standard wait-k and our method on wait-3
       28                                                  28
                                                                                               (measured by the number of batches per second). Results
       26                                                  26
                                                                                               on IWSLT datasets are summarized in Table 2. Our method
       24                                                  24
                                         Wait-k                                                requires 20% ∼ 30% additional training time, which is ac-
BLEU




                                                    BLEU




       22                                                  22
                                         Wait-k *                                              ceptable considering the performance improvements. The
       20                                CL                20
                                         MTL                                                   major overhead comes from computing the training loss by
       18                                Ours              18
                                                                                               wait-k. To verify that, we record the training speed of our
            0.60    0.65   0.70   0.75       0.80               3    4   5     6   7   8   9
                            AP                                               AL                method without the second and third input features of ϕ, i,e,
                   (a) BLEU-AP                                      (b) BLEU-AL                the training loss over data (x, y) evaluated on wait-k, and
                                                                                               the average of historical training losses (denoted by “Ours
Figure 3: Translation quality against latency metrics (AP                                      w/o feature (2,3)”). Without these two features, the training
and AL) on WMT’15 En→De.                                                                       speed of our method is close to wait-k.
                                                                                               Strategy analysis: In Figure 5, we visualize the distribution
Comparison with adaptive simultaneous NMT methods: We                                          of wait-m tasks obtained by the scheduler for two main
further compare our method with WIW, WID, MILk, MMA-                                           tasks, wait-3 and wait-9 on IWSLT En→Zh dataset. We
IL and MMA-H on IWSLT En→Vi. The BLEU-AL curves                                                show the frequency of each wait-m task sampled by the
are shown in Figure 4(a) and the BLEU-AP curves are in                                         scheduler ϕ at the 0th, 1st, 5th, 10th and 40th episode.
                                               Temporally Correlated Task Scheduling for Sequence Learning

                                                                              Wait-3
                   0
         Episode   1

                   5                                                                                                                   m=1
                                                                                                                                       m=2
                   10                                                                                                                  m=3
                                                                                                                                       m=4
                   40                                                                                                                  m=5
                                                                                                                                       m=6
                    0.0           0.1          0.2       0.3       0.4         0.5        0.6      0.7       0.8       0.9       1.0   m=7
                                                                              Wait-9                                                   m=8
                   0                                                                                                                   m=9
                                                                                                                                       m=10
                   1                                                                                                                   m=11
                                                                                                                                       m=12
         Episode




                   5                                                                                                                   m=13
                   10

                   40
                    0.0           0.1          0.2       0.3       0.4         0.5        0.6      0.7       0.8       0.9       1.0


                                Figure 5: The distribution of wait-m tasks for wait-3 and wait-9 on En→Zh dataset.


     Task               wait-k          Ours         Ours w/o feature (2,3)            price and the trading volume. The task Tk ∈ T is to forecast
   En→De                  5.3      4.0 (-23%)              5.2 (-2%)                   the stock price rise percent of the next k-th day, i.e., yt =
                                                                                         pt+k
   En→Vi                  1.5      1.1 (-27%)              1.4 (-7%)                   pt+k−1 − 1. This task lies in the second type of classes as
   En→Zh                  2.5      1.8 (-28%)              2.4 (-4%)                   introduced in Section 2.1. In stock forecasting, we usually
                                                                                       make predictions based on a window of historical inputs of
Table 2: Comparison of training speed (batch / sec) between                            length L, i.e., (xt−L+1 , xt−L+2 , · · · , xt ). We explore three
wait-k and our methods.                                                                different main tasks in this work: forecasting the stock rise
                                                                                       trend of the next 1st, 2nd and 3rd days (i.e., T1 , T2 and T3 ).
                                                                                       As mentioned by Tang et al. (2020), all the above three tasks
We observed that the scheduler uniformly samples different                             are important because investors tend to invest in stocks with
tasks at first, and then the strategies converge within 10                             rising price trends in a continuous period, rather than caring
episodes. After convergence, the scheduler mainly samples                              the next trading day only.
several specific tasks, i.e., m = 5, 9, 12 for wait-3, and
m = 5, 12 for wait-9. The task that both schedulers prefer                             4.2. Background
most is m = 12, which is close to the optimal training
task wait-k ∗ (k ∗ = 11) for both wait-3 and wait-9. This                              Traditional methods for stock trend forecasting are based on
demonstrates that the scheduler can learn which task is more                           time-series analysis models, such as the Auto-regressive In-
beneficial to the main task. However, it is worth noting that                          tegrated Moving Average (ARMA) and Kalman Filters (Yan
the scheduler also samples other tasks, which shows the                                & Guosheng, 2015). With the development of deep learn-
importance of training with multiple tasks instead of one                              ing, applying neural network to stock forecasting becomes
single optimal task. For example, the scheduler for wait-9                             a new trend due to its better performance on noisy data.
samples both wait-5 and 9 with a probability of about 0.1.                             GRU (Chung et al., 2014) is one of the most representa-
                                                                                       tive deep neural networks in stock trend forecasting (Hu
                                                                                       et al., 2018). By utilizing the reset gate and update gate,
4. Application to Stock Trend Forecasting                                              GRU can adaptively choose the information to be kept or
4.1. Task Description                                                                  dropped, which makes it relatively robust to the diverse and
                                                                                       noisy sequential data in the stock market. Other types of
Stock trend forecasting is a core problem in stock market                              recurrent neural networks are also leveraged such as LSTM,
investment. Following the common practice, in this task,                               SFM (Zhang et al., 2017b), ALSTM (Qin et al., 2017b),
X represents the historical transactions data including both                           etc. Recent works start to use graph neural networks (e.g.
prices and trading volumes, and Y denotes the stock price                              GAT (Veličković et al., 2017)) to model different stocks
movement in future days.                                                               so that the information can be propagated along with the
                                                                                       pre-defined relations (Feng et al., 2019; Kim et al., 2019).
At the t-th day, a specific stock can be represented by a
5-dimension feature vector xt including the opening price,                             In addition to neural networks, many machine learning meth-
closing price (denoted as pt ), the highest price, the lowest
                                 Temporally Correlated Task Scheduling for Sequence Learning

ods have been successfully applied to forecast stock future           Methods            Task-1           Task-2           Task-3
trends. A particularly powerful branch is the tree-based              GRU            0.049 / 1.903     0.018 / 1.972    0.014 / 1.989
approach, such as LightGBM (Ke et al., 2017) and Ran-                 MLP            0.023 / 1.961     0.022 / 1.962    0.015 / 1.978
dom Forest. They have outstanding performance and certain             LGB            0.038 / 1.883     0.023 / 1.952    0.007 / 1.987
interpretability, so they are widely used in stock market             GAT            0.052 / 1.898     0.024 / 1.954    0.015 / 1.973
investment (Khaidem et al., 2016; Tan et al., 2019).                  MTL (T3 )      0.061 / 1.862     0.023 / 1.942    0.012 / 1.956
                                                                      CL (T3 )       0.051 / 1.880     0.028 / 1.941    0.016 / 1.962
                                                                      Ours (T3 )     0.071 / 1.851     0.030 / 1.939    0.017 / 1.963
4.3. Settings
                                                                      MTL (T5 )      0.057 / 1.875     0.021 / 1.939    0.017 / 1.959
We conduct experiments on individual stocks in the Chinese            CL (T5 )       0.056 / 1.877     0.028 / 1.942    0.015 / 1.962
A-share market. We explore three groups of temporally cor-            Ours (T5 )     0.075 / 1.849     0.032 /1.939     0.021 / 1.955
related tasks: T3 = {T1 , T2 , T3 }, T5 = {T1 , T2 , · · · , T5 }     MTL (T10 )     0.052 / 1.882     0.020 / 1.947    0.019 / 1.952
and T10 = {T1 , T2 , · · · , T10 }.                                   CL (T10 )      0.051 / 1.882     0.028 / 1.950    0.016 / 1.961
                                                                      Ours (T10 )    0.067 / 1.867     0.030 / 1.960    0.022 / 1.942
Dataset : We use the historical transaction data for 300
stocks on CSI300 (CSI300, 2008) from 01/01/2008 to                  Table 3: Results of stock trend forecasting. The first four rows
08/01/2020. We split the data into training (01/01/2008-            are the results of various model architectures without leveraging
12/31/2013), validation (01/01/2014-12/31/2015), and                temporally correlated tasks. The following rows are the results with
test sets (01/01/2016-08/01/2020) based on the transac-             different algorithms (MTL, CL and ours) and different auxiliary
tion time. All the data is provided by Yang et al. (2020).          task sets (T3 , T5 and T10 ). For each cell, the RankIC is put on the
                                                                    left and MSE on the right.
Models: The forecasting model f is built on top of a 2-layer
GRU with hidden dimension 32. The length of the input
sequence (i.e., the L in Section 4.1) is 60. The scheduler ϕ        tasks, i.e., T3 , T5 and T10 , our method significantly outper-
is a single-layer feed-forward network with ReLU activation.        forms MTL and CL on most settings, which demonstrates
The hidden size of ϕ is 32.                                         the effectiveness of leveraging an adaptive scheduler.
Input features of ϕ: The features consist of four parts: (1) the    (2) Using a larger temporally correlated task set does not
data (x, y) ∈ Dt itself; (2) the training loss of the previous      always bring improvements. Taking task T1 as an example,
iteration; (3) the forecasting results of the previous iteration;   our method achieves the best performance when using 5
(4) the labels of each task in T .                                  temporally correlated tasks, while using 10 hurts the per-
Baselines: Similar to Section 3.3, we implement MTL and             formance. The reason is that more tasks will introduce
CL as baselines by using temporally correlated tasks. In CL,        additional noise to the training.
we start from the easiest task T1 , and then gradually move         (3) There are more advanced methods than GRU like GAT,
to the most difficult one. Besides, we implement different          leveraging temporally correlated tasks can achieve superior
models for stock forecasting for comparison, including sim-         performance than the strong models. Currently, our model
ple feed-forward networks (denoted by MLP), lightGBM                is based on GRU, and we will combine our method with
(briefly, LGB) (Ke et al., 2017) and GAT (Veličković et al.,      GAT and lightGBM in the future for more improvements.
2017; Feng et al., 2019). Note that for GAT, we do not
leverage the specific relation between stocks.
                                                                    5. Conclusions and Future Work
Evaluation: We use rank correlation coefficient (Zhang et al.,
2020) (briefly, RankIC) and the mean square error (briefly,         In this work, we formulated and studied the problem of tem-
MSE) to evaluate the forecasting results. RankIC can be             porally correlated task scheduling, which can cover many
regarded as a correlation between the prediction and the            applications including sequence processing with latency
groundtruth results (the larger, the better). MSE measures          constraints (e.g., simultaneous machine translation) and se-
the gap between prediction results and the groundtruth re-          quence future prediction (e.g. stock trend forecasting). Ex-
sults (the smaller, the better). Due to space limitation, we        periments on four translation tasks and one stock prediction
put the evaluation results using ICIR (a measurement that           task demonstrate the effectiveness of our approach.
takes stability into consideration) in Appendix F.                  For future work, we will apply our method to more appli-
                                                                    cations like action prediction (Kong et al., 2020; Cai et al.,
4.4. Results and Analysis                                           2019), streaming speech recognition, weather forecasting,
                                                                    game AI (Li et al., 2020; Vinyals et al., 2019), etc. We will
The results of stock trend forecasting are reported in Table 3.
                                                                    also design better methods for the problem. Another inter-
We have the following observations:
                                                                    esting direction is to theoretically understand the problem
(1) With different sets of temporally correlated auxiliary          and analyze our method.
                               Temporally Correlated Task Scheduling for Sequence Learning

References                                                        IEEE Winter Conference on Applications of Computer
                                                                  Vision (WACV), pp. 520–529. IEEE, 2017.
Alinejad, A., Siahbani, M., and Sarkar, A. Prediction
  improves simultaneous neural machine translation. In          Edunov, S., Ott, M., Auli, M., Grangier, D., and Ranzato, M.
  Proceedings of the 2018 Conference on Empirical Meth-           Classical structured prediction losses for sequence to se-
  ods in Natural Language Processing, pp. 3022–3027,              quence learning. In Proceedings of the 2018 Conference
  Brussels, Belgium, October-November 2018. Associ-               of the North American Chapter of the Association for
  ation for Computational Linguistics. doi: 10.18653/             Computational Linguistics: Human Language Technolo-
  v1/D18-1337. URL https://www.aclweb.org/                        gies, Volume 1 (Long Papers), pp. 355–364, New Orleans,
  anthology/D18-1337.                                             Louisiana, June 2018. Association for Computational
Arivazhagan, N., Cherry, C., Macherey, W., Chiu, C.-C.,           Linguistics. doi: 10.18653/v1/N18-1033. URL https:
  Yavuz, S., Pang, R., Li, W., and Raffel, C. Mono-               //www.aclweb.org/anthology/N18-1033.
  tonic infinite lookback attention for simultaneous ma-        Fan, Y., Tian, F., Qin, T., Li, X., and Liu, T. Learning
  chine translation. In Proceedings of the 57th Annual            to teach. CoRR, abs/1805.03643, 2018. URL http:
  Meeting of the Association for Computational Linguis-           //arxiv.org/abs/1805.03643.
  tics, pp. 1313–1323, Florence, Italy, 2019. Association
  for Computational Linguistics. URL https://www.               Feng, F., He, X., Wang, X., Luo, C., Liu, Y., and Chua, T.-S.
  aclweb.org/anthology/P19-1126.                                  Temporal relational ranking for stock prediction. ACM
                                                                  Transactions on Information Systems (TOIS), 37(2):1–30,
Bahdanau, D., Cho, K., and Bengio, Y. Neural machine
                                                                  2019.
  translation by jointly learning to align and translate.
  In ICLR, 2014. URL https://arxiv.org/abs/                     Grissom II, A., He, H., Boyd-Graber, J., Morgan, J., and
  1409.0473.                                                      Daumé III, H. Don’t until the final verb wait: Rein-
Cai, Y., Li, H., Hu, J.-F., and Zheng, W.-S. Action knowl-        forcement learning for simultaneous machine transla-
  edge transfer for action prediction with partial videos. In     tion. In Proceedings of the 2014 Conference on Empiri-
  Proceedings of the AAAI Conference on Artificial Intelli-       cal Methods in Natural Language Processing (EMNLP),
  gence, volume 33, pp. 8118–8125, 2019.                          pp. 1342–1352, Doha, Qatar, October 2014. Associ-
                                                                  ation for Computational Linguistics. doi: 10.3115/
Cho, K. and Esipova, M. Can neural machine translation do         v1/D14-1140. URL https://www.aclweb.org/
  simultaneous translation? CoRR, abs/1606.02012, 2016.           anthology/D14-1140.
  URL http://arxiv.org/abs/1606.02012.
                                                                Gu, J., Neubig, G., Cho, K., and Li, V. O. Learning
Chung, J., Gulcehre, C., Cho, K., and Bengio, Y. Empirical        to translate in real-time with neural machine transla-
  evaluation of gated recurrent neural networks on sequence       tion. In Proceedings of the 15th Conference of the Eu-
  modeling. arXiv preprint arXiv:1412.3555, 2014.                 ropean Chapter of the Association for Computational
                                                                 Linguistics: Volume 1, Long Papers, pp. 1053–1062,
CSI300. Csi 300, 2008. URL http://www.csindex.
                                                                 Valencia, Spain, April 2017. Association for Compu-
  com.cn/en/indices/index-detail/
                                                                  tational Linguistics. URL https://www.aclweb.
  000300.
                                                                  org/anthology/E17-1099.
Dai, Y. and Zhang, Y. Machine learning in stock price trend
                                                                He, Y., Sainath, T. N., Prabhavalkar, R., McGraw, I., Al-
  forecasting, 2013.
                                                                  varez, R., Zhao, D., Rybach, D., Kannan, A., Wu, Y.,
Dalvi, F., Durrani, N., Sajjad, H., and Vogel, S. Incre-          Pang, R., Liang, Q., Bhatia, D., Shangguan, Y., Li, B.,
  mental decoding and training methods for simultane-             Pundak, G., Sim, K. C., Bagby, T., Chang, S., Rao, K.,
  ous translation in neural machine translation. In Pro-          and Gruenstein, A. Streaming end-to-end speech recog-
  ceedings of the 2018 Conference of the North Ameri-             nition for mobile devices. In ICASSP 2019 - 2019 IEEE
  can Chapter of the Association for Computational Lin-           International Conference on Acoustics, Speech and Sig-
  guistics: Human Language Technologies, Volume 2                 nal Processing (ICASSP), pp. 6381–6385, 2019. doi:
 (Short Papers), pp. 493–499, New Orleans, Louisiana,            10.1109/ICASSP.2019.8682336.
  June 2018. Association for Computational Linguistics.
  doi: 10.18653/v1/N18-2079. URL https://www.                   Hu, Z., Liu, W., Bian, J., Liu, X., and Liu, T.-Y. Listening to
  aclweb.org/anthology/N18-2079.                                  chaotic whispers: A deep learning framework for news-
                                                                  oriented stock trend prediction. In Proceedings of the
Dong, Q., Gong, S., and Zhu, X. Multi-task curriculum             eleventh ACM international conference on web search
  transfer deep learning of clothing attributes. In 2017          and data mining, pp. 261–269, 2018.
                              Temporally Correlated Task Scheduling for Sequence Learning

Ke, G., Meng, Q., Finley, T., Wang, T., Chen, W.,           Ma, X., Pino, J., Cross, J., Puzon, L., and Gu, J. Monotonic
  Ma, W., Ye, Q., and Liu, T.-Y.           Lightgbm: A        multihead attention. In 8th International Conference on
  highly efficient gradient boosting decision tree. In        Learning Representations, 2020.
  Guyon, I., Luxburg, U. V., Bengio, S., Wallach,
  H., Fergus, R., Vishwanathan, S., and Garnett, R.         Pan, S. J., Yang, Q., Fan, W., and (ph. D, S. J. P. A survey
  (eds.), Advances in Neural Information Processing           on transfer learning. IEEE Transactions on Knowledge
  Systems, volume 30, pp. 3146–3154. Curran Asso-             and Data Engineering, 2010.
  ciates, Inc., 2017. URL https://proceedings. Papineni, K., Roukos, S., Ward, T., and Zhu, W.-J. Bleu:
  neurips.cc/paper/2017/file/                                 a method for automatic evaluation of machine transla-
  6449f44a102fde848669bdd9eb6b76fa-Paper.                     tion. In Proceedings of the 40th Annual Meeting of
  pdf.                                                        the Association for Computational Linguistics, pp. 311–
                                                              318, Philadelphia, Pennsylvania, USA, July 2002. Asso-
Khaidem, L., Saha, S., and Dey, S. R. Predicting the direc-   ciation for Computational Linguistics. doi: 10.3115/
  tion of stock market prices using random forest. arXiv      1073083.1073135. URL https://www.aclweb.
  preprint arXiv:1605.00003, 2016.                            org/anthology/P02-1040.
Kim, R., So, C. H., Jeong, M., Lee, S., Kim, J., and Kang,    Qin, Y., Song, D., Chen, H., Cheng, W., Jiang, G., and
  J. Hats: A hierarchical graph attention network for stock     Cottrell, G. A dual-stage attention-based recurrent neu-
  movement prediction. arXiv preprint arXiv:1908.07999,         ral network for time series prediction. arXiv preprint
  2019.                                                         arXiv:1704.02971, 2017a.

Kim, S., Hong, S., Joh, M., and Song, S. Deeprain: Con-       Qin, Y., Song, D., Chen, H., Cheng, W., Jiang, G., and
  vlstm network for precipitation prediction using multi-       Cottrell, G. A dual-stage attention-based recurrent neu-
  channel radar data. CoRR, abs/1711.02316, 2017. URL           ral network for time series prediction. arXiv preprint
  http://arxiv.org/abs/1711.02316.                              arXiv:1704.02971, 2017b.
                                                              Ren, Y., Liu, J., Tan, X., Zhang, C., Qin, T., Zhao, Z., and
Kingma, D. P. and Ba, J. Adam: A method for stochastic
                                                                Liu, T. Simulspeech: End-to-end simultaneous speech to
  optimization. In International Conference on Learning
                                                                text translation. In ACL, 2020.
  Representations, 2015. URL https://arxiv.org/
  pdf/1412.6980.pdf.                                          Shao, K., Zhu, Y., and Zhao, D. Starcraft micromanage-
                                                                ment with reinforcement learning and curriculum transfer
Kong, Y., Tao, Z., and Fu, Y. Adversarial action prediction     learning. IEEE Transactions on Emerging Topics in Com-
  networks. IEEE Transactions on Pattern Analysis and           putational Intelligence, 3(1):73–84, 2018.
  Machine Intelligence, 42(3):539–553, 2020.
                                                              Shi, X., Chen, Z., Wang, H., Yeung, D.-Y., Wong, W.-k.,
Li, J., Koyamada, S., Ye, Q., Liu, G., Wang, C., Yang, R.,      and Woo, W.-c. Convolutional lstm network: A machine
  Zhao, L., Qin, T., Liu, T.-Y., and Hon, H.-W. Suphx:          learning approach for precipitation nowcasting. In Pro-
  Mastering mahjong with deep reinforcement learning.           ceedings of the 28th International Conference on Neural
  arXiv preprint arXiv:2003.13590, 2020.                        Information Processing Systems - Volume 1, NIPS’15, pp.
                                                                802–810, Cambridge, MA, USA, 2015. MIT Press.
Liu, H., Simonyan, K., and Yang, Y. DARTS: Differ-
  entiable architecture search. In International Confer-      Sinha, A., Malo, P., and Deb, K. A review on bilevel opti-
  ence on Learning Representations, 2019. URL https:            mization: from classical to evolutionary approaches and
  //openreview.net/forum?id=S1eYHoC5FX.                         applications. IEEE Transactions on Evolutionary Com-
                                                                putation, 22(2):276–295, 2017.
Ma, M., Huang, L., Xiong, H., Zheng, R., Liu, K., Zheng,      Sutskever, I., Vinyals, O., and Le, Q. V. Sequence to se-
 B., Zhang, C., He, Z., Liu, H., Li, X., Wu, H., and            quence learning with neural networks. In Ghahramani, Z.,
 Wang, H. STACL: Simultaneous translation with im-              Welling, M., Cortes, C., Lawrence, N. D., and Weinberger,
 plicit anticipation and controllable latency using prefix-     K. Q. (eds.), Advances in Neural Information Processing
 to-prefix framework. In Proceedings of the 57th Annual         Systems 27. Curran Associates, Inc., 2014.
 Meeting of the Association for Computational Linguis-
 tics, pp. 3025–3036, Florence, Italy, July 2019. Asso-       Sutton, R. S. and Barto, A. G. Reinforcement Learn-
 ciation for Computational Linguistics. doi: 10.18653/          ing: An Introduction. The MIT Press, second edition,
 v1/P19-1289. URL https://www.aclweb.org/                       2018. URL http://incompleteideas.net/
 anthology/P19-1289.                                            book/the-book-2nd.html.
                               Temporally Correlated Task Scheduling for Sequence Learning

Tan, Z., Yan, Z., and Zhu, G. Stock selection with random      Zhang, L., Aggarwal, C., and Qi, G.-J. Stock price pre-
  forest: An exploitation of excess return in the chinese        diction via discovering multi-frequency trading patterns.
  stock market. Heliyon, 5(8):e02310, 2019.                      In Proceedings of the 23rd ACM SIGKDD international
                                                                 conference on knowledge discovery and data mining, pp.
Tang, Z., Zhang, T., Wu, J., Du, X., and Chen, K. Multistep-     2141–2149, 2017b.
  ahead stock price forecasting based on secondary de-
  composition technique and extreme learning machine           Zhang, Y. and Yang, Q. A survey on multi-task learning.
  optimized by the differential evolution algorithm. Mathe-      CoRR, abs/1707.08114, 2017. URL http://arxiv.
  matical Problems in Engineering, 2020, 2020.                   org/abs/1707.08114.

Vaswani, A., Shazeer, N., Parmar, N., Uszkoreit, J., Jones,    Zheng, B., Zheng, R., Ma, M., and Huang, L. Simpler and
  L., Gomez, A. N., Kaiser, Ł., and Polosukhin, I. Atten-        faster learning of adaptive policies for simultaneous trans-
  tion is all you need. In Advances in neural information        lation. In Proceedings of the 2019 Conference on Empiri-
  processing systems, pp. 5998–6008, 2017.                       cal Methods in Natural Language Processing and the 9th
                                                                 International Joint Conference on Natural Language Pro-
Veličković, P., Cucurull, G., Casanova, A., Romero, A.,        cessing (EMNLP-IJCNLP), pp. 1349–1354, Hong Kong,
  Lio, P., and Bengio, Y. Graph attention networks. arXiv        China, November 2019a. Association for Computational
  preprint arXiv:1710.10903, 2017.                               Linguistics. doi: 10.18653/v1/D19-1137. URL https:
Vinyals, O., Babuschkin, I., Czarnecki, W. M., Mathieu, M.,      //www.aclweb.org/anthology/D19-1137.
  Dudzik, A., Chung, J., Choi, D. H., Powell, R., Ewalds,      Zheng, B., Zheng, R., Ma, M., and Huang, L. Simulta-
  T., Georgiev, P., et al. Grandmaster level in starcraft ii     neous translation with flexible policy via restricted im-
  using multi-agent reinforcement learning. Nature, 575          itation learning. In Proceedings of the 57th Annual
  (7782):350–354, 2019.                                          Meeting of the Association for Computational Linguis-
Wang, X., Pham, H., Michel, P., Anastasopoulos, A., Car-         tics, pp. 5816–5822, Florence, Italy, July 2019b. Asso-
 bonell, J., and Neubig, G. Optimizing data usage via            ciation for Computational Linguistics. doi: 10.18653/
 differentiable rewards. In International Conference on          v1/P19-1582. URL https://www.aclweb.org/
 Machine Learning, pp. 9983–9995. PMLR, 2020.                    anthology/P19-1582.

Wu, Y., Schuster, M., Chen, Z., Le, Q. V., Norouzi, M.,        Zheng, B., Liu, K., Zheng, R., Ma, M., Liu, H., and
 Macherey, W., Krikun, M., Cao, Y., Gao, Q., Macherey,           Huang, L. Simultaneous translation policies: From
 K., et al. Google’s neural machine translation system:          fixed to adaptive. In Proceedings of the 58th Annual
 Bridging the gap between human and machine translation.         Meeting of the Association for Computational Linguis-
 arXiv preprint arXiv:1609.08144, 2016.                          tics, pp. 2847–2853, 2020a. doi: 10.18653/v1/2020.
                                                                 acl-main.254. URL https://www.aclweb.org/
Yan, X. and Guosheng, Z. Application of kalman filter in the     anthology/2020.acl-main.254.
  prediction of stock price. In 5th International Symposium
  on Knowledge Acquisition and Modeling (KAM 2015).            Zheng, R., Ma, M., Zheng, B., Liu, K., and Huang, L.
  Atlantis Press, 2015.                                          Opportunistic decoding with timely correction for si-
                                                                 multaneous translation. In Proceedings of the 58th
Yang, X., Liu, W., Zhou, D., Bian, J., and Liu, T.-Y. Qlib:      Annual Meeting of the Association for Computational
  An ai-oriented quantitative investment platform. arXiv         Linguistics, pp. 437–442, Online, July 2020b. Associ-
  preprint arXiv:2009.11189, 2020.                               ation for Computational Linguistics. doi: 10.18653/
                                                                 v1/2020.acl-main.42. URL https://www.aclweb.
Zhang, C., Tan, X., Liu, J., Ren, Y., Qin, T., and Liu,          org/anthology/2020.acl-main.42.
  T.-Y. Simuls2s: End-to-end simultaneous speech to
  speech translation. Openreview, 2019. URL https:
  //openreview.net/pdf?id=Ske_56EYvS.

Zhang, F., Guo, R., and Cao, H. Information coefficient as
  a performance measure of stock selection models, 2020.

Zhang, L., Aggarwal, C., and Qi, G.-J. Stock price pre-
  diction via discovering multi-frequency trading patterns.
  In Proceedings of the 23rd ACM SIGKDD International
  Conference on Knowledge Discovery and Data Mining,
  pp. 2141–2149. ACM, 2017a.
                               Temporally Correlated Task Scheduling for Sequence Learning

A. Mathematical definitions
A.1. Latency metrics definitions
Given the input sentence x and the output sentence y, let Lx and Ly denote the length of x and y respectively. Define a
function g(t) of decoding step t, which denotes the number of source tokens processed by the encoder when deciding the
target token yt . For wait-k strategy, g(t) = min{t + k − 1, Lx }. The definitions of Average Proportion (AP) and Average
Lagging (AL) are in Eqn.(3) and Eqn.(4) respectively.

                                                               |y|
                                                       1 X
                                        APg (x, y) =            g(t);                                                      (3)
                                                     |x||y| t=1
                                                             τg (|x|)                
                                                         1    X                t−1
                                        ALg (x, y) =                   g(t) −           ,                                  (4)
                                                     τg (|x|) t=1             |y|/|x|
                                             where τg (|x|) = min{t|g(t) = |x|}.

We use the scripts provided by Ma et al. (2019) to calculate AP and AL scores.

A.2. Mathematical formulation of curriculum transfer learning
For a group of temporally correlated tasks T = {T1 , T2 , · · · , TM }, suppose T is ordered by task difficulty. That is, TM
is the easiest task, followed by TM −1 , TM −2 , etc, and T1 is the hardest task. In the curriculum transfer learning (briefly,
CL) baseline, we gradually change the training task Tm from the easiest task TM to the main task, supposedly, Tk . The
mathematical formulations are shown as follows:
                                                              t−1
                                               m=M −b              (M − k + 1)c                                            (5)
                                                              tmax

where t denotes the current update number (t = 1, 2, ..., tmax ), and tmax denotes the total update number.

B. Model architecture
Following Ma et al. (2019), our model for simultaneous NMT is based on Transformer model (Vaswani et al., 2017). The
model includes an encoder and a decoder, which are used for incrementally processing the source and target sentences
respectively. Both the encoder and decoder are stacked of L blocks.
In Ma et al. (2019), every time a new token is read, the encoder needs to re-encode the entire sentence, which is computa-
tionally expensive. To improve the efficiency, we adopt incremental encoding, so that after reading a new token, we only
encode the new token rather than updating the representations of the whole sentence. The details are as follows:
(1) Incremental encoding: Let hlt denote the output of the t-th position from block l. For ease of reference, let H≤t
                                                                                                                    l
                                                                                                                       denote
   l   l            l             0
{h1 , h2 , · · · , ht }, and let ht denote the embeddings of the t-th token. An attention model attn(q, K, V ), takes a query
q ∈ Rd , a set of keys K and values V as inputs. K and V are of equal size, q ∈ Rd where d ∈ Z+ is the dimension, ki ∈ Rd
and vi ∈ Rd are the i-th key and value. attn is defined as follows:

                                 |K|                                                 |K|
                                 X                        exp((Wq q)> (Wk ki ))      X
              attn(q, K, V ) =          αi Wv vi , αi =                         , Z=     exp((Wq q)> (Wk ki )),            (6)
                                  i=1
                                                                   Z                 i=1


where W ’s are the parameters to be optimized. In the encoder side, hlt is obtained in a unidirectional way: hlt =
attn(hl−1     l−1   l−1
        t , H≤t , H≤t ). That is, the model can only attend to the previously generated hidden representations, and
the computation complexity is O(L2x ). In comparison, (Ma et al., 2019) still leverages bidirectional attention, whose
computation complexity is O(L3x ). We find that unidirectional attention is much more efficient than bidirectional attention
without much accuracy drop (see Appendix B for details).
(2) Incremental decoding: Since we use wait-k strategy, the decoding starts before reading all inputs. At the t-th decoding
step, the decoder can only read x≤t+k−1 . When t ≤ Lx − k, the decoder greedily generates one token at each step, i.e., the
                                          Temporally Correlated Task Scheduling for Sequence Learning

                                           L
token is yt = arg maxw∈V P (w|y≤t−1 ; H≤t+k−1     ), where V is the vocabulary of the target language. When t > Lx − k,
the model has read the full input sentence and can generate words using beam search (Ma et al., 2019).
We compare the performance of original Ma et al. (2019) and our modified model on IWSLT’14 En→De dataset, and the
results are in Figure 6, On IWSLT’14, we observe that the performance of our model slightly drops compared to Ma et al.
(2019). However, the computational cost of Ma et al. (2019) is much larger than our modified model. For example, the
inference speed of our wait-9 model is 57.39 sentences / second, while the inference speed of Ma et al. (2019) is 6.48
sentences / second.


                    28                                                                28

                    26                                                                26

                    24                                                                24




                                                                               BLEU
             BLEU




                    22                                                                22

                    20                                                                20

                    18                                 Ours                           18
                                                       Ma et al. (2019)
                         0.55     0.60   0.65   0.70      0.75   0.80   0.85               1    2    3   4    5   6   7      8   9
                                                AP                                                           AL
                                (a) BLEU-AP, IWSLT’14 En→De                                    (b) BLEU-AL, IWSLT’14 En→De

 Figure 6: Ablation study of different model architectures on IWSLT’14 En→De dataset and WMT’15 En→De dataset.


C. More detailed settings about experiments
C.1. Detailed introduction of the datasets
For IWSLT’14 En→De, following (Edunov et al., 2018), we lowercase all words, tokenize them and apply BPE with 10k
merge operations jointly to the source and target sequences. We split 7k sentences from the training corpus for validation
and the remaining 160k sequences are left as the training set. The test set is the concatenation of tst2010, tst2011, tst2012,
dev2010 and dev2012, which consists of 6750 sentences.
For IWSLT’15 En→Vi, following (Ma et al., 2020), we tokenize the data and replace words with frequency less than 5 by
<unk>1 . We use tst2012 as the validation set and tst2013 as the test set. The training, validation and test sets contains 133k,
1268 and 1553 sentences respectively.
For IWSLT’17 En→Zh, we tokenize the data and apply BPE with 10k merge operations independently to the source and
target sequences2 . We use the concatenation of tst2013, tst2014 and tst2015 as the validation set and use tst2017 as the
test set. The training, validation and test sets contains 235k, 3874 and 1459 sentences respectively. For WMT’15 En↔De,
we follow the setting in (Ma et al., 2019; Arivazhagan et al., 2019). We tokenize the data, apply BPE with 32k merge
operations jointly to the source and target sentences, and get a training corpus with 4.5M sentences. We use newstest2013
as the validation set and use newstest2015 as the test set.

C.2. Detailed training strategy
For the translation model, we use Adam (Kingma & Ba, 2015) optimizer with initial learning rate 5 × 10−4 and
inverse sqrt scheduler (see Section 5.3 of (Vaswani et al., 2017) for details). The batch size and the number of
GPUs of IWSLT En→De, En→Vi, En→Zh and WMT’15 En→De are 4096 × 1GPU, 16000 × 1GPU, 4000 × 1GPU and
3584 × 8 × 16GPU respectively. For IWSLT tasks, the learning rate η is grid searched from {5 × 10−4 , 5 × 10−5 , 5 ×
10−6 , 5 × 10−7 } with vanilla SGD optimizer, and the internal update iteration S is grid searched from { 21 Se , Se , 2Se },
   1
       The data is downloaded from https://nlp.stanford.edu/projects/nmt/, which has been tokenized already.
   2
       The Chinese sentences are tokenized using Jieba ( https://github.com/fxsjy/jieba ).
                                Temporally Correlated Task Scheduling for Sequence Learning

where Se is the number of updates in an epoch of the translation model training. For WMT’15 En→De, due to resource
limitation, we do not train the translation model from scratch. The translation model is warm started from pretrained wait-k
model, the learning rate is set as 5 × 10−5 , and the internal update iteration S is 16.

C.3. Detailed baseline implementation
In this section, we introduce how we reproduce baseline models and get the results on En→Vi task.
For MILk (Arivazhagan et al., 2019) and MMA (Ma et al., 2020), we do not reproduce the results, but directly use the
results reported in Ma et al. (2020). Note that the results for MILk is reproduced by Ma et al. (2020).
For WIW and WID (Cho & Esipova, 2016), we pre-train a standard translation model, using the exact same architecture and
training hyperparameters as our method and in (Ma et al., 2020). For fair comparison, we adopt bi-directional attention.
For Zheng et al. (2020a), we use the pre-trained wait-k model and the model obtained through our results (k = 1, 2, 3, ..., 10).
We use only single model rather than ensemble. As in Zheng et al. (2020a), the thresholds of different k values are obtained
in this way: ρi = ρ1 − (i − 1) ∗ (ρ1 − ρ10 )/9, where we test with ρ1 ∈ {0.2, 0.4, 0.6, 0.8}, ρ10 = 0; and ρ1 = 1,
ρ10 ∈ {0, 0.2, 0.4, 0.6, 0.8}.

D. Supplemental results
In this section, we report the specific BLEU scores and some additional results. The BLEU scores for IWSLT tasks and
WMT’15 En→De task are reported in Table 4 and Table 5 respectively. We further evaluate the baselines and our methods
on WMT’14 and WMT’18 test sets, and report the BLEU-latency curves in Figure 8. The BLEU-AL curves of our methods
and baselines on IWSLT’15 En→Vi are reported in Figure 7(a), the BLEU-AL curves of our method and Zheng et al.
(2020a) are in Figure 7(b).
For significance tests, we compare our method with MTL on all 20 translation tasks (En→{Vi, Zh} tasks and two En→De
tasks, where each task is associated with 5 settings, i.e. wait-1,3,5,7,9), and find that our method significantly outperforms
MTL on 16 tasks with p < 0.05, where 11 out of them are with p < 0.01.




                                Task          wait-k    wait-k ∗ / best k ∗    CL     MTL      Ours
                          En→De (k = 1)        16.75         19.11 / 9        18.23   18.53    19.10
                          En→De (k = 3)        22.79        23.36 / 13        23.41   23.50    24.12
                          En→De (k = 5)        25.34        25.76 / 11        25.88   25.84    26.54
                          En→De (k = 7)        26.74         26.87 / 9        26.85   26.88    27.37
                          En→De (k = 9)        27.25        27.54 / 11        27.48   27.07    27.87
                          En→Vi (k = 1)        25.14         26.14 / 5        26.01   26.12    27.03
                          En→Vi (k = 3)        27.17         28.25 / 5        26.37   28.54    29.01
                          En→Vi (k = 5)        28.29         28.44 / 9        27.97   28.61    28.91
                          En→Vi (k = 7)        28.31        28.38 / 13        28.31   28.77    29.17
                          En→Vi (k = 9)        28.39        28.39 / 9         28.31   28.70    29.06
                          En→Zh (k = 1)        14.24         19.34 / 9        17.26   18.02    19.21
                          En→Zh (k = 3)        19.90        21.66 / 11        21.64   21.36    22.18
                          En→Zh (k = 5)        21.45        23.57 / 11        23.62   22.59    23.70
                          En→Zh (k = 7)        23.23        24.95 / 11        24.32   23.15    24.35
                          En→Zh (k = 9)        23.93        24.83 / 11        24.55   23.55    24.78

                                Table 4: BLEU scores on IWSLT simultaneous NMT tasks.
                                    Temporally Correlated Task Scheduling for Sequence Learning




           29
           28                                                                                        29
           27
           26                                                                                        28
    BLEU




                                                                                              BLEU
           25
                                                                                                     27                        Wait-k
           24
                                                  Wait-k                 MILk                                                  Ours
           23                                     Ours                   WIW
           22                                     MMA-IL                 WID
                                                                                                     26                        Zheng et al.
                                                  MMA-H                                                                        Zheng et al. + ours
           21                                                                                        25
                        0.6        0.7            0.8          0.9          1.0                             0.65 0.70 0.75 0.80 0.85 0.90 0.95 1.00
                                             AP                                                                              AP
    (a) Comparison of our method, WIW, WID, MILk,                                             (b) Comparison and combination of our method and
    MMA-IL and MMA-H.                                                                         Zheng et al. (2020a).

                         Figure 7: BLEU-AP comparison between our method and baselines on En→Vi.




                                                                                              32
                  24
                                                                                              30
                  22                                                                          28

                                                                     Wait-k                   26
           BLEU




                                                                                       BLEU




                  20
                                                                     Wait-k *                 24
                  18                                                 CL
                                                                                              22
                  16
                                                                     Random
                                                                     Ours                     20
                       0.60       0.65            0.70         0.75             0.80                      0.60    0.65       0.70       0.75       0.80
                                                  AP                                                                         AP
                        (a) BLEU-AP, WMT’14 En→De                                                          (b) BLEU-AP, WMT’16 En→De

                                                                                              32
                  24
                                                                                              30
                  22                                                                          28
                                                                                              26
           BLEU




                                                                                       BLEU




                  20
                                                                                              24
                  18
                                                                                              22
                  16
                                                                                              20
                        3     4          5         6       7         8      9                               3    4       5    6     7          8    9
                                                  AL                                                                         AL
                        (c) BLEU-AL, WMT’14 En→De                                                         (d) BLEU-AL, WMT’16 En→De

Figure 8: Translation quality against latency metrics (AP and AL) on WMT’14 and 16 English→German test sets.
                                 Temporally Correlated Task Scheduling for Sequence Learning

                                   k     wait-k   wait-k ∗ / best k ∗    CL     MTL       Ours
                                   1     17.07        19.83 / 9         19.41   17.59    18.63
                                   3     22.86        23.14 / 7         22.51   22.76    23.98
                                   5     25.52        26.09 / 7         25.51   25.66    26.77
                                   7     27.32        27.50 / 9         26.80   26.91    27.92
                                   9     28.05        28.05 / 9         28.20   27.82    28.67

                                       Table 5: BLEU scores on WMT’15 En→De dataset.



E. Additional ablations and analysis on simultaneous translation
E.1. Feature selection
To emphasize the importance of the selected features in Section 3.3 in the main content, we provide four groups of ablation
study, where in each group some specific features are excluded: (i) source and target sentence lengths; (ii) current training
loss and average historical training loss; (iii) current validation loss and average historical validation loss; (iv) training step.
We work on IWSLT’14 En→De task and study the effect to wait-3, 5, 7.
The results are shown in Table 6. We report the BLEU scores only, since the latency metrics (AP and AL) are not significantly
influenced. Removing any feature causes performance drop, indicating that they all contribute to the decision making.
Specifically, network status information including validation performance (feature iii) and training stage (feature iv) is more
important than input data information including sequence length (feature i) and data difficulty (feature ii).


                               k=3                        k=5                        k=7
                     Ours      24.12                      26.54                      27.37
                     - (i)     23.67 (-1.87%, rank 3)     26.03 (-1.92%, rank 3)     26.92 (-1.64%, rank 4)
                     - (ii)    23.70 (-1.74%, rank 4)     26.04 (-1.88%, rank 4)     26.91 (-1.68%, rank 3)
                     - (iii)   23.57 (-2.28%, rank 1)     25.92 (-2.34%, rank 2)     26.72 (-2.37%, rank 1)
                     - (iv)    23.65 (-1.95%, rank 2)     25.63 (-3.43%, rank 1)     26.86 (-1.86%, rank 2)

                         Table 6: Ablation study for feature selection on IWSLT’14 En→De dataset.



E.2. More heuristic baselines
In this section, we conduct ablation studies on two more heuristic baselines to demonstrate the effectiveness of our method.
(1) Randomly selecting k in a window around k ∗ : We implement another baseline which is a combination of wait-k ∗ and
MTL. After obtaining k ∗ , instead of sampling wait-m on all possible {1, 2, · · · , M }, we sample on a smaller region around
k ∗ . We conduct experiments on IWSLT En→De and the results are in Figure 9. We can see that this variant achieves similar
results with wait-k ∗ , but is not as good as our method. This shows the importance of using an adaptive controller to guide
the training.
(2) A variant of CL: Considering that the curriculum transfer learning is related to curriculum learning, we implement
self-paced learning (SPL) for wait-k, a CL method based on loss function: within each minibatch, we remove the τ %
sentences with the largest loss, where τ is gradually decreased from 40 to 0. On IWSLT En→De, when k = 3, the
BLEU/AL/AP for SPL are 22.87/0.66/3.47, which are worse than conventional CL (23.41/0.66/3.48).
(3) An annealing strategy: Inspired by the fact that wait-k ∗ outperforms wait-k, we design a baseline where we randomly
sample the waiting threshold m from a distribution pt (m) at each training step t. The distribution pt (m) linearly anneals
from a uniform distribution to a distribution which prefers larger m. We expect a single annealing strategy can train
reasonably good models for different inference-time k values. Suppose the minimal m value is mmin , the maximal m value
is mmax . mmin and mmax are two integers and m ∈ {mmin , mmin + 1, · · · , mmax }. The total training step is denote as tmax .
                                           Temporally Correlated Task Scheduling for Sequence Learning


                  28                                                                                  28

                  26                                                                                  26

                  24                                                                                  24
           BLEU




                                                                                               BLEU
                  22                                                                                  22
                                                 Wait-k
                  20                             Wait-k *                                             20

                  18
                                                 Ours                                                 18
                                                 Random in k * window
                         0.60      0.65          0.70          0.75      0.80         0.85                    2         3       4       5            6       7       8   9
                                                        AP                                                                                  AL
                          (a) BLEU-AP, IWSLT’14 En→De                                                             (b) BLEU-AL, IWSLT’14 En→De

                                                 Figure 9: Randomly selecting k in a window around k ∗ .


pt (m) is mathematically defined as follows:

                                                                                t                             t
                                                  pt (m) = (1 −                       ) · pinit (m) +                 · pfinal (m),
                                                                 tmax                                        tmax
                                                                    1                                                 m                                                       (7)
                                                 pinit (m) =                 ,                         pfinal (m) = Pmmax                       .
                                                             mmax − mmin + 1                                                    i=mmin i

The results on IWSLT’15 En→Vi are shown in Figure 10, which shows this baseline brings limited improvement compared
to wait-k. A possible reason is that this baseline cannot guarantee the best “annealing” strategy for each separate k, while
our method can adaptively find the optimal strategy. Besides, as shown in Figure 5 in the main content, the learned strategies
for different wait-k inference are pretty different.


                  29.0                                                                                29.0
                  28.5                                                                                28.5
                  28.0                                                                                28.0
                  27.5                                                                                27.5
           BLEU




                                                                                               BLEU




                  27.0                                                                                27.0
                  26.5                                                                                26.5
                  26.0
                                                                         Wait-k                       26.0
                                                                         Ours
                  25.5                                                                                25.5
                                                                         Annealing
                  25.0                                                                                25.0
                            0.65          0.70          0.75          0.80          0.85                          3         4       5       6            7       8   9   10
                                                         AP                                                                                     AL
                          (a) BLEU-AP, IWSLT’15 En→Vi                                                             (b) BLEU-AL, IWSLT’15 En→Vi

                                                                      Figure 10: The annealing strategy.


F. More details about stock trend forecasting
F.1. Detailed introduction of the datasets
For the Chinese A-share market dataset used in stock trend forecasting tasks, all the price and volume data are loaded from
Qlib (Yang et al., 2020). In this paper, only the stocks in CSI300 are included in the experiments. CSI300 consists of the
300 largest and most liquid A-share stocks, that can reflect the overall performance of China A-share market.
                              Temporally Correlated Task Scheduling for Sequence Learning

F.2. Training details
For the stock trend forecasting models, we select the optimal hyper-parameters including learning rate, dropout rate, batch
size and optimizer of scheduler and the sequence length L on the validation set. We repeat each experiment by using 5
random seed and report the average scores (RankIC, ICIR and MSE) to get the final result.

F.3. Supplemental results
We report the specific ICIR scores for stock trend forecasting task in Table 7. Comparing with RankIC and MSE, similar
phenomenon can be observed: 1) with temporally correlated tasks, our method significantly outperforms MTL and CL on
most settings; 2) using a larger temporally correlated task set does not always bring improvements; 3) our method performs
better than some strong models like GAT and lightGBM (briefly, LGB).

                                                     Task-1       Task-2   Task-3
                                           GRU       0.373        0.127    0.111
                                           MLP       0.175        0.164    0.116
                                           LGB       0.297        0.180    0.070
                                           GAT       0.389        0.133    0.113
                                                          MTL
                                           3tasks    0.467        0.179    0.083
                                           5tasks    0.444        0.146    0.115
                                          10tasks    0.403        0.134    0.135
                                                             CL
                                           3tasks    0.397        0.198    0.112
                                           5tasks    0.419        0.200    0.110
                                          10tasks    0.393        0.200    0.117
                                                          Ours
                                           3tasks    0.559        0.228    0.126
                                           5tasks    0.583        0.203    0.117
                                          10tasks    0.532        0.222    0.160

Table 7: ICIR scores. The first four rows are the results of various model architectures without leveraging temporally
correlated tasks. The following rows are the results with different algorithms and different task sets.