source: https://arxiv.org/pdf/1805.04750
fetched_utc: 2026-10-04T18:36:27Z
bytes_raw: 3042653

Multifractal analysis of financial markets

                                                                     Zhi-Qiang Jianga,b,1 , Wen-Jie Xiea,b,1 , Wei-Xing Zhoua,b,c,∗, Didier Sornetted,e
                                                            a Research Center for Econophysics, East China University of Science and Technology, Shanghai 200237, China
                                                        b Department of Finance, School of Business, East China University of Science and Technology, Shanghai 200237, China
                                                      c Department of Mathematics, School of Science, East China University of Science and Technology, Shanghai 200237, China
                                                                         d Department of Management, Technology and Economics, ETH Zurich, Zurich, Switzerland
                                                              e Swiss Finance Institute, c/o University of Geneva, 40 blvd. Du Pont d’Arve, CH 1211 Geneva 4, Switzerland
arXiv:1805.04750v1 [q-fin.ST] 12 May 2018




                                            Abstract
                                            Multifractality is ubiquitously observed in complex natural and socioeconomic systems. Multifractal analysis pro-
                                            vides powerful tools to understand the complex nonlinear nature of time series in diverse fields. Inspired by its
                                            striking analogy with hydrodynamic turbulence, from which the idea of multifractality originated, multifractal analy-
                                            sis of financial markets has bloomed, forming one of the main directions of econophysics. We review the multifractal
                                            analysis methods and multifractal models adopted in or invented for financial time series and their subtle proper-
                                            ties, which are applicable to time series in other disciplines. We survey the cumulating evidence for the presence of
                                            multifractality in financial time series in different markets and at different time periods and discuss the sources of
                                            multifractality. The usefulness of multifractal analysis in quantifying market inefficiency, in supporting risk manage-
                                            ment and in developing other applications is presented. We finally discuss open problems and further directions of
                                            multifractal analysis.
                                            Keywords: Econophysics, Multifractal analysis, Financial markets, Complex systems
                                            PACS: 89.65.Gh, 89.75.Da, 02.50.-r, 89.90.+n, 05.65.+b



                                            Contents

                                            1 Introduction                                                                                                                            5
                                              1.1 A very brief history of econophysics . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .                          5
                                              1.2 Stylized facts . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .                        6
                                              1.3 Benchmark econometric models . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .                              7
                                              1.4 Introduction to multifractality . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .                       9

                                            2 Multifractal analysis                                                                                                                  10
                                              2.1 Partition function approach (MF-PF) . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .                          10
                                                   2.1.1 Generalized dimensions and mass exponents . . . . . . . . . . . . . . . . . . . . . . . . . .                               10
                                                   2.1.2 Scaling behavior of partition functions . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .                         11
                                                   2.1.3 Direct determination of a multifractal spectrum . . . . . . . . . . . . . . . . . . . . . . . . .                           12
                                                   2.1.4 Inverse partition function and inversion formula . . . . . . . . . . . . . . . . . . . . . . . . .                          13
                                                   2.1.5 Ensemble averaging . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .                            16
                                              2.2 Structure function approach . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .                        16
                                                   2.2.1 Direct structure functions (MF-SF) . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .                            16
                                                   2.2.2 Multifractal fluctuation analysis (MF-FA) . . . . . . . . . . . . . . . . . . . . . . . . . . . .                           18
                                                   2.2.3 Inverse statistics and inverse structure functions . . . . . . . . . . . . . . . . . . . . . . . . .                        18

                                               ∗ Corresponding author.

                                                Email addresses: wxzhou@ecust.edu.cn (Wei-Xing Zhou ), dsornette@ethz.ch (Didier Sornette)
                                               1 These authors contribute equally.


                                            Preprint submitted to Physics Reports                                                                                           May 15, 2018
         2.2.4 Extended self-similarity . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .      20
   2.3   Wavelet transform approaches . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .      21
         2.3.1 Multifractal analysis based on wavelet transform (MF-WT) . . . . . . . . . . . . . . . . . . .          21
         2.3.2 Wavelet transform modulus maxima (WTMM) . . . . . . . . . . . . . . . . . . . . . . . . .               22
         2.3.3 Wavelet leader (MF-WL) . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .        23
   2.4   Detrended fluctuation approaches . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .    24
         2.4.1 General framework . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       24
         2.4.2 Multifractal detrended fluctuation analysis (MF-DFA) . . . . . . . . . . . . . . . . . . . . .          26
         2.4.3 Multifractal detrending moving average analysis (MF-DMA) . . . . . . . . . . . . . . . . . .            27
         2.4.4 Other detrending algorithms . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       28
   2.5   Other methods . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .   30
         2.5.1 Multiplier method . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       30
         2.5.2 Multifractal Hilbert-Huang spectral analysis . . . . . . . . . . . . . . . . . . . . . . . . . . .      31
         2.5.3 EMD-based multifractal methods . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .          32
         2.5.4 Multiscale multifractal analysis . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .      33
         2.5.5 Time-varying multifractal analysis . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .      33
         2.5.6 Phase space reconstruction . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .      33
         2.5.7 Asymmetric multifractal analysis . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .        34
         2.5.8 Multifractal diffusion entropy analysis . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .     35
         2.5.9 Symbolization presentation and Rényi dimensions . . . . . . . . . . . . . . . . . . . . . . .          36

3 Joint multifractal analysis                                                                                          36
  3.1 Joint multifractal analysis based on partition functions (MF-X-PF) . . . . . . . . . . . . . . . . . . .         36
        3.1.1 General formalism for arbitrary (p, q) pairs . . . . . . . . . . . . . . . . . . . . . . . . . . .       37
        3.1.2 Analytical results for binomial measures . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       38
        3.1.3 The case p = q . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       39
  3.2 Joint structure function analysis (MF-X-SF) . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .        40
        3.2.1 General formalism for arbitrary (p, q) pair . . . . . . . . . . . . . . . . . . . . . . . . . . . .      40
        3.2.2 The case p = q . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       41
  3.3 Multifractal wavelet coherence analysis (MF-WCA) . . . . . . . . . . . . . . . . . . . . . . . . . . .           42
        3.3.1 Cross wavelet transformation and wavelet coherence analysis . . . . . . . . . . . . . . . . .            42
        3.3.2 MF-X-WT . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .          42
        3.3.3 MF-X-WTMM . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .            43
        3.3.4 MF-X-WL . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .          44
  3.4 Multifractal detrended cross-correlation analysis (MF-DCCA) . . . . . . . . . . . . . . . . . . . . .            44
  3.5 Multifractal cross-correlation analysis (MF-CCA) . . . . . . . . . . . . . . . . . . . . . . . . . . . .         46
  3.6 Multifractal detrended partial cross-correlation analysis (MF-DPXA) . . . . . . . . . . . . . . . . . .          47

4 Multifractal models                                                                                                  48
  4.1 Multiplicative cascade models . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .        48
       4.1.1 Deterministic multinomial models . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .          48
       4.1.2 The p-model . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .         49
       4.1.3 Stochastic multinomial models: Discrete multiplier distribution . . . . . . . . . . . . . . . .           50
       4.1.4 Stochastic multinomial models: Continuous multiplier distribution . . . . . . . . . . . . . . .           52
  4.2 Multifractal model of asset returns (MMAR) . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .         53
       4.2.1 Basic MMAR model . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .            53
       4.2.2 Poisson MMAR model . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .            54
  4.3 Markov-switching multifractal (MSM) models . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .           55
       4.3.1 The framework of MSM models . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .             55
       4.3.2 Binomial MSM model . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .            56
       4.3.3 Lognormal MSM model . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .             56
       4.3.4 Other extensions . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .        57

                                                           2
   4.4   Multifractal random walk (MRW) . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       57
         4.4.1 The original model . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .     57
         4.4.2 Fractional MRW . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       59
         4.4.3 Skewed MRW . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .         59
   4.5   Exponentials of long memory processes . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .      59
         4.5.1 Alternative representation of MRW . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .        59
         4.5.2 Quasi-multifractal model . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .     60
         4.5.3 Self-excited multifractal model . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .    60
   4.6   Agent based models . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .   61
         4.6.1 Percolation models . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .     61
         4.6.2 Spin models . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .    61
         4.6.3 Empirical order-driven models . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .      61
         4.6.4 Other models . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .     62

5 Properties and important issues                                                                                     62
  5.1 Determination of multifractal quantities . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .      62
      5.1.1 Computational precision . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .         62
      5.1.2 What if N/s is not integer . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .        62
      5.1.3 Range of q and convergence of moments . . . . . . . . . . . . . . . . . . . . . . . . . . . .             62
      5.1.4 Determination of scaling range . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .        63
      5.1.5 Integrated moments and factorial moments . . . . . . . . . . . . . . . . . . . . . . . . . . .            65
      5.1.6 Assumed forms for τ(q) (or ζ(q)) and f (α) . . . . . . . . . . . . . . . . . . . . . . . . . . .          66
  5.2 Some important properties . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       67
      5.2.1 Discrete scale invariance and log-periodicity . . . . . . . . . . . . . . . . . . . . . . . . . .         67
      5.2.2 Translation invariance . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .        68
      5.2.3 Negative dimensions f (α) < 0 . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .         68
      5.2.4 Skewness of multifractal spectra . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .        68
  5.3 Superposed components and crossover phenomena . . . . . . . . . . . . . . . . . . . . . . . . . . .             69
      5.3.1 Superposition rule . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .        69
      5.3.2 Polynomial trends . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .         70
      5.3.3 Periodic trends . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       71
      5.3.4 Power-law trends . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .        72
      5.3.5 Additive noises . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       72
      5.3.6 Preprocessing time series with trends . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .         72
  5.4 Effects of nonlinearity and filters . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .   74
      5.4.1 Effects of nonlinearity . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       74
      5.4.2 Effects of filters . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .    74
  5.5 Performance of different methods . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .        75
      5.5.1 Mathematical models as reference . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .          75
      5.5.2 Performance measures . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .          75
      5.5.3 Length of time series (“finite size effects”) . . . . . . . . . . . . . . . . . . . . . . . . . . .       76
      5.5.4 Incomplete comparison of performance . . . . . . . . . . . . . . . . . . . . . . . . . . . . .            76
      5.5.5 Which method should be used? . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .            77

6 Empirical evidence of multifractal markets                                                                          78
  6.1 Asset returns and prices . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .    78
      6.1.1 Daily stock market indices . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .        79
      6.1.2 High-frequency stock market indices . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .           80
      6.1.3 Stock market sector indices . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .         80
      6.1.4 Individual stocks . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       81
      6.1.5 Equity futures . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .      81
      6.1.6 Foreign exchange rates . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .        81

                                                           3
         6.1.7 Commodities . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .          83
         6.1.8 Interest rates . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       84
         6.1.9 Illusionary multifractality . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .        84
   6.2   Volatilities . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .   84
         6.2.1 Stock markets . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .        84
         6.2.2 Foreign exchange rates . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .         85
         6.2.3 Commodities . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .          85
   6.3   Liquidity measures . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       85
         6.3.1 Trading volumes . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .          85
         6.3.2 Bid-ask spread . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .         86
         6.3.3 Price gaps on order books . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .          86
   6.4   Inter-event durations . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .      86
         6.4.1 Recurrence intervals . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .         86
         6.4.2 Intertrade durations . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       86
         6.4.3 Other microstructure variables . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .         87
   6.5   Two time series: MF-X . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .        87
         6.5.1 Return-return pairs . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .        87
         6.5.2 Volatility-volatility pairs . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .      88
         6.5.3 Price-volume pairs . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .         88

7 Sources of apparent multifractality                                                                                     89
  7.1 Spurious multifractality and finite-size effect . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       90
       7.1.1 Bifractality of fat-tailed time series . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .         90
       7.1.2 Spurious multifractality . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .           90
       7.1.3 Finite-size effect . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .         91
  7.2 Empirical investigation of different sources . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .          91
       7.2.1 Impacts of linear and nonlinear correlations (Shuffle) . . . . . . . . . . . . . . . . . . . . . .           91
       7.2.2 Impact of nonlinear correlations (Surrogate) . . . . . . . . . . . . . . . . . . . . . . . . . . .           92
       7.2.3 Impact of broad distributions . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .          94
       7.2.4 Impact of extreme values . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .           95
  7.3 Components of apparent multifractality . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .            96
  7.4 Statistical tests . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .       98
       7.4.1 Test based on parameterized multifractal models . . . . . . . . . . . . . . . . . . . . . . . .              98
       7.4.2 Tests based on f (α) . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .         98
       7.4.3 Tests based on τ(q) . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .          99

8 Applications                                                                                                      100
  8.1 Measures of multifractality strength . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 100
       8.1.1 Measures based on multifractal spectrum . . . . . . . . . . . . . . . . . . . . . . . . . . . . 100
       8.1.2 Measures based on generalized Hurst exponents . . . . . . . . . . . . . . . . . . . . . . . . . 100
       8.1.3 Intermittency . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 101
       8.1.4 Relationship between different measures . . . . . . . . . . . . . . . . . . . . . . . . . . . . 102
  8.2 Measuring market inefficiency . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 102
       8.2.1 Market inefficiency index based on fractality measures . . . . . . . . . . . . . . . . . . . . . 102
       8.2.2 Ranking market efficiency . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 103
       8.2.3 Changing efficiency at different periods . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 104
       8.2.4 Time-varying efficiency . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 105
  8.3 Multifractal volatility . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 105
       8.3.1 Definitions of multifractal volatility . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 105
       8.3.2 Volatility forecasting . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 106
       8.3.3 Value-at-Risk forecasting . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 107
  8.4 Complex networks . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 108

                                                            4
         8.4.1 Multiscale cross-correlation coefficients . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 108
         8.4.2 Multiscale DCCA networks . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 109
         8.4.3 Multifractality-based networks . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 110
         8.4.4 Time series of network variables . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 111
         8.4.5 Eigenportfolios . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 111
         8.4.6 Correlation matrix structure and multifractality . . . . . . . . . . . . . . . . . . . . . . . . . 111
   8.5   Other applications . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 111
         8.5.1 Calibration of agent-based models . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 111
         8.5.2 Detection of outliers . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 112
         8.5.3 Trading strategy . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 112

9 Perspectives                                                                                                       112

Acknowledgments                                                                                                      113

References                                                                                                           113


1. Introduction

1.1. A very brief history of econophysics
    Physicists have long being interested in financial markets both practically and academically. On the investment
side, Sir Isaac Newton, one of the greatest scientists in history, is reported to have invested in the South Sea Company
stock in the 1720s and to have lost 20000 pounds (about 3 million US dollars in today’s money) as a result of the
burst of the infamous South Sea bubble. His speculative endeavors made for the famous quote that “I can calculate
the motions of heavenly bodies, but not the madness of people.” In 1991, Doyne Farmer co-founded the Prediction
Company together with Norman Packard and James McGill to design automatic statistical arbitrage strategies. Pre-
diction Company was quite successful and was sold to UBS in 2006 and was then re-sold to Millenium Management
in 2013. In 1994, Jean-Philippe Bouchaud and Didier Sornette founded together a research company called Science
& Finance, which was merged with Capital Fund Management in 2000. In the mean time, Sornette left Science &
Finance and Bouchaud became Chairman and Chief Scientist of Capital Fund Management. Many other examples
abound of physicists flirting with Wall Street, Emmanuel Derman being a role model [1].
    Intellectually, there are deep relationships (as well as crucial differences) between physics and finance [2, 3] that
have inspired generations of physicists as well as economists. In general, physicists apprehend financial markets as
complex systems and, as such, they conducted numerous scientific investigations. In the 1930s, Ettore Majorana
wrote a paper entitled “The value of statistical laws in physics and social sciences”, which was published by Giovanni
Gentile Jr in 1942 after his disappearance [4], and its English translation by Mantegna was presented in the journal of
Quantitative Finance in 2005 [5]. In the 1960s, Benoit B. Mandelbrot pioneered an empirical approach, which would
be later viewed as a precursor of econophysics, in a series of seminal works of income distributions [6–10], price
variation distributions of speculative assets [11, 12], and long-term correlations in financial and economic time series
using the rescaled range (R/S) analysis [13, 14].
    The current flourishing econophysics has multiple seeds that date from the 1990s. One can identify four main
directions of research that are among the most actives in the field of econophysics in the past two decades. Following
Mandelbrot’s ideas, the first stream of studies focused on the distribution of financial returns, as well as conceptual
formulations. In 1991, Rosario Mantegna studied the Lévy-walk-like superdiffusive behavior of indices of the Milan
stock exchange [15], and with Gene Stanley the scaling behavior of the S&P 500 index in 1995 [16, 17]. In 1996,
Ghashghaie et al. studied the evolving return distributions at different timescales and the multifractal behavior in the
structure function of the US dollar - German mark exchange rates [18]. In 1998, Laherrère and Sornette proposed
stretched exponential distributions for time series in nature and economy as a complement to the often used power-law
distributions [19], while Gopikrishnan et al. observed the inverse cubic law [20–22]. We note that, compared with
power laws, stretched exponentials [23–25] and lognormals [26] are competing alternatives for return distributions
that share hard-to-distinguish tail properties.

                                                           5
    A second stream was devoted to the macroscopic modelling of financial markets. In 1994, Bouchaud and Sornette
generalized the Black-Scholes option pricing problem for a large class of stochastic processes [27] using the functional
integration and derivative approach well-known in field theory. In 1996, Sornette et al. proposed the log-periodic
power-law singularity (LPPLS) model to study financial crashes modelled as critical events [28],. This approach was
soon exploited further by Sornette and Johansen [29, 30], Feigenbaum and Freund [31, 32], Vandewalle et al. [33, 34],
Drożdż et al. [35], Sornette and Zhou [36–39] and many others. Identification of financial bubbles and forecasting of
market turning points advanced successfully in diverse markets [40–42].
    The third stream is concerned with computational econophysics. In 1992, Takayasu et al. [43] developed the first
agent-based model in econophysics with the goal to provide an alternative to dynamical stochastic general equilibrium
(DSGE) models by incorporating agents’ heterogeneous characteristics and the role of extended networks. In 1994,
Palmer et al. designed an artificial stock market model composed of adaptive agents with bounded rationality [44]. In
1996, Bak et al. introduced a multi-agent model based on diffusion and annihilation [45]. In 1997, Challet and Zhang
introduced the minority game [46]. In 1999, Lux and Marchesi proposed an agent-based model with heterogenous
chartists and fundamentalists [47]. In general, there are three basic ingredients for the price formation process in
financial markets, including global news that influence more or less all market participants, mutual imitations among
traders, and idiosyncratic preferences of traders [48, 49]. Overconfidence of traders in interpreting the predictive
power of global news, which mis-attributes the success of news to predict returns to traders’ own stock picking
ability and leads to positive feedbacks and herding behavior, plays a crucial role in generating the main stylized facts
[2, 48, 49], such as the fat-tailed distribution of returns, the absence of linear correlations in returns, the long memory
in volatilities, and the multifractal nature of financial time series.
    A four stream of investigations has been involved in the more recent use of the emerging field of network theory
applied to finance. In 1999, Mantegna studied the hierarchical structure of the US stock market from the angle of
minimal spanning trees [50]. Laloux et al. and Plerou et al. applied random matrix theory to stock return correlation
matrices to identify the information contents hidden in eigenvalues and their corresponding eigenvectors [51–53].

1.2. Stylized facts
    Financial markets are complex adaptive systems, in which universal and non-universal statistical laws emerge at
the macroscopic level from the microscopic behavior of heterogeneous traders through reactions to external stimuli in
a self-organized manner [40, 41, 54–59]. These laws can be explored from the rich dataset of financial stock market
price time series. As an illustration, the left pannel of Fig. 1 shows the daily price trajectories I(t) of two stock market
indices, the Dow Jones Industrial Average (DJIA) index from 26 May 1896 to 29 December 2017 and the Shanghai
Stock Exchange Composite (SSEC) index from 19 December 1990 to 29 December 2017. These two stock markets
are representative of developed and emerging markets that are of great interest. The logarithmic return of I(t) over a
time interval ∆t is defined by
                                                 r∆t (t) = ln I(t) − ln I(t − ∆t).                                       (1)
The middle panel of Fig. 1 illustrates the daily return time series r(t) with ∆t = 1 day and the right panel shows the
corresponding volatility time series. Here, the volatility for a given day is defined as the square root of the sum of
the squares of intraday returns of that day, where the intraday time scale needs to be sufficiently short (say 1 minute)
to provide a good convergence of the volatility estimator. Clear bursty behaviors can be observed in the return time
series, which are associated with volatility clustering.
     Numerous statistical regularities or stylized facts have been reported in different financial markets [60–63]. We
first recall three main stylized facts, which are universal properties of financial markets. The first stylized fact is the
fat-tailed distributions of financial returns. The form of the distribution of asset price fluctuations plays crucial roles in
asset pricing and risk management [25, 54, 55]. Early empirical and theoretical works argued that asset prices follow
geometric Brownian motions [64, 65], which is the main assumption of the Black-Scholes option pricing model [66].
In the 1960s, Mandelbrot suggested that incomes and speculative price returns follow the Pareto-Lévy distribution,
which has power-law tails
                                                      Pr(|r|) ∼ |r|−γ−1 ,                                                  (2)
whose exponents 1 < γ < 2 claimed to be in the domain of attraction of stable Lévy laws [6, 7, 9–11]. Recall that
Lévy laws generalise the Gaussian distribution, and their family exhausts all possible distributions that are stable
under convolution, with no or only weak dependence between the random variables.
                                                              6
 4.5                                                                                                                                                  0.3

  4                                                                         0.1
                                                                                                                                                     0.25
                                                                          0.05
 3.5
                                                                             0                                                                        0.2
  3
                                                                          -0.05
                                                                                                                                                     0.15
 2.5                                                                       -0.1

                                                                          -0.15                                                                       0.1
  2
                                                                           -0.2
 1.5                                                                                                                                                 0.05
                                                                          -0.25
  1                                                                        -0.3                                                                        0
  1890 1900 1910 1920 1930 1940 1950 1960 1970 1980 1990 2000 2010 2020      1890 1900 1910 1920 1930 1940 1950 1960 1970 1980 1990 2000 2010 2020     1890 1900 1910 1920 1930 1940 1950 1960 1970 1980 1990 2000 2010 2020

  4                                                                       0.8                                                                        0.8

                                                                                                                                                     0.7
                                                                          0.6
 3.5                                                                                                                                                 0.6

                                                                                                                                                     0.5
                                                                          0.4
  3                                                                                                                                                  0.4
                                                                          0.2                                                                        0.3

 2.5                                                                                                                                                 0.2
                                                                            0
                                                                                                                                                     0.1

  2                                                                       -0.2                                                                        0
  1990      1995       2000       2005       2010       2015       2020     1990      1995       2000        2005       2010       2015       2020    1990       1995       2000       2005       2010       2015       2020




Figure 1: Time series of daily closing prices (left), daily returns (middle) and daily volatilities (right) of two stock market indices. The upper panel
is for the Dow Jones Industrial Average index and the lower panel is for the Shanghai Stock Exchange Composite index.


    The possibility that financial returns might be distributed according to Lévy laws rather than being Gaussian
immediately attracted the interest of notable financial economists, such as Fama [67], Fama and Roll [68], Samuelson
[69], Sargent [70], and others. But there was also immediate resistance to abandon the statistical theory that exists
for the normal case, which was non-existent for the other members of the Lévy laws, with the like of Cootner [71]
and Granger and Orr [72] opposing strong arguments. Further in-depth studies concluded to the error of Mandelbrot,
in the sense that, while the distributions of returns are fat-tailed, they are not so heavy as to be described by Lévy
laws: more and more statistical tests brought increasing and unavoidable evidence that the variance of the return is
not infinite (and thus the exponent γ is larger than 2), thus irremediably excluding the heavy tail regime of Lévy laws
with tail exponent less than 2 [73–76]. The tools based on variance and covariance could still be used after all. This
led to a lull in the interest of fat-tailed distributions, which was interrupted by the re-discovery by econophysicists in
the early 1990s [15–17].
    More recent empirical investigations with more data converge to γ ≈ 3 (or more prudently that 2 < γ < 4) [20–
22]. Further empirical investigations have been conducted on financial returns at different time scales ∆t and reported
that distributions vary from exponential to stretched exponential to power law [19, 77–94]. These observations are
in agreement with the fact that the fat-tailed nature of the distributions of returns at small scale with γ > 2 implies
that the domain of attraction at large scales is the Gaussian distribution. One should thus observe and we do observe
a progressive transition from a power law like regime at small time scales to a Gaussian regime at large scales [18].
Note that the stretched exponential distribution serves as a convenient bridge between exponential and power-law
distributions [19, 95]. In fact, the power law family of distributions can be shown to be asymptotically nested in
the stretched exponential family, the later converging to the former in the limit of vanishing stretched exponential
exponent [23–25]. This apparently esoteric property is very useful practically as it provides the robust Wilks test to
compare power laws and stretched exponentials for any data set of interest.
    As illustrations of the above, the left column of Fig. 2 shows the empirical distributions of daily returns of the
DJIA and SSEC indices. There are evident fat tails and outliers, compared with the inverted parabola shape that
would be expected under the Gaussian hypothesis.
    Two other main stylized facts are the absence of long memory in returns and the presence of long memory in
volatility, as shown respectively in the middle and right panels of Fig. 2. Quantitatively, performing detrended fluctu-
ation analysis or detrending moving average analysis of the return and volatility time series allows one to obtain the
corresponding Hurst exponents.

1.3. Benchmark econometric models
     In econometric finance, there are several cornerstone models, such as the autoregressive conditional heteroskedas-
ticity (ARCH) model [96], the generalized autorregressive conditional heteroskedasticity (GARCH) model [97], the


                                                                                                           7
   102                                                                                                          1
                                                      0.8                                                    0.8
                                                      0.6
                                                                                                             0.6
   100                                                0.4
                                                                                                             0.4
                                                      0.2
                                                        0                                                    0.2
        -2                                           -0.2                                                       0
   10
        -0.3   -0.2   -0.1     0      0.1     0.2           0      5          10        15          20              0       5            10    15   20

   102                                                                                                          1
                                                      0.8                                                    0.8
                                                      0.6
                                                                                                             0.6
   100                                                0.4
                                                                                                             0.4
                                                      0.2
                                                        0                                                    0.2

   10-2                                              -0.2                                                       0
      -0.2      0      0.2    0.4     0.6     0.8           0      5          10        15          20              0       5            10    15   20


Figure 2: Three main stylized facts: Fat-tailed distribution of returns (left), absence of autocorrelation of returns (middle), and long-range correla-
tions of volatilities (right). The upper panel is for DJIA and the lower panel is for SSEC.


exponential GARCH (EGARCH) model [98], the integrated GARCH (IGARCH) model [99], the fractionally in-
tegrated generalized autoregressive conditional heteroskedasticity (FIGARCH) model [100], and the autoregressive
fractionally integrated moving average (ARFIMA) model [101, 102].
    An autoregressive model of order p, AR(p), is defined as
                                                                       p
                                                                       X
                                                        r(t) = a0 +          ak r(t − k) + ǫt ,                                                     (3)
                                                                       k=1

where a1 , · · · , a p are the parameters of the model, a0 is a constant, and ǫt is white noise. To model a financial time
series using an ARCH process [96], the error term ǫt is split into a stochastic piece zt and a time-dependent standard
deviation σt such that
                                                          ǫt = σt zt .                                                  (4)
The random variable zt is a strong white noise process. The series σ2t is modelled by
                                                                                                  q
                                                                                                  X
                                            σ2t = α0 + α1 ǫt−1
                                                           2                 2
                                                               + · · · + αq ǫt−q = α0 +                     2
                                                                                                        αi ǫt−i ,                                   (5)
                                                                                                  i=1

where α0 > 0 and αi ≥ 0 for i > 0.
    Considering a regression with coefficient b between a variable xt and yt , the GARCH(p, q) model of the residuals
is given by [97]
                                                    yt = bxt + ǫt
                                                                 ǫt |ψt ∼ N(0, σ2t )

                                                                                                         q
                                                                                                         X                  p
                                                                                                                            X
                      σ2t = ω + α1 ǫt−1
                                    2                 2
                                        + · · · + αq ǫt−q + β1 σ2t−1 + · · · + β p σ2t−p = ω +                      2
                                                                                                                αi ǫt−i +         βi σ2t−i ,        (6)
                                                                                                          i=1               i=1

where p is the order of the GARCH terms σ2 and q is the order of the ARCH terms ǫ 2 . In finance, one usually applied
the GARCH model to the return time series formulated as (4) with σ given by (6).

                                                                          8
    In the ARCH, GARCH and EGARCH models, the autocorrelation of volatility decays at exponential rates. In
contrast, the volatility of the integrated models has long memory. Empirical analyses show that GARCH-type models
without long memory in volatility can hardly capture the multifractal nature in financial time series, while other
models with long memory component can capture partly the apparent multifractality, which is however spurious by
definition of the integrated models [103–112]. Therefore, benchmark economic models fail to capture an important
dimension of market complexity, namely the multifractal nature of financial market [113, 114].

1.4. Introduction to multifractality
    Multifractality has been observed in many diverse complex systems [115–121], including financial markets [113].
The term “multifractal” was coined by Frisch and Parisi in 1983 [122], as confirmed by Benoit B. Mandelbrot [123],
who is the well respected Father of Fractals [124]. The concept of multifractality can be traced back to Novikov
[125] and Mandelbrot [126, 127] in their study of turbulence in fluid mechanics. On the other hand, two groups
led by Grassberger and Procaccia generalized the fractal dimension, the information dimension and the correlation
dimension into a unified expression of generalized dimensions through the Rényi entropy [128–130], with the initial
aim of describing strange attractors in nonlinear dynamics [131]. Halsey et al. also made seminal contributions in the
early development of multifractal theories, with applications to fractal growth processes [132].
    There are two equivalent descriptions of multifractals, i.e., via the function τ(q) or the function f (α), where q is the
order of certain moments, τ(q) is the mass exponent function, α is the singularity strength, and f (α) is the singularity
spectrum. These two representations are related through the Legendre transform [122, 132] such that

                                                       α = dτ(q)/dq                                                     (7a)

and
                                                     f (α) = qα − τ(q).                                                 (7b)
 Concerning the τ(q) representation, there are two additional equivalent functions Dq and H(q). The Dq function
presents the generalized dimensions that are determined by

                                                                τ(q′ )
                                                    Dq = lim            ,                                                (8)
                                                          q →q (q′ − 1)
                                                          ′



while H(q) is defined by
                                                               τ(q′ ) + 1
                                                  H(q) = lim              ,                                              (9)
                                                          ′
                                                          q →q    q′
and corresponds to the generalized Hurst exponents. The detailed meaning of these quantities and there relations will
be made clear later.
    In the study of turbulence, there are two classical methods for the analysis of multifractals, i.e., the structure
function approach and the partition function approach [122, 125–127, 133–136]. Due to the striking similarities
between turbulence and financial markets, though the analogy has its limitations [137], the multifractal nature of
financial time series has attracted much interest [17, 18]. The structure function approach dominated in the first
wave of multifractal analysis in econophysics [138]. Since the seminal work of Kantelhardt et al. in 2002 [139], the
multifractal detrended fluctuation analysis soon became the dominant method not only for financial time series but
also for other time series. In 2008, Podobnik and Stanley introduced the detrended cross-correlation analysis for non-
stationary time series [140], which was extended by one of us (Wei-Xing Zhou) to analyze multifractal time series
[141]. These milestone works triggered the third wave of simultaneous multifractal analysis of two time series and
the invention of many variant types of multifractal analyses.
    In financial markets, risk is a central concept in all financial activities. Large financial fluctuations, especially
finance “tsunamis” such as the one that broke out in 2008 [42], usually cause tremendous economic distress and are
followed by vigorous changes in risk perception and regulations [40, 41]. Identifying, measuring and forecasting
financial risks are of great theoretical and practical significance in risk management. Econophysicists have shown that
multifractal analysis provides an alternative way in studying market risks. Indeed, large singularity strengths qualify
the behavior of small fluctuations, while small singularity strengths characterize large fluctuations. Therefore, quite

                                                             9
a few efforts have been made to apply multifractal analysis to quantifying market inefficiency, measuring financial
volatility, and so on.
    This review provides an extensive survey of the multifractal analysis of financial time series. We start with different
methods of multifractal analysis for univariate and multivariate time series in Section 2 and Section 3. We review also
the methods that were invented in other fields, because they have potential application value in econophysics. We
discuss important mathematical and econophysical models in Section 4 that can deepen our understanding of the
multifractal nature of financial markets. Important properties and subtle issues associated with the algorithms used in
empirical multifractal studies are discussed in Section 5, many of which are often overlooked by researchers leading
to unreliable results. In Section 6, we give an extensive survey of the literature on empirical multifractal analysis
of financial time series, which overall confirms the presence of multifractality in financial markets. We raise in
Section 7 the important issue of apparent and effective multifractality and discuss different sources causing apparent
multifractality. Different applications of the multifractal nature of financial time series are reviewed in Section 8. We
discuss open problems and provide perspectives for future research in Section 9.
    Although this review focuses on the multifractal analysis of financial markets, most of its contents are suitable for
multifractal time series analysis in all other fields. Moreover, a large part of this review can be usefully read to inspire
multifractal analyses of measures on surfaces and in higher dimensional spaces.

2. Multifractal analysis

2.1. Partition function approach (MF-PF)
2.1.1. Generalized dimensions and mass exponents
                                                                                     ′              ′
R Consider a measure m embedded in a geometric support F , whose density is ṁ(t ) at position t . By definition,
           ′   ′                                          ′        ′    ′
 t′ ∈F
       ṁ(t )dt = 1. The measure in the neighbourhood of t is ṁ(t )dt . Using the idea of the classic box-counting
method [124], we cover the geometric support F using boxes of size s. The integrated measure m(s, t) in the tth box
B(s, t) is                                             Z
                                             m(s, t) =       ṁ(t′ )dt′ ,                                      (10)
                                                             t′ ∈B(s,t)
        P
where    t ṁ(s, t) = 1 for any s. The fractal dimension of F can be determined as follow
                                                                       P                0
                                                                  ln      t [m(s, t)]
                                             D f := D0 = lim                                ,                          (11)
                                                            s→0           ln 1/s
                 P
where the term t [m(s, t)]0 gives the number of non-empty boxes needed to cover the support F . Note that fractal
dimension is also called similarity dimension or capacity dimension. It is obvious that, if there is no measure dis-
tributed in a box, the box should not be counted. In most cases in handling financial time series, we have D0 = 1. In
                                             P
the empirical determination of D0 , we plot t [m(s, t)]0 against s in log-log scales and the slope of the linear part in a
proper scaling range is regarded as its estimate.
    The information entropy or Shannon entropy of the measure can be defined as [142, 143]
                                                      X
                                             I(s) = −    m(s, t) ln[m(s, t)],                                        (12)
                                                        t

and one can define the information dimension D1 as follows
                                                                  I(s)
                                                    σ = lim              ,                                             (13)
                                                            s→0 ln (1/s)

which was introduced by Balatoni and Rényi in 1956 [144, 145] and used to study strange attractors [146, 147].
   A third index used to characterize the measure is the correlation dimension [148, 149]. The correlation dimension




                                                              10
was originally introduced to study the scaling behavior of the correlation integral of time series of length N:

                                            1 X                             X
                                                    N
                                 C(s) = lim 2        H(s − |~xi − ~x j |) ≈   [m(s, t)]2 ,                           (14)
                                        N→∞ N
                                              i, j=1                        t

where H(x) is the Heaviside function. The correlation dimension is defined as follows
                                                        P
                                                      ln t [m(s, t)]2
                                             ν = lim                  .                                              (15)
                                                  s→0    ln 1/s
    These three dimensions D f , σ and ν can be unified into one framework of generalized dimensions [128–130]. We
define the q-order Rényi entropy as [150, 151]
                                                          1     X
                                           Iq (s) = lim       ln [m(s, t] p ,                                        (16)
                                                    p→q 1 − p
                                                                t

and the generalized dimension as [152]
                                                            
                                                            
                                                            
                                                                   1 ln χ(p, s)
                                                             lim                  ,             q,1
                            Iq (s)             1 ln χ(p, s) 
                                                            
                                                             s→0 p − 1 ln s
                  Dq = lim         = lim lim               =
                                                                 P                                                  (17)
                       s→0 ln(1/s)   s→0 p→q p − 1  ln s    
                                                            
                                                                   t m(s, t) ln[m(s, t)]
                                                            
                                                             lim                         ,      q=1
                                                              s→0          ln s
where                                                        X
                                                 χ(q, s) =        [m(s, t)]q                                         (18)
                                                              t

is the q-order partition function of the measure. It is easy to verify that D0 = D f , D1 = σ and D2 = ν. In practice, we
can compute Dq according to Eq. (17). For a given q, we plot Iq (s) against ln s for various box sizes s and perform
linear regression in a proper scaling range to obtain the slope Dq .
     We can rewrite Eq. (17) as follows
                                                                  ln χ(q, s)
                                               (q − 1)Dq = lim                                                       (19)
                                                              s→0     ln s
or
                                                      χ(q, s) ∼ sτ(q) ,                                              (20)
where
                                                   τ(q) = (q − 1)Dq .                                                (21)
In practice, we can compute τ(q) according to Eq. (20). For a given q, we can compute χ(q, s) for various box sizes
s and perform a linear regression of ln χ(q, s) against ln s in a proper scaling range to obtain τ(q). Alternatively, τ(q)
can be transformed from Dq using Eq. (21).
    Recently, Xiong and Shang proposed a variance-weighted partition function approach and established the relation-
ship between the corresponding multifractal functions [153]. Numerical simulations show that the variance-weighted
partition function approach performs comparatively as the standard partition function approach.

2.1.2. Scaling behavior of partition functions
    Based on the box-counting idea, the geometric support is partitioned into non-overlapping boxes of size s. The
local singularity strength α in the tth box B(s, t) is defined according to the following relationships [132]:

                                                        m(s, t) ∼ sα ,                                               (22)




                                                             11
which may differ for different boxes. Let N s (α) denote the number of boxes in which the singularity strengths are
within [α, α + dα]. Hence, the fractal dimension of the set is determined according to
                                                                        ′
                                                N s (α) = ρ(α′ )s− f (α ) dα′ ,                                        (23)

where ρ(α) is the density of the singularity strength and f (α) is the fractal dimension of the boxes under consideration
[132], which is usually called multifractal spectrum or singularity spectrum. One can directly obtain α from Eq. (22)
and f (α) from Eq. (23) using local and pointwise singularity methods [154–156].
   Inserting Eq. (22) into the partition function (18) and rewriting the sum into an integral over α, we have
                                          Z                             Z
                                                 ′             ′                   ′      ′
                                χ(q, s) =     sqα ρ(α′ )s− f (α ) dα′ =   ρ(α′ )sqα − f (α ) dα′ .                   (24)

Assume that ρ(α) is nonzero and non-singular. It therefore contributes a constant proportional factor to the leading
behavior of the integral. Because s is small, according to the method of steepest descent, the integral will be dominated
by the value of α(q) that makes the power qα′ − f (α′ ) smallest. We thus replace α′ by α(q), which is defined by the
extremal condition:
                                                            
                                              d qα′ − f (α′ ) /dα′ α′ =α(q) = 0                                     (25a)
and
                                                          
                                           d2 qα′ − f (α′ ) /dα′2 α′ =α(q) > 0.                                       (25b)
Then, Eq. (24) becomes
                                                    χ(q, s) ∼ sqα− f (α) .                                             (26)
It follows from Eq. (25) that
                                                 f ′ (α) = d f (α)/dα = q                                             (27a)
and
                                                        f ′′ (α) < 0,                                                 (27b)
which means that the multifractal spectrum f (α) is a concave function and its slope at point (α(q), f (α(q)) is q.
   Comparing Eq. (20) and Eq. (26), we have

                                                    τ(q) = qα − f (α).                                                 (28)

Taking the derivative of Eq. (28) with respect to q, we have
                                          dτ(q)       dα d f (α) dα
                                                = α+q    −          = α.                                               (29)
                                           dq         dq   dα dq
Rewriting Eq. (28) and Eq. (29), we have
                                                      α = dτ(q)/dq                                                    (30a)
and
                                                    f (α) = qα − τ(q) .                                               (30b)
This shows that f (α) is the Legendre transform of τ(q) [122, 132]. Therefore, after obtaining τ(q), we can determine
numerically α(q) using Eq. (30a) and f (α) using Eq. (30b). To qualify a multifractal measure, we can use either (q, τ)
or (α, f ), which are equivalent.

2.1.3. Direct determination of a multifractal spectrum
    From the canonical perspective, we can obtain the f (α) function directly [157, 158]. We can define the canonical
measures
                                                             [m(s, t)]q
                                               µ(q, s, t) = P             q
                                                                            .                                    (31)
                                                              t [m(s, t)]



                                                             12
The singularity strength α(q) and its spectrum f (q) can be computed by linear regressions in log-log scales using the
following equations:                                   P
                                                          µ(q, s, t) ln[m(s, t)]
                                           α(q) = lim t                          ,                                  (32a)
                                                   s→0           ln s
and                                                         P                          
                                                               µ(q, s, t) ln µ(q, s, t)
                                    f (q) , f (α(q)) = lim t                              .                         (32b)
                                                        s→0             ln s
                                P
 To compute α(q), we can plot t µ(q, s, t) ln [m(s, t)] against ln s, determine the scaling range and obtain the slope by
linear regression. The f (q) function can be determined similarly based on Eq. (32b). Combining Eqs. (20) and (32),
we can verify Eq. (28) easily. The mass exponent function τ(q) can be obtained by using Eq. (28).

2.1.4. Inverse partition function and inversion formula
    For financial volatilities, we can further define the inverse partition function [159]. We start with an illustration of
the partition function approach using a high-frequency volatility time series.
    Denote {I(t) : t = 1, · · · , T } the price time series of a financial asset. The logarithmic return r(t) at the finest time
resolution is calculated by
                                                    r(t) = ln I(t) − ln I(t − 1),                                           (33)
where t = 2, · · · , T . The absolute return is utilized as a proxy for volatility according to

                                                                                                                                                   v(t) = |r(t)|.                                                                                                                                     (34)

Figure 3(a) illustrates a segment of the 1-min volatility time series of the S&P 500 index, in which, according to the
partition function method, the original volatility time series is divided into N boxes with identical size s = T/N. The
box sizes are chosen such that the number of boxes of each size is an integer to cover the whole time series.
                                      −3
                          x 10
                     3                                                                                                                                                                                                             1
                                                                                                                        1
                                                                                                                                                                                                        µ5                                                                                                µ
                    2.5
                                                                                                                                                                                                  s                               0.8    µ = 0.2                                                s5
                                                                                                                       0.8        s = 200
                                                                                                                                                                                                                                                                                          µ
                     2                                                                                                                                                                    µ4                                                                                        s4
                                                                                                                       0.6                                                                                                        0.6
                                                                                                                                                                                    s
                                                                                                                                                                                                                 U (t)
  v(t)




                                                                                                    U (t)




                    1.5
                                                                                                                                                                            µ3                                                                                                  µ
                                                                                                                       0.4
                                                                                                                                                                  s                                                               0.4
                                                                                                                                                                                                                                                                   s3
                     1                                                                                                                                   µ2                                                                                                 µ
                                                                                                                       0.2
                                                                                                                                                   s                                                                              0.2
                                                                                                                                                                                                                                                       s2
                    0.5
                                                                                                                                         µ1                                                                                                     µ
                     0                                                                                                  0           s                                                                                              0
                                                                                                                                                                                                                                          s1
                      1                    200       400           600       800           1000                          1              200            400                600           800           1000                          1           200         400           600        800             1000
                                                               t                                                                                                  t                                                                                               t
                                                                                                                         2
                         2                                                                                             10                                                                                                          10
                    10


                                                                                                                         −2
                                                                                                                                                                                                                                    6
                         −1                                                                                            10
                    10
                                                                                                    χ† (µ, p)1/(p−1)
  χ(s, q)1/(q −1)




                                                                                                                                                                                                                 τ (q), τ † (p)




                                                                                                                                                                                                                                    2
                         −4                                                                                              −6
                    10                                                                                                 10
                                                                                                                                                                                                                                   −2
                                                                                       q = −3                                                                                                     p = −3
                         −7                                                            q = −1                          10
                                                                                                                         −10                                                                      p = −1
                    10                                                                                                                                                                            p=0                                                                                    τ † (p)
                                                                                       q=0                                                                                                                                         −6                                                    −τ [−1] (−p)
                                                                                       q=2                                                                                                        p=2
                                                                                       q=4                                                                                                        p=4                                                                                    τ(q)
                                                                                       q=6                               −14
                                                                                                                                                                                                  p=6                                                                                    −τ †[−1] (−q )
                         −10                                                                                           10
                    10            1              2         3             4         5            6                              −3             −2             −1                 0             1              2                    −10
                             10             10        10            10        10            10                               10          10             10                  10            10             10                         −6     −4         −2    0         2         4    6         8          10
                                                               s                                                                                                      µ                                                                                           p, q

Figure 3: (color online) Multifractal analysis of high-frequency financial volatility based on the partition function approach and the inverse partition
function approach. The time series contains about 1.7 million data points of the S&P 500’s 1-min volatility from 1 January 1982 to 31 December
1999. (a) A segment of volatility time series {v(t) : t = 1 : 1000}. (b) Cumulative volatility measure U(t) showing the determination of µ for a fixed
scale s. (c) Cumulative volatility U(t) showing the determination of sk for a fixed measure ∆v. (d) Dependence of [χ(s, q)]1/q−1 as a function of
box size s for q = −3, q = −1, q = 0, q = 4, and q = 6. The curves have been translated vertically by a factor of 0.001, 0.01, 0.1, 10, and 100 in
turn for better visibility. The solid lines are power-law fits in the scaling range. (e) Dependence of [χ† (µ, p)]1/p−1 on the thresholds µ. The curves
have been translated vertically for clarity. The solid lines are the best fits to the data. (f) Testing the inversion formula in financial volatility.


                                                                                                                                                             13
   We define the continuous volatility measure u(t′ ) for any t′ ∈ (t − 1, t] by
                                                                  v(t)
                                                       u(t′ ) = PT        ,                                            (35)
                                                                 t=1 v(t)

where t = 1, · · · , T . The cumulative function of the volatility measure is obtained as
                                                            Z t
                                                     U(t) =      u(t′ )dt′ .                                           (36)
                                                                  0

The function U(t) of v(t) in Fig. 3(a) is presented in Fig. 3(b). The measure in each box of size s is determined by

                                               µn (s) = U(ns) − U(ns − s),                                             (37)

which is also illustrated in Fig. 3(b). Usually, one computes the measure in a discrete way,
                                                                   X
                                                                   ns
                                                     µn (s) =                u(t),                                     (38)
                                                                t=(n−1)s+1

in which T/s must be an integer to avoid edge effects (see Section 5.1.2 for more information). When the continuous
measure u(t) is used, more choices for s values are possible as N can be any integer.
    For a given order q, the direct partition function χq (s) can be estimated by using

                                                                X
                                                                N
                                                     χq (s) =          [µn (s)]q .                                     (39)
                                                                 n=1

In Fig. 3(d), we plot [χq (s)]1/q−1 as a function of s for different q’s. The scaling exponent function τ(q) can be obtained
through power-law regressions to the data points in the scaling range, which spans about three orders of magnitude.
We find from Fig. 3(f) that τ(q) is a nonlinear function of q, confirming the presence of multifractality in the volatility
measure.
     We now turn to investigate the inverse partition function. For each threshold µ, a sequence of exit times {s j (µ) :
 j = 1, · · · , J} can be determined successively by

                                               X
                                               J
                                                     s j = inf {t : U(t) ⩾ jµ} ,                                       (40)
                                               j=1

where J = 1/µ is an integer. Graphically, Fig. 3(c) shows how the exit times s j can be determined. The inverse
measure is defined as the normalized exit time
                                                 µ†j (µ) = s j /T,                                         (41)
and the inverse partition function can be determined as follows:

                                                                 X
                                                                 J h            ip
                                                 χ† (µ, p) =             µ†j (µ) ,                                     (42)
                                                                  j=1


Figure 3(e) shows the dependence of [χ†p (∆v)]1/(p−1) as a function of the thresholds ∆v for different p values. Power-
law scaling can be observed over about three orders of magnitude:
                                                                         †
                                                        χ†p (µ) ∼ µτ (p) .                                             (43)

The scaling exponent function τ† (p) can be obtained through power-law regressions to the data points in the scaling
range, as is shown in Fig. 3(f). The nonlinearity of the τ† (p) function confirms the presence of multifractality in the

                                                                 14
exit time measure.
    An important issue arises concerning the relationship between τ(q) and τ† (p). Mandelbrot and Riedi proved an
elegant inversion formula mathematically for both discontinuous and continuous multifractal measures [160, 161].
Roux and Jensen independently proved the exact relation between the direct and inverse scaling exponents for the
classical binomial measures [162]. Xu et al. provided a simple “proof” of the inversion formula for multinomial
measures [163], which is presented below.
    Let µ be a probability measure on [0, 1] with its integral function M(t) = µ([0, t]). Then its inverse measure can
be defined by                                      (
                                                     inf{t : M(t) > s},      if s < 1
                                    µ† = M † (s) =                                     ,                             (44)
                                                     1,                      if s = 1
                                                                                          P
where M † (s) is the inverse function of M(t). If µ is self-similar, then the relation µ = ni=1 pi µ(m−1
                                                                                                      i (·)) holds, where
                                                                              Pn
the mi ’s are similarity maps with scale contraction ratios ri ∈ (0, 1) and i=1 pi = 1 with pi > 0. The multifractal
spectrum of measure µ is the Legendre transform f (α) of τ, which is defined by the generating function
                                                     X
                                                     n
                                                               q
                                                              pi ri−τ = 1.                                          (45)
                                                        i=1


It can be shown [160, 161] that the inverse measure µ† is also self-similar with ratio ri† = pi and p†i = ri , whose
multifractal spectrum f † (α† ) is the Legendre transform of τ† , which is defined implicitly by
                                                  X
                                                  n
                                                                      †
                                                        (p†i ) p (ri† )−τ = 1.                                      (46)
                                                  i=1

It is easy to verify that the following inversion formula holds
                                                    (
                                                      τ(q) = −p
                                                                  .                                                 (47)
                                                      τ† (p) = −q

Two equivalent testable formulae follow immediately
                                            (
                                              τ(q) = −τ†[−1] (−q)
                                                                   ,                                                (48)
                                              τ† (p) = −τ[−1] (−p)

where the superscript [−1] denotes the inverse function operator. Figure 3(f) verifies that the inversion formulae (48)
hold for the high-frequency volatility time series of the S&P 500 index [159].
    We can also relate the direct and inverse singularity strengths and the direct and inverse singularity spectra. From
Eq. (47), we have
                                                  dτ(q)       −dp         1
                                          α(q) =         =           =        .                                      (49)
                                                    dq      −dτ† (p) α† (p)
Combining Eq. (47), Eq. (49) and the Legendre transform, we have

                     f (α) = qα − τ = −τ† (p)α + p = α[−τ† (p) + pα† ] = f † (α† )/α† = α f † (1/α).                (50)

Rigorous proofs of these results can also be found in Refs. [160, 161]. It is easy to obtain the relation between direct
and inverse generalized dimensions [164]:
                                        (
                                           p       = −(q − 1)D(q)
                                                                               ,                                   (51)
                                           D† (p) = q/[1 + (q − 1)D(q)]

where D† (p) is the inverse generalized dimension function.



                                                                15
2.1.5. Ensemble averaging
    In the multifractal analysis of financial time series, almost all studies with very few exceptions focused on individ-
ual time series. One can further investigate an ensemble of financial time series of individual assets [165]. Ensemble
averaging was developed to determine the multifractal dimensions of Diffusion-Limited Aggregations [166–170], and
unearthed a subtle discrete hierarchy quantified by complex fractal dimensions [171].
    One defines the quenched and annealed mass exponents τquen (q) and τann (q) as follows,
                                                 D         E
                                                  ln χq (s) ∼ −τquen (q) ln s,                                        (52)
                                                    D      E
                                                 ln χq (s) ∼ −τann (q) ln s,                                          (53)

where the angular brackets h·i signify the ensemble average over all time series. The annealed exponents are more
sensitive to rare samples of the ensemble with unusual values of χq (s), while the quenched exponents are more
characteristic of typical members of the ensemble [172].
    The reasoning under the ensemble averaging lies in the consideration that one performs the measurement many
times of the dynamics of an “ensemble” of financial instruments. The ensemble averaging method provides an alterna-
tive way to measure market risks from individual equities other than the market index. It is also different from directly
averaging the risk measures of many individual equities. In addition, although the method was initially developed for
the partition function approach, its extension to other multifractal analysis methods is straightforward.

2.2. Structure function approach
2.2.1. Direct structure functions (MF-SF)
    Another important statistical quantity of turbulent fields is the structure function of velocity increments [133, 134].
Classical experiments have been carried out to measure the structure function and its nonlinear scaling behaviors [135].
Such nonlinear scaling behavior is also termed as multifractality [122, 136]. The structure function approach has been
also employed to investigate financial time series [18, 138, 173]. The qth-order structure function is also called the
qth-order height-height correlation function in the literature [174, 175].
    Consider a time series {X(i) : i = 1, · · · , N}. The increments or innovations over time scale s are defined as

                                                ∆X(i, s) = X(i) − X(i − s).                                            (54)

For financial assets, X(i) is the logarithmic price and ∆X is the return over the time interval of duration s. The qth-order
structure function is defined as the qth-order moment of the increment distribution:
                                                               1 PN                        q
                                             h|∆X(i, s)|q i   N−s   i=s+1 |X(i) − X(i − s)|
                                   K(q, s) =                =          1 P
                                                                                             .                          (55)
                                               h|X(i)|q i              N   i [X(i)]
                                                                                    q


We stress that q ≥ 0 for time series in turbulence [135], finance [138, 176], and other fields, because ∆X(i, s) can be
zero such that the moments of negative orders are not defined. When q = 0, we have K(0, s) ≡ 1, which is independent
of the scale s. When q = 2, K(2, s) is proportional to the autocorrelation function ∼ hX(i)X(i − s)i [138, 176].
    For self-similar time series, we expect to have

                                                 K(q, s) ∼ sζ(q) , sqH(q) ,                                            (56)

where H(q) is the generalized Hurst exponent. The scaling function is obtained as [177]

                                              τ(q) = ζ(q) − 1 = qH(q) − 1.                                             (57)

When q = 0, we have
                                                        τ(0) = −1.                                                     (58)
In practice, for each fixed q, we calculate the K(q, s) values with varying s values and perform a linear least-squares
regression of ln K(q, s) against ln s in a properly chosen scaling range [smin , smax ] to obtain qH(q) and τ(q). It follows

                                                            16
that                                                                                   P            P                             P
                                                                                           s ln s       s ln K(q, s) − N    s ln s ln K(q, s)
                                          τ(q) = qH(q) − 1 =                                             P        2   P          2
                                                                                                                                              −1                                                              (59)
                                                                                                            s ln s − N   s (ln s)
We can further determine the singularity function α(q) and the singularity spectrum f (α) through the Legendre trans-
form. When X(t) is monofractal, H(q) = H is a constant. When X(t) has a multifractal nature, H(q) decreases with
q.
     According to the definition of K(q, s), we have
                                                                        P      P q
                              d ln K(q, s)      1 dK(q, s)       1 d t vq         t v ln v
                                           =                  =P q           = P        q
                                                                                            ,                      (60)
                                   dq         K(q, s) dq         t v    dq           tv
        P
where t is the sum for s + 1 ≤ t ≤ T with v > 0. Denote k the proportionality coefficient of the scaling relation (56).
It is obvious that k > 0. Combining Eq. (56) and Eq. (57), we have
                                                                              P q
                                 ′           d[τ(q) + 1]k ln s d ln K(q, s)     t v ln v
                               τ (q)k ln s =                  =             = P       q
                                                                                          .                        (61)
                                                     dq              dq            tv

Let g(x) = x ln x. We have g′ (x) > 0 when x ∈ [1/e, +∞) and g′ (x) < 0 when x ∈ (0, 1/e].
    Figure 4 presents the results of the multifractal analysis of the daily time series of the logarithmic price X(t) of the
Dow Jones Industrial Average index (DJIA, 1896-2015) based on the structure function approach.
          10                                                                 0
                                                                                                                                                         0.6
                                                                        10
           9

           8
                                                                             −5                                                                          0.5
                                                                        10
           7
  X(t)




                                                                                                                                                 H(q)
                                                               Kq (s)




           6

                                                                        10
                                                                             −10                                                                         0.4
           5                                                                                                                          q=1
                                                                                                                                      q=2
           4                                                                                                                          q=3
                                                                                                                                      q=4
                                                                                                                                      q=5
                                                                                                                                      q=6
           3                                                            10
                                                                             −15
                                                                                                                                                         0.3
          1895     1915   1935   1955     1975   1995   2015                       0                1                2        3              4              0     1         2         3         4         5    6
                                                                                 10             10           10              10             10
                                  t                                                                              s                                                                    q
           1.5                                                          0.6
                                                                                                                                                          1.2

                                                                        0.5                                                                                 1
               1

                                                                                                                                                          0.8
           0.5                                                          0.4
                                                               α(q)
  τ (q)




                                                                                                                                                          0.6
                                                                                                                                                 f (α)




               0                                                        0.3                                                                               0.4

                                                                                                                                                          0.2
          −0.5                                                          0.2
                                                                                                                                                            0

           −1                                                           0.1                                                                              −0.2
             0        1      2        3      4      5      6               0                1           2        3       4        5          6              0.1       0.2       0.3       0.4       0.5       0.6
                                      q                                                                          q                                                                    α

Figure 4: (color online) Multifractal analysis of the daily time series of the logarithmic price X(t) of the Dow Jones Industrial Average index (DJIA,
1896-2015) based on the structure function approach. (a) The daily price time series of the DJIA index. (b) Power-law dependence of the structure
function K(q, s) on time lag s for different q values. (c) The generalized Hurst exponent H(q) as a function of q. (d) The scaling exponent function
τ(q). (e) The singularity strength function α(q). (f) The multifractal singularity spectrum f (α).

    In a seminal study [173], Müller et al. presented a statistical analysis of financial data documenting scaling
laws in the form of Eq. (56) for q = 1 and q = 2, though they did not mention “multifractal”, “multiscaling” or
“structure function”. Their analysis included intra-day prices over 3 years and daily prices over 15 years of four
foreign exchange spot rates (DEM/USD, JPY/USD, CHF/USD, USD/GBP) and intra-day prices over 3 years of gold
(XAU/USD). Similar analyses for the first- and second-order moments have been adopted by other economists [178].



                                                                                                            17
2.2.2. Multifractal fluctuation analysis (MF-FA)
    The method of fluctuation analysis is a classical approach to extract the Hurst exponent of time series [179], which
has been applied extensively in econophysics [180–184]. The fluctuation function can be calculated as follows,
                                                      D                       E
                                  Z(2, s) = σ22 (s) = [∆X(i, s) − h∆X(i, s)i]2 ∼ s2H .                              (62)

where H is the fluctuation analysis (FA) exponent, i.e. approximatively the Hurst index. A value of the Hurst exponent
H larger than 0.5 means that the time series is correlated, For H < 0.5, the time series is anti-correlated, and for
H = 0.5, it is uncorrelated.
   One can extend the fluctuation analysis in equation (62) to higher orders as follows [185–187],

                                        Z(q, s) = h|∆X(i, s) − h∆X(i, s)i|q i ∼ sζ(q) .                                (63)

which enables us to understand the multifractal nature in the dynamics of markets. The relationship between the
scaling exponent ζ(q) and the generalized Hurst exponent H(q) can be described by Eq. (57). When q = 2, H = H(2)
is the Hurst exponent presented in Eq. (63). Using the Legendre transform, we can obtain the singularity strength α
and its spectrum f (α).

2.2.3. Inverse statistics and inverse structure functions
    Analogous to the inverse measure in the partition function approach [161, 188], Jensen [189] investigated the
moments of exit time or first passage time. For a given increment ∆X, using definition (54), the exit time scale s at
time i is defined by
                                           s(i, ∆X) = inf{s† : ∆X(i, s† ) ≥ ∆X} ,                               (64)
which is the minimal time needed for the fluctuation to exceed the threshold ∆X ≥ 0. The first passage time has
important usage in finance. For instance, Cho and Frees adopted it to construct an asymptotically unbiased volatility
estimator [190]. They argued that the natural volatility estimator focuses on how much the price changes, whereas
the “temporal” estimator based on the first passage time focuses on how quickly the price changes [190]. The inverse
statistics have also some connections to the persistence probability [191–194]. The variable s(i, ∆X) and derived
quantities have natural interpretations in finance, such the “time to recovery” after a drawdown and are part of metrics
used in a standard way in evaluating performance of financial strategies and hedge-funds. This explains that inverse
statistics have been extensively applied in finance, as well as in other fields like in the study of heart beat rate and
cardiac diseases [195].
    If X(i) is a Brownian motion, the distribution of s is solved analytically as a Gamma distribution [196, 197]:
                                                                           !
                                                         1 a            a2
                                               Pr(s) = √ 3/2 exp −                                                  (65)
                                                          πs             s

where a is proportional to ∆X. Since asset prices are not Brownian motions, Simonsen et al. [198] proposed a
generalized shifted Gamma distribution
                                                                "         !ν #
                                            ν      β2δ               β2
                                    Pr(s) =            δ+1
                                                             exp −             ,                        (66)
                                           Γ δ (s + s0 )           s + s0
                                                   ν

which has a power-law tail Pr(s) ∼ s−(δ+1) . The Gamma distribution in Eq. (65) is recovered if ν = 1, δ = 1/2, s0 = 0
and β = a. They analyzed the wavelet filtered logarithmic daily closing prices of the DJIA (26 May 1896 to 5 June
2001) and found that the distribution (66) with δ ≈ 0.5 fits the data well. This observation seems quite ubiquitous for
uniformly spaced time series of indices and stocks in different markets [199–201], although there are studies reporting
that δ can deviate from 0.5 [202, 203]. For tick-by-tick data at the transaction level, the tail exponent can be larger than
0.5, as found for five highly liquid stocks (AstraZeneca, GlaxoSmithKline, Lloyds TSB Group, Shell, and Vodafone)
in the electronic market (SETS) of the London Stock Exchange (LSE) during the year 2002 [200] and the foreign
exchange rate of DEM against USD for the full year of 1998 (δ = 1.4) [204].


                                                              18
   Simonsen et al. [198] argued that the most probable first passage time s∗ is the optimal investment horizon and
found that s∗ scales with ∆X as a power law,
                                                  s∗ ∼ (∆X)γ ,                                                (67)
where γ ≈ 1.8, deviating from γ = 2 for Brownian motions. It is found that γ < 2 holds for regularly spaced samples in
most markets and the γ value is larger in developed stock markets than emerging markets [199, 205]. For tick-by-tick
data that are unevenly sampled, it was reported that γ > 2 [206].
    For asset prices, it is natural to also consider the minimal time needed for the price to depreciate by a certain return
∆X ≤ 0. Then, the exit time s at time i is defined by [207]

                                            s(i, ∆X) = inf{s† : ∆X(i, s† ) ≤ ∆X}.                                         (68)

A lot of research has shown that the optimal investment horizon is longer for gains than for losses, which is termed
the gain-loss asymmetry [205, 207–215]. Several models have been proposed to reproduce the gain-loss asymmetry
[216–218]. Nevertheless, there are also assets that do not show significant gain-loss asymmetry [202, 219].
     An analysis in the frequency space based on the discrete wavelet transform showed that the gain-loss asymmetry
is introduced mainly by the low-frequency content of the price series and the asymmetry disappears if enough of the
low-frequency content is removed [218]. Alternatively, the gain-loss asymmetry is found to be caused by the non-
Pearson-type autocorrelations in the time series [220]. Furthermore, the gain-loss asymmetry vanishes if the temporal
dependence structure is destroyed by shuffling the time series [221].
     The gain-loss asymmetry can be related to the leverage effect as follows. Recall first that the leverage effect is
the fact that, after a large negative return, the volatility increases significantly and then relaxes back, usually roughly
exponential in time [222–224]. In contrast, after a positive return, there is no significant change of volatility. And the
causality is from (negative) returns to future volatility and not the reverse, in the sense that a variation of volatility does
not produce any measurable change of the expected return in the future. The leverage effect can be interpreted as due
to the impact of a loss on the risk perception of the firm, which increases as the equity over debt ratio has decreased as
a result of the loss [222]. It also reflects a behavioral response of investors, who after a loss frantically reassess their
risk exposure and readjust their portfolios, leading to large price moves. The leverage effect allows one to account for
both (i) the asymmetry in the average time for a price drop of a fixed percentage versus a price gain of the same value
(for instance 10 days for a loss of 5% and 20 days for a gain of 5% on the DJIA) and (ii) the fact that this asymmetry
in waiting times for positive vs negative objectives is stronger for indices and weaker or absent for individual stocks
[218, 221]. ? Consider a fixed drop target of -5%. Such a drop is achieved by a succession of daily returns, more
negative than positive. When some negative loss occurs on one day, the leverage effect leads to an increase of the
amplitude of the next daily return. Because we are calculating a waiting time conditional to a cumulative drop of -5%,
the following returns will tend to be negative and with larger amplitude due to the leverage effect. In contrast, for the
waiting time to reach a positive gain of +5%, a majority of the daily moves will be positive, and the leverage effect will
be weaker or absent if there are no or weak negative returns along the price path. As a consequence, as the amplitude
of the daily returns tend to be small for a sequence of daily returns involved in a positive level (+5%), the average
waiting time to reach a positive return (+5%) is larger than for a negative return goal. The asymmetry of a single stock
is small because the leverage effect has a rather short memory and the difference between the number of up and down
daily moves for reaching the target threshold is not large. In contrast, for an index, or equivalently a portfolio of N
stocks, one must account for the ubiquitous existence of correlations between the returns of the stocks constituting the
portfolio. These correlations, which are in general positive (most stocks move approximately together on average),
produce an amplification of the gain-loss asymmetry, because the leverage effect is stronger by the averaging over
the idiosyncratic residuals of the constituting stocks. This also leads to predict that the gain-loss asymmetry for a
portfolio is the stronger, the stronger is the average correlation coefficients of its constituting stocks.
     The moments of the exit time, called the distance structure functions [189] or inverse structure functions [225,
226], are defined by
                                                    T p (∆X) ≡ hs p (∆X)i.                                                 (69)
Due to the duality between the structure function and the inverse structure function, one can intuitively expected that
there is a power-law scaling stating that
                                                  T p (∆X) ∼ ∆X φ(p) ,                                            (70)

                                                              19
where φ(p) is a nonlinear concave function [189].
    Synthetic data for the GOY shell model of turbulence show perfect power-law dependence of the inverse structure
functions on the velocity threshold [189]. For two-dimensional turbulence, the inverse structure functions exhibit well-
defined multifractal properties [226]. In contrast, for three-dimensional turbulence, the inverse structure functions of
an experimental time series at high Reynolds number do not exhibit clear power law scaling [225]. Nevertheless,
different experiments show that the inverse structure functions of three-dimensional turbulence exhibit a more general
scaling behavior called extended self-similarity (see next subsection) [227–229]. To our knowledge, the behavior of
inverse structure functions of financial asset prices has not been studied.
    The inversion formula relating the direct scaling exponents ζ(q) of direct structure functions and the inverse scaling
exponents φ(p) of inverse structure functions can also be derived [230, 231] and give
                                                   (
                                                      ζ(q) = −p
                                                                       .                                              (71)
                                                      φ(p) = −q

These expressions are verified by the simulated velocity fluctuations from the shell model [162]. However, this
prediction (71) cannot be confirmed by wind-tunnel turbulence experiments (Reynolds numbers Re = 400 ∼ 1100)
[228], which is not surprising because the inverse structure function does not scale as a power law of the velocity
increment thresholds [225, 228].

2.2.4. Extended self-similarity
    To investigate the scaling properties of the inverse structure functions, one can define a set of relative exponents
using the framework of extended self-similarity (ESS) [232]:

                                                 K(q, s) ∼ [Kq0 (s)]ξ(q,q0 ) ,                                        (72)

where q0 is the order taken as a reference value. If Eq. (56) holds, we have
                                                                  qH(q)
                                                   ξ(q, q0 ) =             .                                          (73)
                                                                 q0 H(q0 )
When the time series is monofractal, H(q) is independent of q, that is, H(q) = H(q0 ). It follows for monofractal time
series that
                                                  ξ(q, q0 ) = q/q0 .                                              (74)
In the case of velocity structure functions in fluid mechanics, q0 = 3 is a natural choice based on the exact Kol-
mogorov’s Four-Fifth Law [229, 233]. For financial time series, we suggest to choose q0 = 2 because H(2) is the
Hurst index. Generally, the ESS approach provides a wider scaling range for the extraction of scaling exponents.
    Fig. 5(a) presents the log-log plots of K(q, s) against K2 (s) for q = 1, 2, · · · , 6 with s ∈ [1, 211 ]. The straight
lines hold over more than two orders of magnitude and over at least 3.5 orders of magnitudes for q ≤ 3, showing the
existence of extended self-similarity in the structure functions. The scaling range for small q’s seems to be broader
than for large q’s. The ESS scaling exponents ξ(q, 2) are shown in Fig. 5(b). There is a weak indication that ξ(q, 2)
has a nonlinear dependence as a function of q, with a downward curvature making the curve depart from the linear
dependence ξ(q, 2) = q/2 observes for small q’s.
    Whether a time series possesses monofractal or multifractal behaviors is related to the innovation distributions.
For simplicity of notation, we denote v = |∆X(t, s)|. By definition, we have
                                          Z ∞                          Z ∞
                                K(q, s) =      vq Pr(s; v)dv = [σ(s)]q     dx Φ(s; x)xq ,                              (75)
                                            0                                  0

where Pr(s; v) is the distribution of v, σ(s) is the standard deviation of v, x = v/σ is the normalized volatility, and




                                                             20
                                                                                                                               0
                0                                                                                                         10
           10                                                            2.5                                                                                  s=1
                                                                                                                                                              s=2
                                                                                                                          10
                                                                                                                               −1                             s=4
                                                                          2
                −5
           10                                                                                                                  −2
                                                                                                                          10
                                                                         1.5
  Kq (s)




                                                                  ξ(q)




                                                                                                                          P
                                                                                                                               −3
                                                                                                                          10
                −10                                                       1
           10
                                                       q=1
                                                       q=2                                                                     −4
                                                       q=3                                                                10
                                                       q=4               0.5
                                                       q=5
                −15
                                                       q=6                                                                     −5
           10                                                                                                             10        −1        0           1         2
                         −6    −5      −4         −3         −2
                    10        10     10      10          10               0                                                    10        10          10         10
                                                                           0        1      2        3     4      5    6
                                    K2 (s)                                                          q                                    |∆X(t, s)|/σ(s)

Figure 5: (color online) Extended self-similarity analysis of the daily price time series of the DJIA index (1896-2015). (a) Power-law dependence
of the qth-order structure function K(q, s) on the second-order structure function K2 (s) for different q values. (b) The ESS scaling exponent ξ(q) as
a function of q. (c) The distributions of normalized volatility |∆X(t, s)|/σ(s) for s = 1, s = 2 and s = 4.


Φ(s; x) is the distribution of x. Eliminating σ(s) using q = 2, it follows that
                                                              R∞
                                                                    dx Φ(s; x) xq
                                        K(q, s) = [K2 (s)] hR 0
                                                          q/2
                                                                                 iq/2 .                                                                         (76)
                                                               ∞               2
                                                              0
                                                                  dx Φ(s; x) x

If Φ(s; x) is universal and independent of s, then the last term in Eq. (76) is a number independent of s (and thus
of K2 (s)) and the monofractal behavior ξ(q, 2) = q/2 follows. Fig. 5(c) shows the distributions of the normalized
volatility |∆X(t, s)|/σ(s) at three different scales. Although the three curves well overlap in their tails, they show clear
differences in the bulk around x = 1. This suggests that the ESS cannot be nonfractal, which is consistent with the
presence of nonlinear curvature in Fig. 5(b).
    We note that the ESS analysis is not constrained to the structure functions. Rather, it can be used for the moments
of other multifractal analysis approaches. In validating and qualifying the multiscaling behaviour of the recurrence
intervals of financial volatility, the relative dependence of recurrence interval moments of different orders of empirical
time series has been investigated [234], which is in essence an ESS analysis [235].

2.3. Wavelet transform approaches
2.3.1. Multifractal analysis based on wavelet transform (MF-WT)
     The wavelet transform is widely used as a mathematical microscope to analyze time series [236, 237]. In particular,
it can be used to analyze the singular structure of fractal and multifractal time series [238–240].
     The wavelet transform of function X(t) is [236, 237]
                                                         Z                  !
                                                       1 +∞           t−b
                                           Cψ (b, s) =         X(t)ψ          dt,                                  (77)
                                                       s −∞             s

where b ∈ R is the position parameter, a ∈ R+ is the dilation parameter, ψ(t) is the analyzing “mother” wavelet.
Gaussian wavelets are widely adopted [241] and are defined as derivatives of the Gaussian function:
                                                                                                        dn −t2 /2
                                                                               gn (t) = g(n) (t) = cn       e     ,                                             (78)
                                                                                                        dtn
where cn is the normalization coefficient. The second order (n = 2) Gaussian wavelet is known as the Mexican hat.
                                                          N
    To perform wavelet transform on a time series {X(i)}i=1 , one usually discretizes Eq. (77) in which b can take any
value along the sampling spacing and s takes n s scales forming a geometric sequence:

                                                                               s j = λ j−1 smin , 1 ⩽ j ⩽ n s ,                                                 (79)



                                                                                               21
where λ > 1. The discretised wavelet transform of a given time series Y(i) is then

                                                    1X
                                                       N          j − i
                                          W(s, i) =       X( j)ψ          , i = 1, · · · , N.                             (80)
                                                    s j=1            s

The wavelet transform is used to identify different types of singularities in the signals in the time-scale plane, depend-
R on the order n of derivative of the mother wavelet (78). More generally, choosing a mother wavelet ψ satisfying
ing
   xm+1 ψ(s)dx = 0 implies that the wavelet transform is blind to polynomial dependence up to order m and only higher
order powers are detected. For instance, for m = 0, the wavelet transform is independent of the level of the signal and
informs essentially on the local slope. For m = 1, the wavelet transform is independent of the level of the signal and
of its local slope, and it informs on the local curvature. We should also mention the existence of orthogonal wavelet
transforms [241–243] and biorthogonal wavelet transform [244], which can be used directly to determine the Hurst
index of a long-range correlated time series [245–247].
    To investigate the multifractal nature of a time series, one can calculate the qth order moments of the wavelet
coefficients [248, 249]
                                                          1 X
                                                             N
                                                 Mq (s) =       |W(s, i)|q                                            (81)
                                                          N i=1
and we expect that
                                                          Mq (s) ∼ sqH(q) , s ≫ 0.                                        (82)
We note that Mq (s) might diverge for q ≤ 0 because some values of |W(i, k)| might be close or equal to 0.
    One can obtain the scaling exponents through ordinary least-squares regression. Or, we can adopt the weighted
least-squares regression by putting more weight on the points with smaller variance [247]. Denoting

                                                               L j,q = ln Mq /q,                                          (83)

the corresponding weight w j is
                                                              w j ∼ Var(L j,q )−1                                         (84)
and the objective function is                    X           h                          i
                                                        w j E (L j,q − H(q) ln s j − A)2 .                                (85)
                                                  j

The estimate of H(q) is determined as follows:
                                       P       P                       P              P
                                          j wj    j w j ln s j L j,q −   j w j ln s j   j w j L j,q
                               Ĥ(q) =       P        P                  P               2        .                     (86)
                                                                   2
                                                j wj     j w j ln s j −      j w j ln s j


2.3.2. Wavelet transform modulus maxima (WTMM)
    A more elegant approach, which removes the redundancy contained in continuous wavelet transforms, is based on
the wavelet transform modulus maxima (WTMM) [245, 249–251]. At each scale s j , there exists several local maxima
of |W(s j , i)|. These maxima form several maxima lines in the (i, s) plane. The WTMM is capable of detecting all
the singularities of a large class of time series [252]. The traditional method based on partition functions may face
problems in dealing with the situation of q ≤ 0. However, we will find that the multifractal analysis based on WTMM
can overcome this difficulty because the wavelet coefficients on the WTMM line are local maxima that are non 0
[251].
    Assume that there are N j local maxima at scale s j and W(i j,k , s j ) is the kth local maximum located at i j,k . The qth
order moments defined on the WTMM are
                                                                          Nj
                                                                   1 X
                                                      M(q, s j ) =         |W(i j,k , s j )|q                             (87)
                                                                   N j k=1


                                                                       22
or alternatively the partition functions read
                                                                   Nj
                                                                   X
                                                    Z(q, s j ) =          |W(i j,k , s j )|q .                            (88)
                                                                    k=1

For multifractal time series, we have
                                                            Z(q, s) ∼ sτ(q) .                                             (89)
The generalized dimensions and singularity spectrum can then be calculated straightforwardly.
   Analogous to the thermodynamic approximation in the direct determination of singularities and singularity spec-
trum in Section 2.1.3, we can define the canonical measure [250],
                                                                       |W(i j,k , s j )|q
                                                     µk (q, s j ) =                       ,                               (90)
                                                                         Zq (s j )

such that the singularity strength α is
                                                                 Nj
                                                           1 Xh                                      i
                                        α(q) = lim                  µk (q, s j ) ln |W(i j,k , s j )|                     (91)
                                                  s j →0 ln s j
                                                                i=1

and the singularity spectrum f (α) is
                                                                  Nj
                                                            1 Xh                                 i
                                          f (α) = lim                µk (q, s j ) ln µk (q, s j ) .                       (92)
                                                   s j →0 ln s j
                                                                 i=1

In applications, we use different scales s j and perform (weighted) linear regression on the log-log scales.
    Using respectively the partition function approach and wavelet analysis to detect the multifractal nature of a single
time series, it is found that τPF (q) = τWT (q) + q and αPF (q) = αWT (q) + 1 [253–255].

2.3.3. Wavelet leader (MF-WL)
    A more recent multifractal formalism is based on wavelet leaders [256–261]. Wavelet leaders, introduced by
Jaffard [256, 257], are defined based on discrete wavelet coefficients, which decompose the time series X(i) on the
bases {ψ j,k } j∈Z,k∈Z composed of discrete wavelets ψ j,k . The integers j ∈ Z and k ∈ Z define the scale s = 2 j and location
b = k2 j . The discrete wavelets {ψ j,k } j∈Z,k∈Z are space-shifted and scale-dilated templates of an analyzing wavelet ψ(t):
                                                                               !
                                                                  1   i − k2 j
                                                      ψ j,k (t) = j ψ            ,                                         (93)
                                                                 2       2j

which usually uses the Daubechies wavelet of order 1 for the mother wavelet. The discrete wavelet coefficients are
defined as                                        Z                    !
                                                          1   i − k2 j
                                        W( j, k) = X(i) j ψ              .                                    (94)
                                                    i     2      2j
One defines a dyadic interval λ( j, k) as                     h                 
                                                    λ( j, k) = k2 j , (k + 1)2 j ,                                        (95)
and denotes the union of interval λ and its two adjacent neighbors as 3λ,

                                          3λ( j, k) = λ( j, k − 1) ∪ λ( j, k) ∪ λ( j, k + 1).                             (96)

The wavelet leader ℓ( j, k) is defined by [256, 257]

                                                     ℓ( j, k) =       sup |W(λ′ )|,                                       (97)
                                                                   λ′ ⊂3λ( j,k)


                                                                      23
which corresponds to the largest value of the absolute wavelet coefficients |W( j′ , k′ )| calculated on intervals (k−1)2 j ≤
   ′                                                                                                         ′
2 j k′ < (k + 2)2 j with 0 < j′ ≤ j. Note that, to compute the wavelet leaders, all the fine scales 2 j ≤ 2 j must be
considered.
     The multifractal analysis based on wavelet leaders can be described as follows [256–261]. As usual, we can define
the moments of order q by
                                                               nj
                                                           1 X
                                                M(q, j) =         ℓ( j, k)q ,                                           (98)
                                                          n j k=1

where n j is the number of wavelet leaders at scale s = 2 j . One can also expect the following scaling behavior if the
underlying processes are jointly multifractal,

                                                              M(q, j) ∼ 2 jζ(q) = sζ(q) .                                   (99)

where ζ(q) is related to τ(q) by
                                                            ζ(q) = τ(q) + 1 = qH(q).                                       (100)
We can also provide a canonical approach to determine the singularity strength function α(q) and the multifractal
spectrum f (α(q)) directly, as for the WTMM case in Section 2.3.2.
    An interesting application of wavelet leaders is the pointwise wavelet leaders entropy [262], which is defined over
different scales ( j) for a given point (k) by
                                                                               X
                                                                               m
                                                            E(k) = −                  ρ j,k log2 ρ j,k ,                   (101)
                                                                                j=1

where ρ j,k log2 ρ j,k = 0 if ρ j,k = 0 and
                                                  (                       Pm
                                                       W( j, k)2 /            j=1 W( j, k)
                                                                                                 2
                                                                                                      if W( j, k) , 0
                                       ρ j,k =                                                                             (102)
                                                       0                                              if W( j, k) = 0

When applied to the DJIA index (1928-2011), the resulting wavelet leader entropy is able to identify historical large
market fluctuations [262].
   Recently, wavelet p-leaders are introduced to characterize the p-exponents of negative pointwise regularity [263].
Based on the wavelet coefficients calculated in Eq. (94), the wavelet p-leaders are defined by
                                                                                                                   1/p
                                                                         X                                       
                                              ℓ(p) ( j, k) =                            |W( j, k)| p 2 j − j  .
                                                                                                            ′
                                                                                                                           (103)
                                                                      j′ ≤ j,λ′ ⊂3λ( j,k)

The p-leader multifractal formalism relies on the sample moments of the p-leaders [264]:
                                                                                      nj
                                                                                1 X h (p)        iq
                                                       M (p) (q, j) =                   ℓ ( j, k) ,                        (104)
                                                                                n j k=1

It is found that MF-DFA characterizes local regularity via the 2-exponent, not the Hölder exponent, and the wavelet
p-leader multifractal formalism can be viewed as an wavelet-based extension of MF-DFA [264]. The p-leaders suffer
from finite-resolution effects, which can be resolved through an explicit and universal closed-form correction [265].

2.4. Detrended fluctuation approaches
2.4.1. General framework
    Consider a time series {X(i)|i = 1, 2, · · · , N}, whose data points are usually the cumulative sums of a time series
                    e be the local trend function, which is usually determined locally around the data points using
of innovations. Let X(t)



                                                                                   24
some method. The detrended residuals are defined by
                                                                     e
                                                       ǫ(i) = X(i) − X(i).                                                  (105)

    We divide {ǫ(i)} into N s = int[N/s] non-overlapping segments with boxes of size s, where int[y] is the largest
integer that is no larger than y. We denote the vth segment as S v = {ǫ((v − 1)s + j)| j = 1, 2, · · · , s}. The local detrended
fluctuation function Fv (s) in the vth box is defined as the r.m.s. of the detrended residuals:

                                                           1 X
                                                               s
                                                                                
                                             [Fv (s)]2 =         ǫ((v − 1)s + j) 2 .                                        (106)
                                                           s i=1

The qth-order overall detrended fluctuation is
                                                                          1q
                                                           1 X q 
                                                           
                                                                Ns
                                                                          
                                                                          
                                                  Fq (s) = 
                                                                   Fv (s)
                                                                              ,                                            (107)
                                                            Ns           
                                                                v=1

where q can take any real value except q = 0. When q = 0, we have

                                                                   1 X
                                                                        Ns

                                                 ln[F0 (s)] =              ln[Fv (s)],                                      (108)
                                                                   N s v=1

according to L’Hôspital’s rule.
    When the whole series {ǫ(i)} cannot be completely covered by N s boxes, one can use 2N s boxes to cover the
series from both ends of the series, where N s = int[N/s] and a short part at each end of the residuals may remain
uncovered [139]. We denote the vth segment partitioned from left to right as S v = {ǫ((v − 1)s + j)| j = 1, 2, · · · , s} for
v = 1, 2, · · · , N s and the vth segment partitioned from left to right as S v = {ǫ(N − (v − N s )s + j)| j = 1, 2, · · · , s} for
v = N s + 1, N s + 2, · · · , 2N s . The local detrended fluctuation function Fv (s) in the vth box is defined as the r.m.s. of
the detrended residuals,
                                                  1 X
                                                     s
                                                                       
                                      [Fv (s)]2 =       ǫ((v − 1)s + j) 2 for v = 1, 2, · · · , N s                        (109a)
                                                  s i=1
and
                                   1 X
                                        s
                                                               
                                2
                        [Fv (s)] =       ǫ(N − (v − N s )s + j) 2 for v = N s + 1, N s + 2, · · · , 2N s .                 (109b)
                                   s i=1
The qth-order overall detrended fluctuation is
                                                                               1q
                                                         
                                                          1 X
                                                               2N s           
                                                                               
                                                                              q
                                                Fq (s) = 
                                                                    [F v (s)] 
                                                                                   ,                                       (110)
                                                          2N s                
                                                                v=1

where q can take any real value except for q = 0. When q = 0, we have

                                                                 1 Xs
                                                                        2N
                                                ln[F0 (s)] =             ln[Fv (s)],                                        (111)
                                                                2N s v=1

according to L’Hôspital’s rule.
    Varying the values of the segment size s, we can determine the power-law relation between the function Fq (s) and
the size scale s,
                                                    Fq (s) ∼ sH(q) .                                            (112)
According to the standard multifractal formalism, the multifractal scaling exponent τ(q) can be used to characterize


                                                                   25
the multifractal properties, which reads
                                                     τ(q) = qH(q) − D f ,                                         (113)
where D f is the fractal dimension of the geometric support of the multifractal measure [139]. For time series analysis,
we have D f = 1. If the scaling exponent function τ(q) is a nonlinear function of q, the time series is regarded to have
a multifractal nature.
    Following the approach determining directly f (α) from the partition function [157, 158, 266], the singularity
strength and its spectrum in the detrended fluctuation approaches can also be determined directly [267]. Defining the
canonical measure µ(q, s, v)
                                                                 q
                                                               F (s)
                                                µ(q, s, v) = PN v q ,                                              (114)
                                                               s
                                                              v=1 F v (s)
we have                                                    PN s
                                                               v=1 µ(q, s, v) ln F v (s)
                                           α(q) = lim                                      ,                     (115a)
                                                     s→0                ln s
and                                                       PN s                                
                                                              v=1 µ(q, s, v) ln µ(q, s, v)
                                      f (α(q)) = lim                          .                             (115b)
                                                    s→0       ln s
 Numerical experiments based on the p-model and fractional Brownian motions showed that MF-DMA and its direct
determination variant have comparative performance to unveil the fractal and multifractal properties [267].

2.4.2. Multifractal detrended fluctuation analysis (MF-DFA)
     The Detrended Fluctuation Analysis (DFA) was invented originally to investigate the long-range dependence in
coding and noncoding DNA nucleotide sequences [268]. The multifractal extension of DFA, MF-DFA, was developed
shortly thereafter [269, 270]. Since the work of Kantelhardt et al. [139], MF-DFA has become one of the most
important methods for multifractal analysis in diverse fields.
     In the MF-DFA method, the trend function is a polynomial [139], and the linear trend is most generally adopted.
                                   e is determined together with other points in the same box S v , using a polynomial
For each point i, its trend value X(i)
fitting of order l to the s data points in i ∈ S v :
                                                       ℓ
                                                       X
                                              e =
                                              X(i)            ak ik , l = 1, 2, · · · .                           (116)
                                                        k=0

The detrending process for ℓ = 1 is shown in Fig. 6. The figure shows a case with N s < N/s in which the data
points at each end of the time series should not be included to form a box. Otherwise, one obtains incorrect results
with fmax = f (q = 0) > 1, as will be elaborated in Section 5.1.2. In the standard procedure implementing MF-DFA,
researchers remove the constant shift h∆Xi from the increments ∆X and work on the cumulative profile

                                              X
                                              i
                                     x(i) =         [∆X(i) − h∆Xi] , i = 1, 2, · · · , N,                         (117)
                                              j=1

where h∆Xi is the sample mean of the ∆X(i) series. However, when the trend function is polynomial, this manipulation
does not have any impact on the results.
    A subtle issue of the MF-DFA method is the choice of polynomial order. Using classic mathematical models
(fractional Brownian motion, Lévy process and binomial measure) and real-world time series (foreign exchange rate
and literary texts), Oświȩcimka et al. found that the calculated singularity spectra could be very sensitive to the
order of the detrending polynomial and this sensitivity depends on the analyzed time series [271]. Without a deep
understanding of the underlying mechanism driving the dynamics, it is hard to determine which polynomial order
should be used. Anyway, for financial time series such as returns, we can check if the value of the Hurst index H(2)
is close to 0.5, based on the fundamental stylized fact of the absence of long memory in financial returns [60], which
however might not hold at the transaction level [272].

                                                                  26
                                  20                                                          10
                                              Y (i)
                                              Ye (i)
                                                                                               5
                                  10
                      Y (i), Ye (i)
                                                                                               0




                                                                                       ǫ(i)
                                      0
                                                                                               -5

                                -10
                                                                                              -10

                                -20                                                           -15
                                          0      100   200       300      400    500                0   100   200       300   400   500
                                                             i                                                      i
                                  20                                                          10
                                              Y (i)
                                              Ye (i)
                                  10                                                           5
                      Y (i), Ye (i)




                                                                                       ǫ(i)
                                      0                                                        0


                                -10                                                            -5


                                -20                                                           -10
                                          0      100   200       300      400    500                0   100   200       300   400   500
                                                             i                                                      i

Figure 6: (color online) Detrending process in the MF-DFA method. The time series has 500 data points and the timescale is s = 150. The first
row shows the detrending process from left to right in which the data points with i = 451, 452, · · · , 500 should not be used in calculating F, and the
second row illustrates the detrending process from right to left in which the data points with i = 1, 2, · · · , 150 should not be used.


     A possible solution is to use “feasible trend functions” in the multifractal feasibly detrended fluctuation analysis
(MFFDFA) [273]. One presets a priori a set of any trend functions, say, {ax2 +bx+c, a sin(x2 )+bx+c, ax3 +bx+c}, and
fit each segment with all the preset trend functions. For each segment, only one detrended function is chosen which
has the maximum coefficient of determination R2 . Hence, for each time scale s, the trend functions for different
segments are not necessary the same. Numerical experiments on fractional Brownian motions and binomial measures
show that the MFFDFA method outperforms the MF-DFA method [273]. For binomial measures, the improvement is
partially due to the fact that the fluctuation functions Fq (s) for MFFDFA have much smaller log-periodic oscillation
amplitudes, which reduces the impact of the choice of scaling ranges [274].

2.4.3. Multifractal detrending moving average analysis (MF-DMA)
    Based on the moving average (MA) technique for estimating the Hurst exponent of self-affinity signals [275],
the Detrending Moving Average (DMA) analysis considers the difference between the original signal and its moving
average function [276, 277]. The DMA method can also be easily implemented to estimate the correlation properties
of non-stationary series without any a priori assumptions, which is widely applied to the analysis of real-world time
series [278–285] and synthetic signals as well [286]. Extensive numerical experiments unveil that the performance
of DMA is comparable to DFA with slightly different priorities under different situations and both DFA and DMA
remain “The Methods of Choice” in determining the Hurst index of time series [287–289].
    The DMA method was generalized to MF-DMA for the investigation of the multifractal nature of time series
[290]. The main difference between the MF-DFA and MF-DMA algorithms is about the detrending procedure. In the
MF-DMA approach, one calculates the moving average function X(i)e in a moving window of size s [283],

                                                                              ⌈(s−1)(1−θ)⌉
                                                                                  X
                                                                       e =1
                                                                       X(i)                X(i − k),                                            (118)
                                                                            s k=−⌊(s−1)θ⌋

where ⌊y⌋ is the largest integer not greater than y, ⌈y⌉ is the smallest integer not smaller than y, and θ ∈ [0, 1] is the
position parameter. In other words, one considers ⌈(s − 1)(1 − θ)⌉ data points in the past and ⌊(s − 1)θ⌋ points in the
                                                                                    27
                                      0                                                    20
                                               Y (i)
                                      -5       Ye (i)                                      15

                                                                                           10
                      Y (i), Ye (i)
                                -10




                                                                                    ǫ(i)
                                -15                                                         5

                                -20                                                         0

                                -25                                                         -5

                                -30                                                        -10
                                           0      100   200       300   400   500                0   100   200       300   400   500
                                                              i                                                  i
                                      0                                                    20
                                               Y (i)
                                      -5       Ye (i)                                      15

                                                                                           10
                      Y (i), Ye (i)




                                -10


                                                                                    ǫ(i)
                                -15                                                         5

                                -20                                                         0

                                -25                                                         -5

                                -30                                                        -10
                                           0      100   200       300   400   500                0   100   200       300   400   500
                                                              i                                                  i

Figure 7: (color online) Detrending process in the MF-BDBA method (θ = 0). The time series has 500 data points and the timescale is s = 150.
The time series shown are obtained by truncating the points on both ends from a much longer time series. The first row shows the detrending
process from left to right in which the data points with i = 451, 452, · · · , 500 should not be used in calculating F, and the second row from right to
left in which the data points with i = 1, 2, · · · , 150 should not be used.


                    e
future to determine X(i). When i is close to each of the endpoints, the size of the box might be less than s. One
can either abandon those points or calculate the moving averages directly. Usually, we consider three special cases,
corresponding to three representative versions of MF-DMA:

    • MF-BDMA. The first case θ = 0 refers to the backward moving average [287], in which the moving average
               e is calculated over all the past s − 1 data points of the signal.
      function X(i)
    • MF-CDMA. The second case θ = 0.5 corresponds to the centered moving average [287], where X(i) e contains
      half past and half future information in each window. This version is also termed MF-CMA [291].
                                                                                e considers the trend infor-
    • MF-FDMA. The third case θ = 1 is called the forward moving average, where X(i)
      mation of s − 1 data points in the future.

We note that the size of the window used to calculate the moving averages must be identical to the segment size in
calculating the detrended functions [290, 291]. The detrending process is illustrated in Fig. 7.

2.4.4. Other detrending algorithms
    Although determining the intrinsic trend embedded in non-stationary time series is difficult, there are many differ-
ent options [292]. Because the intrinsic trend of a time series is usually unknown, methods have different performances
for different types of time series. Hence, quite a few variants of MF-DFA and MF-DMA have been proposed. Lo-
cal trends can be be further classified into discontinuous ones and continuous ones. MF-DFA and MF-DMA belong
respectively to these two classes (see also Fig. 6 and Fig. 7).
    Zhou and Leung proposed the multifractal temporally weighted detrended fluctuation analysis (MF-TWDFA) in
moving windows [293]. For each i, they fit a linear function to the data points (X(i − s), · · · , X(i), · · · , X(i + s)) in the



                                                                                28
moving window of size 2s + 1, using weighted least-squares regression. The objective function is
                                                                            2
                                        X
                                        s 
                                                        X
                                                           l                 
                              O(i; s) =      X(i + j) −   ak × (i + j)  wi j , |i − j| ≤ s,
                                                                         k
                                                                                                                    (119)
                                         j=−s              k=0

                                                                                                                   
where wi j ’s are weights that decrease with increasing |i − j|. In other words, the deviation X − a0 − a1 × (i + j) 2 has
a larger weight when j is far from i. The weights wi j in MF-TWDFA are defined by [293]
                                                         "     i − j 2 #2
                                                   wi j = 1 −               .                                       (120)
                                                                  s

For the equally weighted case,
                                                           wi j = 1,                                                (121)
we obtain the multifractal moving window detrended fluctuation analysis (MF-MWDFA) [293]. These two methods
belong actually to the continuous class, since the trend changes mildly without jumps. Indeed, when l = 0, we recover
the centered MF-DMA method [293].
    The empirical mode decomposition (EMD) is an innovative method of analysis for nonlinear and non-stationary
                                                                  s
time series, which decomposes the time series {X((v − 1)s + i)}i=1    into a finite number of intrinsic mode functions
(IMFs) [294]. Let {x(i)}i=1 , {X((v − 1)s + i)}i=1 . The decomposition is a sifting process, which has six steps [292]:
                         s                       s

(1) Identify all extrema of x(i); (2) Interpolate the local maxima to form an upper envelope U(i); (3) Interpolate the
local minima to form a lower envelope L(i); (4) Calculate the mean envelope:

                                                  µ(i) = [U(i) + L(i)]/2;                                           (122)

(5) Extract the mean from the signal
                                                    Ck (i) = X(i) − µ(i);                                           (123)
(6) Check whether Ck (i) satisfies the IMF conditions. If the IMF conditions are fulfilled, Ck (i) is an IMF, and the
sifting stops. Otherwise, let x(i) = Ck (i) and keep sifting. Finally, we obtain the EMD-based local trend of the time
                                 s
series segment {X((v − 1)s + i)}i=1 :

                                                                                  X
                                                                                  K
                                        e − 1)s + i) = X((v − 1)s + i) −
                                   rn , X((v                                            Ck (i).                     (124)
                                                                                  k=1

Qian et al. used this local trend in the MF-DFA method and developed the EMD-based MF-DFA method [295].
Numerical experiments on multifractal binomial measures indicate that the EMD-based MF-DFA method has compa-
rable performance with respect to the MF-DFA method except that the EMD-based method performs slightly better
for small singularities [295]. The method has been applied to analyze stock market indices [295, 296], foreign ex-
change rates [297], and Certified Emission Reduction (CER) and European Union Allowances(EUA) futures prices
[298], all of which confirm the presence of multifractality in financial returns.
    In order to handle time series with highly non-stationary sinusoidal and polynomial overlying trends, Horvatic
et al. proposed to detrend with polynomials of varying orders [299]. In this method, the polynomial order ℓ is not
fixed but increases with the scale s and the detrended fluctuations at different scales should be normalized to secure an
identical intercept. Although an objective criterion for the determination of the varying order is lacking, a subjective
choice (ℓ = 1 for s = 4, ℓ = 2 for s = 6, ℓ = 4 for s = 10, ℓ = 8 for s = 18, and ℓ = 16 for s > 18) seemingly works
well [299]. The underlying logic is that we need high-order polynomials to detrend properly the oscillations.
    Du et al. constructed the dual-tree complex wavelet transform based multifractal detrended fluctuation analy-
sis (DTCWT-MFDFA) for non-stationary time series [300]. Based on the anti-aliasing and nearly shift-invariance
of the dual-tree complex wavelet transform [301, 302], the raw time series is decomposed through the pyramid al-
gorithm to extract the scale-dependent trends and the fluctuations from the wavelet coefficients. The length of the
non-overlapping segment on each time scale is computed through the Hilbert transform and each of the extracted

                                                              29
fluctuations is partitioned into non-overlapping segments with identical size. The detrended fluctuation function for
each segment can be calculated. The DTCWT-MFDFA method is found to outperform the MF-DFA method for
multifractal binomial measures [300].
    In order to perform the MF-DFA, Manimaran et al. proposed to detrend using discrete wavelet transform [303].
The discrete wavelets belonging to the Daubechies family are adopted to analyze the raw time series up to level s.
The resulting low-pass coefficients capture the polynomial trends in the data. One then reconstructs a time series
using these low-pass coefficients to represent the local trends at different scales. The method has been tested for
synthetical time series and applied to NASDAQ and BSE indices [304, 305]. Ghosh et al. used Db4 and Db6 basis
sets to isolate respectively the local linear and quadratic trends at different scales from the closing prices of fifteen
large-capitalization companies listed on the New York Stock Exchange (NYSE) [306]. Multifractality is observed in
the investigated stock indices and individual stocks.
    We note that other detrending methods used to preprocess the raw time series in Section 5.3.6 can also be used in
the local detrending at different scales to construct variants of MF-DFA.

2.5. Other methods
    In this section, we will review several other multifractal analysis methods. It should be keep in mind that different
multifractal analysis methods have been proposed in diverse fields and it is hard to mention all of them. We focus on
the methods that are relevant to those discussed in the previous sections and that are utilized for financial time series
analysis. Besides the ones presented below, we would like to mention the multifractal signal fluctuation analysis based
on the 0-1 test [307] and the focus-based multifractal formalism [308].

2.5.1. Multiplier method
    The concept of the multiplier was introduced by Novikov to describe the intermittency and scale self-similarity in
turbulent flows [125]. In econophysics, one can apply this concept to study volatility multipliers. For high-frequency
financial data, we first construct an additive measure in the time interval [t1 , t2 ], which is the sum of absolute returns:
                                                                      X
                                                                      t2
                                                    µ([t1 , t2 ]) =          |r(t)|,                                   (125)
                                                                      t=t1

The absolute return is actually a measure of the volatility on [t1 , t2 ] [309]. The volatility time series |r(t)| is divided
into boxes of identical size s. Each mother box is further partitioned into a daughter boxes, in which a is called a base.
The multiplier ma,s is determined by the ratio of the measure on a daughter box to that on her mother box [310, 311].
    If the multiplier is scale invariant, for any two bases a and b, the multiplier density functions pa (ma ) and pb (mb )
are related through Mellin transform M as follows [311]:

                                          [M{pa (ma )}]1/ ln a = [M{pb (mb )}]1/ ln b ,                                (126)

which leads to                           R1                             R1
                                       ln 0 mqa pa (ma )dma           ln 0 mqb pb (mb )dmb
                                                      =                      .                                         (127)
                                          ln a                   ln b
The mass scaling exponent τ(q) of the moment of ma can be obtained as [310, 311]

                                                                       lnhmqa i
                                                   τ(q) = −D0 −                 ,                                      (128)
                                                                         ln a
where D0 is the fractal dimension of the support of the measure. For time series, we have D0 = 1.
    The local singularity exponent α and its spectrum f (α) are related to τ(q) through the Legendre transform. It
follows that
                                                          hmq ln ma i
                                                 α(q) = − aq                                                 (129)
                                                           hma i ln a



                                                                30
and
                                                     hmqa i lnhmqa i − hmqa ln mqa i
                                           f (α) =                 q                 .                               (130)
                                                               hma i ln a
Eqs. (127-130) imply that, for each q, each of these characteristic multifractal quantities converges to a constant in the
scaling range and is independent of the base a.
    Note that, for financial volatility, q > −1 [312], which is quite analogous to the situation in turbulence [228].
Because the returns can be zero, the multiplier m can be zero and the probability density pa (0) , 0 at ma = 0. When m
                                                                                   R1
is smaller than a small number δ, p(m) = p(0) is a constant. For a given small δ, δ mq p(m)dm = C is finite. However,
the moment                   Z 1               Z δ                                     δ
                                                                             1
                                 mq p(m)dm =       mq p(m)dm + C = p(0)           mq+1 + C                          (131)
                              0                  0                          q+1        0
                                                                                                                 q
diverges when q ≤ −1. This property is verified empirically [312], based on the idea that the integrand ma pa (ma )
diverges for a given q [229, 313].
    The scale-invariant multiplier distribution is perceived to be more fundamental than the standard multifractal
spectrum f (α) [310, 311]. Moreover, it needs exponentially less computational time and is more accurate than the
partition function approach [310, 311].
    Using 1-min high-frequency data of the S&P 500 index, Jiang and Zhou reported that the volatility multiplier is
scale invariant and the volatility has the property of multifractality [312]. Niu and Wang confirmed the presence of
scale invariance in the multiplier distributions in the Shanghai SSEC index and in the simulated data from the model
of “voter interacting dynamic system” [314].

2.5.2. Multifractal Hilbert-Huang spectral analysis
    The Hilbert-Huang transform combines the EMD and the Hilbert spectral analysis [294, 315], in which the Hilbert
transform is applied to each component Ck (i) in Eq. (123). The overall trend can be expressed as
                                           X
                                           n                        X
                                                                    n                    Z          !
                             e = X(i) −
                             X(i)                Ck (i) = X(i) −          Ak (i) exp j       ωk (ℓ)dℓ ,              (132)
                                           k=1                      k=1

where j2 = −1. For each mode, the Hilbert-Huang spectrum is defined as the squared amplitude

                                                     H(ω, i) = A2 (ω, i),                                            (133)

The Hilbert-Huang marginal spectrum of the original time series is then written as
                                                      Z
                                              h(ω) =     H(ω, i) di,                                                 (134)

which corresponds to an energy density at frequency ω. This method is known as EMD-based Hilbert spectral analysis
(EMD-HSA), which we term the Hilbert-Huang spectral analysis (HHSA) for simplicity.
    Huang, Schmitt, Lu and Liu proposed the multifractal Hilbert-Huang spectral analysis (MF-HHSA) by general-
izing the Hilbert-Huang transform from the second order to arbitrary order [316, 317]. The Hilbert-Huang spectrum
H(ω, i) represents the original signal at the local level and can be used to define the joint probability density function
p(ω, A) of the frequency ωk and amplitude Ak . The Hilbert-Huang marginal spectrum in Eq. (134) can be rewritten
as                                                     Z ∞
                                               h(ω) =       p(ω, A)A2 dA,                                            (135)
                                                          0
which corresponds to the second-order moment. Huang et al. generalize Eq. (135) into arbitrary-order moments
                                                  Z ∞
                                         Lq (ω) =     p(ω, A)Aq dA,                                         (136)
                                                           0




                                                               31
where q ≥ 0 and h(ω) = L2 (ω). In the inertial range, we assume the following scaling relation,

                                                          Lq (ω) ∼ ω−τ(q) ,                                           (137)

where τ(q) is the corresponding scaling exponent function in the amplitude-frequency space.
    Li and Huang applied this MF-HHSA method to the CSI 300 index of the Chinese stock market and confirmed
the presence of multifractality [318].

2.5.3. EMD-based multifractal methods
    Welter and Esquef proposed an EMD-based dominant amplitude multifractal formalism (EMD-DAMF), which is
implemented as follows [319]:
      Step 1: Perform EMD on X(i) to obtain K IMFs Ck (i).
      Step 2: Determine the amplitude ak (i) and characteristic timescale s for Ck (i). The characteristic timescale s
      could be estimated in each mode by the Hilbert spectral analysis (HSA) as the reciprocal of the mean frequency,
      or simply by twice the mean time interval among all adjacent zero crossings.
      Step 3: Determine the dominant amplitude coefficients

                           uk, j := sup {max[|ak′ (i ∈ Ik, j )|]}, k = 1, 2, · · · , K and j = 1, 2, · · · , nk ,     (138)
                                   k′ ⩽k

      where nk is the number of local maxima of ak (i) and Ik, j is a time support around the jth maxima of ak (i).
      Step 4: Calculate the qth order moment for different q values:

                                                           1 X
                                                               nk

                                             Mq (sk ) =           (uk, j )q , k = 1, 2, · · · , K,                    (139)
                                                           nk i=1

      where the characteristic time scale sk can be obtained by HSA in each mode as the reciprocal of the mean
      (linear) frequency or simply by the mean time interval among all adjacent zero crossings.
      Step 5: Estimate the scaling function
                                                            Mq (sk ) ∼ skτ(q)+1−q .                                   (140)

    In real applications, Welter and Esquef suggested that the number of siftings is fixed to ten (that is, K = 10) and
signal envelopes are computed through cubic spline interpolation [319]. They validated the method with fractional
Brownian motions [320], Lévy processes [321], Multifractal random wavelet cascades [322, 323], and multifractal
multiplicative cascades from the p model [324]. Note that the EMD-DAMF method has a small number nk of am-
plitude maxima at larger scale modes and a limited number of scales [319]. The latter drawback might impact the
determination of the scaling range.
    Alternatively, Zhou et al. proposed the so-called EMD-DFA method [325]. The integrated time series X(i) is
decomposed into a set of intrinsic mode functions and a residual or trend component. All intrinsic time scales s are
identified by computing the number of data points between each neighboring local minima throughout each intrinsic
mode function (IMF). For a given s, all IMFs are resampled through replacing by 0’s all data points corresponding
to scales not equal to s and the fluctuation time series X s (i) is obtained by summing all resampled IMFs. The overall
fluctuation at scale s is the root mean square of X s (i):
                                                                               1/2
                                                             1 XN
                                                                        2 
                                                                                
                                                  F2 (s) =         X s (i) ,
                                                                N i=1

which produces better scaling than the DFA method [325]. The EMD-DFA method can be extended for multifractal


                                                                   32
time series by working on the q-order moments:
                                                                               1/q
                                                          1 XN               
                                              Fq (s) =          |X s (i)|  .
                                                                            q
                                                                                                                  (141)
                                                             N i=1

Note that the EMD-DFA method does not have an explicit detrending form like Eq. (105).

2.5.4. Multiscale multifractal analysis
     Gieraltowski et al. proposed the multiscale multifractal analysis (MMA) based on the MF-DFA method [326].
After calculating all values of the overall fluctuations Fq (s) by the MF-DFA method, rather than estimating H(q) from
Eq. (112) in the scaling range, they proceeded to estimate the local generalized Hurst exponents H(q, s) in moving
windows around different scales. In this method, two free parameters are introduced, the moving window size and the
step. Although the original MMA method is designed for MF-DFA, it can obviously be applied to other methods of
multifractal analysis.
     The MMA method has been applied to investigate the multifractal nature of daily returns of the Dow Jones Indus-
trial Average (DJIA), New York Stock Exchange Index (NYSE), S&P 500 Index, Heng Seng Index (HSI), Shanghai
Stock Exchange Composite Index and Shenzhen Stock Exchange Component Index (SZCI) from 12 May 1992 to 8
May 8 2012 [327, 328] and nine stock market indices (CAC 40, DAX, FTSE 100, HSI, NIKKEI 225, SSEC, NAS-
DAQ, S&P 500) from 3 January 2000 to 1 October 2014 [329].
     More generally, this method is equivalent to calculate the local logarithmic slopes of the Fq (s) functions:

                                                                 d ln Fq (s′ )
                                               h(q, s) = lim                   ,                                  (142)
                                                          ′ s →s    d ln s′
which is widely utilized in the study of structure functions in turbulence [226, 229], as well as in DFA [330]. The idea
to estimate local logarithmic slopes is especially informative when the scaling range is narrow and it can serve as a
method for the determination of scaling ranges. Different numerical methods can be adopted to estimate numerically
the local logarithmic slopes H(q, s) and the linear fitting in a moving window suggested in the MMA method is one of
them. Empirical analyses have been performed on financial time series, such as the WTI crude oil market [331] and
stock market indices [332], without referring to the name of multiscale multifractal analysis.

2.5.5. Time-varying multifractal analysis
    To quantify the evolution of a multifractal spectrum, one can perform a multifractal analysis of time series in
moving windows or rolling windows. We would like to stress that short window sizes will reduce the estimation
accuracy of multifractal quantities and increase the uncertainty of the results. Time-varying multifractal quantities
have practical implications, as discussed in Section 8.2.4.
    Alternatively, Xiong and Zhang proposed the time-varying multifractal spectrum distribution (TM-MFSD) [333].
The key idea is to perform multifractal analysis on the instantaneous autocorrelation function

                                          r(i, δ) = E[X ∗ (i − ∆/2)X(i + ∆/2)],                                   (143)

rather than the raw time series X(i), where the time-delayed conjugation X ∗ (i) of the analyzed series X(i) is selected
as the window function. To obtain the time-varying multifractal spectrum distribution of a time series, one can adopt
different multifractal analysis methods described in previous sections, such as WTMM [333], wavelet leaders [334,
335], MF-DMA [336], and MF-DFA [337]. Essentially, the multifractal analysis is performed with these methods on
moving windows.

2.5.6. Phase space reconstruction
    A classic method in nonlinear dynamics is to embed properly the time series into a phase space and estimate the
generalized dimensions Dq of the data points in the phase space [128, 148, 149, 338], which is however less applied in
econophysics. Based on the delay embedding technique [339], the time series X(i) can be converted into a sequence
of vectors:
                           →
                           −
                           X ( j) = [X( j), X( j + τ), · · · , X( j + (d − 1)τ)], j = 1, · · · , Nv ,           (144)
                                                               33
where Nv is the number of points (or vectors) in the phase space, τ is a suitably chosen time delay, and d is the
embedding dimension of the phase space. The embedding dimension d and the delay τ can be determined in different
ways [149, 340–344].
   The relative number of data points within a distance R to point i is calculated by

                                                1 X
                                                     Nv                        
                                                                  →
                                                                  −      →−
                                       ci (s) =             H s − X (i) − X ( j) ,                                 (145)
                                                Nv j=1, j,i

where H is the Heaviside function. The generalized correlation integral Cq (s) is [345]
                                                                       1/(q−1)
                                                   
                                                   1 X
                                                       Nv              
                                                                        
                                                                    q−1 
                                          Cq (s) = 
                                                          [c i (s)]    
                                                                                ,                                 (146)
                                                    Nv                 
                                                         i

which is the generalization of the correlation integral [128, 148, 149]. The generalized dimensions are given by [338]
                                                                log Cq (s)
                                                    Dq ≡ lim               .                                       (147)
                                                          s→0     log s
     Lee investigated the multifractal characteristics of the 1-min volatility of the Korea composite stock price index
KOSPI from 20 March 1992 to 28 February 2007 [346]. The volatility time series is first detrended with a wavelet
filter and then a multifractal analysis in the phase space with τ = 1 and d = 1 is performed to confirm the presence of
multifractality.

2.5.7. Asymmetric multifractal analysis
    Inspired by the stylized fact that the correlation between two assets is usually asymmetric [347–350], Alvarez-
Ramirez et al. developed the asymmetric multifractal detrended fluctuation analysis (A-MF-DFA) to detect asymmet-
ric multifractal scaling in individual time series [351]. In this method, the trend function is linear such that ai = 0
for all i > 1 in Eq. (116). The main idea is to calculate the upwards (downwards) fluctuation functions in which the
removed linear trends have non-negative (negative) slopes. Mathematically, the qth-order upwards overall detrended
fluctuation is
                                                  2N s "                 #q  1
                                        
                                        
                                            1     X      1 + k              
                                                                             
                                                                             
                                                                               q
                                                                v
                              Fq+ (s) = 
                                         P                       F v (s)    
                                                                                = h[Fv (s)]q i |a1 ≥0 ,          (148)
                                         2Ns 1+kv          2                
                                          v=1   2  v=1

and the qth-order downwards overall detrended fluctuation is

                                                Fq− (s) = h[Fv (s)]q i |a1 <0 ,                                    (149)

where kv = 1 if the slope of the linear trend (116) is nonnegative, that is a1 ≥ 0, and kv = −1 if the slope a1 < 0. When
q = 0, we apply L’Hôspital’s rule as in Eq. (111). The respective generalized Hurst exponents can be determined by
                                                                    ±
                                                      Fq± (s) ∼ sH (q) .                                           (150)

Note that the original A-MF-DFA method uses the mean absolute value of the residuals in each segment v [351].
    Empirical studies using the A-MF-DFA method investigated and confirmed the asymmetric multifractal behavior
in the daily returns of the DJIA index from 23 May 1980 to 25 August 2008 [352], the WTI oil price from 2 January
1986 to 14 December 2010 [352], the SSEC index from 19 December 1990 to 27 April 2012 and the SZCI index from
2 April 1991 to 27 April 2012 [353], and the DJIA, NASDAQ, NYSE, and S&P500 indices from 1 January 1991 to
31 December 2015 [354].
    The A-MF-DFA method can be easily extended to design the asymmetric multifractal detrending moving aver-
age analysis (A-MF-DMA), in which moving averages serve as the trend function and the direction (or “sign”) is
determined exactly as for the A-MF-DFA method [355]. The asymmetric multiscale detrended fluctuation analysis is
obtained by calculating the local exponents at different time scales, which has been applied to investigate the hourly

                                                             34
returns of the California electricity spot prices during years 1999 and 2000 [356].
    Cao et al. developed the asymmetric multifractal detrended cross-correlation analysis (MF-ADCCA) method
[357], as an asymmetry extension of the MF-X-DFA method (see Section 3.4). The method has been applied to
identify asymmetric cross-correlations between the daily returns of the SSEC index and six foreign exchange rates
from 22 July 2005 to 13 January 2012 [357], the 5-min returns of the CSI 300 index spot and futures returns from 30
June 2011 to 7 June 2013 [358], the daily returns of the gold spot prices in the Shanghai Gold Exchange (Au 99.95) and
the New York Gold Exchange from 2 January 2003 to 27 April 2012 [359], the EU ETS for carbon emission trading
products vs. energy futures – Brent crude oil (Brent), Richards bay coal (Coal), UK base electricity (Electricity) and
UK natural gas (Gas) – from 1 January 2008 to 31 December 2012 [360], the daily returns of the WTI price and
eight foreign exchange rates (CAD, MXN, NOK, GBP, 