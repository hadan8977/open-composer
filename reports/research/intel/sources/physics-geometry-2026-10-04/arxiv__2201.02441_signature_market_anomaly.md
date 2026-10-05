source: https://arxiv.org/pdf/2201.02441
fetched_utc: 2026-10-04T18:39:11Z
bytes_raw: 2399843

Applications of Signature Methods to Market Anomaly Detection

                                                       Erdinc Akyildirima,b , Matteo Gambaraa,, Josef Teichmanna,, Syang Zhoua
                                                                         a
                                                                         Department of Mathematics, ETH, Zurich, Switzerland
                                                           b
                                                               Department of Banking and Finance, University of Zurich, Zurich, Switzerland




                                           Abstract
arXiv:2201.02441v2 [q-fin.CP] 8 Feb 2022




                                           Anomaly detection is the process of identifying abnormal instances or events in data sets which
                                           deviate from the norm significantly. In this study, we propose a signatures based machine learning
                                           algorithm to detect rare or unexpected items in a given data set of time series type. We present
                                           applications of signature or randomized signature as feature extractors for anomaly detection algo-
                                           rithms; additionally we provide an easy, representation theoretic justification for the construction of
                                           randomized signatures. Our first application is based on synthetic data and aims at distinguishing
                                           between real and fake trajectories of stock prices, which are indistinguishable by visual inspection.
                                           We also show a real life application by using transaction data from the cryptocurrency market. In
                                           this case, we are able to identify pump and dump attempts organized on social networks with F1
                                           scores up to 88% by means of our unsupervised learning algorithm, thus achieving results that are
                                           close to the state-of-the-art in the field based on supervised learning1 .


                                           Keywords: Machine Learning, Signature, Randomized Signature, Market Fraud, Reservoir
                                           Computing, Stock market, Cryptocurrency, Imbalanced data, Anomaly detection
                                           JEL: C21, C22, G11, G14, G17




                                                 Email addresses: erdinc.akyildirim@math.ethz.ch (Erdinc Akyildirim), matteo.gambara@math.ethz.ch
                                           (Matteo Gambara), josef.teichmann@math.ethz.ch (Josef Teichmann), syang.zhou@math.ethz.ch (Syang Zhou)
                                               1
                                                 The full code used for the anomaly detection case study on cryptocurrency data can be found under
                                           https://gitlab.ethz.ch/Syang/reservoir-anomaly-detection.
1. Introduction

    Anomaly detection (or outlier detection) is defined as the task of detecting abnormal instances,
which are the rare items, events or observations deviating significantly from the majority of the
data. While these instances are called outliers (anomalies), the normal instances are called inliers.
Anomaly detection is a fundamental research problem that has been investigated by researchers
from diverse research fields and application areas. Anomaly detection can be made manually by
searching through whole data clouds to diagnose the problem, but clearly this is a long and labour-
intensive process. Anomaly detection often appears in the context of uncertainty, i.e. absence,
principal or not, of knowledge on the data generating process.
    Hence, over time, a plethora of anomaly detection techniques ranging from simple statistical
techniques to complex machine learning algorithms has been developed for certain application
areas such as fraud detection in financial transactions (West and Bhattacharya (2016)), fault de-
tection in production (Miljković (2011)), intrusion detection in a computer network (Sabahi and
Movaghar (2008)), etc. Some of the well known statistical methods such as z-score, Tukey method
(Interquartile Range) or Gaussian Mixture models can be useful for the initial screening of outliers.
Although these statistical or econometric anomaly detection methods have been well rooted in the
literature (we refer the reader to Chandola et al. (2009) for an extensive review) dating back to
Edgeworth (1887), many of them have failed to provide sufficient performance and accuracy in the
last decade. This is mainly in view of big data collected from various sources such as financial
transactions, health records, and surveillance logs etc. Nowadays high-volume, high-velocity, and
high-variety data sets demand cost-effective novel data analytics for decision-making and to infer
useful insights1 .
    Due to their inherent scaling properties machine learning algorithms take up the challenge of
big data and seem to improve the success of anomaly detectors. Machine learning models can
be configured to create complex anomaly detection systems with benefits such as higher perfor-
mance, time saving, overall system stability, and cost saving in the long run. Machine learning
algorithms for anomaly detection are essentially classified under two major paradigms: supervised
or unsupervised, which depend on data at hand.
    Under the supervised paradigm, data arrive labelled as anomaly and normal, that is all outliers
are known in advance. Some of the frequently used machine learning algorithms under this setting
are support vector machine (Suykens and Vandewalle (1999)), k-nearest neighbors (Fix and Hodges
(1989)), Bayesian networks (Pearl (1985)), and decision trees (Breiman et al. (1984)).
    Although the supervised setting is ideal for the efficient application of ML algorithms, it is not
common to obtain this structured data in most of real life applications. Under the unsupervised
paradigm, in turn, the algorithm is not provided with any pre-labelled points in the training data
hence the algorithm itself must discover what is anomalous and what is normal. Some of the
frequently used machine learning algorithms in this case are neural networks (Ivakhnenko and

   1
       https://www.gartner.com/en/information-technology/glossary/big-data


                                                        2
Lapa (1967)), self-organizing maps (Kohonen (1982)), expectation-maximization meta-algorithm
(Dempster et al. (1977)), one-class support vector machine (Choi (2009)). In our study we employ
Minimum Covariance Determinant (MCD) (Rousseeuw (1985)) and isolation forests (Tony Liu et al.
(2008)), which are also unsupervised learning algorithms.
    As mentioned above, the anomaly detection under the unsupervised paradigm (of unlabelled
data) is a challenging task as it requires the algorithm to detect previously unseen rare objects
or events without any prior knowledge about these. In this study, we consider time series data
and we employ the powerful signature theory from rough path theory Lyons (2014) as well as its
randomized counterpart studied in Cuchiero et al. (2021) together with isolation forests and robust
covariance techniques to detect anomalies under the unsupervised paradigm.
    Signatures provide a versatile encoding of the information of a continuous time bounded varia-
tion path. This can be used to construct a regression basis for non-linear, continuous maps on path
space. We consider classification maps (in a relaxed way) as continuous maps on such path spaces.
We demonstrate the application of (randomized) signature methodology for market anomaly de-
tection in the financial markets, however, the same line of thought can also be applied in the other
fields.
    Let us reflect a moment what an anomaly could mean in case of market data: as it is well known,
the efficient market hypothesis (EMH) (Fama (1970), Sharpe (1970), Fama (1976)) depends on the
random walk theory which suggests that price changes are random of a martingale type and thus
cannot be predicted with certainty given all the currently available information, and the available
information is optimally used by market participants. In other words, EMH states that stock prices
(and their past) already reflect all available information and expectations about the value of the
firm hence investors cannot earn excess profits using any past, public or private information which
they obtain (legally). EMH has been one of the most widely researched and tested hypothesis
in the last decades. It has been found that there are many instances where a security or group
of securities performs contrary to efficient markets and these instances are viewed as anomalies.
Financial market anomalies can occur in different extremes ranging from fraud or insider trading
to calendar anomalies such as weekend, turn of the month, or January effects. There are also other
type of technical and fundamental anomalies in between such as low price to book, high dividend
yield, moving averages or momentum.
    The methodology developed in this paper allows to detect many different kinds of financial mar-
ket anomalies mentioned above. In particular, we show the application of (randomized) signature
methodologies for market anomaly detection by using simulated data (geometric Brownian motions
with artificial changes) and also real transaction data from the cryptocurrency markets.
    One of the closest papers to our research in the mathematical framework is Cochrane et al.
(2020) which provides a data-driven notion of a distance (called conformance) between an arbitrary
stream of data and the corpus. They combine conformance with signatures to analyse anomalies
in streamed data. They achieve area under the curve (AUC) score of more than 98% (89%) in the
PenDigits (marine vessel traffic) data sets. They also show that their approach outperforms a state-


                                                 3
of-the-art shapelet method for 19 out of 28 data sets for the univariate (non-financial) time series
from the UEA & UCR time series repository. Results from our methodology based on randomized
signatures are mainly in line with their outcomes which shows the efficiency of the signatures based
methodologies. On the other hand, from the finance literature, La Morgia et al. (2021) is a very
closely related work to our research. They investigate pump and dump and crowd pump type of
manipulations organized by communities from the social media. They follow these groups for more
than three years and collect around 900 manipulation cases. They show that their machine learning
model is able to detect a pump and dump in 25 seconds from the moment it starts with an F1 -score
of 94.5%. We also employ this unique dataset of confirmed pump and dumps released by La Morgia
et al. (2021) to the literature. Although we achieve F1 scores up to 88%, the main advantage of our
approach is that it is an unsupervised machine learning algorithm which does not require labelled
data set, hence it can be applied in many different frameworks without data constraints.

   Our contribution to the literature is manifold: first, to the best of our knowledge, this is the
first paper which employs randomized signatures and truncated signatures for anomaly detection
in a financial market context. Second, we provide a new proof that qualifies randomized signatures
as universal approximators in the space of continuous functions (under specific conditions). This
complements the contribution of Cuchiero et al. (2021), which is more inspired by Reservoir Com-
puting. Third, we contribute to the scarce literature on the detection of pump and dump schemes
in the exponentially growing cryptomarkets. Moreover, our results reveal the improving market
efficiency in the crypto ecosystem as the market manipulations can be detected with high accu-
racy rates in advance with our unsupervised machine learning algorithm soley relying on publically
available data. Finally, the small differences between the results obtained by truncated signatures
and randomized signatures empirically prove the robustness of the randomized signature method
which can be applied in higher dimensional problems efficiently.

   The rest of the paper is organized as follows: Section 2 explains the methodologies that we em-
ploy to detect the market anomalies. Section 3 presents the numerical applications using simulated
and cryptocurrency market data together with the empirical findings and, eventually, Section 4
concludes.

2. Methodology

   The information contained in a time series can be encoded in non-linear maps on path space.
Having several values of such a map enables its learning. In order to design learning algorithms
efficient (linear or non-linear) regression bases have to be constructed. Signatures provide one
universal solution for this problem, randomized signatures an efficient approximatively universal
solution (with regularization properties).

2.1. Signatures
   In this subsection, we provide some basics about signatures or signature transforms as well as
the foundations of the theory of randomized signature. While a gentle introduction is also given

                                                 4
by Chevyrev and Kormilitzin (2016), we also refer the reader to Lyons et al. (2007) and Friz and
Victoir (2010) for a detailed discussion on the signatures and rough paths.
   In this section we shall introduce different ways to represent the information of paths, i.e. func-
tions γ : I → V , where I is a compact interval in R and V is a Hilbert space with an associated norm
stemming from a scalar product k · k. For simplicity we assume V to be finite dimensional here, so
tensor products coincide with their algebraic counterparts and can be used without ambiguity.
                                                              P
   The total variation of a path γ is defined as kγkT V = supI (t1 ,...,tk )∈I kγ(ti ) − γ(ti−1 )k, where
the supremum is taken over all partitions2 of I, called I.
Note that our path shall always start at 0.

Definition 2.1 (Bounded variation). A continuous path γ : I → V is said to be of bounded
variation if kγkT V < +∞. The set of all bounded variation paths on V is denoted by BV(V ) = {γ :
I → V | kγkT V < +∞}.

   Analogously, we can define the p-variation of a path:

Definition 2.2 (p-variation). Let p ≥ 1 be a real number and γ : I → V be a continuous path. The
p-variation of γ on the interval I is defined as
                                                                                         1/p
                                                         X
                                   kγkp = sup                         kγ(ti ) − γ(ti−1 )kp     .
                                                 I
                                                     (t1 ,...,tk )∈I

Note that for a fixed continuous path γ the function p 7→ kγkp is non-increasing, hence, if q ≥ p,
then kγkq ≤ kγkp and, thus, any finite p-variation path has also finite q-variation.

   One of the most remarkable properties of signatures is being universal approximators. To clarify
this from two perspectives let us first define tensor algebras. For any integer n the n-th power tensor
of V is defined as V ⊗n = V ⊗· · ·⊗V . For example, for V = Rd , it holds that V ⊗2 = Rd ⊗Rd ≃ Rd×d .
By convention, V ⊗0 = R.

Definition 2.3 (Tensor algebra). Consider V as a finite dimensional Hilbert space. The extended
tensor algebra T ((V )) over V is defined as the space (notice the sum notation which we often apply)
                                                             ∞
                                    (                                        )
                                                             X
                         T ((V )) = v = (v0 , v1 , . . . ) =   vn | vn ∈ V ⊗n .                   (1)
                                                                             n=0

It is equipped with element-wise addition, with element-wise scalar multiplication
                                                                           Pj        (in the usual way)
and with an inner product: v ⊗ w = (z0 , z1 , . . . ) such that V ⊗j 3 zj = k=0 vk ⊗ wj−k for all j ≥ 0.

   We are now ready for the definition of a signature of a bounded variation path.

Definition 2.4 (Signature). Let I = [s, t] be a compact interval and X : I → V be a continuous
path with bounded variation starting at 0. Consider furthermore a basis e1 , . . . , ed in V and denote
by X i the coordinate of X in this basis.

   2
       That is, increasing sequences of ordered (time) indices such that I = {(t0 , . . . , tr ) | 0 = t0 < t1 < · · · < tr = T }.


                                                                       5
    Let i = (i1 , i2 , . . . , in ) be a multi-index of length n where ij ∈ {1, . . . , d}, for all j ∈ {1, 2, . . . , n}.
Define the coordinate signature of the path X associated to the multi-index i as iterated integral as
follows                                           Z
                    S(X)i ei1 ⊗ · · · ⊗ ein =                       dXui11 . . . dXuinn ei1 ⊗ · · · ⊗ ein .           (2)
                                                  s≤u1 ≤···≤un ≤t

Then the signature S(X) of X is defined as

                                 S(X) = (1, S(X)(1) , . . . , S(X)(k) , . . . ),                        (3)

where S(X)(k) = i=(i1 ,...,ik ) S(X)i ei1 ⊗ · · · ⊗ ein = s≤u1 ≤···≤un ≤t dXu1 ⊗ · · · ⊗ dXuk for any k ≥ 1
                  P                                      R

has been defined in (2). In a similar way, we introduce the truncated signature of X of degree N :

                                      SN (X) = (1, S(X)(1) , . . . , S(X)(N ) ).                                      (4)

Remark 2.5. Signatures can be defined beyond bounded variation paths. For bounded variation its
definition is possible by classical Lebesgue-Stiltjes integration theory. For p-variation 1 < p < 2,
signature can be defined by Young integration, see Lyons et al. (2007). For path of p-variation
with p > 2 one needs – depending on p – additional data from the path X. This data turn out
to be components of signature up to [p]. We shall only work with signatures of bounded variation
paths here, but we note that we could also define – in complete analogy to the above and in line of
signatures for geometric rough path stemming from a continuous semi-martingale – signature of a
continuous semi-martingale via Stratonovich integration.
Remark 2.6. For a path in V = Rd there are dN iterated integrals of order N . This implies that the
size of signatures
             P grows     exponentially in degree. In particular, the truncated signature of degree N
has in total N      dj = dN +1 −1 for d ≥ 1.
                j=0        d−1

    Analytically, signature of a path is just defined as the collection of all iterated integrals of
components of the path with itself. Signature also appears as a dynamical system driven by the
path X on the interval I = [0, t] for running t, and has therefore several geometric properties.
We can also easily interpret components of signature: the first levels are simply the increments
of the path, while the second levels are linked to Lévy areas drawn by paths (see Chevyrev and
Kormilitzin (2016)).
    An important property of signatures is Chen’s identity (Levin et al. (2016)):

Theorem 2.7 (Chen’s identity). Let X and Y be paths with bounded variation defined on con-
secutive time intervals and starting at 0, e.g. [0, t] and [t, T ], for 0 ≤ t ≤ T . Then it holds that

                                            S(X ? Y ) = S(X) ⊗ S(Y ),                                                 (5)
where the concatenation of the two paths X and Y is defined as
                                         (
                                          Xu ,       for u ∈ [0, t],
                             (X ? Y )u =
                                          Xt + Yu , for u ∈ [t, T ].

This fundamental relation stemming from the fact that signature is related to a canonical dynamical
system in T ((V )) is the key ingredient to calculate (truncated) signatures with the computer as it
is implemented in the Python package iisignature (see Reizenstein and Graham (2020)). In fact,


                                                            6
it turns out that for piecewise linear paths, we have
                                  m                   ∞
                                                   m X
                                  O                O              X            1 i1                             
          S(X1 ? · · · ? Xm ) =         S(Xj ) =                                  Xj · · · Xjin ei1 ⊗ . . . ein   ,
                                                                               n!
                                  j=1              j=1   n=0 i=(i1 ,...,in )

i.e. it can be calculated from standard polynomials of components of the linear paths Xj by taking
products in T ((V )).

    A priori, it is not clear whether truncated signatures are able to perform well enough for
our purposes, as they simply contain only a fraction of the information of the “entire” signature.
Nonetheless, as the following theorem shows, this is completely analogous to polynomial expansions
(see Chapter 2 of Lyons et al. (2007)).
Theorem 2.8. Let X : I = [s, t] → V be a path of bounded variation. Then, for each n ≥ 0, one
has
                                                              kXknT V
                       Z
                                        dXu1 ⊗ · · · ⊗ dXun ≤         .                   (6)
                        s≤u1 ≤···≤un ≤t                         n!
Thus, high-order signature terms contain less and less information, since we have a factorial decay,
and truncated signatures should express similar features as standard signatures, provided the trun-
cation degree is sufficiently high. The link between normal signatures and truncated signatures is
given by the so-called canonical projection:
Definition 2.9 (Canonical Projection). The canonical projection πN of an element of T ((V )) on
the truncated tensor space T N (V ) is defined by T ((V )) → T N (V ), (v0 , v1 , . . . , vN , vN +1 , . . . ) 7→
(v0 , v1 , . . . , vN ).

Exploiting this projection, we see that the truncated signature solves an ordinary differential equa-
tion (ODE) in finite dimensions, i.e. it is a dynamical system, that can be directly derived from
signature definition (we refer to Chapter 7 of Friz and Victoir (2010) for a proof and more details).
Proposition 2.10. Let us fix the interval I = [s, t] and let X : I → V be a path of bounded
variation and Y : I → T N (V ). Then the solution of the controlled ODE
                             (
                               dYu = πN (Yu ) ⊗ dXu , for u ∈ [s, t]
                                                                     ,                  (7)
                               Ys = (1, 0, 0, . . . )

is the signature of X truncated at order N . Appropriately interpreted one can choose N = ∞ in
this assertion, too.

    Since T ((V )) is an associative, non-commutative algebra freely generated by dim V generators
with unit 1 signatures, as defined in (3), there are elements in such algebra solving an ODE
controlled by the path X.
    From the point of feature extraction we view signature as a map S : BV(V ) → T ((V )). The
analytic properties of signatures allow for the following remarkable statement (which is just the
Leibniz rule expressed in a fancy way): any product of two components of a signature is a linear
combinations of components of signature: therefore the set of linear combinations of signature

                                                          7
components forms an algebra of functions on BV(V ). Algebraically speaking T ((V )) is additionally
a Hopf algebra and signature is a group-like element therein.
   Additionally, if we shall always include running time as the zeroth component of a path X,
then the map from X to its signature is actually injective. This can be seen in the following way:
knowing the signature of a path means to know in particular

                                                                     1 t n i
                     Z                                                 Z
                                          dXu00 . . . dXu0n−1 dXvi =      v dXv
                      s≤u0 ≤...≤un−1 ≤v≤t                            n! s

for some fixed interval [s, t], for n ≥ 0, and i ∈ {1, . . . , d}, whence all Fourier coefficients of the
path are determined and therefore the path itself (notice again that the path starts at 0!).
   Whence linear combinations of components of signature form a point separating subalgebra of
continuous functions on BV(V ) and by the Stone-Weierstrass theorem, for any compact set K of
continuous paths of bounded variation, the set of linear functionals on signatures of paths from K
is dense in the set of continuous real-valued functions on K, denoted by C(K, R):

Theorem 2.11. For any function f ∈ C(K, R), K ⊂ BV(V ) compact and ε > 0, there exists a
l ∈ T (V ), the dual space of T ((V )) (the free vector space of words in {0, . . . , d} or the space of
non-commutative polynomials in e0 , . . . , ed ), such that suph∈K kf (h) − hl, S(h)ik < ε.

By using the above theorem signatures are a complete set of feature extractors and are therefore
universal approximators (Kiraly and Oberhauser (2019)).
   However, in any application these infinite dimensional objects have to be approximated by finite
dimensional objects. Therefore, in practice, we will never deal with the full signatures but use a
truncated version of those, which are defined in truncated signatures (introduced in Definition 2.4).
An alternative approach to this standard procedure is presented in the sequel.

2.2. Randomized Signatures
   Instead of the abstract tensor algebra T ((V )) we can consider concrete realizations, or – alge-
braically speaking – representations.
   Consider V being generated by e0 , . . . , ed (e0 will correspond to time), then we can consider
maps from ei to vector fields on some Rk

                                           ei 7→ σ(Ai · +bi )

for k × k matrices Ai and vectors bi ∈ Rk and some real analytic, bounded activation function σ
which is applied componentwise.

Definition 2.12. Let X : [0, T ] 7→ Rd+1 be a continuous path of bounded variation augmented by
time in the 0-th component. Then the solution of
                             (
                                d RSt = di=0 σ(Ai RSt +bi ) dXti
                                        P
                                                                  ,                         (8)
                                RS0 ∈ Rk

is called randomized signature.

                                                   8
   If the above representation from the free algebra generated by e0 , . . . , ed to the algebra of
differential operators on Rk is faithful, i.e. injective, then randomized signature for any initial value
should contain precisely the same information as the signature itself:

Theorem 2.13. Let σ be real analytic with infinite radius of convergence and let A1 , . . . , Ad ,
b1 , . . . , bd be independent samples of a probability law absolutely continuous with respect to Lebesgue
measure. Then linear combinations of randomized signature for all possible initial values RS0 ∈ Rk
are dense in C(K) on compact subsets of bounded variation curves.

Proof. By construction the vector fields σ(Ai · +bi ) cannot satisfy any non-trivial relation with
probability one, since otherwise we would have constructed a non-zero real analytic function on
                2
some R(d+1)×k +(d+1)×k , the product space of d matrices and d vectors with product measure
equivalent to Lebesgue measure, whose zero set has positive Lebesgue measure. This is impossible
by Mityagin (2015). Therefore the representation of T ((V )) into real analytic vector fields on Rk is
faithful. Compare here very similar arguments in Cuchiero et al. (2020) in a slightly different but
comparable context of generalized Hörmander or Chow theorems.
    By boundedness of σ randomized signatures are well defined and by the fact that σ is real ana-
lytic with infinite radius of convergence we obtain by Baudoin and Zhang (2012) that the stochastic
Taylor expansion converges and represents RSt for any t > 0. Whence signature components can
be expressed by randomized signature components for different initial values and we are done.


Remark 2.14. In practise we choose k moderately high, but we usually do only calculate RS for
one initial value. One could improve in view of the above proof the approximation properties by
calculating RS for different initial values.
Remark 2.15. Notice also that we could take any free set of d + 1 vector fields on any geometric
structure and construct randomized signatures thereon. Notice also that different initial values of
RS just corresponds to different shifts bi . Stacking together these equations leads to one initial
value for a moderately high dimensional system of type (8).
   The use of exact, truncated or randomized signatures as a feature set is very closely related to
the concept of reservoir computing which models input - output systems as
                                         
                                         x = F (x , z )
                                           t      t−1 t
                                                               ,                                      (9)
                                         y = h(x )
                                            t       t

where F is some mapping of inputs zt and previous features xt−1 to the next feature xt . h, usually
called readout or observation map in the context of reservoir computing, fulfills the role of mapping
the features, in our case either truncated exact signatures or randomized signatures, to the output.
The activation function σ in (8) plays the role of a squashing function which ensures that the results
do not blow up. A detailed discussion on reservoir computing and state-affine systems together with
some important theoretical results can be found in Grigoryeva and Ortega (2018) and Cuchiero
et al. (2021). In line with this interpretation, we will call k the reservoir dimension.

   Next, we will present, how randomized and exact (truncated) signatures can be used in practice
for classification tasks. For this, we will first present an example based on simulated data and


                                                    9
Figure 1: Sample paths of Geometric Brownian Motion (GBM) used as synthetic data. Parameters are µ = 0.25, σ =
0.2 and each path, representing 1 year, is made by 252 steps. All trajectories are shifted subtracting S0 = 100.




afterwards a case study based on real data, in which we aim to identify market frauds using
signatures. In the remainder of this article, we will write signature for either exact or randomized
signatures and we will specify it explicitly when necessary.

3. Numerical Applications

    In this section, we show the applications of our methodology first by using the simulated price
paths from geometric Brownian motion and later with some real data obtained for cryptocurrency
pump and dumps cases.

3.1. Simulated Data
    In this section we illustrate how our machine learning algorithm with signatures can be used to
differentiate the price paths that follow a geometric Brownian motion from the price paths coming
from a fake Brownian motions which contain artificial forgeries.
    Our synthetic data set consists of sample paths from a geometric Brownian motion (GBM in
the following) of the form
                                          dXt = µXt dt + σXt dWt ,                                         (10)

and artificially manipulated geometric Brownian motions. In general, manipulated Brownian mo-
tions do not exhibit all typical behaviours from real Brownian motions. Particularly, in successful
market manipulations, some market participants have knowledge about the price paths, which is
not publicly available. This manifests itself, for instance, in a lack of randomness for the periods
of market manipulation.
    Using this fact, we choose to generate artificially manipulated Brownian motions in the following
way: Given price differences Ri = Xi − Xi−1 , a pattern P of the form Pn = (p1 , . . . , pn ),             pi ∈
{−1, 1} and a partition P with subintervals of length n, we prevent the occurrence of P in the


                                                      10
return path. In order to ensure that the expected mean value of the paths do not change, we
always also prevent the occurrence of −Pn = (−p1 , . . . , −pn ) in the return path. More concretely,
our synthetic data consists of 20’000 paths, equally divided in real and manipulated, which are then
split into train and test sets. Longer patterns P will make the problem more difficult, as there will
be less differences between paths to distinguish them. In our experiments, we choose to remove
patterns of length 6 or higher.

Figure 2: Histogram of the number of consecutive increases/decreases in the paths. Fake GBM do not have any
combination of more than 5 consecutive increases/decreases along their paths.




   Samples paths of the fake geometric Brownian motions (GBM) and real Brownian motions can
be found in Figure 1. From this figure it can be seen that it is not easy to understand the difference
between real and fake Brownian motions by visual inspection. Also obvious characteristics of
the paths like mean and variance will be preserved and therefore they cannot be easily used to
differentiate the paths.
   The manipulated Brownian motions can of course be differentiated by counting the number of
long streaks as illustrated in Figure 2. As the number of occurrences of streaks does not differ
substantially between real and fake Brownian motions, it is not a trivial task to differentiate them.

3.2. Feature set generation
   We follow the methodology developed in Section 2 to transform the simulated data described
into features which are then used by a logistic regression. We add the time dimension and the
first differences to the path yielding (t, Xt , ∆Xt ) as the 3-dimensional time series which we use
for the classification task. The first differences are added as our experiments have shown that
they improved robustness and performance. Note that the information content does not change
with the addition of the first differences. Table 1 gives a full overview for all parameters used to


                                                    11
generate the results in Section 3.2.1. The features are finally generated by solving (8) with the
hyper-parameters described in Table 1 using a forward Euler scheme. In this example, we compute
the random signatures for each path and use a logistic regression on the training set. The weights
are then used to evaluate the performance of the models. For each path, model outputs will be
in [0,1] which indicates the probabilities. The model labels each path as either a real geometric
Brownian motion or a fake geometric Brownian motion by rounding the model outputs.




                            Table 1: Hyper parameters for random signatures

    Symbol    Description                              Simulated data    Cryptocurrency data
    σ         Activation function in (8)               tanh              tanh
    µA        Mean of A in (8)                         0.15              0.05
    σA2       Variance of A in (8)                     0.6               0.1
    µb        Mean of b in (8)                         0                 0
    σb2       Variance of b in (8)                     1                 1
    w         Window size as described in 3.7.1        -                 100
    o         Offset length as described in 3.7.1      -                 5
    k         Reservoir dimension                      200               50
Table 1 shows the results all hyper parameters used for both the simulated data and the
cryptocurrency data for the generation of random signatures.




                                                  12
3.2.1. Results
Figure 3: ROC curve (left) and PR curve (right) for the classification task of differentiating paths of the form 1.
Both figures show very similar results for the exact truncated signatures and the random signatures.




    We evaluate the performance of our methods by comparing the total accuracy. For that, it
is useful to introduce the following definitions that are common in classification (and pattern
recognition):

Definition 3.1 (Precision). Precision is the number of true positives (i.e. the number of items
correctly labelled as belonging to the positive class) divided by the total number of elements labelled
as belonging to the positive class (i.e. the sum of true positives and false positives, which are items
incorrectly labelled as belonging to the class). Briefly, p = tp/(tp+f p).

Definition 3.2 (Recall). Recall in this context is defined as the number of true positives divided by
the total number of elements that actually belong to the positive class (i.e. the sum of true positives
and false negatives, which are items which were not labelled as belonging to the positive class but
should have been). Briefly, r = tp/(tp+f n).

Definition 3.3 (Accuracy). Accuracy is the proportion of correct predictions (both true positives
and true negatives) among the total number of cases examined. Briefly, a = (tp+tn)/(tp+tn+f p+f n).

    In our experiments, model performances obtained on the train set were similar to the test set,
which indicates good generalisation properties. Additionally, we also compared the accuracy scores
for different regression outputs. This can be seen in Figure 4. This figure confirms that regression
outputs closer to 0 and 1 yield higher accuracy scores. Notably the results for the top quantiles
are better than for the bottom quantiles. This can be explained by the fact that in our particular
way of modifying Brownian motions, the existence of long streaks will be a very strong indicator
that the path is a real Brownian Motion whereas the absence of long streaks does not always imply


                                                        13
that the path has been manipulated as strongly. Therefore, our methods show better results in
correctly identifying real Brownian motions than in detecting manipulated Brownian motions.
    Next, we compare the model performance quantitatively. The results are summarised in Table
2. Comparing the methods, we observe a similar outcome for randomized signatures and exact
truncated signatures.

Definition 3.4 (ROC curve). ROC (Receiver Operating Characteristics) graphs are two-dimensional
graphs in which tp-rate (defined as the recall) is plotted on the y axis and fp-rate (defined as
f p/(f p+tn)) is plotted on the x axis. An ROC graph depicts relative tradeoffs between benefits (true
positives) and costs (false positives).

Definition 3.5 (PR curve). PR (Precision Recall) graphs are two-dimensional graphs in which
recall is plotted on the y axis and precision is plotted on the x axis. The focus of the PR curve on
the minority class makes it an effective diagnostic for imbalanced3 binary classification models.

Also the ROC curve and the PR curve both show very similar results for randomized signatures
compared to exact signatures as seen in Figure 3. This indicates the validity of our approach as
the results suggest that information content in the exact truncated signatures can be retained by
using randomized signatures. The results shown serve to demonstrate, that both random signatures
and exact signatures with even a simple readout function can be successfully used on this sample
problem.

Figure 4: The x-axis shows ordered model outputs for 10 separate quantiles. The y-axis shows the accuracy of given
set of model outputs. Here one can see that accuracy is higher for model outputs, which are farther from the cutoff.




   3
       As it will be the case for cryptocurrency data in Section 3.3




                                                           14
                               Table 2: Real signature vs random signature

                                          Exact signature     Randomized signature
         Mean accuracy                    71.81%              72.4%
         Mean accuracy bottom 10%         83.56 %             84.95 %
         Mean accuracy top 10%            95.11 %             95.74 %
Table 2 shows the results for the randomized and the truncated exact signatures for the sample
problem. Here top/bottom 10% displays the accuracies when only taking the top/bottom 10% of
the regression results respectively.


3.3. Cryptocurrency pump and dumps
   Due to the unregulated nature of cryptocurrency brokers, cryptocurrencies have been the target
of all sorts of market manipulation attempts. In this case study, we will focus on pump and dump
schemes. Typically, pump and dump schemes in the cryptocurrency space are organised via private
chat groups in channels using different softwares, such as Telegram or Discord, where any interested
person can join the channels and receive the date and currency pair of the planned pump and dump
schemes. The exact currency pair is given only seconds before the start of the pump, typically via
OCR (optical character reading-resistant) resistant images similar to captchas. There are even
aggregate web pages, which collect information of pump and dump channels and display them on
their web page, see for example Figure 5 taken from pump olymp. We would like to emphasize
that we do not recommend using such websites to participate in pump and dump schemes. As
can be seen in the following process description, there is great uncertainty with this strategy, with
participants having the least amount of information. This makes following such strategies extremely
risky besides the moral considerations.
   In the following we will describe the main ingredients and process of a typical cryptocurrency
pump and dump scheme. A more detailed description of the phenomenon can be found in Xu and
Livshits (2019) and La Morgia et al. (2021).

3.4. Pump and Dump ingredients
   • Organisers: Most often, pump and dump organisers are admins of the corresponding Telegram
     / Discord channels and use various means to advertise upcoming pumps. They are the ones
     who also determine the exchange and the currency pair which will be the target of the pump
     and dump scheme.

   • Participants: These are the traders who participate in pump and dump schemes in order
     to generate abnormal returns by using non-public information. They are subscribed to the
     channels and receive the information about the exchange and the currency pair targeted. It is
     worth noting that participants are usually categorised into different tiers depending on their
     financial contribution to the organisers or their help in spreading the channel; in other words,
     there is an internal hierarchy. Participants in different tiers receive the information about
     the exchange and currency pair at different time points, where participants in the lowest tier

                                                    15
                   Figure 5: Example of a web page collecting pump and dump channels




     receive the information last. This obviously creates an extremely unbalanced situation where
     participants in higher tiers have a way higher chance to generate profits.

   • Exchange: Cryptocurrencies are typically traded in crypto exchanges, which function as
     brokers. Due to the currently unregulated nature of these exchanges, they do not have too
     much incentive to stop pump and dump schemes as they generate profits for them due to
     transaction costs. As a matter of fact, some exchanges such as Yobit has have openly organised
     pump and dump multiple times Xu and Livshits (2019).

   • Currency pair: The currency pair is a price quote of the exchange rate for two different
     cryptocurrencies (e.g. BCT/ETH is the price of Bitcratic denominated in Ethereum). Pump
     and dump schemes usually target coins with a low market capitalisation so that the price can
     be influenced significantly with relatively small trades.

3.5. Pump and Dump process
   Typically a pump and dump scheme has three phases, which will be described in the following.

   • Pre-pump activity: Organisers are advertising the upcoming pump via their respective chan-
     nels. On predetermined times, see Figure 5, a countdown is started in order to reveal the
     currency pair being targeted. In order to mask automatic detection by bots, the information
     is typically revealed as manually modified pictures, which are difficult to read for machines.

   • Pump: The organisers urge their members to buy the coin and hold it in order to inflate the
     price on the short term. If the pump is successful, this leads to an immediate price spike,

                                                  16
       which can often also be recognised by human eye.

     • Dump: After the coin has drastically increased in price, invariably some participants will
       start consolidating their gains by selling the coin. This leads to the price decreasing which
       then leads to a cascading effect of more and more participants selling the coin. This often
       results in the price returning to the level close to the pre-pump level.

     This whole process takes place in a matter of minutes if not seconds. In fact, among the pump
and dump schemes we consider and which we could classify based on graphical comparison, the
longest one lasts 8 minutes and the average duration is about 2.3 minutes. In this case study, we
follow the methodology introduced by La Morgia et al. (2021) and Kamps and Kleinberg (2018).
La Morgia et al. (2021)4 manually collect pump and dump cases by joining the various Telegram /
Discord channels. We are also using these cases in order to verify the results from our algorithm.

3.6. Data analysis
     As mentioned above, we take our data labels from the database created by La Morgia et al.
(2021), which they obtain by collecting information joining more than 100 groups from July 2017
to January 2019. The database consists of a list of what we call as Pump-and-Dump attempts,
which we will abbreviate as PD attempts for the rest of this article. Every entry of the list is made
by

     1. the acronym for the name of the coin, e.g. BTC stands for Bitcoin and ETH for Ethereum,
       usually called symbol of the coin;
     2. the name of the Telegram / Discord group where this information was retrieved;
     3. the date (day) of the PD attempt;
     4. the time (hour and minute) of the PD attempt;
     5. the exchange on which the PD attempt took place.

Using this information and the Python-library ccxt, it is possible to fetch data from exchanges in
a neighbourhood of the PD attempt. In this way, we avoid downloading an overwhelming quantity
of data which would be even difficult to store. For every entry of the aforementioned database, we
decided to download and work with trades, that is all orders that were placed and also realized by
selling or buying cryptocurrencies. Every trade is characterized by the following information:

     1. Symbol which denotes the traded coin. In practice, this is not just one acronym, but it
       refers to the traiding pair, e.g. BTC/USD, where Bitcoins (BTC) are traded using USD (US
       Dollars);
     2. Timestamp, an integer, denoting the UNIX time in milliseconds;
     3. Datetime, i.e. the ISO8601 datetime with milliseconds;

    4
      We would like to personally thank the authors for the long and tedious work done and for the choice of making
these data freely available at https://github.com/SystemsLab-Sapienza/pump-and-dump-dataset.



                                                        17
   4. Side, string, either “buy” or “sell” to distinguish the operation kind: for the symbol BTC/USD
      “buy” means buying BTC using USD, while “sell” means receiving USD for your BTC;
   5. Price, float, indicating the price at which the pair was traded;
   6. Amount, float, denoting the quantity (in base currency, i.e. USD in the example of BTC/USD
      pair) which was traded.

For the moment, all analyses we conducted are made using pairs of the type · /BTC, where BTC
is seen as the base currency. For this reason, why we will not explicitly write the entire pair in the
following. We decided to download all trades in different time intervals: by considering the moment
of the PD attempt as the center of a time window, we retrieved data for intervals ± 1.5, ± 3 days
and ± 7 days, obtaining for every PD attempt intervals of 3, 6 and 14 days respectively. Increasing
here the analysis for ± 7 days has to be treated carefully, as there might be manipulations which
took place without being recorded in the database5 . We also observed that this is indeed the case
for some coins (see, for example, Figure 8).
    The numerical data we used for the analyses required some preprocessing on the raw data.
First of all, we aggregated the data in the same way as in La Morgia et al. (2021), in other words
whenever trades have the same timestamp, side and price, then the trade volumes are summed
accumulated. In that case, one can interpret the trades as one larger trade without losing any
information.
    Furthermore, the variable side was translated into a numerical format by encoding all “buy”
signals as 0.5 and all “sell” as -0.5. In a similar way, we calculate volume as the product of price
and amount. Moreover, prices are used to compute the simple returns. Hence, we use the time
series of the trade time, returns, volume and trade side information to compute the signatures.
Finally, our experiments showed that the normalization of all of these variables to the [0,1] interval
yield better results.
    A visual example of the data that we use is given in Figure 6. We plot the price (top panel) and
volume (bottom panel) against prescribed time interval for the Pump & Dump attempt, which was
in this case successful. In particular, we show the price and volume charts of GRS (Groestlcoin)
against the base currency (BTC) and we plot all the trades which occur in the time interval 31
minutes before and 71 minutes after the prescribed PD time. On the figure, “buy” (“sell”) trades
are shown in red (green).

3.7. PD detection
    Our methodology for detecting the PD attempts has two main steps. As a first step, we use
the data described in the Section 3.6 and we transform it into our features set. In the next step,
we use this features set together with the commonly used anomaly detection algorithms to produce
our final predictions.

    5
      In particular, as the authors of La Morgia et al. (2021) write, they were not able to retrieve information from
groups in Russian or Chinese.



                                                         18
Figure 6: GRS price and volumes around Pump & Dump (successful) attempt which was recorded on 5th March 2019
at 16:30 (UNIX time) - a visual example. In the top plot the lines follow the price evolution through the different
trades, while in the bottom plot we can see the volume in terms of the basis currency (BTC). In both cases, red
colour is used for ‘buy’ trades and the greenorders_GRS_btc_2019-03-05
                                              for ‘sell’ trades.       16.30

             1e 5
      8.00
      7.75
      7.50
      7.25
      7.00
      6.75
      6.50
      6.25


        7
        6
        5
        4
        3
        2
        1
        0
                16:00   16:10   16:20   16:30       16:40        16:50           17:00   17:10      17:20   17:30    17:40
                                                                                                                    2019-Mar-05
                                        buy-price       sell-price         buy-vol       sell-vol



3.7.1. Feature set generation
      We follow the methodology developed in Section 2 to transform the time series data described
in Section 3.6 into the features which can be used by the standard anomaly detection algorithms.
Let
                                                        Dc ⊂ Rn×4

denote the vector of time series composed of trades’ timestamp, side, price, and volume for a coin c.
Here n denotes the number of trades during the pre-specified time interval around the PD attempt
which is chosen to be 1.5, 3 or 7 days. We split the data set Dc into dn/oe subsets of w trades,
where o denotes the offset of how many trades to move forward in time. In other words, we identify
the trade-window specified by w trades and then we move on shifting among the listed trades.
                                                               dn/oe
                                                                 [
                                                     Dc =                Dci .
                                                                 i=1

      Each subset Dci is then transformed into our feature set by calculating either the exact signa-
ture or the randomized signature. Let R̃ci and Rci denote the randomized and exact signatures,
respectively. This process is repeated for all the coins in the data set so that we construct our final




                                                               19
feature set

                                                          [ dn[
                                                              c /oe

                                                   R̃ =                 R̃ci ,
                                                          c        i
                                                              dnc /oe
                                                          [ [
                                                   R=                   Rci ,
                                                          c        i

where the number of trades nc depends on the coin c. In this methodology, the offset o and the
window size w can be seen as hyper-parameters which can be optimized to improve the final results.
   Note that especially the offset o can have a big impact on the run time as the number of samples
per coin will be dn/oe. (Our numerical experiments show that choosing w = 100 and o = 5 yields
a good balance between the run time and precision.
   Including the time dimension, which is clearly non-decreasing, in the features set also helps to
obtain better behaved signatures, in the sense that the signatures in this case are able to uniquely
determine the original time series (see Lemma 2.14 and Lemma 4.8 in Levin et al. (2016) for a
proof6 ). The hyper-parameters used for the feature generation from cryptocurrency data can be
found in table 1.
Remark 3.6. Actually, since we are working with finite data on finite intervals, we can use Fubini’s
theorem to exchange the order of integration inside the signature terms. In particular, we can move
the integral on time as if it were the last integration. This shows that every signature will clearly
encode information generated by paths integrated over time every particular time interval.
For this reason, it is important to note that the time intervals identified by the first and last trades
of the selected window are not uniform throughout our analysis. In fact, because trades are not
equidistant in time, each sample could potentially represent a different time length. Working with
a heterogeneous grid of time is not easy a priori (and this is why La Morgia et al. (2021) first
transform the data into an equidistant time grid. However, the non-equidistant time grid does not
pose a problem to our algorithm, because by including the timestamp in the data set, the correct
time scale is reflected in the calculation of the randomized and exact truncated signatures.

3.8. Anomaly detection algorithms
   Anomaly detection involves being able to distinguish whether an element of the sample belongs
or not to the same distribution which generated the (greatest part of the) sample. Elements of
this latter group are usually called inliers, while elements of the former are commonly referred to
as outliers. The task is of course difficult because we cannot rely on visual inspection for multi-
dimensional data and we do not have a priori a clear description of the “exact” distribution and its
samples. In the literature there are a number of anomaly detection algorithms, each with its own
pros and cons, but most commonly used algorithms share the following steps:

  1. Give a feature set F ⊂ Rn×m consisting of n samples and m features, each sample is inter-
        preted as a point in Rm .

   6
       Essentially, we are avoiding tree-like paths (trajectories that cancel out by themselves as controls).



                                                              20
   2. Using some metric, for each such point the distance to neighboring points is calculated.
   3. Based on the density of points, a 1-dimensional anomaly score is calculated where either
        higher or lower values correspond to more abnormal observations depending on the exact
        algorithm.
   4. Lastly, based on a predetermined contamination rate, a cutoff is set and all samples with an
        anomaly score higher or lower than the cutoff are declared as anomalies.

In our case study, we use the robust covariance and isolation forest anomaly detection algorithms.
These methods are implemented in the Sklearn Python package (Pedregosa et al. (2011)). We refer
the reader to Rousseeuw and Driessen (1999) and Tony Liu et al. (2008) for more details about the
used algorithms.

3.8.1. Robust covariance
   The idea behind the first one is quite simple: the goal is to compute elliptical contours inside
which inscribing the inliers. The ellipsoid is constructed through a robust covariance matrix and
has form:
                             E(Σ, µ, ρ) = x ∈ Rm : (x − µ)0 Σ−1 (x − µ) ≤ ρ2 .
                                         

The robust covariance matrix is built using Minimum Covariance Determinant (MCD) estimator
whose goal is finding which elements in the complete sample yield the empirical covariance matrix
with the smallest determinant, suggesting a “regular” subset of observations from which the location
and covariance matrix are preserved. In particular, we need to fix a fraction 0 < γ < 1 and consider
a subsample of observations (hopefully, inliers), i.e. I ⊂ {O1 , . . . , On } that contains dnγe points.
Subsample mean and covariance are given by
                                              1 X
                                        µ
                                        cI =           Oi ,
                                             |I|
                                                 Oi ∈I

                                        cI = 1
                                                 X
                                        Σ              (Oi − µ         cI )0 .
                                                             cI )(Oi − µ
                                             |I|
                                                   Oi ∈I


The ellipsoid determined by points in I is E(Σ
                                             cI , µ
                                                  cI , ρbI ), where ρbI = inf r>0 PI (E(Σ    cI , r) ≥ γ),
                                                                                        cI , µ
with PI being the empirical measure associated to I. Finally, Mahalanobis distance with the robust
covariance is used to rank outliers. The algorithm is looking for the covariance matrix with lowest
determinant because the volume of the ellipsoid is proportional to the square root of the determi-
nant. The MCD algorithm also has a high breakdown point, which is equal to [(n − m + 1)/2].
Inconveniences of this method are the fact that data are supposed to belong to an elliptical dis-
tribution and that to compute the covariance matrix (in a sufficiently reliable way) we need the
number of samples larger than the square of the number of features (n > m2 )7 , which imposes
another condition to the truncation degree used in our algorithm, but which can easily accounted
for in case of randomized signatures.

   7
       This condition is actually requested by the algorithm in the Sklearn package.


                                                           21
The algorithm was mainly developed by Rousseeuw, starting from Rousseeuw (1985) and it be-
came popular in 1999, thanks to Rousseeuw and Driessen (1999), where a faster version of the
same procedure was formulated. For extensions and other results, we suggest Hubert et al. (2017)
(and references therein).

3.8.2. Isolation forest
   The second anomaly detection algorithm we use is called isolation forests and was first published
in Tony Liu et al. (2008). The idea of this algorithm is to recursively partition the data until either
all unique points are separated or a predefined limit is reached. The recursion of partitions is
expressed as a proper binary tree, where each node has either two or zero descendants.
Definition 3.7. The path length h(x) of a point x is the height of the point x is the random tree.

   Intuitively points, which are anomalies, are easier to separate from the other points, which
results in lower height scores h(x). The reason for this is that anomalies lie outside of clusters,
which is why a random partition will end up isolating the point more quickly and hence yield a
lower height score h(x). An isolation forest consists of a sample of these random trees where the
height scores are averaged. The height h(x) can not directly be used as an anomaly score, because
the average height is given by log n where n is the number of points in the input data. As such,
the height can not be directly compared across different samples and a normalisation is required.
Given an input data set of n points, we define

                                  c(n) = 2H(n − 1) − (2(n − 1)/n)
                                                Pi    1
where H(i) is the harmonic number given by        k=1 k . The anomaly scores is then defined as

                                                           E(h(x))
                                                       −
                                         s(x, n) = 2        c(n)




where E(h(x)) is the averaged height from the isolation forest. As discussed, anomalies should
yield lower E(h(x)), which is why high scores of s(x, n) indicate anomalies. Interestingly, isolation
forest work better with smaller data sets, which is why sub-sampling methods are used. Note that
this is directly contrary to the robust covariance method, where, for fixed number of features, more
points are preferable to construct the ellipsoid. This also give an intuitive reason, why isolation
forests work well with both truncated exact signatures and random signatures, as is discussed in
the subsequent section.

3.9. Results
   In order to evaluate the quality of our anomaly detection algorithm, we compare our predictions
with the manually labeled PD attempts. We evaluate our predictions by considering 1.5, 3, and
7 days before and after each PD attempt. Choosing a longer time interval makes the predictions
more useful but at the same time carries the risk of PD attempts to be absent from our data set. As
a benchmark, we use the anomaly detection method employed by Kamps and Kleinberg (2018)). In
this method, anomalies are labeled by considering volatility spikes and price spikes. They describe

                                                  22
Figure 7: Example of labeled anomalies by signature (green diamond) and benchmark predictions (green circle),
while in purple it is time window of the PD attempt.




the best configuration setting as the volume spike threshold to be Vspike = 300% and the price spike
threshold to be Sspike = 105%. This means that time windows are labeled as anomalies, if they
contain both a volume and price increase higher than the threshold compared to a moving average.
In order to obtain a full precision-recall plot, we linearly interpolate the threshold Vspike between
0% and 300% and Sspike between 0% and 105%. This also enables us to compare the algorithms on
the full precision-recall plot while ensuring that the benchmark configuration is always considered.
As the main metric to evaluate our results we consider the maximum of the F1 scores across the
precision-recall plot.
Definition 3.8 (F1 score). The F1 score is defined as the harmonic mean between precision and
recall, i.e. F1 = 2/(p−1 +r−1 ). It measures of the classifier’s accuracy by merging precision and recall
in one metric and its values range between 0 (worst case) and 1 (base case). Since it is defined as
a harmonic mean, it gives more weight to smaller “values”, thus a classifier has a high F1 score
only when both precision and recall are high.

   Following Kamps and Kleinberg (2018), we aggregate our results to hourly windows. Figure 7
shows an example where the predictions using signatures produce more accurate results as there
are less false positives compared to the benchmark. This result is not surprising as the benchmark
model produces many false positives since it does not quantify by how much the volatility and price
thresholds are breached. Additionally, the benchmark prediction was not able to detect the real
PD attempt, as the price spike was not high enough to breach the threshold.
   Figure 8 shows a less successful example where, even though the reservoir prediction correctly
labels PD attempts, it also incorrectly labels other time windows as PD attempts. Visual inspection
of the price plot shows that both the reservoir prediction and the benchmark prediction incorrectly

                                                     23
Figure 8: Example of mislabelling by signature (green diamond) predictions close to the line denoting 21st July 2018,
while in purple the time window of the PD attempt. The other outlier identified by signatures before 23rd July might
be a correct guess that was not recorded in the dataset.




marks another significant price spike as a PD attempt. Additionally, there is also a wrong classifi-
cation by the reservoir prediction around 21st July 2018 in the figure where an unusual price drop
occurs. This can be explained by the fact that the reservoir prediction is an unsupervised learning
method hence there is no way of learning that unusual price dip should not be considered as an
anomaly.
    In the following, we present our results using the complete data set described in Section 3.6.
In order to compare our results with the ones from La Morgia et al. (2021), we first consider 3
days interval for each PD attempt. As Figure 9 clearly shows both the isolation forest predictions
and the robust covariance predictions using random signatures as a feature set outperform the
benchmark model for almost every given recall.




                                                         24
Figure 9: Results for random signatures for both the isolation forest and robust covariance methods. The figures
show precision-recall plots for the random signature predictions. The vertical lines show the respective recall values,
where the maximum of the F1 scores was achieved.




    Figure 10 shows, that the isolation forest predictions using exact truncated signatures shows
similar results to the ones obtained using random signatures. On the other hand, the robust covari-
ance predictions using exact truncated signatures under-performs even compared to the benchmark.
The problem with the robust covariance method using exact signatures features is a consequence of
the matrix bad condition number which shows warnings during the training step. It is interesting
to note that we did not observe the same result for random signatures and this can be explained by
the fact that randomness can act as a method for implicit regularisation. Two possible references
for this behavior are Heiss et al. (2019), in the context of shallow neural networks, and Jacot et al.
(2020), for random features extracted by a Gaussian process used for kernel regression. Explicit
regularisation of the exact reservoirs might help with the bad condition number but experiments
of this kind have not been performed by the authors.
    The fact that results for isolation forest show comparable results suggests that random signa-
tures and truncated exact signatures contain a similar amount of information. This is unsurprising,
as the randomized signatures are an approximation of the exact signatures in a lower dimension
and should therefore approximate the information contained in the exact signature.
    Table 3 shows the full results obtained in our experiments. As expected, for every classifier, the
results get worse the detection duration increases. The main reason for this is that the chance of us
missing PD attempts in our data set increases and also there are more unusual market behaviors
which makes the classification harder in general.
    For isolation forests, both the randomized signatures and the truncated signatures show similar
results for each time window. As previously discussed, the exact signatures show poor performance


                                                          25
Figure 10: Results for exact truncated signatures for both the isolation forest and robust covariance methods.
Compared to figure 9, the robust covariance method algorithm significantly worse while the isolation forest algorithm
shows similar results.




for the robust covariance algorithm.
    Excluding the results for using exact truncated signatures with the robust covariance algorithm,
our results outperform the results in Kamps and Kleinberg (2018) for all time windows. Due to
the complexity of their method, we did not fully replicate the results described in La Morgia et al.
(2021) and hence we are only able to compare the results for the ± 1.5 days time window. Even
their results are significantly better in terms of F1 score, our best classifier comes relatively close.
Here we would like to emphasize that the classifier used in La Morgia et al. (2021) is based on
supervised learning, while our classifier and the one in Kamps and Kleinberg (2018) are based on
unsupervised learning.
    Compared to supervised learning, our methodology has the big advantage, that there is no need
for labeled training data and can hence be used without the need for manually collecting pump
and dump cases. Additionally, given the generic nature of our method, it can potentially also be
employed for the detection of other kinds of market anomalies.




                                                         26
                                    Table 3: Anomaly detection performance

                           Classifier                        Days    Precision   Recall     F1
                          Kamps et al.                        3        65%        86%      74%
                                                               6       48%        86%      62%
                                                              14       29%        81%      43%
                        La Morgia et al.a                      3       98%        91%      95%
                                                               6         -          -        -
                                                              14         -          -        -
            Randomized signature (Isolation forest)           3        93%        83%      88%
                                                               6       82%        83%      82%
                                                              14       75%        75%      75%
          Randomized signature (Robust covariance)            3        80%        94%      86%
                                                               6       80%        84%      82%
                                                              14       75%        75%      75%
          Exact truncated signature (Isolation forest)         3       83%        92%      87%
                                                               6       81%        82%      81%
                                                              14       71%        74%      72%
        Exact truncated signature (Robust covariance)          3       61%        61%      60%
                                                               6       61%        47%      54%
                                                              14       58%        32%      44%
Table 3 shows the full results for our classifiers together with the results from Kamps and Kleinberg (2018)
and La Morgia et al. (2021). The results from La Morgia et al. (2021) were not replicated by the authors
and are taken directly from their paper as comparison. Here for each methodology and detection duration,
the maximum F1 score together with the precision and recall score at which it was obtained are displayed.
    a
      In their methodology, the authors use cross validation in order to compute the out of sample performance. As
our methodology does not have use a training / test set split, results of might vary slightly even though the same
overall data set is used. Therefore, the results here are only of an indicative nature.


4. Conclusion

    In this article, we explore the usage of randomized and truncated signatures as a feature set
for anomaly detection purposes. As an empirical application, we first show how to detect real
and fake trajectories of stock prices which are indistinguishable by visual inspection. Second,
we investigate pump and dump schemes in the cryptocurrency ecosystem. Our analysis shows
that both randomized and truncated signatures yield promising results as non-linear inputs for
well established anomaly detection algorithms. In particular, our work reveals that the use of
signatures can significantly improve anomaly detection algorithms purely based on price and volume
spikes. Furthermore, given the remarkable level of precision and recall achieved by our unsupervised
learning algorithm, which are comparable to the results obtained from supervised learning, we are
able to show that all necessary information to identify the pump and dump operations in the
cryptocurrency market is already inherited in the historical time series of the related trades. More
specifically, historical values of trade price, volume, date&time, and side information are the only
inputs in our machine learning algorithm.
    Our findings also have important implications for the market efficiency. Clearly, cryptocurrency
markets attract increasing attention from the investment community due to the recent advances


                                                       27
in their underlying technology. Cryptocurrencies now constitute an important asset class both for
researchers and traders. In particular, the introduction of related derivative products will complete
the market; enlargement by liquidity pools and non-fungible tokens will help to increase market
efficiency. Since our work shows that unsupervised learning algorithms, which only use publicly
available information to detect anomalies, achieve a similar performance as the supervised learning
algorithms, market efficiency is supported. In fact, this carries an important message both for
market designers and regulators since they can use our work to design or improve the market
conditions so that certain types of anomalies do not appear. Furthermore, we also show that
signatures are very successful in extracting valuable features from the input data hence this can
also be used by traders to develop successful investment strategies.
   Last but not least, the small difference between the results obtained by truncated signatures and
randomized signatures empirically confirms the theory developed in Section 2. As the tasks explored
in this article are relatively low dimensional, it is still feasible to compute exact signatures up to a
relatively high degree. As the number of coefficients for the exact signatures grows exponentially in
the degree (and polynomially in the path dimension), higher dimensional problems can make the
computation of exact signatures infeasible. For these sorts of problems, for example in Wang et al.
(2019), dyadic signatures have been used, which approximates higher order signatures using lower
order signatures on path segments. In this article, we show that randomized signatures can be an
alternative method to approximate the exact signatures. This, in turn, also serves as a robustness
check for our newly developed methodology of randomized signatures.
   As future work, it would be interesting to preprocess the data to reflect the prior knowledge
that we have about PD attempts by prescribing a certain kind of pattern as the one described
in Section 3.5. Hence, our algorithm can be improved by processing the input data to reflect the
prior knowledge. Other possible future directions for this research are to investigate whether the
methods can be improved by considering multiple currency pairs as inputs, which would also take
correlations into account, or to modify outlier detection algorithms with new and more sophisticated
variants.




                                                  28
References

Baudoin, F., Zhang, X., 2012. Taylor expansion for the solution of a stochastic differential equation
  driven by fractional Brownian motions. Electron. J. Probab. 17, no. 51, 21. URL: https:
  //doi.org/10.1214/EJP.v17-2136, doi:10.1214/EJP.v17-2136.

Breiman, L., Friedman, J., Charles J., S., R. A., O., 1984. Classification and regression trees.

Chandola, V., Banerjee, A., Kumar, V., 2009. Anomaly detection: A survey. ACM computing
  surveys (CSUR) 41, 1–58.

Chevyrev, I., Kormilitzin, A., 2016. A primer on the signature method in machine learning .

Choi, Y.S., 2009. Least squares one-class support vector machine. Pattern Recognition Letters 30,
  1236–1240.

Cochrane, T., Foster, P., Lyons, T., Arribas, I.P., 2020. Anomaly detection on streamed data.
  arXiv preprint arXiv:2006.03487 .

Cuchiero, C., Gonon, L., Grigoryeva, L., Ortega, J.P., Teichmann, J., 2021. Discrete-time signatures
  and randomness in reservoir computing. IEEE Transactions on Neural Networks and Learning
  Systems Forthcoming. doi:10.1109/TNNLS.2021.3076777.

Cuchiero, C., Larsson, M., Teichmann, J., 2020. Deep neural networks, generic universal in-
  terpolation, and controlled ODEs.       SIAM J. Math. Data Sci. 2, 901–919.         URL: https:
  //doi.org/10.1137/19M1284117, doi:10.1137/19M1284117.

Dempster, A.P., Laird, N.M., Rubin, D.B., 1977. Maximum likelihood from incomplete data via
  the em algorithm. Journal of the Royal Statistical Society: Series B (Methodological) 39, 1–22.

Edgeworth, F.Y., 1887. Xli. on discordant observations. The london, edinburgh, and dublin philo-
  sophical magazine and journal of science 23, 364–375.

Fama, E.F., 1970. Efficient capital markets: A review of theory and empirical work. The Journal
  of Finance 25, 383–417.

Fama, E.F., 1976. Efficient capital markets: reply. The Journal of Finance 31, 143–145.

Fix, E., Hodges, J.L., 1989. Discriminatory analysis. nonparametric discrimination: Consistency
  properties. International Statistical Review/Revue Internationale de Statistique 57, 238–247.

Friz, P.K., Victoir, N.B., 2010. Multidimensional Stochastic Processes as Rough Paths: Theory
  and Applications. Cambridge Studies in Advanced Mathematics, Cambridge University Press.
  doi:10.1017/CBO9780511845079.

Grigoryeva, L., Ortega, J.P., 2018. Echo state networks are universal. Neural Networks Forthcom-
  ing. doi:10.1016/j.neunet.2018.08.025.

                                                 29
Heiss, J., Teichmann, J., Wutte, H., 2019. How implicit regularization of neural networks affects the
  learned function - part I. CoRR abs/1911.02903. URL: http://arxiv.org/abs/1911.02903,
  arXiv:1911.02903.

Hubert, M., Debruyne, M., Rousseeuw, P.J., 2017. Minimum covariance determinant and exten-
  sions. WIREs Computational Statistics 10. URL: http://dx.doi.org/10.1002/wics.1421,
  doi:10.1002/wics.1421.

Ivakhnenko, A.G., Lapa, V.G., 1967. Cybernetics and forecasting techniques. volume 8. American
  Elsevier Publishing Company.

Jacot, A., Şimşek, B., Spadaro, F., Hongler, C., Gabriel, F., 2020. Implicit regularization of random
  feature models. arXiv:2002.08404.

Kamps, J., Kleinberg, B., 2018. To the moon: defining and detecting cryptocurrency pump-and-
  dumps. Crime Science 7.

Kiraly, F.J., Oberhauser, H., 2019. Kernels for sequentially ordered data. Journal of Machine
  Learning Research 20, 1–45. URL: http://jmlr.org/papers/v20/16-314.html.

Kohonen, T., 1982. Self-organized formation of topologically correct feature maps. Biological
  cybernetics 43, 59–69.

La Morgia, M., Mei, A., Sassi, F., Stefa, J., 2021. The Doge of Wall Street: Analysis and Detection
  of Pump and Dump Cryptocurrency Manipulations .

Levin, D., Lyons, T., Ni, H., 2016. Learning from the past, predicting the statistics for the future,
  learning an evolving system. Papers 1309.0260. arXiv.org. URL: https://ideas.repec.org/p/
  arx/papers/1309.0260.html.

Lyons, T., 2014. Rough paths, Signatures and the modelling of functions on streams URL: http:
  //arxiv.org/abs/1405.4537, doi:10.1049/iet-rsn.2017.0265, arXiv:1405.4537.

Lyons, T., Caruana, M., Lévy, T., 2007. Differential Equations Driven by Rough Paths. Springer,
  Berlin. doi:10.1007/978-3-540-71285-5_5.

Miljković, D., 2011. Fault detection methods: A literature survey, in: 2011 Proceedings of the 34th
  international convention MIPRO, IEEE. pp. 750–755.

Mityagin, B., 2015. The zero set of a real analytic function. arXiv:1512.07276.

Pearl, J., 1985. Bayesian netwcrks: A model cf self-activated memory for evidential reasoning,
  in: Proceedings of the 7th conference of the Cognitive Science Society, University of California,
  Irvine, CA, USA, pp. 15–17.




                                                  30
Pedregosa, F., Varoquaux, G., Gramfort, A., Michel, V., Thirion, B., Grisel, O., Blondel, M.,
  Prettenhofer, P., Weiss, R., Dubourg, V., Vanderplas, J., Passos, A., Cournapeau, D., Brucher,
  M., Perrot, M., Duchesnay, E., 2011. Scikit-learn: Machine learning in Python. Journal of
  Machine Learning Research 12, 2825–2830.

Reizenstein, J., Graham, B., 2020. Algorithm 1004: The iisignature library: Efficient calculation
  of iterated-integral signatures and log signatures. ACM Transactions on Mathematical Software
  (TOMS) .

Rousseeuw, P., 1985. Multivariate estimation with high breakdown point. Mathematical Statis-
  tics and Applications Vol. B , 283–297URL: https://wis.kuleuven.be/stat/robust/papers/
  publications-1985/rousseeuw-multivariateestimationhighbreakdown-1985.pdf, doi:10.
  1007/978-94-009-5438-0_20.

Rousseeuw, P.J., Driessen, K.V., 1999. A fast algorithm for the minimum covariance determinant
  estimator. Technometrics 41, 212–223.

Sabahi, F., Movaghar, A., 2008. Intrusion detection: A survey, in: 2008 Third International
  Conference on Systems and Networks Communications, IEEE. pp. 23–26.

Sharpe, W.F., 1970. Efficient capital markets: a review of theory and empirical work: discussion.
  The Journal of Finance 25, 418–420.

Suykens, J.A., Vandewalle, J., 1999. Least squares support vector machine classifiers. Neural
  processing letters 9, 293–300.

Tony Liu, F., Ming Ting, K., Zhou, Z.H., 2008. Isolation Forest ICDM08. Icdm .

Wang, B., Liakata, M., Ni, H., Lyons, T., Nevado-Holgado, A., Saunders, K., 2019. A path
  signature approach for speech emotion recognition, pp. 1661–1665. doi:10.21437/Interspeech.
  2019-2624.

West, J., Bhattacharya, M., 2016. Intelligent financial fraud detection: a comprehensive review.
  Computers & security 57, 47–66.

Xu, J., Livshits, B., 2019. The anatomy of a cryptocurrency pump-and-dump scheme. Proceedings
  of the 28th USENIX Security Symposium , 1609–1625.


List of Figures

   1    Sample paths of Geometric Brownian Motion (GBM) used as synthetic data. Pa-
        rameters are µ = 0.25, σ = 0.2 and each path, representing 1 year, is made by 252
        steps. All trajectories are shifted subtracting S0 = 100. . . . . . . . . . . . . . . . . . 10



                                                 31
2    Histogram of the number of consecutive increases/decreases in the paths. Fake GBM
     do not have any combination of more than 5 consecutive increases/decreases along
     their paths. . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 11
3    ROC curve (left) and PR curve (right) for the classification task of differentiating
     paths of the form 1. Both figures show very similar results for the exact truncated
     signatures and the random signatures. . . . . . . . . . . . . . . . . . . . . . . . . . . 13
4    The x-axis shows ordered model outputs for 10 separate quantiles. The y-axis shows
     the accuracy of given set of model outputs. Here one can see that accuracy is higher
     for model outputs, which are farther from the cutoff. . . . . . . . . . . . . . . . . . . 14
5    Example of a web page collecting pump and dump channels . . . . . . . . . . . . . . 16
6    GRS price and volumes around Pump & Dump (successful) attempt which was
     recorded on 5th March 2019 at 16:30 (UNIX time) - a visual example. In the top
     plot the lines follow the price evolution through the different trades, while in the
     bottom plot we can see the volume in terms of the basis currency (BTC). In both
     cases, red colour is used for ‘buy’ trades and the green for ‘sell’ trades. . . . . . . . . 19
7    Example of labeled anomalies by signature (green diamond) and benchmark predic-
     tions (green circle), while in purple it is time window of the PD attempt. . . . . . . 23
8    Example of mislabelling by signature (green diamond) predictions close to the line
     denoting 21st July 2018, while in purple the time window of the PD attempt. The
     other outlier identified by signatures before 23rd July might be a correct guess that
     was not recorded in the dataset.     . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 24
9    Results for random signatures for both the isolation forest and robust covariance
     methods. The figures show precision-recall plots for the random signature predic-
     tions. The vertical lines show the respective recall values, where the maximum of
     the F1 scores was achieved. . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 25
10   Results for exact truncated signatures for both the isolation forest and robust co-
     variance methods. Compared to figure 9, the robust covariance method algorithm
     significantly worse while the isolation forest algorithm shows similar results. . . . . . 26




                                               32