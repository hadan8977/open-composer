source: https://arxiv.org/pdf/2502.09318
fetched_utc: 2026-10-04T18:44:04Z
bytes_raw: 141609

SigGate: Enhancing Recurrent Neural Networks
                                                 with Signature-Based Gating Mechanisms
                                                                                       Rémi Genet∗§ and Hugo Inzirillo† §
                                                                                     ∗ DRM, Université Paris Dauphine - PSL
                                                                                 † CREST-ENSAE, Institut Polytechnique de Paris



                                            Abstract—In this paper, we propose a novel approach that      of the entire history of a sequence. In our recent work [17]
arXiv:2502.09318v1 [cs.LG] 13 Feb 2025




                                         enhances recurrent neural networks (RNNs) by incorporating       we have shown that incorporating path signatures as weighting
                                         path signatures into their gating mechanisms. Our method         mechanisms within neural networks can significantly improve
                                         modifies both Long Short-Term Memory (LSTM) and Gated
                                         Recurrent Unit (GRU) architectures by replacing their forget and their performance on sequential tasks. Building upon these
                                         reset gates, respectively, with learnable path signatures. These foundations, we propose a novel modification to LSTM and
                                         signatures, which capture the geometric features of the entire   GRU architectures that leverages path signatures to enhance
                                                                                                          their gating mechanisms. In our approach, we replace the
                                         path history, provide a richer context for controlling information
                                         flow through the network’s memory. This modification allows the  forget gate in LSTM and the reset gate in GRU with signature-
                                         networks to make memory decisions based on the full historical
                                         context rather than just the current input and state. Through    based gates that compute their values using the signature
                                         experimental studies, we demonstrate that our Signature-LSTM     of the input sequence up to the current time step. This
                                         (SigLSTM) and Signature-GRU (SigGRU) models outperform           modification allows these gates to make decisions based on
                                         their traditional counterparts across various sequential learningthe entire history of the input sequence, rather than just
                                         tasks. By leveraging path signatures in recurrent architectures, the current input and state. The signature stream provides a
                                         this method offers new opportunities to enhance performance in
                                         time series analysis and forecasting applications.               natural way to capture the evolving dynamics of the input
                                                                                                          sequence, making it particularly well-suited for controlling
                                                                    I. I NTRODUCTION                      memory retention and reset decisions in recurrent architectures.
                                            The modeling of sequential data is crucial in machine Our work demonstrates that integrating path signatures directly
                                         learning application, particularly in time series analysis [1] into the gating mechanisms of recurrent networks leads to
                                         and forecasting. Understanding temporal dependencies is fun- improved performance across various sequential learning tasks.
                                         damental to make accurate prediction. Traditional methods The resulting Signature-LSTM (SigLSTM) and Signature-
                                         such as autoregressive models [2] and hidden Markov models GRU (SigGRU) architectures show an enhanced ability to
                                         [3] often struggle to capture these long term dependencies capture long-term dependencies while maintaining the com-
                                         in highly complex nonlinear sequences [2]. With the advent putational efficiency of their traditional counterparts. These
                                         of deep learning [4], Recurrent Neural Networks (RNNs) [5] improvements are particularly notable in tasks requiring an
                                         have emerged as a powerful tool for modeling sequential understanding of complex temporal patterns and long-range
                                         data, demonstrating remarkable success in tasks ranging from interactions in the data. The implementation of the SigLSTM
                                         financial forecasting [6], [7], [8], [9], to speech recognition and SigGRU are available as an open-source Python package
                                         and healthcare analytics Among RNN variants, Long Short- sig_rnn on PyPI, and the complete source code can be found
                                         Term Memory (LSTM) [10] and Gated Recurrent Units (GRU) at sig_rnn. This repository includes all the code necessary to
                                         [11] are particularly successful due to their ability to capture reproduce our experiments.
                                         long-term dependencies. These architectures rely on gating                             II. R ELATED W ORK
                                         mechanisms to control the flow of information through their
                                         memory cells, traditionally using the current input and previ-      Recurrent Neural Networks (RNNs), particularly Long
                                         ous state to make these decisions. However, this local view      Short-Term    Memory (LSTM) and Gated Recurrent Unit
                                         might limit their ability to capture broader temporal patterns   (GRU)   architectures,  have been widely employed in sequential
                                         and relationships in the data. Path signatures, first introduced learning  tasks  due   to  their ability to capture temporal de-
                                         by Chen [12], offer a powerful mathematical framework for        pendencies.  However,     traditional gating mechanisms in these
                                         encoding the essential features of sequential data through iter- models  primarily  rely  on  local context using only the "current"
                                         ated integrals. Recent works have demonstrated the utility of input and "hidden state" for memory updates which can
                                         signatures in various machine learning applications [13], [14], limit their effectiveness in modeling long-range dependencies
                                         particularly in time series analysis [15], [16]. The key insight [18]. Some researchers proposed refinements on the gating
                                         is that path signatures can capture important geometric and mechanisms to enhance gradient flow and learning [19], [18],
                                         temporal patterns in the data, providing a rich representation [20]. At the same time, the concept of path signatures, derived
                                                                                                          from rough path theory, has emerged as a key mathematical
                                           § These authors contributed equally.                           tool for deciphering the geometric structure of sequential



                                                                                                              1
data [21]. These signatures have been successfully adapted in         2) Gated Recurrent Unit: The GRU simplifies the LSTM
neural architectures, enhancing their ability to process complex architecture by combining the forget and input gates into a
temporal patterns. In particular, [22] showed that integrating single update gate and merging the cell state and hidden state.
these signatures into LSTM networks optimized the solution of Given an input xt and previous hidden state ht−1 , the GRU
path-dependent partial differential equations, with applications computes:
in finance. In the same vein, [23] recently proposed Rough
Transformers, models exploiting path signatures to improve                    zt = σ(Wz xt + Uz ht−1 + bz )                        (Update Gate)
the analysis of continuous-time data. Recent studies have
                                                                               rt = σ(Wr xt + Ur ht−1 + br )                         (Reset Gate)
also investigated the application of path signatures in RNN-
based models. [18] introduced alternative gating mechanisms         h̃t = tanh(Wh xt + Uh (rt ⊙ ht−1 ) + bh ). (Candidate State)
to address saturation issues in traditional RNNs, while path-
based feature extraction has been utilized in areas such as The hidden state is then updated as:
personalized user modeling (e.g., Sequential Path Signature
Networks) and path classification tasks. These signatures have             ht = (1 − zt ) ⊙ ht−1 + zt ⊙ h̃t .                 (Hidden Update)
been also leveraged in classification tasks in finance to build In both architectures, σ represents the sigmoid activation
a novel approach to portfolio construction for digital assets function, tanh is the hyperbolic tangent activation function,
[24]. These advancements indicate that incorporating path ⊙ denotes element-wise multiplication, and W∗ , U∗ , b∗ are
signatures into deep learning frameworks can enhance the learnable parameters.
representation of both short-term and long-term sequences.
Building upon these advances, our work proposes a novel A. Path Signatures
SigLSTM and SigGRU, where we replace the forget and                   Path signatures provide a systematic way to encode se-
reset gates, respectively, with learnable path signatures. This quential data by computing iterated integrals along a path.
allows for richer contextual modeling by incorporating the For a path X : [0, T ] → Rd , the signature captures infor-
full historical trajectory into memory updates. Our approach mation about both the path’s values and their patterns of
extends prior work by leveraging path signatures in a fully variation. Given an N-dimensional path (X )
                                                                                                                                 t t∈[0,T ] where
learnable manner within standard recurrent architectures, im- X = (X , ..., X ), the signature is constructed through
                                                                     t          1,t           N,t
proving performance across diverse sequence modeling and successive levels of iterated integrals. The first level consists
time series forecasting tasks.                                    of the increments of each coordinate path over the interval
                                                                  [0, t]:
                  III. M ODEL A RCHITECTURE
                                                                                             Z t
   At their core, Recurrent Neural Networks with gated ar-                 S(X)0,t =n
                                                                                                  dXsn , n ∈ {1, ..., N }.               (Level 1)
chitectures aim to solve the vanishing gradient problem en-                                    0
countered in simple RNNs by introducing a memory cell. The second level captures pairwise interactions between coor-
This memory cell maintains information over time and is dinates through double iterated integrals:
controlled by different gates that determine what information                               Z t
should be kept, forgotten, or updated. The two most prominent           S(X)n,m         =        S(X)n0,s dXsm , n, m ∈ {1, ..., N },
                                                                                0,t
architectures implementing this concept are the Long Short-                                   0
Term Memory (LSTM) and the Gated Recurrent Unit (GRU).                                                                                   (Level 2)
   1) Long Short-Term Memory: The LSTM architecture main-         This    pattern   continues      for  higher    levels,  with    the  k-th level
tains a cell state ct that acts as a memory conveyor belt, with   signature    terms      defined   recursively     as:
gates controlling the flow of information. At each time step                                      Z t
                                                                                   i1 ,...,ik               i1 ,...,ik−1
t, given an input xt and the previous hidden state ht−1 , the              S(X)    0,t         =      S(X)0,s            dXsik ,         (Level k)
                                                                                                   0
LSTM computes:
                                                                  where i1 , ..., ik ∈ {1, ..., N }. The complete signature is the
           it = σ(Wi xt + Ui ht−1 + bi ),            (Input Gate) collection of all these terms:

          ft = σ(Wf xt + Uf ht−1 + bf ),               (Forget Gate)            S(X)0,T = (1, S(X)10,T , ..., S(X)N
                                                                                                                  0,T ,
                                                                                                   1,1
                                                                                               S(X)0,T , ..., S(X)N,N
                                                                                                                  0,T ,        (Full Signature)
         c̃t = tanh(Wc xt + Uc ht−1 + bc ),               (Cell Gate)
                                                                                                          S(X)1,1,1
                                                                                                              0,T , ...)
          ot = σ(Wo xt + Uo ht−1 + bo ),               (Output Gate)        In practice, we truncate this infinite series at a specified depth
The cell state and hidden state are then updated as:                        M , resulting in a finite-dimensionalPvector.kThe dimension of
                                                                            the truncated signature grows as M      k=1 N , where N is the
             ct = ft ⊙ ct−1 + it ⊙ c̃t ,               (Cell Update)        dimension of the input path. For computational efficiency and
                                                                            to maintain a reasonable number of parameters, we typically
               ht = ot ⊙ tanh(ct ).                   (Hidden State)        use M = 2 or M = 4 in our models. To normalize the



                                                                        2
signature values across different sequence lengths, we apply package, which provides efficient GPU-accelerated signature
time normalization:                                           calculations within Keras models. By enabling the stream op-
                      S(X)0,t                                 tion in keras-sig, we obtain the complete sequence of iterated
          Ŝ(X)0,t =          .         (Time Normalization) integrals up to time t for each timestep, which is essential
                          t
                                                              for our sequential processing. For computational efficiency,
This normalization helps ensure that the signature terms re-
                                                              we extensively use Einstein summation operations (einsum)
main comparable across different time scales and sequence
                                                              to batch-compute transformations across the entire sequence.
lengths, which is crucial for their use in neural network
                                                              For instance, in both architectures, we compute the input trans-
architectures.
                                                              formations for all timesteps simultaneously. Let X ∈ RB×T ×I
B. Integration of Path Signatures in Gating Mechanisms        be the input tensor, where B represents the batch size, T
                                                              represents the number of time steps, and I represents the
   Our approach enhances traditional RNN architectures by
                                                              input feature dimension. Similarly, let K ∈ RI×J denote the
replacing specific gates with signature-based computations.
                                                              kernel matrix (or weight matrix), where I is the input feature
Before computing the signatures, we first reduce the dimen-
                                                              dimension (matching the last dimension of X), and J is the
sionality of the input sequence through a learnable linear
                                                              output feature dimension, which defines the dimensionality
transformation:
                                                              of the transformation applied to the input tensor.The output
               X̃t = Wsig Xt            (Input Preprocessing) Y ∈ RB×T ×J , is computed as:
where Wsig ∈ R5×d projects the d-dimensional input to a                        X
                                                                               I

5-dimensional space. This preprocessing step is crucial for         Yb,t,j =         Xb,t,i · Ki,j ,
                                                                                                                                         (1)
computational efficiency, as the signature dimension grows                     i=1

exponentially with the input dimension. For instance, with a             ∀b ∈ {1, . . . , B}, t ∈ {1, . . . , T }, j ∈ {1, . . . , J}.
hidden state of size 100, a direct signature computation of        This equation specifies that for each batch b, each time step
degree 2 would result in a signature of dimension 10,000,          t, and each output feature j, the corresponding output Yb,t,j
making the model computationally intractable.                      is computed by summing over the product of Xb,t,i (the input
  In the SigLSTM, we replace the traditional forget gate           feature at batch b, time step t, and feature i) and Ki,j (the
computation with a signature-based version:                        weight from input feature i to output feature j). This operation
                                                                   transforms the input features X into a new feature space
       ft = σ(Wf S(X̃)0,t + bf )         (Signature Forget Gate)   defined  by K, while preserving the batch and time dimen-
                                                                   sions.This operation efficiently combines the input sequence
where S(X̃)0,t represents the time-normalized signature of the with the weight matrices in a single operation, avoiding the
preprocessed input sequence up to time t, and Wf is now a need for explicit loops. When using the JAX backend, we
matrix that maps from the signature space to the hidden state implement the sequential processing using the scan operation,
dimension. Similarly, for the SigGRU, we modify the reset which offers significant advantages over traditional loops. The
gate computation:                                                  scan operation allows explicit control over the unroll level of
                                                                   the computation, making the compilation process more man-
        rt = σ(Wr S(X̃)0,t + br )         (Signature Reset Gate) ageable. This implementation strategy results in models that
The other gates and computations in both architectures re- are both computationally efficient and practical for deployment
main unchanged from their traditional counterparts. This tar- across different backend environments, while maintaining the
geted modification allows us to leverage the rich temporal theoretical advantages of signature-based gating mechanisms.
information captured by signatures specifically for memory
                                                                                        IV. L EARNING TASKS
control decisions, while maintaining the overall structure and
efficiency of the original architectures.The signature stream         We evaluate our signature-based RNN architectures on two
provides these gates with a comprehensive view of the input distinct forecasting tasks using cryptocurrency market data
history, allowing them to make more informed decisions about from the Binance exchange, spanning from January 1, 2020,
memory retention. The path signature captures not just the to December 31, 2022. Our dataset focuses on USDT markets,
current state of the input, but also how it has evolved over time, which represent the most actively traded pairs on the exchange.
including important geometric features and temporal patterns For the learning task we used the package Keras Sig [25].
that might be relevant for determining what information should
be maintained or discarded from the memory cell.                   A. Task Definitions
                                                                      The first task involves predicting trading volumes, utilizing
C. Implementation Details                                          hourly notional amounts traded across multiple assets (BTC,
   The implementation of both SigLSTM and SigGRU lever- ETH, ADA, XMR, EOS, MATIC, TRX, FTM, BNB, XLM,
ages the multi-backend capabilities of Keras, making these ENJ, CHZ, BUSD, ATOM, LINK, ETC, XRP, BCH, and LTC)
architectures compatible with TensorFlow, JAX, and PyTorch to forecast BTC volume. This multivariate approach allows
backends. The signature computations utilize the keras-sig the models to capture potential cross-market dependencies



                                                                3
and leading indicators. The second task focuses on predicting                       V. R ESULTS A NALYSIS
absolute returns of BTC prices, using the same multivariate        Let us first examine the performance on the volatility predic-
input structure. This modification from the original univariate tion task. Table I presents the R2 scores across different model
setup in prior work enables us to investigate whether cross- architectures. For short-term predictions (1-step ahead), we
market information can enhance volatility forecasting accuracy,
while absolute returns provide a direct measure of price TABLE I: Average and Standard Deviation of R2 Scores for
variability.                                                    Absolute Returns Prediction
B. Data Preprocessing                                                    Model                  1-step ahead      6-step ahead
                                                                                               Mean      Std     Mean       Std
  For volume prediction, we use a two-stage scaling approach.
                                                                         Two-Layer LSTM Models
First, we divide each series by its two-week moving median,              LSTM                  0.1620   0.0017   0.1257   0.0075
shifted forward by the prediction horizon to prevent look-               SignatureLSTM-2-2     0.1597   0.0099   0.1313   0.0031
                                                                         SignatureLSTM-3-2     0.1642   0.0043   0.1312   0.0084
ahead bias. This transformation helps achieve stationarity               SignatureLSTM-3-3     0.1544   0.0103   0.1312   0.0068
across time. Subsequently, we apply MinMax scaling per asset             SignatureLSTM-4-4     0.1625   0.0033   0.1303   0.0048
to constrain values within [0,1], using only training data to            Two-Layer GRU Models
compute scaling parameters. For absolute returns prediction,             GRU                  0.1604    0.0033   0.1263   0.0070
                                                                         SignatureGRU-2-2     0.1531    0.0072   0.1135   0.0077
we maintain the same multivariate structure but scale the data           SignatureGRU-3-2     0.1503    0.0097   0.1135   0.0117
using the maximum value from the training set to ensure all              SignatureGRU-3-3     0.1519    0.0107   0.1151   0.0038
                                                                         SignatureGRU-4-4     0.1589    0.0042   0.1222   0.0027
values fall within [0,1], with the possibility of test set values
                                                                         Three-Layer Models
exceeding this range.                                                    LSTM-3                0.1533   0.0106   0.1248   0.0047
                                                                         SignatureLSTM-3-3-3   0.1637   0.0029   0.1324   0.0057
C. Model Variants and Training Setup                                     GRU-3                 0.1564   0.0071   0.1190   0.0155
                                                                         SignatureGRU-3-3-3    0.1502   0.0087   0.1143   0.0067
   All models are implemented with a consistent hidden state
                                                                          Flattened Output Models
size of 100 units across all recurrent layers. We evaluate                LSTM                    0.1551  0.0036 0.1234 0.0049
several architectural variants:                                           SignatureLSTM-3-3       0.1515  0.0085 0.1175 0.0069
                                                                          GRU                     0.1429  0.0131 0.1156 0.0022
   1) Signature-Based Models: Our signature-based architec-               SignatureGRU-3-3        0.1444  0.0054 0.1119 0.0045
tures explore different configurations while maintaining the
                                                                          Extended Signature Input Models
base hidden size:                                                         SignatureLSTM-2-2       0.1631  0.0057 0.1298 0.0054
                                                                          SignatureGRU-2-2        0.1530  0.0055 0.1111 0.0039
   • Varying signature depths (2, 3, and 4) with consistent
      architecture depth
   • Different input projection dimensions (default 5 and         observe that LSTM-based models generally outperform their
      expanded 10)                                                GRU counterparts, with traditional LSTM achieving an R2
   • Architectural variations (2-layer, 3-layer, and flattened    of 0.1620. However, signature-enhanced variants demonstrate
      output versions)                                            superior performance, with SignatureLSTM-3-2 reaching the
                                                                              2
   2) Baseline Models: Standard LSTM and GRU models highest R of 0.1642. This improvement, while modest,
are implemented with matching architectures and the same is consistent across multiple runs as indicated by the low
hidden size of 100 units, ensuring a fair comparison with our standard deviation of 0.0043. For medium-term predictions
signature-based versions.                                         (6-step ahead), the performance dynamics shift significantly.
                                                                  Here, signature-based architectures show a more substantial
D. Training Protocol                                              advantage, with SignatureLSTM-3-3-3 achieving an R2 of
   The training process was configured with a batch size of 0.1324. This represents a marked improvement over traditional
128 and a maximum of 1000 epochs. Early stopping was models, where performance typically degrades more rapidly
employed to prevent overfitting, with a patience of 10 epochs with prediction horizon. The computational requirements for
and a minimum delta of 0.00001 to determine significant im- these models, shown in Table II, reveal important practical
provement. Additionally, a learning rate reduction on plateau considerations. While signature-based models demonstrate
mechanism was implemented, reducing the learning rate by superior predictive performance, they come with increased
a factor of 0.25 after 5 epochs of no improvement, with a computational costs. The training time for SignatureLSTM
minimum learning rate set at 0.000025. The training data was variants is typically 5-6 times longer than traditional LSTMs,
split with 20% reserved for validation, ensuring robust per- though SignatureGRU models show a more moderate increase
formance evaluation during training. The sequence length for of 2-3 times. This computational overhead must be weighed
all models is set to the maximum between 45 and 5 times the against the performance benefits when considering deployment
prediction horizon, providing sufficient historical context while scenarios. Turning to the volume prediction task, Table III
maintaining computational efficiency. For volume prediction, presents a notably different performance pattern. In contrast
we evaluate horizons of 1, 9, and 15 steps ahead, while for to the volatility task, GRU-based architectures consistently
absolute returns prediction, we focus on 1 and 6 steps ahead. outperform LSTM variants for volume prediction, particu-
Each model configuration is trained and evaluated five times larly at longer horizons. Standard LSTM models struggle
to assess stability and statistical significance of the results.  with nine and fifteen-step predictions, often yielding negative



                                                                    4
TABLE II: Average Training Time (seconds) for Model Vari- TABLE IV: Average Training Time (seconds) for Volume
ants                                                      Prediction
           Model                     1-step ahead   6-step ahead             Model                     1-step ahead   9-step ahead   15-step ahead
           Two-Layer LSTM Models                                             Two-Layer LSTM Models
           LSTM                         14.88          14.27                 LSTM                         14.71          18.46           21.95
           SignatureLSTM-2-2            80.62          87.69                 SignatureLSTM-2-2            82.66          82.51          154.06
           SignatureLSTM-3-2            86.94          93.13                 SignatureLSTM-3-2            85.63          86.71          159.63
           SignatureLSTM-3-3            86.83          91.79                 SignatureLSTM-3-3            86.77          87.78          160.49
           SignatureLSTM-4-4            93.15          98.96                 SignatureLSTM-4-4            97.23          93.57          174.18
           Two-Layer GRU Models                                              Two-Layer GRU Models
           GRU                          17.03          15.81                 GRU                          19.08          19.19           25.04
           SignatureGRU-2-2             39.00          39.66                 SignatureGRU-2-2             41.74          47.77           50.31
           SignatureGRU-3-2             43.15          42.79                 SignatureGRU-3-2             47.77          51.98           58.42
           SignatureGRU-3-3             42.20          42.11                 SignatureGRU-3-3             43.89          46.83           53.00
           SignatureGRU-4-4             48.74          46.76                 SignatureGRU-4-4             51.15          53.95           65.14
           Three-Layer Models                                                Three-Layer Models
           LSTM                         21.06          20.58                 LSTM                         22.82          24.01           30.49
           SignatureLSTM-3-3-3         122.06         130.08                 SignatureLSTM-3-3-3         122.44         126.40          215.36
           GRU                          24.41          23.20                 GRU                          28.58          26.55           41.78
           SignatureGRU-3-3-3           55.36          57.53                 SignatureGRU-3-3-3           66.96          62.16           78.30
           Flattened Output Models                                           Flattened Output Models
           LSTM                         14.42          14.82                 LSTM                         18.31          17.70           25.38
           SignatureLSTM-3-3           116.28          95.98                 SignatureLSTM-3-3           128.54          87.42          162.89
           GRU                          16.61          17.96                 GRU                          18.78          20.80           28.87
           SignatureGRU-3-3             42.77          40.37                 SignatureGRU-3-3             48.97          45.55           59.60
           Extended Signature Input Models                                   Extended Signature Input Models
           SignatureLSTM-2-2          85.12            92.14                 SignatureLSTM-2-2          89.37            87.39          155.90
           SignatureGRU-2-2           42.39            39.38                 SignatureGRU-2-2           46.29            47.30           52.02


TABLE III: Average and Standard Deviation of R2 Scores for
Volume Prediction                                                               GRUs prove superior for volume forecasting. This underscores
                                                                                the importance of maintaining a diverse model portfolio
   Model                     1-step ahead      9-step ahead     15-step ahead
                            Mean       Std   Mean        Std   Mean        Std  rather than seeking a one-size-fits-all solution. Second, the
   Two-Layer LSTM Models                                                        flattening strategy shows task-specific benefits. For volatility
   LSTM                    0.3847    0.0061 -0.0934    0.1288 -0.1718    0.1369
   SignatureLSTM-2-2       0.3931    0.0171 -0.1346    0.2016 -0.1072    0.0940
                                                                                prediction, flattened architectures perform competitively with
   SignatureLSTM-3-2       0.4010    0.0059 -0.0399    0.0521 -0.0396    0.1167 their sequential counterparts, particularly in longer horizons.
   SignatureLSTM-3-3       0.3996    0.0136 -0.1359    0.0828 -0.1486    0.1463
   SignatureLSTM-4-4       0.3956    0.0101 -0.1228    0.0944 -0.0779    0.0726 However, for volume prediction, flattening generally leads to
   Two-Layer GRU Models                                                         decreased performance, suggesting that maintaining temporal
   GRU                     0.3972    0.0018 0.0949     0.0224  0.0807    0.0411
   SignatureGRU-2-2        0.3995    0.0070 0.1183     0.0098  0.0944    0.0045
                                                                                structure is more critical for this task. Third, signature-based
   SignatureGRU-3-2        0.4029    0.0032 0.1164     0.0077  0.0833    0.0080 modifications consistently improve upon the best-performing
   SignatureGRU-3-3        0.4051    0.0019  0.1210    0.0078  0.0963    0.0062
   SignatureGRU-4-4        0.4042    0.0048  0.1196    0.0041  0.0891    0.0076 base architecture for each task. When LSTMs perform better
   Three-Layer Models                                                           (volatility), SignatureLSTM variants achieve the highest scores.
   LSTM                    0.3700    0.0212 -0.0662    0.1228 -0.1644    0.0467
   SignatureLSTM-3-3-3     0.4025    0.0036 -0.2870    0.1957 -0.1309    0.0725 Similarly, when GRUs are superior (volume), SignatureGRU
   GRU
   SignatureGRU-3-3-3
                           0.3840
                           0.3941
                                     0.0079
                                     0.0045
                                             0.0614
                                             0.1185
                                                       0.0536
                                                       0.0080
                                                               0.0253
                                                               0.0800
                                                                         0.0634
                                                                         0.0065
                                                                                models lead the performance metrics. This pattern suggests
   Flattened Output Models
                                                                                that signature-based gating mechanisms effectively enhance
   LSTM                    0.3861    0.0071 -0.2347    0.2266 -0.3657    0.4826 the underlying strengths of each architecture rather than fun-
   SignatureLSTM-3-3       0.4038    0.0028  0.0775    0.0368 -0.0027    0.0469
   GRU                     0.3878    0.0026  0.0891    0.0107  0.0759    0.0041 damentally altering their characteristics. The optimal signature
   SignatureGRU-3-3        0.3933    0.0056  0.1136    0.0088  0.0669    0.0123 depth appears to be task-specific, with depth-3 models gener-
   Extended Signature Input Models
   SignatureLSTM-2-2       0.3898    0.0132 -0.1497    0.1205 -0.1256    0.0867
                                                                                ally providing the best balance of performance and compu-
   SignatureGRU-2-2        0.4041    0.0037  0.1207    0.0114  0.0900    0.0037 tational cost. Increasing to depth-4 shows diminishing returns
                                                                                relative to the additional computational overhead, while depth-
                                                                                2 models sometimes lack sufficient expressiveness for complex
R2 values, while GRU maintains positive performance. The patterns. These findings highlight the adaptability of signature-
SignatureGRU-3-3 achieves the best results across all horizons based modifications across different architectural choices and
(R2 of 0.4051, 0.1210, and 0.0963 for one, nine, and fifteen prediction tasks, while also emphasizing the importance of
steps respectively), demonstrating remarkable stability as indi- careful model selection based on specific application require-
cated by low standard deviations.The timing results for volume ments and computational constraints.
prediction, presented in Table IV, follow similar patterns
to the volatility task. These comprehensive results reveal                                             VI. C ONCLUSION
several key insights about model architecture choices: First,                      This paper introduces a novel approach to enhancing re-
the effectiveness of LSTM versus GRU architectures is highly current neural networks through the integration of path signa-
task-dependent. While LSTMs excel at volatility prediction, tures into their gating mechanisms. By modifying the forget



                                                                       5
gate in LSTMs and the reset gate in GRUs, our method                                   [12] K.-T. Chen, “Integration of paths–a faithful representation of paths by
leverages the rich geometric information captured by path                                   noncommutative formal power series,” Transactions of the American
                                                                                            Mathematical Society, vol. 89, no. 2, pp. 395–407, 1958.
signatures to improve the networks’ ability to process sequen-                         [13] I. Chevyrev and A. Kormilitzin, “A primer on the signature method in
tial data. Our comprehensive empirical evaluation across two                                machine learning,” arXiv preprint arXiv:1603.03788, 2016.
distinct forecasting tasks reveals several significant findings.                       [14] A. Fermanian, “Embedding and learning with signatures,” Computa-
                                                                                            tional Statistics & Data Analysis, vol. 157, p. 107148, 2021.
The signature-based modifications consistently improve perfor-                         [15] L. G. Gyurkó, T. Lyons, M. Kontkowski, and J. Field, “Extracting
mance over traditional architectures, with particularly notable                             information from the signature of a financial data stream,” arXiv preprint
gains in longer-horizon predictions. The effectiveness of these                             arXiv:1307.7244, 2013.
                                                                                       [16] J. Dyer, P. W. Cannon, and S. M. Schmon, “Deep signature statistics
enhancements varies between LSTM and GRU architectures                                      for likelihood-free time-series models,” in ICML Workshop on Invertible
in a task-dependent manner, demonstrating the flexibility of                                Neural Networks, Normalizing Flows, and Explicit Likelihood Models,
our approach in augmenting different base architectures. The                                2021.
                                                                                       [17] H. Inzirillo and R. Genet, “Sigkan: Signature-weighted kolmogorov-
computational overhead introduced by signature calculations,                                arnold networks for time series,” arXiv preprint arXiv:2406.17890, 2024.
while significant, is offset by meaningful improvements in                             [18] A. Gu, C. Gulcehre, T. Paine, M. Hoffman, and R. Pascanu, “Improving
predictive performance and model stability. The Signature-                                  the gating mechanism of recurrent neural networks,” in International
                                                                                            conference on machine learning. PMLR, 2020, pp. 3800–3809.
GRU variant, in particular, offers an attractive balance between                       [19] Y. Lu and F. M. Salem, “Simplified gating in long short-term memory
computational efficiency and prediction accuracy, making it                                 (lstm) recurrent neural networks,” in 2017 IEEE 60th international
particularly suitable for practical applications. These results                             midwest symposium on circuits and systems (MWSCAS). IEEE, 2017,
                                                                                            pp. 1601–1604.
open several promising directions for future research. The suc-                        [20] Z. Cheng, Y. Xu, M. Cheng, Y. Qiao, S. Pu, Y. Niu, and F. Wu, “Refined
cess of signature-based gating suggests potential applications                              gate: A simple and effective gating mechanism for recurrent units,” arXiv
in other neural architectures beyond traditional RNNs. Ad-                                  preprint arXiv:2002.11338, 2020.
                                                                                       [21] T. J. Lyons, “Differential equations driven by rough signals,” Revista
ditionally, investigating more efficient methods for signature                              Matemática Iberoamericana, vol. 14, no. 2, pp. 215–310, 1998.
computation could further enhance the practical applicability                          [22] M. Sabate-Vidales, D. Šiška, and L. Szpruch, “Solving path depen-
of these models. The task-dependent nature of performance                                   dent pdes with lstm networks and path signatures,” arXiv preprint
                                                                                            arXiv:2011.10630, 2020.
improvements also warrants further study into the relationship                         [23] F. Moreno-Pino, A. Arroyo, H. Waldon, X. Dong, and Á. Cartea, “Rough
between data characteristics and optimal model configuration.                               transformers for continuous and efficient time-series modelling,” arXiv
Our work contributes to the growing body of research com-                                   preprint arXiv:2403.10288, 2024.
                                                                                       [24] H. Inzirillo, “Clustering digital assets using path signatures: Application
bining classical mathematical techniques with modern deep                                   to portfolio construction,” arXiv preprint arXiv:2410.23297, 2024.
learning architectures. The consistent improvements achieved                           [25] R. Genet and H. Inzirillo, “Keras sig: Efficient path signature computa-
across different tasks and architectures demonstrate the po-                                tion on gpu in keras 3,” arXiv preprint arXiv:2501.08455, 2025.
tential of path signatures as a powerful tool for enhancing
sequential data processing in neural networks.
                              R EFERENCES
 [1] R. H. Shumway, D. S. Stoffer, and D. S. Stoffer, Time series analysis
     and its applications. Springer, 2000, vol. 3.
 [2] G. E. Box, G. M. Jenkins, G. C. Reinsel, and G. M. Ljung, Time series
     analysis: forecasting and control. John Wiley & Sons, 2015.
 [3] A. A. Markov, “Essai d’une recherche statistique sur le texte du roman
     “Eugene Onegin” illustrant la liaison des epreuve en chain (‘Example of
     a statistical investigation of the text of “Eugene Onegin" illustrating
     the dependence between samples in chain’),” Izvistia Imperatorskoi
     Akademii Nauk (Bulletin de l’Académie Impériale des Sciences de St.-
     Pétersbourg), vol. 7, pp. 153–162, 1913, english translation by Morris
     Halle, 1956.
 [4] Y. LeCun, Y. Bengio, and G. Hinton, “Deep learning,” nature, vol. 521,
     no. 7553, pp. 436–444, 2015.
 [5] L. Medsker and L. C. Jain, Recurrent neural networks: design and
     applications. CRC press, 1999.
 [6] B. Lim and S. Zohren, “Time-series forecasting with deep learning: a
     survey,” Philosophical Transactions of the Royal Society A, vol. 379, no.
     2194, p. 20200209, 2021.
 [7] R. Genet and H. Inzirillo, “Tkan: Temporal kolmogorov-arnold net-
     works,” arXiv preprint arXiv:2405.07344, 2024.
 [8] B. Lim, S. Ö. Arık, N. Loeff, and T. Pfister, “Temporal fusion transform-
     ers for interpretable multi-horizon time series forecasting,” International
     Journal of Forecasting, vol. 37, no. 4, pp. 1748–1764, 2021.
 [9] R. Genet and H. Inzirillo, “A temporal kolmogorov-arnold transformer
     for time series forecasting,” arXiv preprint arXiv:2406.02486, 2024.
[10] S. Hochreiter and J. Schmidhuber, “Long short-term memory,” Neural
     computation, vol. 9, no. 8, pp. 1735–1780, 1997.
[11] K. Cho, B. Van Merriënboer, C. Gulcehre, D. Bahdanau, F. Bougares,
     H. Schwenk, and Y. Bengio, “Learning phrase representations using
     rnn encoder-decoder for statistical machine translation,” arXiv preprint
     arXiv:1406.1078, 2014.




                                                                                   6