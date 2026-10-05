source: https://arxiv.org/pdf/2603.04525
fetched_utc: 2026-10-04T18:45:02Z
bytes_raw: 1044848

THE VOLTERRA SIGNATURE

                                                   PAUL P. HAGER, FABIAN N. HARANG, LUCA PELIZZARI, AND SAMY TINDEL


                                                   Abstract. Modern approaches for learning from non-Markovian time series, such as
                                                   recurrent neural networks, neural controlled differential equations or transformers, typ-
                                                   ically rely on implicit memory mechanisms that can be difficult to interpret or to train
                                                   over long horizons. We propose the Volterra signature VSig(x; K) as a principled, explicit
                                                   feature representation for history-dependent systems. By developing the input path x
arXiv:2603.04525v2 [stat.ML] 21 May 2026




                                                   weighted by a temporal kernel K into the tensor algebra, we leverage the associated
                                                   Volterra–Chen identity to derive rigorous learning-theoretic guarantees. Specifically, we
                                                   prove an injectivity statement (identifiability under augmentation) that leads to a univer-
                                                   sal approximation theorem on the infinite dimensional path space, which in certain cases
                                                   is achieved by linear functionals of VSig(x; K). Moreover, we demonstrate applicability
                                                   of the kernel trick by showing that the inner product associated with Volterra signatures
                                                   admits a closed characterization via a two-parameter integral equation, enabling numer-
                                                   ical methods from PDEs for computation. For a large class of exponential-type kernels,
                                                   VSig(x; K) solves a linear state-space ODE in the tensor algebra. Combined with inher-
                                                   ent invariance to time reparameterization, these results position the Volterra signature
                                                   as a robust, computationally tractable feature map for data science. We demonstrate
                                                   its efficacy in dynamic learning tasks on real and synthetic data, where it consistently
                                                   improves classical path signature baselines.




                                                                                     1. Introduction

                                              Memory-effects in real-world data streams are ubiquitous: their future evolution de-
                                           pends not only on the current state but also on the history of the signal, often in intricate
                                           ways, with different importance assigned to distant versus recent changes and to periods
                                           corresponding to different regimes. To name only a few examples of history-dependent phe-
                                           nomena, we mention biological and neuroscientific systems exhibiting synaptic plasticity
                                           and delay effects [42, 64], memory in disease spread models [21], the long- and short-range
                                           dependence observed in realized volatility [31, 40, 46] and a variety of engineering and
                                           signal-processing applications featuring long or short memory [20, 65, 23, 24].
                                              To learn such phenomena from data, increasingly complex architectures such as re-
                                           current neural networks (RNNs) [38, 58], long short-term memory networks (LSTMs) [55],
                                           Transformers [82, 83], and more recently structured State Space Models (SSMs) like S4 and
                                           Mamba [45, 44, 36] have been introduced and widely employed. These approaches emulate
                                           memory implicitly by storing information about the past in hidden states or attention ma-
                                           trices. While powerful, they often function as highly parameterized “black boxes” [67, 78]:
                                           the learned dependence structure is difficult to interpret, and training can be notoriously
                                           unstable over long horizons due to vanishing or exploding gradients [15, 74]. Moreover,

                                              Date: May 22, 2026.
                                              Key words and phrases. Signatures, machine learning, memory, Volterra equations, Volterra kernel,
                                           rough paths theory.
                                              AMS 2020 Mathematics Subject Classification: 60L10, 60L70, 45D05.
                                           Acknowledgments. FH: This work was supported by the SURE-AI Centre grant 357482, Research Council
                                           of Norway. All authors would like to thank Eduardo Abi Jaber for helpful discussions.
                                                                                               1
                                THE VOLTERRA SIGNATURE                                      2

implicit memory models may require large amounts of data to recover decay structures
that can be encoded a priori in scientific settings [76, 59].
   In contrast, a classical mathematical approach to modeling systems with memory is via
Volterra dynamics, where a kernel K(t, s) explicitly encodes how past inputs at time s < t
influence the present at time t. To make this concrete in discrete time, consider a sequence
of innovations of a signal (∆xti )i=1,...,n driving the system; in our context, these are the
increments of an incoming data stream. Information from the past is then propagated
forward through accumulation,
                                      X
                                            K(tj , ti ) ∆xti .                          (1.1)
                                          i≤j


This quantity can be interpreted as a (first-order) memory state that influences the system
at time tj . Such a kernel-based formulation accounts for long-range effects through the
off-diagonal decay of K (e.g., exponential or power-law decay), short-range effects through
its near-diagonal behavior (e.g., fractional-type behavior), and oscillatory regimes through
periodic terms. Passing now to continuous time, a Volterra model driven by a signal x can
be formulated through the integral equation
                                     Z t
                         zt = z0 +         f (zs ) K(t, s) dxs ,   t ≥ 0,               (1.2)
                                      0

                                           d
where, for simplicity, we interpret dxs as ds xs ds (i.e., x is assumed differentiable). Such
models are standard in control theory [32, 43] and in stochastic analysis [73, 72]. In
domain sciences applications the vector field f is typically specified by a small number of
interpretable parameters. To turn (1.2) into a versatile machine-learning model, one can—
similarly to successful approaches for neural ordinary and neural controlled differential
equations [28, 60]—replace f by a larger parametric model, leading to an instance of a
neural integral equation [84, 17].
   Here we propose a different, representation-based approach by constructing a universal
feature map above (1.2). In this context, the path signature—the sequence of iterated inte-
grals as put forward by Chen [27] and later by Lyons [69]—arises canonically in controlled
and stochastic differential equations as a feature map that separates paths up to reparam-
eterization invariances [49] and yields a universal linearizing feature map for continuous
functionals of paths. These properties have powered a vibrant line of work employing signa-
tures in machine learning tasks on sequential data (see [11, 70, 34] and references therein).
The applicability of the kernel trick [62, 79]—namely, the fact that the signature kernel
can be computed directly and efficiently—has opened up the kernel universe and provided
an additional boost to the field. However, the classical signature is inherently tailored to
differential (local) systems driven directly by the signal—it does not natively encode the
additional, kernel-mediated (global) interactions that define a Volterra (history-dependent)
system.
   This article develops an object called Volterra signature (denoted in the sequel by VSig)
for smooth paths, a kernel-weighted counterpart of the classical signature designed to
add control over the memory effects in signature based modeling and learning. Infor-
mally, VSig(x; K) contains higher-order extensions of the K-weighted memory state de-
fined in (1.1). Formally, it is the collection of iterated integrals arising from the Picard
expansion of linear Volterra equations, i.e., of (1.2) for all linear f .
  Our main contributions can be summarized as follows:
                                 THE VOLTERRA SIGNATURE                                       3

     • Algebraic and analytic structure. We construct VSig in the smooth setting and
       prove a Chen-type identity: VSig is closed under a convolution product that en-
       codes temporal concatenation for Volterra paths. This structure incorporates the
       propagation of information from the past when composing features across time seg-
       ments. We further demonstrate that solutions to linear Volterra equations admit
       a full expansion in terms of the Volterra signature, which thus plays the role of
       a multidimensional resolvent for controlled Volterra equations. For a large class
       of exponential-type kernels (including sums of exponential and periodic kernels),
       we show that VSig can be obtained by solving a state-space ODE. Moreover, for
       K(t, s) = αe−λ(t−s) , we prove an invertible conversion formula to the classical
       signature.
     • Invariance, injectivity, universality and the kernel trick: We provide the theoreti-
       cal foundation for using VSig as a feature map by proving time-reparameterization
       invariance and injectivity (ensuring model identifiability under natural augmen-
       tations). This entails a Stone–Weierstrass-type universality theorem for approxi-
       mating continuous functionals on path space. We also prove universality for linear
       functionals in the case of exponential kernels, leaving the general kernel case as
       an interesting open problem. To complete the picture, we show that the feature
       kernel induced by VSig admits a closed-form characterization via a two-parameter
       integral equation, thereby enabling standard kernel methods.
     • Numerical experiments: We present a collection of experiments demonstrating the
       numerical efficacy of the Volterra signature for learning problems with underlying
       dynamical structure. We begin with a synthetic problem, where the goal is to
       learn the solution map of a stochastic Volterra equation as a function of the driving
       noise. We then move to real-world data and consider S&P 500 time series, where we
       forecast realized volatility. In the third experiment, we classify several UEA time-
       series datasets [6]. In all settings, incorporating a temporal kernel yields substantial
       gains in predictive accuracy over classical signature baselines. The code required
       to reproduce all experiments is available at https://github.com/lucapelizzari/
       Volterra_signature_learning.
   For the practical applicability of a feature map, it is of course crucial to have efficient
algorithms for its computation. For the Volterra signature, these algorithmic aspects are
intricate, as they require resolving both the algebraic and analytic components of the Chen
identity. We therefore address these issues in a companion paper [47], where we derive
efficient algorithms applicable to a wide range of kernels, including fractional and gamma
kernels. The algorithms presented in [47] are implemented in the publicly available package
tensordev; see https://github.com/hagerpa/tensordev. The latter supports general
higher-order schemes for computing the Volterra signature, which due to the underlying
Volterra structure exhibit quadratic scaling in the number of time steps. For convolutional
kernels, however, this cost can be reduced to almost linear complexity, of order O(J log(J)),
by exploiting fast Fourier transforms (FFT). For exponential-type kernels, this can be
pushed further: as foreshadowed by the state-space ODEs presented in this paper, the
Volterra signature can be computed with a cost that scales linearly in the number of time
steps.
   While the above covers the most essential questions for the employment of VSig in data
science, it also opens a wide-ranging programme of mathematical questions and possibilities
for tackling challenging learning tasks. To name a few directions on the theoretical side,
we have not yet developed a precise algebraic structure satisfied by the Volterra signature.
Some work in this direction has been done in [52, 22]; however, the representations of
                                 THE VOLTERRA SIGNATURE                                        4

Volterra signatures for exponential kernels given below suggest that simpler structures
may arise in this case. Another question of interest is to characterize the class of paths
with trivial Volterra signature, which again deviates from the tree-like equivalence in the
classical signature setting. Finally, when transitioning from smooth drivers x to stochastic
processes such as Brownian motion, the Volterra signature can still be defined via the
canonical lift of [51]. From the computational perspective adopted in this paper, where
the signal x is obtained by smooth interpolation, a further pressing question concerns
Wong–Zakai-type limit results, with renormalization required in the singular-kernel case,
as in [48, 12].
   Beyond the numerical examples studied in this paper, there are several further applica-
tion areas in which the Volterra signature may offer advantages over the classical signature.
For instance, we expect VSig to perform particularly well in dynamical learning tasks, such
as reinforcement learning, and in settings where the underlying structure exhibits station-
arity, long-range dependence, or fractional scaling relations. Furthermore, damped periodic
kernels (Prony) within the Volterra signature framework appear especially promising, and
they could lead to a powerful class of path-dependent models in mathematical finance.
Finally, and perhaps most intriguingly, further exploration of kernel learning within the
Volterra signature framework provides a natural next step, for instance in path-dependent
regression. Conditional time-series generation in the spirit of [66] provides a natural ap-
plication, where Volterra signature kernels can be used to define MMD-type losses with
explicit control of the memory structure through the choice of Volterra kernel.
Related literature. The definition of the Volterra signature and its Chen relation are
rooted in the analytic construction of Volterra rough paths in [51, 52]. In extension to
classical rough path theory, these works establish continuity properties of the solution
map for singular Volterra equations. As such, they are related to other extensions, most
notably those based on regularity structures [12, 22]. However, these analytic results
will not play a direct role here, as we focus primarily on the nonsingular case and on the
expressive properties of the full lift. While there are general approaches to defining features
from regularity structures [29], this has not yet been developed for the Volterra setting.
By contrast, other extensions of rough path theory, such as branched rough paths, have
already been suggested for use in data science [37, 4].
   More closely related to the data-science context, the work [57] is the closest to the
present paper. It introduces a modification of the signature with exponentially fading
memory (EFM), providing an alternative way to incorporate an exponential kernel. This
approach exploits the fact that the Volterra equation (1.2) with K(t, s) = αe−λ(t−s) can
be rewritten in a Markovian (mean-reverting) dynamical form, which naturally induces
dynamics on the signature group. While this has the strong advantage that the EFM
signature retains the classical algebraic properties of the signature, it is tightly tied to the
exponential-kernel setting. In contrast, our approach lifts the Volterra equation directly,
which alters the algebraic structure, but applies to any suitably integrable memory-kernel.
Finally, on the architectural side, our formulation of finite state space kernels provides a
rigorous tensor-algebraic counterpart to the linear continuous-time memory mechanisms
driving recent deep learning state space models [45, 44], a connection we formalize in
Section 2.5.
Organization of the paper. We begin by formally defining the Volterra signature and
establishing its convolutional Chen property in Section 2, including a brief preliminary on
tensor-algebra notation. In Section 2.3 we characterize VSig as the solution to a funda-
mental linear Volterra equation in the tensor algebra. In Section 2.4 we prove a dynamical
                                   THE VOLTERRA SIGNATURE                                     5

representation of VSig for a large class of exponential-type kernels. Section 3 then develops
key properties of reparameterization invariance, injectivity, universality and the applicabil-
ity of the kernel trick. Finally, in Section 4 we demonstrate the effectiveness of the Volterra
signature in numerical experiments on synthetic and real data.

                               2. The Volterra signature

   This section is devoted to introduce the definition and fundamental properties of the
Volterra signature studied in this article. While some notions here are borrowed from [51],
we focus exclusively on smooth Volterra paths and signatures. We will present a bottom-
up construction of the Volterra signature, starting from the coordinate-wise definition as
a sequence of iterated Volterra integrals. In analogy with the classical signature, we show
that the intrinsic definition can be characterized via a fundamental Volterra equation in the
tensor algebra. This formulation immediately yields the associated Chen’s relation with
respect to a suitable convolution-type tensor product ⊛. We justify the terminology “fun-
damental” by showing that the Volterra signature acts as a resolvent for linear controlled
Volterra equations. Finally, we study a class of finite-state-space kernels which allow one
to realize Volterra signatures as solutions to a mean-reverting system of equations, which
are later exploited in the numerical experiments of Section 4.

2.1. Preliminaries. Before defining our main objects of study, let us introduce some
general notation which will be used throughout the article. We start by labeling our
notation for simplexes.
Definition 2.1. The n-simplex in a hypercube [s, t]n is defined by
                       ∆ns,t := {(r1 , . . . , rn ) ∈ [s, t]n | r1 ≤ · · · ≤ rn }.        (2.1)
Whenever the underlying interval [s, t] is not relevant (or whenever it is clear from context),
we simply write ∆n .

Next we will need the notion of words created from an alphabet in order to properly define
our notion of signature.
Definition 2.2. For any d ∈ N≥1 we set Ad := {1, . . . , d} and call it an alphabet with d
letters. A word in the alphabet Ad of length n ∈ N is given by w = i1 · · · in where ik ∈ Ad
for all k = 1, . . . , n. We denote by Wdn the set of all words of length n ∈ N from the
alphabet Ad . For n = 0 we write Wd0 = {∅}, where ∅ is the empty word. We further let
Wd denote the set of all words over the alphabet Ad . For a word w = i1 · · · in ∈ W we
denote the length of the word by |w| = n, so that Wdn = {w ∈ Wd : |w| = n}. Whenever
the dimension d is not important or otherwise well understood, we simply write W or A.
Eventually we introduce the algebra R⟨Ad ⟩ = T (vectR (Ad )), the vector space generated
by Wd .

We now define concatenations of two words in W.
Definition 2.3. On the set of words Wd we introduce the concatenation product by setting,
for two words w = i1 · · · in ∈ Wdn and v = j1 · · · jm ∈ Wdm ,
                               wv = i1 · · · in j1 · · · jm ∈ Wdn+m .
In particular, for concatenation with the empty word we set w∅ = ∅w = w. In other words,
Wd forms the free non-commutative monoid with neutral element ∅ over the indeterminates
                                 THE VOLTERRA SIGNATURE                                         6

Ad . The free algebra over Ad is then represented by
                                                                            
                      X                                                     
      R⟨Ad ⟩ := ℓ =        αw w αw ∈ R, αw ̸= 0 for only finitely many w ∈ Wd ,
                                                                            
                       w∈Wd

where the concatenation product on Wd extends by bilinearity to a product on R⟨Ad ⟩.

   The algebraical dual of R⟨Ad ⟩ consist of infinite series of words, which will play a crucial
role to use. We will represent these objects as tensor series over the euclidean vector space
V = Rd . The basic notions we will use are summarized below.
Definition 2.4. Let {e1 , . . . , ed } ⊂ V be a basis. Set V ⊗0 = R and for n ∈ N≥1 denote
by V ⊗n the n-fold tensor power of the vector space V . For any word w = i1 · · · in ∈ Wd
we define ew = ei1 ⊗ · · · ⊗ ein ∈ V ⊗n and note that {ew | w ∈ Wdn } forms a basis of V ⊗n .
The extended tensor algebra over V is given by the direct product
                                                    Y
                                        T ((V )) :=   V ⊗n ,
                                                 n≥0
which forms a vectors space by componentwise summation and scalar multiplication. For
element in x ∈ T ((V )) we ill use the following equivalent notations as a sequence and as a
formal series for the decomposition into its tensor levels
                                                 X∞
                                 (0)  (1)
                          x = (x , x , . . . ) =     x(n) ∈ T ((V )),
                                                    n=0

so that x(n) ∈ V ⊗n for all n ∈ N.    We define the tensor product ⊗ on T ((V )) in terms of
the concatenation product of basis elements, i.e., ew ⊗ ev = ewv for all w, v ∈ W, which
extends to all of T ((V )) by bilinearity. In particular, for a, x, y ∈ T ((V )) we may write
                                               Xn
          z = a + x ⊗ y,          (n)
                                z =a +   (n)
                                                   x(k) ⊗ y(n−k) ∈ V ⊗n ,       n ∈ N.
                                              k=0

Definition 2.5. We write πn : T (V ) → V ⊗n for the canonical projection, so that πn (x) =
x(n) for all x ∈ T ((V )) and n ∈ N. Furthermore, for N ∈ N we define the tensor truncation
               π≤N : T ((V )) → T ((V )),     x 7→ (x(0) , x(1) , . . . , x(N ) , 0, . . . ).
The image of the truncation map T N (V ) := π≤N T ((V )) is called the truncated tensor
algebra, which indeed forms an algebra under the truncated tensor product
                         x ⊗N y := π≤N (x ⊗ y),           x, y ∈ T N (V ).
Definition 2.6. We define a dual paring
                                ⟨·, ·⟩ : R⟨Ad ⟩ × T ((V )) → R,
by setting ⟨w, ev ⟩ = 1w=v for all v, w ∈ Wd and extending by bilinearity. In this vein we
define components of a tensor series by setting
                        xw = ⟨w, x⟩,         x ∈ T ((V )), w ∈ Wd .
                                 Pn
In particular, any element ℓ = k=1 ℓk wk ∈ R⟨Ad ⟩ defines a linear functional on T ((V ))
by
                                                         Xn
                          ⟨ℓ, ·⟩ : T ((V )) → R, x 7→       ℓk xwk
                                                            k=1

  The above is only one instance of a dual pairing within T ((V )). Another, important
paring is given through the the following natural Hilbert-space in T ((V )).
                                     THE VOLTERRA SIGNATURE                                            7

Definition 2.7. We define the subspace T 2 ⊆ T ((V )) by
                         n                       p           o
                  T 2 := x ∈ T ((V )) ∥x∥T 2 := ⟨x, x⟩T 2 < ∞ ,

where ⟨x, y⟩T 2 := k≥0 ⟨x(k) , y(k) ⟩V ⊗k for all x, y ∈ T ((V )), and ⟨·, ·⟩V ⊗k is defined by the
                  P

Hilbert-Schmidt inner product on V ⊗k , i.e.
                            k
                            Y
            ⟨v, w⟩V ⊗k :=     ⟨vl , wl ⟩,     v = v1 ⊗ · · · ⊗ vk ,       w = w1 ⊗ · · · ⊗ wk ,
                            l=1

where ⟨vl , wl ⟩ = ⟨vl , wl ⟩V denotes the standard product on V = span{e1 , . . . , ed }.

  At last, we will introduce the following concept of extending linear maps on V to linear
operators acting on tensors, as it will be needed later for the expansion of linear Volterra
equations.

Definition 2.8. Let E ∼= Rm be another vector space. We denote by L(V, E) the set of
all linear maps from V to E. When V = E we simply write L(V, V ) = L(V ) for the set
of endomorphisms. Next note that L(V, E) equipped with the usual operator norm forms
a vector space isomorphic to Rn×m . Then for any A ∈ L(V, L(E)) we define a linear map
e : L∞ V → L(E) by setting A(1)
A                              e    = IdE and
       n=0

             e 1 ⊗ · · · ⊗ vn ) = A(vn ) · · · A(v1 ),
             A(v                                                v1 , . . . , vn ∈ V,   n ∈ N≥1 ,   (2.2)

and then extend by linearity.

2.2. Iterated Volterra integrals. This section is devoted to define our main object of
study, that is iterated Volterra integrals of a Lipschitz continuous path x. Related to
this notion, we will also specify what we mean by the Volterra signature. We begin by
introducing the following shorthand.

Notation 2.9. For a LipschitzRcontinuous path x starting in 0, which we denote by x ∈
                                      ·
C 0,1 ([0, T ], Rd ), satisfying x = 0 ẋt dt, we will write dxt = ẋt dt. In particular, for A ∈
L(Rd , Rm ) and an index i ∈ Am = {1, . . . , m} we set
                                                  d
                                                        Aij (ẋjt ) dt.
                                                  X
                                       Ai dxt =                                                    (2.3)
                                                  j=1

2.2.1. Basic definition of Volterra signature. Our generic Volterra path is obtained by
weighting a differentiable path by a kernel K. In the same line as x is assumed to be
differentiable, we will assume that the kernel is sufficiently regular. Specifically, since the
noise x is assumed to be differentiable, it will suffice to suppose integrability of K in the
second variable uniformly over the first one.

Hypothesis 2.10. Consider a matrix-valued kernel K : ∆2 → L(Rd , Rm ). In the sequel we
assume K ∈ L∞,1 (∆2 ; L(Rd ; Rm )), where the latter space stands for the set of measurable
functions on ∆2 which satisfy
                                     Z t
                                 sup     |K(t, s)| ds < ∞,
                                     t∈[0,T ] 0

with | · | denoting here any matrix norm on L(Rd , Rm ).
                                     THE VOLTERRA SIGNATURE                                       8

Example 2.11. Clearly any continuous function K : ∆2 → L(Rd ; Rm ) lies in the space
L∞,1 (∆2 ; L(Rd ; Rm )) alluded to in Definition 2.10. In particular, the constant kernel K ≡
A ∈ L(Rd ; Rm ), as well as sum of matrix exponentials kernel
                        q
                        X
            K(t, s) =         e−λp (t−s) Ap ,   λp > 0,     Ap ∈ Rm×d ,      (s, t) ∈ ∆2 ,
                        p=1
which will be studied in detail in Section 2.4, lie in this class.
Example 2.12. Another relevant class of kernels which fall under the banner of our Hy-
pothesis 2.10 are those K’s admitting at most a fractional singularity of order γ ∈ (0, 1).
Otherwise stated, if we assume |K(t, s)| ≲ |t−s|−γ , then K will be in L∞,1 (∆2 ; L(Rd ; Rm )).
This type of kernel is also at the heart of the analysis for the rough setting in [51]. Note that
this includes fractional kernels of the form K(t, s) = (t − s)β−1 A for some A ∈ L(Rd ; Rm )
and β > 0.

Matrix-valued kernels give us some extra freedom to model data with nontrivial depen-
dence on the past. However, our setting obviously encompasses the case of scalar kernels
considered in [51]. We now set up a notation for this specific case.
Notation 2.13. For fixed d = m and a given one-dimensional kernel k : ∆2 → R satisfying
Hypothesis 2.10, we will identify k(t, s) with the diagonal matrix
                         K(t, s) = diag(k(t, s), . . . , k(t, s)) ∈ Rm×m .                   (2.4)

   With our notion of matrix-valued kernel in hand, we are now ready to introduce the
most general form of Volterra signature considered in this paper. This object summarizes
all the iterated integrals of the signal x weighted by the kernel K.
Definition 2.14. Recall that the simplex ∆ns,t is defined by (2.1) and that the alphabet A
is introduced in Definition 2.2. Consider a signal x ∈ C 0,1 ([0, T ]; Rd ), as well as a kernel K
with values in L(Rd ; Rm ) that satisfies Hypothesis 2.10. We define the Volterra signature
                                                  n and (s, t, τ ) ∈ ∆3 by
VSig component-wise for all n ∈ N, i1 · · · in ∈ Wm
                                                Z n
                                  i1 ···in ,τ
                                                  Y
                       VSig(x; K)s,t          =     K il (rl+1 , rl ) dxrl ,                  (2.5)
                                                 ∆n
                                                  s,t l=1

with the convention rn+1 = τ , where we also recall from Definition 2.9 that K il dx denotes
component il in the Rm valued vector K(τ, ·) dx· .
Remark 2.15. Note in particular that the word w = i1 · · · in in Definition 2.14 is taken
from the alphabet Am , generated from the dimension of the product K dx ∈ Rm . This
is in contrast to the case of classical signatures, where the words are generated over the
alphabet Ad coming from the d-dimensional nature of the path x. Of course, in the case
where K takes the diagonal matrix form in (2.4) with m = d, then the alphabet Am = Ad .
Therefore, in this situation, we keep the same intuitive understanding of the word related to
the signal x. The flexibility introduced in allowing for matrix valued K is often necessary in
practical modeling, as illustrated for example in the theory of Ambit fields [9], or modeling
of commodity derivatives (as illustrated for example in [16]).
Remark 2.16. In view of the above Proposition 2.21 we readily observe that in case K(·, ·) ≡
A ∈ L(Rd , Rm ) the Volterra signature reduces to the usual signature of a smooth path Ax
(as introduced in [26, 69]). Indeed, for n ∈ N and i1 · · · in ∈ Wdn it reads
                                                          Z     n
                                                 i1 ···in
                                                               Y
                               i1 ···in
                    VSig(x; A)          = Sig(Ax)s,t =            Ail dxrl ,          (2.6)
                                                              ∆n
                                                               s,t l=1
                                  THE VOLTERRA SIGNATURE                                         9

The above will serve as a definition for the “usual” or “classical” signature.
Remark 2.17. We stress that in general, unlike the usual signature of a path, VSig(x; K)
does not define a group-like element, i.e., does not admit a (simple) shuffle identity. See
[51, Remark 11] for more details about this fact.

2.2.2. Intrinsic definition of Volterra signature. In order to specify VSig(x; K) in Defini-
tion 2.14, we were given a signal x, a kernel K and every word in W = Wm . However,
in our smooth setting one can achieve a full description of the Volterra signature starting
from its first level only. This first level is denoted by
                            z = {z i = VSig(x; K)i : i = 1, . . . , d}.                     (2.7)
Below we properly define paths of the form (2.7) and see how they relate to the full Volterra
signature.
Definition 2.18. We define the set of differentiable Volterra paths V 1 ([0, T ]; Rm ) as the
set of functions z : ∆2 → Rm : (t, τ ) 7→ ztτ such that
     (i) z is bounded and measurable,
    (ii) z0τ = 0 for all τ ≥ 0,
   (iii) t 7→ ztτ is absolutely continuous for almost every τ ∈ [0, T ].
We further identify V 1 ([0, T ]; Rm ) with its quotient modulo almost everywhere equivalence.
In addition, for z ∈ V 1 ([0, T ]; Rm ) we set
                                                    dz τ
                                           dztτ := t dt.                                 (2.8)
                                                     dt
A norm on V 1 ([0, T ]; Rm ) is then defined by
                                                     Z t
                                                         dzut
                                    ∥z∥V 1 = sup              du.                        (2.9)
                                             t∈[0,T ] 0  du

  As the title of this section indicates, the notion of Volterra path in Definition 2.18 is
more intrinsic than Definition 2.14. Otherwise stated, it does not refer to a specific path
x or a kernel K. One can go back to a more extrinsic version thanks to the lemma below.
Lemma 2.19. Let V 1 ([0, T ]; Rm ) be the space introduced in Definition 2.18. For z : ∆2 →
Rm it holds that z ∈ V 1 ([0, T ]; Rm ) if and only if it is of the form
                                             Z t
                                       ztτ =     K(τ, s) dxs ,                         (2.10)
                                        0
in for some x ∈ C ([0, T ]; R ) and K ∈ L∞,1 (∆2 ; L(Rd ; Rm )).
                 0,1         d


Proof. Clearly, any path of the form (2.10) satisfies the properties (i)-(iii) of Definition 2.18.
Hence, we only have to prove that z ∈ V 1 ([0, T ]; Rm ) is of the form (2.10) for some
x ∈ C 0,1 ([0, T ]; Rd ) and K ∈ L∞,1 (∆2 ; L(Rd ; Rm )).R To this end, we define a finite signed
                                                           τ θ
measure on [0, T ]2 by setting ν([0, t] × [0, τ ]) := 0 zt∧θ    dθ. By differentiability of z it
follows that ν is absolutely continuous with respect to the Lebesgue measure on [0, T ]2 .
Thus by the RRadon-Nikodym theorem there exists a measurable K : [0, T ]2 → R such
that ν(A) = A K(t, s) ds dt. By definition of ν we readily verify that (2.10) holds almost
everywhere on ∆2 with K(τ, t) ∈ Rm ∼      = Rm×1 and x : [0, T ] → R1 defined by xt = t. Since
ν is finite, it is also clear that K ∈ L∞,1 (∆2 ; L(Rd ; Rm )). It is then readily checked that
ztτ can be realized as
                                             Z t
                                       ztτ =     K(τ, s) ds,
                                             0
                                         THE VOLTERRA SIGNATURE                                   10

which finishes our proof.                                                                         □
Remark 2.20. The proof of Lemma 2.19 highlights the non uniqueness of the pair (K, x)
whenever a Volterra path z is given. Indeed, we have simply used K(τ, t) ∈ Rm and xt = t,
while other choices would certainly be in order. To justify why we choose to define the
Volterra signature associated to a given pair (x, K), instead of giving a somewhat less
ambiguous definition directly based on a suitable class of smooth Volterra paths z (defined
below), we note that in the application we have in mind, K is usually fixed but x will vary
(or otherwise x might also be fixed and K may vary). Moreover, in Section 3.2 we will
study the injectivity of the Volterra signature map when keeping either of the components
fixed.

   We are now in a position to prove that one can generate the full signature VSig(x; K)
from its first level.
Proposition 2.21. Let x ∈ C 0,1 ([0, T ]; Rd ) and K ∈ L∞,1 (∆2 ; L(Rd ; Rm )). We consider
the Volterra path z ∈ V 1 ([0, T ]; Rm ) defined by (2.10). Then for every word i1 · · · in ∈ W
it holds
                                 Z
                   i1 ···in ,τ
         VSig(x; K)s,t         =     dzri11,r2 · · · dzrin−1
                                                         n−1
                                                             ,rn
                                                                 dzrinn,τ , (s, t, τ ) ∈ ∆3 , (2.11)
                                   ∆n
                                    s,t

                                 d τ
where we recall that dztτ = dt                                e ∈ C 0,1 ([0, T ]; Rd ) and K
                                  zt . In particular, for any x                            e ∈
L∞,1 (∆2 ; L(Rd ; Rm )), it holds
                                         VSig(x; K) ≡ VSig(e
                                                           x; K)
                                                              e

almost everywhere if and only if
           Z t               Z t
               K(τ, r) dxr =     K(τ,
                                 e r) de
                                       xr ,           for almost every (s, t, τ ) ∈ ∆3 .
              s                      s

Proof. The first statement is a direct consequence of (2.10). It then follows from the
representation (2.11) that the Volterra signature VSig(x; K) only depends on the Volterra
path defined in the first level z = (VSig(x; K)i )i∈A ∈ V 1 ([0, T ]; Rm ). In other words, two
Volterra signatures coincide if their first levels coincide in V 1 ([0, T ]; Rm ), which is precisely
translates to the equivalence condition stated above. Note that the almost everywhere
quantifier comes from the fact that V 1 ([0, T ]; Rm ) was also equipped with almost every
everywhere equivalence.                                                                            □
Definition 2.22. For a Volterra path z ∈ V 1 ([0, T ]; Rm ) we call z = VSig(x; K) the
full lift of z, where (x, K) is any representation of z, i.e., any x ∈ C 0,1 ([0, T ]; Rm ) and
K ∈ L∞,1 (∆2 ; L(Rd ; Rm )) such that (2.10) holds.

2.2.3. Chen’s relation. Our next endeavor is to provide a Chen’s relation for Volterra signa-
tures. The crucial ingredient to express this relation in a concise form is the availability of
suitable convolution product for Volterra paths. In the accompanying work [47], it is shown
how to mitigate this lack of algebraic structure when performing numerical computations.
Definition 2.23. Let z be a Volterra path in V 1 ([0, T ]; Rm ) as given in definition 2.18.
Then for any bounded measurable path y : [0, T ] → R we define the nth order convolution
of y with z by
                               Z
                  1 ···in ,τ
         [y ∗ z]is,t         =   yr1 dzri11,r2 · · · dzrin−1
                                                         n−1
                                                             ,rn
                                                                 dzrinn,τ , (s, t, τ ) ∈ ∆3 , (2.12)
                            ∆n
                             s,t
                                             THE VOLTERRA SIGNATURE                                                       11

for all n ∈ N and i1 · · · in ∈ W. As a convention we also set
                                          [y ∗ z]∅,τ
                                                 s,t = yτ ,         (s, t, τ ) ∈ ∆3 .                                 (2.13)

Remark 2.24. For any Volterra path z ∈ V 1 ([0, T ]; Rm ), recall that the full lift of z is the
proper intrinsic generalization of the Volterra signature from Definition 2.14. It can also
be expressed from (2.12) by setting
                                                 zi1 ···in = [1 ∗ z]i1 ···in ,                                        (2.14)
for every word i1 · · · in ∈ W.
Remark 2.25. While for the smooth case the convolution product (2.14) is defined canon-
ically from the underlying Volterra path, we caution that for the rough case this changes
fundamentally (see [51]). Indeed, in that case the convolution product for the first levels
need to be provided as part of the definition of the Volterra rough path.

  Before stating Chen’s relation, we first collect a few basic properties of the convolution
product which will be used in the sequel.
Lemma 2.26. Consider a Volterra path z and a function y as in Definition 2.23. Then
the following holds true
    (i) For every word i1 · · · in ∈ W, one has the recursive property
                         Z t
                                        1 ···in−1 ,r                     1 ···in ,τ
                               [y ∗ z]is,r           dzrin ,τ = [y ∗ z]is,t         .                                 (2.15)
                                      s
    (ii) Conversely, any n-th order convolution can be expressed in terms of the full signa-
         ture z. Namely, for every word i1 · · · in ∈ W we have
                                             Z t                i2 ···in ,τ
                               i1 ···in ,τ             d i1 ,·
                        [y ∗ z]s,t         =     yu     z ∗z                  du      (2.16)
                                              s       du u         u,t
                                                Z t                   
                                                         d i1 ···in ,τ
                                           =−       yu      z            du.
                                                 s      du u,t
Remark 2.27. Note that both identities (2.15) and (2.16) may serve to define the higher-
order convolution inductively.
Remark 2.28. We have seen in Lemma 2.19 that any Volterra path z ∈ V 1 ([0, T ]; Rm )
admits a representation of the form (2.10). Owing to this representation we easily get
                                             d τ
                                                z = K(τ, σ)ẋσ .
                                            dσ σ
Therefore using Fubini, expressions like the bracket in (2.16) can be conveniently written
as
                        i2 ···in ,τ
             d i1 ,·
               z ∗z
            dσ σ          s,t
                                                  n−1
          Z t Z rn       Z r3                                               !
                                                  Y
        =            ···        K i1 (r2 , σ)ẋσ      K ik (rk+1 , rk ) dxrk K in (τ, rn ) dxrn
               s   s            s                         k=2
                                                            n−1
              Z tZ t          Z t                                                            !
                                                            Y
          =             ···           K in (τ, rn ) dxrn            K ik (rk+1 , rk ) dxrk       K i1 (r2 , σ)ẋσ ,
               s   r2          rn−1                           k=2

for all (σ, s, t, τ ) ∈ ∆4 .
                          These terms arise naturally for the case t = τ when performing
Picard iteration of a linear Volterra equations starting from τ backwards in time.
                                             THE VOLTERRA SIGNATURE                                                             12

Proof of Lemma 2.26. The first identity (2.15) follows directly from Definition 2.23. Hence
we will focus our efforts on the proof of (2.16). To this aim we first consider the case n = 1,
for which one can start again from Definition 2.23. This enables to write
                         Z t           Z t                Z t             ∅,τ
                   i,τ            i,τ         d i,τ               d i,·
            [y ∗ z]s,t =     yr dzr =      yr zr dr =        yr     z ∗z        dr,
                          s             s     dr           s     dr r       s,t

where we have invoked the convention (2.13). The case n ≥ 2 in (2.16) is more conveniently
handled by resorting to a representation of z as in relation (2.10). Then recalling (from
Definition 2.14) that K i (τ, ·) dx denotes the component i in the vector K(τ, ·) dx and
applying Fubini’s theorem we get
                                      Z t Z rn     Z r2     n
                        i1 ···in ,τ
                                                            Y
                 [y ∗ z]s,t         =          ···      yr1   K il (rl+1 , rl )ẋrl drl
                                              s    s            s           l=1
                                             Z tZ t           Z t         n
                                                                          Y
                                         =              ···         yr1         K il (rl+1 , rl )ẋrl drl .
                                              s    r1          rn         l=1
Thus, applying Fubini again we obtain
                                                             n
                        Z t     Z t     Z t                                          !
          i1 ···in ,τ
                                                             Y
                                             i1                 il
   [y ∗ z]s,t         =     yr1     ···     K (r2 , r1 )ẋr1   K (rl+1 , ri )ẋrl drl dr1
                        s               r1        rn                            l=2
                                                                                  n
                       Z t             Z t Z rn         Z r3                                                      !
                                                                d i1 ,r2         Y
                   =         yr1                  ···             z                   K il (rl+1 , rl )ẋrl drl       dr1   (2.17)
                        s               r1   r1          r1    dr1 r1
                                                                                l=2
                       Z t                    i2 ···in ,τ
                                       d i1 ,·
                   =         yu         z ∗z                du.
                        s             du u      u,t

This proved the first identity in (2.16). For the second identity in (2.16), it is now enough
to apply the above identity to the case y = 1. This yields, for u < t
                                                        Z t         i2 ···in ,τ
                     i1 ···in ,τ          i1 ···in ,τ        d i1 ,·
                    zu,t         = [1 ∗ z]u,t         =        z ∗z               dv.
                                                         u   dv v     v,t
It is readily checked from the above relations that
                              d i1 ···in ,τ   hd        ii1 ···in ,τ
                                                  i1 ,·
                                z           =−   z ∗z                .
                             du u,t            du u      u,t

Plugging this relation into (2.17), the second part of (2.16) is now achieved. This finishes
our proof.                                                                                □

   Combining our definitions of convolution and Lemma 2.26, we can now state Chen’s
identity for smooth Volterra signatures.
Proposition 2.29. Let z be the full lift of a Volterra path z ∈ V 1 ([0, T ]; Rm ), defined as
in Remark 2.24. Then z satisfies
                                      n
                     1 ···in ,τ
                                         i1 ···i · ik+1 ···in ,τ
                  zis,t
                                      X
                                =        zs,u k ∗ z u,t            ,                    (s, u, t, τ ) ∈ ∆4 .                (2.18)
                                      k=0
for all n ∈ N and i1 · · · in ∈ W, where we recall that the convolution product above is defined
by (2.12).

   In the spirit of presentation of the remaining paper, we will postpone the proof of
Proposition 2.29 and present it below in Corollary 2.36 based on a dynamic representation
of the Volterra signature. This is the theme of the next section.
                                         THE VOLTERRA SIGNATURE                                             13

2.3. A fundamental linear Volterra equation. We recall from Section 2.1 that W
denotes the set of words in the alphabet A = {1, . . . , m} and ei1 ···in := ei1 ⊗ · · · ⊗ ein ∈
(Rm )⊗n denotes the basis tensor of level n corresponding to the coordinate i1 · · · in ∈ W.
To give a dynamic representation of the Volterra signature, we henceforth represent the
collection of its iterated integrals by a tensor series.
Notation 2.30. Let x be a signal in C 0,1 ([0, T ]; Rd ), and consider a kernel K with values in
L(Rd ; Rm ) that satisfies Hypothesis 2.10. Then the iterated integrals {VSig(x; K)w }w∈W
characterizing VSig in Definition 2.14 can be represented by a formal tensor series, i.e.,
                         ∞                       ∞ X
                                      (n),τ
                                                           VSig(x; K)w,τ
                        X                       X
     VSig(x; K)τs,t :=      VSig(x; K)s,t :=                          s,t ew   ∈ T ((Rm )),
                              n=0                           n=0 w∈W
                                                                |w|=n

for all (s, t, τ ) ∈ ∆3 , where we recall that T ((Rm )) is introduced in Definition 2.4.

  Notation 2.30 allows an easy characterization of the Volterra signature by a linear
Volterra equation in the extended tensor algebra, which is manifested by the following
Proposition 2.31. Under the same conditions as in Notation 2.30, the Volterra signature
z = VSig(x; K) : ∆3 → T ((Rm )) uniquely solves a linear system of the form
                             Z t
                    τ
                  zs,t = 1 +     zus,u ⊗ K(τ, u) dxu ,  (s, t, τ ) ∈ ∆3 ,        (2.19)
                                     s
where we have used the representation (2.10) of z.
                                                                   dz τ
Remark 2.32. Using once more (2.8), i.e. dztτ = dtt dt, we can equivalently present the
                                                       τ = t K(τ, u) dx by
                                                              R
equation (2.19) using the underlying Volterra path zs,t         s        u
                                    Z t
                        zτs,t = 1 +     zus,u ⊗ dzuτ , (s, t, τ ) ∈ ∆3 .         (2.20)
                                             s
                                                                                 z=
Remark 2.33. Drawing on Remark 2.16, the linear equation for the usual signature e
Sig(x) can be written as
                                    Z t
                         zs,t = 1 +
                         e              zs,u ⊗ dxu , (s, t) ∈ ∆2 .
                                        e                                      (2.21)
                                                 s
That is the convolution aspect, apparent in (2.19), is absent here. As we will see below,
this is a substantial computational advantage.

Proof of Proposition 2.31. Equation (2.19) is given meaning to – and in fact is solved by
– projection to coordinates:
                Z t
         wi,τ
        zs,t =      zw,u  i
                     s,u K (τ, u) dxu , for all w ∈ W, i ∈ A, (s, t, τ ) ∈ ∆3 .     (2.22)
                  s
Indeed, starting with w = ∅, with z∅ ≡ 1, we observe inductively over the length of words,
that zw is measurable and bounded over ∆3 , hence, all integrals are well defined. This
already fully determines the solution and hence uniqueness is settled. One then readily
verifies form the Definition 2.14 that with w = j1 · · · jn it holds
                                               n
   Z t                               Z tZ                            !
                                               Y
                  w,u i
       VSig(x; K)s,u K (τ, u) dxu =               K (rl+1 , rl ) dxrl K i (τ, u) dxu
                                                      jl
    s                                            s   ∆n
                                                      s,u    l=1
                                    n
                          Z                                        !
                                                                       K i (τ, u) dxu = VSig(x; K)wi,u
                                    Y
                      =                   K jl (rl+1 , rl ) dxrl                                  s,t . (2.23)
                          ∆m+1
                           s,t      l=1
                                       THE VOLTERRA SIGNATURE                                          14

Hence, z = VSig(x; K) solves equation (2.19).                                                          □

   To express the properties of the Volterra signatures more conveniently in the tensor
setting, we formally extend the convolution operation ∗ from Definition 2.23 for both y
and z. We obtain an operation denoted by ⊛, acting on paths in T ((Rm )).
Definition 2.34. Let z : ∆3 → T ((Rm )) be the full lift of a Volterra path z ∈ V 1 ([0, T ]; Rm ).
Then for any y : [0, T ] → T ((Rm )) such that yw is measurable and bounded for all w ∈ W
we define for all n, k ∈ N:
            h             iτ       X
              y(n) ⊛ z(k)    :=            ev ⊗ ew [yv ∗ z]w,τ
                                                           s,t ,    (s, t, τ ) ∈ ∆3 ,     (2.24)
                           s,t
                                        w,v∈W,
                                      |v|=n,|w|=k

with [yv ∗ z]w,τ
             s,t still defined by (2.12), and further
                                     ∞ X
                                     X n h                        iτ
                  [y ⊛ z]τs,t :=                  y(n−k) ⊛ z(k)          ,   (s, t, τ ) ∈ ∆3 .     (2.25)
                                                                   s,t
                                     n=0 k=0

We also denote by y ⊛ z the function from ∆3 to T ((Rm )) given by (s, t, τ ) 7→ [y ⊛ z]τs,t .

   As a first demonstration of the utility of a compact notation like ⊛, we will translate the
inductive properties of Lemma 2.26 into associative properties for the convolution product
in T ((Rm )). The proof is immediate and therefore omitted.
Lemma 2.35. Let z and y be as in Definition 2.34. Then
                 h          iτ
                   y ⊛ z(0)    = [y ⊛ 1]τs,t = yτ , (s, t, τ ) ∈ ∆3 .                              (2.26)
                                      s,t

Furthermore, for k, n ∈ N:
              h          i·        τ  h           iτ
                      (k)       (n)
                y⊛z          ⊛z        = y ⊛ z(n+k)    ,                       (s, t, τ ) ∈ ∆3 .   (2.27)
                               s,·          s,t                        s,t

In particular, the linear equation (2.20) for z can be recast as
                                               τ
                          zτs,t = 1 + z·s,· ⊛ z s,t , (s, t, τ ) ∈ ∆3 .
                                     


  The notion of convolutional tensor product in Definition 2.34 also allows to express
Chen’s relation from Proposition 2.18 in a more elegant way. As promised above, we will
prove this relation using the curent tensor product setting.
Corollary 2.36. Let z be the full lift of a Volterra path z ∈ V 1 ([0, T ]; Rm ) considered as a
function z : ∆3 → T ((Rm )). Then z satisfies
                                         τ
                        zτs,t = z·s,u ⊛ z u,t ,    (s, u, t, τ ) ∈ ∆4 .
                               
                                                                                          (2.28)

Proof of Proposition 2.29 and Corollary 2.36. One first notices that (2.18) is precisely the
coordinate wise projection of (2.28), hence the two identities are equivalent and it suffices
to prove (2.28).
   In order to prove (2.28), let us start from equation (2.19) which characterizes the signa-
ture z, for (s, t, τ ) ∈ ∆3 . Then we further split the interval [s, t] into [s, u] ∪ [u, t], which
yields
                           Z t                    Z u                Z t
              zτs,t = 1 +      zrs,r ⊗ dzrτ = 1 +     zrs,r ⊗ dzrτ +     zrs,r ⊗ dzrτ .       (2.29)
                           s                             s                     u
                                   THE VOLTERRA SIGNATURE                                       15

On the right hand side of (2.29) we then recognize the expression for zτs,u from (2.19). We
thus get
                                              Z t
                                 τ      τ
                                zs,t = zs,u +     zrs,r ⊗ dzrτ .
                                                         u
Now fix (s, u) ∈ ∆2 arbitrarily. It follows from the above that ytτ := zτs,t for (t, τ ) ∈ ∆2u,T
solves the equation
                                     Z t
                         τ     τ
                       yt = zs,u +       yrr ⊗ dzrτ , (t, τ ) ∈ ∆2u,T .                   (2.30)
                                           u
Since the above equation can be solved by inductively projecting to tensor levels as in the
proof of Proposition 2.31, it is clear that it admits a unique solution. Hence,        the claim
                                                                                           τ
                                                                         etτ := z·s,u ⊛ z u,t for
                                                                                  
now follows after verifying that this is equation is also solved by y
(t, τ ) ∈ ∆2u,T . To this end we plug y e into the right-hand side of (2.30), and invoke both
definitions (2.24) and (2.25) to write
                      Z t                   X∞ X n h                 i·         τ
                 τ          r    τ    τ                (n−k),·    (k)        (1)
               zs,u +     er ⊗ dzr = zs,u +
                          y                           zs,u     ⊛z        ⊛z         .
                      u                                                       u,·   u,t
                                                   n=0 k=0

Now resort to (2.27) and then (2.26) to get
                 Z t                      ∞ X
                                          X n h                    iτ
         zτs,u +     err ⊗ dzrτ = zτs,u +
                     y                          z(n−k),·
                                                 s,u     ⊛ z (k+1)
                  u                                                          u,t
                                               n=0 k=0
                                  ∞ h
                                  X               iτ   ∞ X
                                                       X n h                iτ
                                      (n),·   (0)
                                =    zs,u ⊛ z        +      z(n−k),·
                                                             s,u     ⊛ z(k)    .
                                                             u,t                          u,t
                                   n=0                             n=1 k=1

Gathering the two terms in the right hand side above and recalling our definition (2.25)
again we end up with
                   Z t              ∞ X
                                      n h                 iτ
                                    X                                   τ
             τ
                       err ⊗ dzrτ =      z(n−k),·     (k)
                                                             = z·s,u ⊛ z u,t .
                                                               
            zs,u +     y                  s,u     ⊛ z
                      u                                                u,t
                                         n=0 k=0

We have thus shown that y                                  e = y and hence zτs,t =
                        e solves (2.30), which proves that y
 ·      τ
 zs,u ⊛ z u,t .                                                                  □

   We end this section with a result that presents how linear Volterra equations are ex-
panded in terms of the Volterra signature, thus justifying, in particular, the discussion
from the introduction to this subsection and the choice of terminology “fundamental linear
Volterra equation”. To ensure global existence of such expansions, we require the Volterra
signature to have an infinite radius of convergence, by which we mean
                               ∞
                                                (n),τ
                              X
                       sup        λn |VSig(x; K)s,t | < ∞,      λ > 0.              (2.31)
                      (s,t,τ )∈∆3 n=0

The following lemma shows that condition (2.31) is fulfilled under mild assumptions on K.
Lemma 2.37. Let K : ∆2 → L(Rd ; Rm ) be a matrix-valued kernel. Assume that K satis-
fies an improved version of hypothesis 2.10, that is suppose K is in L∞,p (∆2 ; L(Rd ; Rm ))
for some p > 1. Otherwise stated, we assume
                                        Z t               1/p
                      ∥K∥L∞,p := sup          |K(t, s)|p ds     < ∞.                 (2.32)
                                        t∈[0,T ]     0

Then condition (2.31) is fulfilled. In particular, VSig(x; K) can be considered as an element
of T 2 (see Definition 2.7).
                                         THE VOLTERRA SIGNATURE                                      16

Proof. Defining the scalar kernel k = |K|, for any x ∈ C 0,1 ([0, T ]; Rd ) and (s, t) ∈ ∆2 we
have
                         Z     n                                     Z  n
                 (n),τ
                              Y                                        Y
                                                                   n
     |VSig(x; K)s,t | ≤           |K(rl+1 , rl )||ẋrl | drl ≤ ∥ẋ∥∞       k(rl+1 , rl ) drl .
                                   ∆n
                                    s,t l=1                                ∆n
                                                                            s,t l=1
                                                 R      Qn                 p         np
Moreover, an inductive argument shows that ∆n
                                                    s,t   l=1 k(rl+1 , rl ) drl ≤ ∥k∥L∞,p , so that
by the Hölder inequality we have
           Z     n
                 Y
                   k(rl+1 , rl ) drl ≤ ∥k∥nL∞,p Vol(∆ns,t )1/q , q = p/(p − 1) > 0.
                    ∆n
                     s,t l=1

                               n
Using Vol(∆ns,t ) = (t−s)
                      n! , we can conclude that
                     ∞
                     X                    (n),τ
                                                   X     zn
         sup              λn |VSig(x; K)s,t | ≤                < ∞,     z = λ∥ẋ∥∞ ∥k∥L∞,p T 1/q ,
      (s,t,τ )∈∆3 n=0                              n≥0
                                                       (n!)1/q

so that (2.31) indeed holds true.                                                                    □

   We are now ready to state our representation of linear equations in terms of Volterra
signatures.
Proposition 2.38. Let ξ ∈ Rk , x ∈ C 0,1 ([0, T ]; Rd ) and K ∈ L∞,p (∆2 ; L(Rd ; Rm )) for
some p > 1. For A ∈ L(Rm ; L(Rk ; Rk )), we consider the linear Volterra equation
                            Z t
                                              
                   yt = ξ +     A K(t, u) ẋu yu du,        t ∈ [t0 , T ].          (2.33)
                                         t0

Also recall our convention (2.2) for linear maps acting on tensors, specialized here to
E = Rk . Then it holds that
                                                ∞
                                                  e VSig(x; K)(n),τ
                                                X
                     ∆3 ∋ (s, t, τ ) 7→ Ψτs,t =
                                                                    
                                                  A           s,t                (2.34)
                                                           n=0

lies in L∞ (∆3 ; L(Rk ; Rk )).   Moreover, for any initial condition ξ ∈ Rk , the path yt =
Ψtt0 ,t (ξ) is the unique, bounded and measurable solution to (2.33).

Proof. By definition of Ã and lemma 2.37, it readily follows that
                     e VSig(x; K)(n),τ | ≤ sup                           (n),τ
                X                                    X
                                                         |A|n |VSig(x; K)s,t | < ∞.
                                      
         sup        |A            s,t
        (s,t,τ )∈∆3 n≥0                               (s,t,τ )∈∆3 n≥0

Therefore the Volterra increment Ψ, as introduced in (2.34), is analytically well defined.
In addition, as a direct consequence of the definition (2.2) of A,                               e 1⊗
                                                                             e it holds that A(v)A(v
                                                                     m
· · · ⊗ vn ) = A(v1 ⊗ · · · ⊗ vn ⊗ v) for all v1 , . . . , vn , v ∈ R . Thus we get
               e
           Z t                               XZ t
                               u                          e VSig(x; K)(n),u ⊗ K(t, u) dxu (ξ)
                                                                                             
               A(K(t, u)ẋu )Ψt0 ,u (ξ) du =             A              t0 ,u
          t0                                      n≥0 t0

Therefore resorting to (2.27) we find
         Z t
                                                          (n),t
                                            X
             A(K(t, u)ẋu )Ψut0 ,u (ξ) du =   A(VSig(x;
                                              e         K)t0 ,t )(ξ) = Ψtt0 ,t (ξ) − ξ,
               t0                                  n≥1

where the second identity stems from (2.34). We have thus proved that yt = Ψtt0 ,t (ξ)
indeed solves (2.33). Finally, uniqueness follows from a Gronwall inequality for Volterra
                                      THE VOLTERRA SIGNATURE                                      17

equations: Assume y and ŷ are bounded and measurable solutions to (2.33), and define
f (t) = |yt − ŷt |. Then by linearity we have
                                 Z t                             Z t
             f (t) ≤ |A|∥x∥C 0,1     |yu − ŷu ||K(t, u)| du = C     f (u)|K(t, u)| du.
                                    t0                                  t0

An application of the Volterra-Gronwall Lemma [43, Lemma 9.8.2] shows that f = 0 a.e.,
which concludes the proof.                                                         □

2.4. Finite state space representation. As mentioned in the introduction, Volterra
signatures are useful objects when one wishes to model systems with memory. However,
one common pitfall of all representations for this type of systems is their computational
cost. In this section we focus on a class of exponential kernels which encompasses relevant
examples and leads to simplified computations. This class is defined below.

Definition 2.39. Consider a constant matrix Λ ∈ RR×R and a family of coefficients
{Ar , br : 1 ≤ r ≤ q} with Ar ∈ Rm×d and br ∈ RR . Denote by 1⊤ the R1,R row vector
(1, . . . , 1). For (s, t) ∈ ∆2 we define
                                         q
                                         X
                          Λ
                         KA,b (t, s) =     (1⊤ e−Λ(t−s) br )Ar ∈ L(Rd ; Rm ).                 (2.35)
                                         r=1

Remark 2.40. Notice that for diagonal matrices  PR Λ, Definition
                                                            −λ  (t−s)
                                                                       2.39 includes, in particular,
sums of exponential kernels like k(t, s) =         i=1 αi e
                                                              i       . Such multi-factor kernels
are widely used to model processes with short-term or fading memory, as the exponential
decay naturally captures the rapid loss of dependence on past inputs. Moreover, completely
monotone kernels - such as the fractional kernels - can be arbitrarily well approximated by
finite sums of exponential factors. For these reasons, Volterra systems driven by (sums of)
exponential kernels appear in various applications, most prominently in path-dependent
volatility modeling [1, 3, 10, 46], and therefore it is natural to study the Volterra signature
induced by this type of kernel matrices.

Remark 2.41. Beyond (sum of) exponential kernels, the class (2.35) also includes mixed
exponential-polynomial kernels
                         Q X
                           mr
                         X                      (t − s)l−1
             K(t, s) =             e−λr (t−s)              Ar,l ,   Ar,l ∈ Rm×d ,   mi ∈ N.   (2.36)
                                                 (l − 1)!
                         r=1 l=1

More generally, it also covers damped periodic (Prony) kernels obtained by allowing com-
plex conjugate pairs of exponents, which lead to factors of the form e−a(t−s) cos(ω(t − s))
and e−a(t−s) sin(ω(t − s)), possibly multiplied by polynomials in (t − s). More details
on such representations, as well as their implications regarding computational aspects of
Volterra signatures, are discussed in the accompanying article [47].

   The main observation of this section is that Volterra signatures with kernels restricted to
the class (2.35) can be realized as the solution to a system of mean-reverting equations in
the tensor algebra. As motivated in the introduction, this observation already suggests the
possibility of computing VSig(x; KA,b Λ ) with linear complexity, much like in the classical

case K = Id . Indeed, the dynamics of the lifted Volterra signature reduce to a classical
controlled differential equation in the tensor algebra, in contrast to the general case (2.19)
involving convolutions.
                                         THE VOLTERRA SIGNATURE                                                  18

Proposition 2.42. Let x ∈ C 0,1 ([0, T ]; Rd ) and consider a kernel KA,b
                                                                      Λ as in Definition
                                                Λ can be decomposed as
2.10. Then the Volterra signature related to KA,b

                                                                   R
                                                                   X
                                             Λ t
                                    VSig(x; KA,b )s,t = 1 +               Zℓs,t ,
                                                                   ℓ=1

where Zs,t ∈ T ((Rm ))R solves the system of ordinary differential equations

                                                                     R
                                                                                      !
                                                                     X
                Zs,s = 0,        dZs,t = −Λ.Zs,t dt +           1+            Zis,t       ⊗ d(B.xt ),        (2.37)
                                                                        i=1

and where the vectors Λ.Zs,t , B.xt are respectively defined by

                      R
                      X                                                             q
                                                                                    X
      (Λ.Zs,t )ℓ :=         Λℓk Zks,t ∈ T ((Rm )),      and     (B.xt )ℓ :=               bℓr Ar xt ∈ Rm .   (2.38)
                      k=1                                                           r=1

Remark 2.43. Let m = d, q = 1 and A1 = Id . Choosing Λ = diag(λ1 , . . . , λR ) and
b1 = (α1 , . . . , αR )⊤ , for some λi , αi ∈ R+ , we have
                                                       R
                                                       X
                                      Λ
                                     KA,b (t, s) :=          αℓ e−λℓ (t−s) Id                                (2.39)
                                                       ℓ=1

in (2.35), that is the standard sum of exponentials kernel. Projected to the first level
π1 (T ((Rd ))R ) ∼
                 = Rd×R , the dynamics of Zs,t = π1 (Zs,t ) in eq. (2.37) read
                        ℓ          ℓ
                      dZs,t = −λℓ Zs,t dt + αℓ dxt ,          (s, t) ∈ ∆2 ,           1 ≤ ℓ ≤ R.             (2.40)

Note that the representation (2.40) corresponds to the multivariate Ornstein–Uhlenbeck
                                                             Rt
dynamics, acting as a Markovian lift above the Volterra path 0 K(t, s) dxs . In the same
way, we may view Z in (2.37) acting as a lift above VSig for exponential kernels, which
leads to computational benefits as illustrated in [47].

Proof of Proposition 2.42. We start by expressing the equation for z = VSig(x; K) and
K = KA,bΛ in convolutional form thanks to Proposition 2.31. That is plugging the expres-

sion (2.35) for K into equation (2.19), we get that VSig(x; K) satisfies
                                                     q
                               Z t                                        !
                                                     X
                      t                       u           ⊤ −Λ(t−u)
           VSig(x; K)s,t − 1 =     VSig(x; K)s,u ⊗      (1 e        br )Ar dxu .
                                        s                          r=1

Expanding part of the matrix products in coordinates, we thus obtain
                                                                  R
                                                                  X
                                        VSig(x; K)ts,t − 1 =            Zis,t ,                              (2.41)
                                                                  i=1

where the increments Zis,t are defined by

                             q X
                             X R Z t
                  Zis,t =                    (e−Λ(t−u) )ij bjr VSig(x; K)us,u ⊗ d(Ar xu ).                   (2.42)
                              r=1 j=1    s
                                              THE VOLTERRA SIGNATURE                                                           19

Let us now give more information about the dynamics (2.41). First we clearly have Zℓs,s = 0.
Next an application of the Leibniz rule (with respect to t) to expression (2.42) shows that
             q X
               R Z t                                                                         
             X        d                −Λ(t−u)
                                                    
  dZℓs,t =                          e                        bjr VSig(x; K)us,u ⊗ d(Ar xu )       dt
                           s   dt                       ℓj
             r=1 j=1
                                                                 q X
                                                                 X R
                                                             +             1{j=ℓ} bjr VSig(x; K)ts,t ⊗ d(Ar xu ), (2.43)
                                                                 r=1 j=1

where we have used the fact that e−Λt |t=0 = IdR to get the term 1{j=ℓ} . In addition, from
basic matrix exponential calculus [54] we know that
                                                                                  R
                     d −Λ(t−s)                           X
                        (e     )ij = (−Λe−Λ(t−s) )ij = −   Λik (e−Λ(t−s) )kj .
                     dt
                                                                                  k=1

Reporting this idendity into (2.43) we obtain
               R
               X           q X
                           X R Z t                                                                    
                                                   −Λ(t−s)
  dZℓs,t = −         Λℓk                      (e               )kj bjr VSig(x; K)us,u ⊗ d(Ar xu )          dt
               k=1         r=1 j=1        s
                                                                                                  q
                                                                                                                 !
                                                                                                  X
                                                                      + VSig(x; K)ts,t ⊗                bℓr Ar       dxt . (2.44)
                                                                                                  r=1

We now easily recognize the relation (2.42) defining the coordinates Zis,t (of VSig(x; K)ts,t −
1) in the right hand side of (2.44). Thus we end up with
                           R                     R              q
                                                         !              !
                           X                     X            X
                dZℓs,t = −    Λℓk Zks,t dt + 1 +    Zis,t ⊗       bℓr Ar dxt ,          (2.45)
                                k=1                                   i=1               r=1

for all ℓ = 1, . . . , R.       Recalling our notation (2.38), this concludes the proof of our
claim (2.37).                                                                               □

  As mentioned above, the advantage of equation (2.37) is that one obtains an Ornstein-
Uhlenbeck type system which is easy to simulate. On top of that, in case K is a scalar-
valued kernel, one obtains an explicit solution in terms of the classical signature of the
underlying noise x. We detail this in the following proposition.
Proposition 2.44. We consider the same situation as in Proposition 2.42, albeit in the
scalar case q = R = 1 and KA,b    Λ (t, s) =: K λ (t, s) = αe−λ(t−s) I . Recall that the usual
                                                 α                     d
signature Sig(x) is defined by (2.6). Then equation (2.37) admits an explicit solution as a
function of Sig(x):
                                             Z t
                      −λ(t−s)
               t
    VSig(x; K)s,t = e         Sig(αx)s,t + λ     e−λ(t−r) Sig(αx)r,t dr, (s, t) ∈ ∆2 .  (2.46)
                                                                  s

More generally, for any (s, t, τ ) ∈ ∆3 we have
                                                                            Z t
  VSig(x; K)τs,t = 1 + e−λ(τ −s) (Sig(αx)s,t − 1) + λ                             e−λ(τ −u) (Sig(αx)u,t − 1) du. (2.47)
                                                                              s

Proof. Let us denote by ỹ the right hand side of (2.46). Applying the product rule like
in (2.43), we get
                                                         Z t                      
                                 −λ(t−s)                        −λ(t−r)
         dỹs,t = −λỹs,t dt + e         dSig(αx)s,t + λ      e         dSig(αx)r,t dr.
                                                                                   s
                                  THE VOLTERRA SIGNATURE                                       20

Then one resorts to relation (2.21), which enables to write
                                                         Z t                               
                        −λ(t−s)                                 −λ(t−r)
dỹs,t = −λỹs,t dt + e         Sig(αx)s,t ⊗ d(αxt ) + λ      e         Sig(αx)r,t ⊗ d(αxt ) dr.
                                                           s
                                                                                       (2.48)
Similarly to what we did in (2.45), we now recognize the right hand side of (2.46) in (2.48),
and thus
                             dỹs,t = −λỹs,t dt + ỹs,t ⊗ d(αxt ),
so that so that indeed VSig(x; K)ts,t = ỹ by proposition 2.42. This finishes the proof
of (2.46). Finally, the second assertion (2.47) is achieved by plugging the explicit expression
for VSig(x; K)ts,t in (2.46) into the fundamental equation (2.19), and follow the same lines
of arguments used to prove (2.46). This finishes our proof. u where we applied Fubini in
the penultimate equation.                                                                     □

2.5. Connection to deep learning state space models. The finite state space kernel
formulation introduced in Definition 2.39 shares its fundamental mathematical construction
with recent models proposed in deep learning called state space models (SSMs), such as
structured state space sequence models (S4) and Mamba/Mamba-2 [45, 44, 36].
   At their core, modern continuous-time neural SSMs map a one-dimensional input signal
ut to a one-dimensional output yt via a latent state ht ∈ RR , where the latent state is
governed by the linear differential equation
                             dht = M ht dt + But dt,     yt = Cht .
Here, we have M ∈ RR×R , C ∈ R1×R and B ∈ RR×1 . In the case when h0 = 0 the exact
solution to this system can be written in terms of a convolution of the form
                                     Z t
                                yt =     CeM (t−s) Bus ds.
                                         0
This is precisely a Volterra integral, as described in the first level of the Volterra signature,
and which we sometimes refer to as the memory state. Indeed, identifying M = −Λ,
B = br and C = 1⊤ yields the kernel kr (t, s) = 1⊤ e−Λ(t−s) br as proposed in Definition
2.39. While neural SSMs typically handle multi-dimensional sequences by applying these
scalar linear-time-invariant systems independently across feature channels, our formulation
handles
Pq        the multi-dimensional input-output mapping via the linear combination K(t, s) =
   r=1 kr (t, s)Ar ∈ L(Rd ; Rm ), for matrices Ar .
  A fundamental distinction, however, lies in how non-linear expressivity is achieved.
Mamba and its successors achieve universal approximation by making the state matrices
data-dependent (selective SSMs) and stacking multiple layers interwoven with non-linear
activation functions. In contrast, the Volterra signature achieves non-linearity algebraically
by lifting this linear memory mechanism into the extended tensor algebra T ((Rm )).
   This algebraic lift can be seen explicitly through the lens of the fundamental equation
described in Proposition 2.42 which governs the Volterra signature dynamics over the
state-space kernel as seen in (2.37). We can interpret this equation as a high-order tensor
valued SSM, where the first level of the equation describes exactly (under specific matrix
choices) the structure of models like S4, and Mamba (1 and 2), but where the equation also
contains high order information that captures more intricate dynamics and connections.
The signature state Zs,t in (2.37) undergoes a linear, mean-reverting decay −ΛZs,t dt, while
the increment d(B xt ) interacts with the aggregated history multiplicatively via the tensor
                                          Rt
product ⊗. Here we can think of xt = 0 ut dt, where ut is the input signal to the SSM.
It replaces black-box stacked layers with a graded Picard expansion that retains strong
                                  THE VOLTERRA SIGNATURE                                     21

universality guarantees, as will be shown in the next section, while maintaining the exact
same underlying memory architecture.


                    3. The Volterra signature as feature map

   This section presents the key properties of the Volterra signature that make it relevant
as a feature map on path space. Specifically, we will discuss its invariance under time
reparameterization, continuity and injectivity. As a consequence, we will characterize
classes of simple Volterra signature functionals, which are universal for the approximation
of continuous functionals defined on the path space. Recall (from Definition 2.14 and
Proposition 2.21) that the Volterra signature can either be defined above the data (x, K), or
equivalently above Volterra paths z ∈ V 1 ([0, T ]; Rm ). This observation would compel us to
study invariance and universality of the signature by considering only the T ((Rm ))-valued
signature z given intrinsically by equation (2.19). However, as mentioned in Remark 2.20,
the kernel K can be seen as an additional modeling component. It allows for more flexibilty
compared to the classical signature transform. Therefore we also consider the mappings
introduced in Notation 2.30, namely
                      C 0,1 ([0, T ]; Rd ) → T ((Rm )),     x 7→ VSig(x; K),              (3.1)
for a fixed kernel K, and similarly
                   L1,∞ (∆2 , L(Rd ; Rm )) → T ((Rm )),         K 7→ VSig(x; K)           (3.2)
for given underlying noise x.

3.1. Time reparameterization and continuity properties. In this section we will
address two basic though important properties of Volterra signatures: invariance under
time reparameterization and continuity with respect to both the underlying signal x and
kernel K. The two questions have consequences on data analysis, since good invariance
and continuity properties are convenient for modeling in an uncertain environment.
  Let us start by discussing invariance under reparametrization. By time reparameteri-
zation we mean a smooth and increasing function ρ : [0, T ] → [0, T ] with ρ(0) = 0 and
ρ(T ) = T . For a given reparameterization ρ and a two-parameter function f : ∆2 → R,
we also define f ◦ ρ as follows:
                       f ◦ ρ : ∆2 → R,      (f ◦ ρ)(s, t) := f (ρ(s), ρ(t)).              (3.3)
With this notation in hand, if one considers the case of usual signatures Sig(x) (introduced
in Remark 2.16), it is a well-known fact (see [39, Proposition 7.10]) that
                    Sig(x)0,T = Sig(x ◦ ρ)0,T ,           ∀x ∈ C 0,1 ([0, T ]; Rd ).      (3.4)
In the next proposition we generalize (3.4) to the VSig context, showing that Volterra
signatures enjoy valuable invariance properties.

Proposition 3.1. Let ρ : [0, T ] → [0, T ] be a smooth and monotone increasing function
such that ρ(0) = 0 and ρ(T ) = T . Then the invariance of VSig under the reparameteriza-
tion ρ can be expressed in the two following ways.
    (i) When one considers x ∈ C 0,1 ([0, T ]; Rd ), a kernel K ∈ L1,∞ (∆2 , L(Rd ; Rm )) and a
        signature VSig(x; K) as given in Notation 2.30, we have
                          VSig(x ◦ ρ; K ◦ ρ)T0,T = VSig(x; K)T0,T .                       (3.5)
                                         THE VOLTERRA SIGNATURE                                                      22

   (ii) For an intrinsic Volterra path z ∈ V 1 ([0, T ]; Rm ) from Definition 2.18 and its cor-
        responding intrinsic Volterra signature z satisfying (2.19), the invariance reads
                                             zT0,T (z ◦ ρ) = zT0,T (z).                                           (3.6)
                                                         Rt
Proof. First notice that for any Volterra path ztτ = 0 K(τ, u) dxu , by a simple change of
variables it follows that
            Z ρ(t)                   Z t                                 Z t
(z ◦ ρ)τt =        K(ρ(τ ), u) dxu =     K(ρ(τ ), ρ(u))ẋρ(u) ρ̇(u) du =     K(ρ(τ ), ρ(u)) dxρ(u) .
             0                               0                                                    0
In view of Lemma 2.19, it is therefore sufficient to prove (3.5).
  To this end, we aim to prove that for any (s, t, τ ) ∈ ∆3 , it holds that
                                                                                 ρ(τ )
                                VSig(x ◦ ρ; K ◦ ρ)τs,t = VSig(x; K)ρ(s),ρ(t) ,                                    (3.7)
from which the claim immediately follows for s = 0 and t = τ = T . In order to show (3.7),
we proceed by induction over n ∈ N. On the first level, a change of variables u = ρ(r)
shows that
                                  Z t                         Z ρ(t)
                         (1),τ
       VSig(x ◦ ρ; K ◦ ρ)s,t   =      K(ρ(τ ), ρ(r)) dxρ(r) =        K(ρ(τ ), u) dxu
                                                  s                                        ρ(s)
                                                        (1),ρ(τ )
                                         =    VSig(x; K)ρ(s),ρ(t) .
We have already seen in (2.22) and (2.23) that, for any word i1 · · · in+1 ∈ W it holds
                                     Z t
                     i1 ···in+1 ,τ                           1 ···in ,r
   VSig(x ◦ ρ; K ◦ ρ)s,t           =     VSig(x ◦ ρ; K ◦ ρ)is,r         K in+1 (ρ(τ ), ρ(r)) dxρ(r) .
                                             s
Now assuming (3.7) holds for the tensor level n ∈ N, the same change of variables u = ρ(r)
shows
                                          Z t
                          i1 ···in+1 ,τ                 i1 ···in ,ρ(r)
        VSig(x ◦ ρ; K ◦ ρ)s,t           =     VSig(x; K)ρ(s),ρ(r)      K(ρ(τ ), ρ(r)) dxρ(r)
                                                       s
                                                      Z ρ(t)
                                                                           1 ···in ,u
                                                 =             VSig(x; K)iρ(s),u      K in+1 (ρ(τ ), u) dxu
                                                       ρ(s)
                                                              1   n+1i ···i   ,ρ(τ )
                                                 = VSig(x; K)ρ(s),ρ(t)                 ,
where we again invoked (2.23) for the last equality.                                                                 □

  We now turn to continuity properties of Volterra signatures, which are summarized in
the proposition below.
Proposition 3.2. For any Volterra path z ∈ V 1 ([0, T ]; Rm ), recall from definition 2.22,
that we denote by z the full signature of z. Then, for any n ∈ N, the mapping
                 (n),T                                                                                 (n),T
              z0,T       : (V 1 ([0, T ]; Rm ), ∥ · ∥V 1 ) → ((Rm )⊗n , ∥ · ∥),                   z 7→ z0,T ,     (3.8)
                                                                                                          (n),T
is locally Lipschitz continuous. Similarly, the Volterra signature VSig(x; K)0,T , as intro-
duced in definition 2.14, is locally Lipschitz continuous jointly in (x, K) seen as a pair in
C 0,1 ([0, T ]; Rd ) × L∞,1 (∆2 ; L(Rd ; Rm )).

Proof. Consider two Volterra paths z, y ∈ V 1 ([0, T ]; Rm ) with Volterra signatures denoted
by z and y. For n = 1, we have for any t ∈ [0, T ]
                                     Z t
                     (1),t   (1),t        dzut     dy t
                   ∥z0,t − y0,t ∥ ≤             − u du ≤ ∥z − y∥V 1 ,
                                       0  du        du
                                          THE VOLTERRA SIGNATURE                                    23

where we recall that the norm ∥ · ∥V 1 is introduced in (2.9). Therefore the claim (3.8) holds
on the first level. We will now show by induction, that for any n ∈ N we have
                           (n),t          (n),t
                        ∥z0,t − y0,t ∥ ≤ Cn ∥z − y∥V 1 ,                  ∀t ∈ [0, T ],          (3.9)

for some constant Cn = Cn (∥y∥V 1 , ∥z∥V 1 ). To this aim, observe that applying Fubini’s
theorem to (2.11) one gets the following expression which stems from (2.14):
                                         Z t
                               (n+1),t        (n),u  dz t
                              z0,t     =     z0,u ⊗ u du,                          (3.10)
                                          0          du
                                                            (n+1),t
and the same type of expression holds for y0,t      . Hence an application of the triangle
inequality shows
                          Z t
    (n+1),t    (n+1),t         (n),u dz t    (n),u    dy t
  ∥z0,t     − y0,t     ∥≤     z0,u ⊗ u − y0,u ⊗ u du
                           0          du              du
                          Z t                  t         Z t          t
                               (n),u   (n),u dyu              (n),u dzu   dy t
                        ≤     z0,u − y0,u          du +      z0,u       − u du. (3.11)
                           0                 du            0        du    du
We now bound the two terms in the right hand side of (3.11) separately. On the one hand
assuming that the induction hypothesis (3.9) is satisfied for n ∈ N, we have
                   Z t                    t
                         (n),u  (n),u dyu
                       z0,u − y0,u          du ≤ Cn ∥z − y∥V 1 ∥y∥V 1 .
                    0                   du
On the other hand, for the second term in (3.11), again
                    Z t           t
                          (n),u dzu   dy t
                         z0,u       − u du ≤ Cn ∥z∥V 1 ∥z − y∥V 1 .
                     0          du     du
Reporting those two observations in the right hand side of (3.11), we conclude
                                   (n+1),t        (n+1),t
                             ∥z0,t            − y0,t        ∥ ≤ Cn+1 ∥z − y∥V 1 ,

where the constants Cn satisfy the recursive relation

                     Cn+1 = Cn (∥y∥V 1 , ∥z∥V 1 )∥y∥V 1 + Cn (0, ∥z∥V 1 )∥z∥V 1 .

We have thus proved the first part of our statement, namely continuity of the mapping
      (n),T
z 7→ z0,T for every n. For the second part of the statement, we can notice that the
mapping
                     n      Z t                           o
                       τ
            (x, K) 7→ zt =      K(τ, u) dxu : (t, τ ) ∈ ∆2 ∈ V 1 ([0, T ]; Rm ),
                                      0
is jointly locally Lipschitz continuous. This follows by similar arguments as before: for
two pairs (x, K), (x′ , K ′ ) ∈ C 0,1 ([0, T ]; Rd ) × L∞,1 (∆2 ; L(Rd ; Rm )), the triangle inequality
shows
                                  Z t                              Z t
                     ′   ′ τ                              ′
             τ
     z(x, K)t − z(x , K )t ≤            |K(τ, u)||ẋu − ẋu | du +     |K(τ, u) − K ′ (τ, u)||ẋ′u | du
                                      0                                   0
                               ≤ ∥x − x′ ∥C 0,1 ∥K∥L∞,1 + ∥K − K ′ ∥L∞,1 ∥x′ ∥C 0,1 .

Therefore, VSig is the composition of two locally Lipschitz continuous functions, which
finishes the proof.                                                                  □
                                                 THE VOLTERRA SIGNATURE                                   24

3.2. Injectivity. In this section we investigate the injectivity (or point-separation) of the
Volterra signature. Since we are advocating for the Volterra signature as a feature map
on the space of paths (or time-series), injectivity becomes a relevant property in many
applications, such as supervised learning problems like classification and regression. As
observed in the last section, point-separation can fail since for example z and z ◦ ρ produce
the same Volterra signature when ρ is a monotone function, see Proposition 3.1. This
phenomena is well-understood in the classical case, where K ≡ 1, and a full characterization
of paths with identical signature is given by the notion of tree-like equivalence, see [49, 19].
A typical strategy to ensure a point-separating signature, is to augment the paths x with a
monotone component, and thereby making the tree-like equivalence classes trivial. Indeed,
we can for instance notice that on the space of time-augmented paths x̂t = (t, xt ), the
relation x̂1 = x̂2 ◦ ρ is only possible if already x1 = x2 .
  Returning to the Volterra framework, in order to guarantee point-separation, we intro-
duce the space of Volterra paths augmented by a function y.
                                                                         ′
Definition 3.3. For any fixed y ∈ V 1 ([0, T ]; Rm ) and m′ ∈ N, we define the space of
y-augmented Volterra paths by
                             ′
                                 n                      ′                      ′
                                                                                      o
          V̂y1 ([0, T ]; Rm+m ) = z ∈ V 1 ([0, T ]; Rm+m ) : (z 1 , . . . , z m )⊤ = y . (3.12)

   With the definition of augmented Volterra path in hand, we label a general Hypothesis
under which we will achieve point separation by Volterra signatures. The reader is referred
to the Examples 3.10-3.11 below for more specific and natural examples of application.
                                                                                     ′
Hypothesis 3.4. In the sequel we suppose y ∈ V 1 ([0, T ]; Rm ) is such that there exist
sequences of words (wn )n∈N , (vn )n∈N in the alphabet {1, . . . , m′ }, such that the families
                                                                           
                          wn ,t                         d vn ,T
                   {t 7→ y0,t : n ≥ 1} and         t 7→ yt,T : n ≥ 1                        (3.13)
                                                        dt
lie dense in L2 ([0, T ], R), where y is defined through (2.14).

  The following is the main result of this section. It shows that under hypothesis 3.4, the
Volterra signature carries enough information to uniquely determine the two-parameter
                 τ .
path (t, τ ) 7→ z0,t
                                                            ′
Theorem 3.5. For any y ∈ V 1 ([0, T ]; Rm ) such that hypothesis 3.4 holds true, the follow-
ing map is injective:
                                                   ′                 ′
                                     V̂y1 ([0, T ]; Rm +m ) −→ T ((Rm +m )),   z 7−→ zT0,T ,          (3.14)
                                                                 ′
where we recall that the space V̂y1 ([0, T ]; Rm+m ) is defined by (3.12).

Proof. As a first step, based on the convolution properties seen in Section 2 we can show
the following identity, similarly to what we did for (3.10):
                                          Z t
                           i1 ···in ,τ           1 ···ik ,u
                                                             d ik+1 ···in ,T
                          zs,t         =−     zis,u           z              du,    (3.15)
                                           s                du u,T
for all i1 · · · in ∈ W and 0 ≤ k ≤ n − 1. Indeed, combining the expression for the
                                                                                    1 ···in ,τ
convolution product in Definition 2.23 with the identity (2.11), we observe that zis,t         =
    1 ···ik ,·   i        ···in ,τ                                                   1 ···ik ,t
[zis,·              k+1
               ∗ z]s,t               . An application of Lemma 2.26–(ii) for yt = zis,t         then readily
implies (3.15).
                                    THE VOLTERRA SIGNATURE                                      25


   Next let z, h ∈ V̂y1 and suppose that zT0,T = hT0,T . Moreover for i ∈ {1, . . . , m + m′ } and
the two sequences (wn ), (vn ) in hypothesis 3.4, define πn,k = wn · i · vk . Then it follows
from (3.15) and the fact that z j = hj = y j for j ∈ {1, . . . , m′ }, that
                            Z T
        πn,k ,T   πn,k ,T           n ·i,u         n ·i,u
                                                            d vk ,T
   0 = z0,T − h0,T        =     (hw
                                  0,u      − zw  0,u      ) yu,T     du
                             0                             du
                                                                      ! !
                                                    dhi,u      dzri,u
                            Z T Z u
                                           wn ,r         r                  d vk ,T
                          =             y0,r                 −          dr   y      du, ∀n, k ≥ 1.
                             0     0                   dr       dr         du u,T
                                         d vk ,T
Now by hypothesis 3.4, the family {u 7→ du yu,T : k ≥ 1} lies dense in L2 , so that
                                 !
                   dzri,u dhi,u
        Z u
             wn ,r            r
            y0,r         −         dr = 0 for a.e. u ∈ [0, T ] and for all n ≥ 1.
         0          dr       dr
                        wn ,r
Similarly, since {r 7→ y0,r   : n ≥ 1} lies dense in L2 , we conclude

                          dzri,u   dhi,u
                                     r
                                 =         for a.e. (u, r) ∈ ∆2 .
                           dr       dr
Since we assume in Definition 2.18 that z0τ = 0, we get z = h everywhere. This proves
injectivity.                                                                       □

   As a first application of theorem 3.5, we can show that the Volterra signature above a
time-augmented Volterra path ẑs,tτ = (t − s, z τ ) uniquely characterizes z.
                                               s,t

Corollary 3.6. Let m′ = 1 and consider the Volterra path ys,t      τ = t − s. We define the y-

augmented Volterra path z ∈ V̂y1 ([0, T ]; Rm+1 ) as in Definition 3.3. Then we have injectivity
of the map in (3.14) in this context.

Proof. Note that y is indeed a Volterra path according to Definition 2.18, applied to K ≡ 1
and xt = t. Now choosing the sequences of words in hypothesis 3.4 consisting of n − 1,
resp. n consecutive 1’s, i.e. wn = 1⊗(n−1) = 1 · · · 1 and vn = 1⊗n for n ≥ 1 we can easily
verify that for any z ∈ V̂y1 it holds

                  wn ,t       tn−1             d vn ,t     (T − t)n−1
                 y0,t   =            ,   and      yt,T = −            ,   n ≥ 1.           (3.16)
                            (n − 1)!           dt           (n − 1)!
But since monomials are dense in Lp by the Weierstrass theorem, we see that hypothesis 3.4
is satisfied and we can conclude using theorem 3.5.                                     □

   In Corollary 3.6 we have augmented the path z with a path ys,tτ = (t − s), which is very

similar to the augmentations used in classical rough paths theory (see [30]). In order to be
consistent with our Volterra perspective we now specialize to an augmentation by Volterra
paths. Let us first define this notion.
                                                   ′                           ′     ′
Definition 3.7. Let z ∈ V 1 ([0, T ]; Rm+m ) and K y ∈ L∞,1 (∆2 ; L(Rd ; Rm )). In the
framework of Definition 3.3, we say that z is K y -augmented if one can write
                                                        Z t
                         τ       1,τ            m′ ,τ
                        ys,t ≡ (zs,t , . . . , zs,t ) =     K y (τ, r) dxyr ,
                                                       s
                                  ′
for a path xy ∈ C 0,1 ([0, T ]; Rd ). Provided with another kernel K ∈ L∞,1 (∆2 ; L(Rd ; Rm )),
                                                   ′
the corresponding path z ∈ V̂y1 ([0, T ]; Rm+m ) will be denoted by
                                           Z t
                                     τ         b y (τ, u) db
                                   zs,t  =     K           xyu ,                           (3.17)
                                               s
                                      THE VOLTERRA SIGNATURE                                    26

                                                  ′                     ′       ′
                     b y ) in C 0,1 ([0, T ]; Rd+d ) × L∞,1 (∆2 ; L(Rd+d ; Rm+m )) is such that
                xy , K
where the pair (b
                                                                 y      
                          y       y     ⊤              y          K    0
                        x
                        b = (x , x) , and K (t, s) = b                      .               (3.18)
                                                                   0 K

   While K1 -augmented path are a particular case of general augmented paths, it is also
true that any augmented Volterra path can be seen as a K1 -augmented path. We label this
property in the lemma below. Its proof is omitted due to its similarity with Lemma 2.19.
                                                                    ′
Lemma 3.8. Let z be a path in the space V̂y1 ([0, T ]; Rm+m ), as introduced in Definition 3.3.
Then
                            xy , K
   (i) One can find a pair (b    b y ) like in (3.18), such that z is represented as in (3.17).
                                                                            ′
   (ii) In particular, one can choose x byt = t and K y ∈ L∞,1 (∆2 , Rm ) in (3.17). Then the
        path z is more specifically written as
                           Z t
                     τ
                    zs,t =     K(τ, r) dx̂r , with x̂t = (t, xt )⊤ ∈ Rd+1 .            (3.19)
                                s

Remark 3.9. In the context of a representation of the form (3.19), consider a fixed kernel
K y = K1 . Then, for any word w = i1 · · · in in the alphabet {1, . . . , m′ }, we have
                                               Z      n
                      w,τ              w,τ
                                                     Y
                    zs,t = VSig(t; K1 )s,t =            K1il (rl+1 , rl ) drl ,         (3.20)
                                                         ∆n
                                                          s,t l=1

where we are still using the convention rn+1 = τ in (3.20). As we shall see in the following
examples, VSig(t; K1 ) admits a closed-form expression for many kernels of interest, allowing
hypothesis 3.4 to be verified directly.
Example 3.10. Following up on Remark 3.9, consider representation (3.19) with K y ≡ 1
    byt = (t, xt ). In this case we can observe
and x
                                                 (t − s)n
                                                 (n),τ
                                       VSig(t; 1)s,t     =,
                                                    n!
which led to the expressions (3.16) in corollary 3.6, so that hypothesis 3.4 was satisfied
thanks to the Weierstrass theorem.
Example 3.11. Still continuing Remark 3.9, let us now take K y (t, s) = Γ(α)−1 (t − s)α−1
in (3.19). We then get
                                         Z t
                              (n),τ
                  VSig(t; K1 )s,t = cα,n     (τ − u)α−1 (u − s)(n−1)α ds,
                                                  s
for some explicit constant cα,n . In particular, one can easily check that
                       (n),u                     d             (n),T
          VSig(t; K1 )0,u      = ĉ1α,n unα ,      VSig(t; K1 )u,T = ĉ2α,n (T − u)nα−1 ,
                                                du
for some constants ĉ1α,n , ĉ2α,n ̸= 0. Both families are dense in L2 , as a consequence of the
Szász’s theorem [81, Satz A]: For any sequence of real numbers 0 < λ1 < λ2 < · · · , the linear
                                                                               P 1+2λi
span of the family {tλi : i ≥ 1} is dense in L2 ([0, T ], R), if and only if i 1+(λ   i)
                                                                                        2 = ∞.


   Having set a notation for augmented paths related to kernels, we now turn to the question
of injectivity of the Volterra signature in terms of the kernel K or in terms of the signal
x. Otherwise stated, we shall discuss the injectivity of the mapping (3.1) and (3.2). Note
that both questions are relevant in applications.
                                                          ′
Proposition 3.12. Assume y ∈ V 1 ([0, T ]; Rm ) is such that hypothesis 3.4 holds. We
                                ′
consider z ∈ V̂y1 ([0, T ]; Rm+m ), represented as in (3.17)-(3.18). Then
                                     THE VOLTERRA SIGNATURE                                      27

    (i) For a fixed K ∈ L∞,1 (∆2 ; L(Rd ; Rm )) such that det(K(T, t)) ̸= 0 for a.e. t ∈ [0, T ],
        the map
          h                                    i
            C 0,1 ([0, T ]; Rd ) ∩ {x : x0 = ξ} ∋ x 7→ VSig(b    b y )T0,T ∈ T ((Rm+m′ ))
                                                            xy ; K

        is injective for any initial value ξ ∈ Rd .
   (ii) For a fixed M ⊂ C 0,1 ([0, T ]; Rd ) with |M| < ∞ and such that span{ẋt : x ∈ M} =
        Rd for a.e. t ∈ [0, T ], the map
                                                                            ′
          L∞,1 (∆2 ; L(Rd ; Rm )) ∋ K 7→ VSig(b    xy ; K
                                                        b y )T0,T   ∈ T ((Rm+m ))|M|
                                                                    x∈M
        is injective.

Proof. For any (x1 , K1 ), (x2 , K2 ) ∈ C 0,1 × L1,∞ , it follows from theorem 3.5 that whenever
VSig(bxy1 ; K
            b y )T = VSig(b
             1 0,T           xy2 ; K
                                   b y )T , the corresponding Volterra paths coincide, and thus
                                    2 0,T
in particular
                        K1 (τ, t)ẋ1,t = K2 (τ, t)ẋ2,t for a.e. (t, τ ) ∈ ∆2 .           (3.21)
If K = K1 = K2 as in (i), choosing τ = T and using det(K(T, t)) ̸= 0 shows that
ẋ1 = ẋ2 almost everywhere. Since we have assumed in (i) that x1,0 = x2,0 = ξ, we get
x1 = x2 . Let us now turn to case (ii). Then for each x ∈ M we obtain from (3.21) with
x1 = x2 = x that K1 (τ, t)ẋt = K2 (τ, t)ẋt for a.e. (t, τ ) ∈ ∆2 . Then owing to the fact
that span{ẋt : x ∈ M} = Rd for a.e. t (part of our assumptions in (ii)), we also get
K1 (τ, t) = K2 (τ, t) for a.e. (t, τ ) ∈ ∆2 . This finishes our proof.                        □

3.3. Universal approximation. In this section we provide a theoretical basis for how
the Volterra signature can be used for learning continuous functions on path space. We
start by stating a generic result, which leverages the continuity and injectivity properties
from the previous section to formulate a universal approximation result.
Definition 3.13. We say that a sequence of function classes (Hn )n≥1 with Hn ⊂ C 0 (Rn ; R)
is a universal approximator if, for every n ≥ 1 and every compact set Kn ⊂ Rn , the set
{f |Kn | f ∈ Hn } is dense in (C 0 (Kn ; R), ∥ · ∥∞ ).

   Paired with a suitable continuous and injective feature map, such universal approxima-
tors can be used for approximation of continuous functions on generic (infinite dimensional)
topological spaces. Here we spell this out for the Volterra signature as a feature map on
path space.
  Recall from the previous section that there are augmentation maps of the form
                                                                    ′
                        b· : V 1 ([0, T ]; Rm ) → V 1 ([0, T ]; Rm+m ),   z 7→ zb
such that the Volterra lift z 7→ b  zT0,T := [1 ∗ ẑ]T0,T becomes injective (e.g. time-augmentation
in Corollary 3.6). Similarly, under suitable assumptions on the kernel K, there are aug-
mentation maps
                                                                     ′
                     b· : C 0,1 ([0, T ]; Rd ) → C 0,1 ([0, T ]; Rd+d ), x 7→ x
                                                                              b
                                                           T
such that the Volterra signatures x 7→ VSig(x̂; K)0,T become injective (see Remark 3.9 and
proposition 3.12). For the following result we fix any such map.
Proposition 3.14. Let (Hn )n≥1 be a universal approximator according to Definition 3.13
and let K ⊂ C 0,1 ([0, T ]; Rd ) (respectively K ⊂ V 1 ([0, T ]; Rm )) be compact. Then for all
                                                                                             ′
continuous functionals F : K → R and ϵ > 0 there exist n ≥ 1, π1 , . . . , πn ∈ T (Rd+d )
                                 ′
(resp. π1 , . . . , πn ∈ T (Rm+m )) and fn ∈ Hn such that
                                                                                
                    sup F (x) − fn ⟨π1 , VSig(x̂; K)⟩, . . . , ⟨πn , VSig(x̂; K)⟩ < ϵ,
               x∈K
                                     THE VOLTERRA SIGNATURE                                        28

respectively
                                                                          
                                             zT0,T ⟩, . . . , ⟨πn , b
                        sup F (z) − fn ⟨π1 , b                      zT0,T ⟩ < ϵ,
                       z∈K

where the pairings ⟨πj , VSig(b                zT0,T ⟩ are understood thanks to Definition 2.4.
                              x; K)⟩ and ⟨πj , b

Proof. We treat both cases simultaneously. Let e ∈ {d + d′ , m + m′ } and let Φ denote the
corresponding injective and continuous (see Proposition 3.2) feature map, i.e.

                            x; K) ∈ T ((Re ))
               Φ(x) := VSig(b                          or              zT0,T ∈ T ((Re )).
                                                               Φ(z) := b

Set X := T (Re ) and X ′ := T ((Re )) = ∞                 e ⊗k                   ′
                                                 Q
                                                    k=0 (R ) , and equip X with the product
topology. By construction, this is the coarsest topology such that the linear maps ⟨π, ·⟩ :
X ′ → R are continuous for all π ∈ X . Consider the class of cylindrical functions
        n                                                                                           o
 Acyl := X ′ → R : x 7→ f (⟨π1 , x⟩, . . . , ⟨πn , x⟩) n ≥ 1, π1 , . . . , πn ∈ X , f ∈ C 0 (Rn ; R) .

Clearly Acyl is a unital subalgebra of C 0 (X ′ ; R) that separates points on X ′ .
  Now define the class of functions on K obtained by composition with Φ,
                             AΦ := { f ◦ Φ | f ∈ Acyl } ⊂ C 0 (K ; R).
Since Φ is continuous, AΦ is a unital subalgebra of C 0 (K ; R). Crucially, due to the
injectivity of Φ it also separates points on K . As K is compact, the Stone–Weierstrass
theorem implies that AΦ is dense in C 0 (K ; R) in the uniform norm. Therefore, for any
continuous functional F : K → R and ε > 0 there exist n ≥ 1, π1 , . . . , πn ∈ X and
f ∈ C 0 (Rn ; R) such that
                                                                       ε
                        sup F (u) − f ⟨π1 , Φ(u)⟩, . . . , ⟨πn , Φ(u)⟩ < .
                       u∈K                                              2
Set                          n                                              o
                     Kn :=       ⟨π1 , Φ(u)⟩, . . . , ⟨πn , Φ(u)⟩ ∈ Rn   u∈K .
                                                                 

Then Kn is compact as the continuous image of the compact set K . Since (Hn )n≥1 is a
universal approximator, there exists fn ∈ Hn such that
                                                       ε
                                 sup |f (y) − fn (y)| < .
                                y∈Kn                   2
The statement now follows by combining the two estimates with the triangle inequality. □

Remark 3.15. For the universal approximator (Hn )n≥1 , we can simply use polynomials,
as suggested in the context of Itô signatures in [50]. However, numerical methods for
stochastic control problems with classical signatures have proven successful when using
deep neural networks, see [2, 8, 13, 14].

Remark 3.16. Recall that V 1 ([0, T ]; Rm ) is introduced in Definition 2.18. We get a compact
subspace K of V 1 ([0, T ]; Rm ) if we replace Definition 2.18-(iii) by some Hölder regularity
condition on the derivative of z. Namely define K as
                                                                                   
                                              d
        K = z ∈ V 1 ([0, T ]; Rm ) : t 7→ ztτ α ≤ M1 and τ 7→ ztτ β ≤ M2 ,
                                             dt     C                       C

where α, β ∈ (0, 1) and M1 , M2 > 0 are fixed constants. Then it is a classical fact (see
e.g [7, Corollary 2.96]) that K is compact in V 1 ([0, T ]; Rm ).
                                       THE VOLTERRA SIGNATURE                                          29

  Compared with the classical signature, the above result is only partially satisfying, as
one hopes for a universal approximation theorem by linear functionals. As the (generally
kernel-dependent) algebraic properties of the Volterra signature are out of the scope of this
paper, we cannot prove such a theorem in the general case. However, as we demonstrate
below, for the case of exponential kernels, linear approximation is possible, suggesting that
such a theorem may hold in a more general setting as well.
  Specifically, we consider time-augmented signals t 7→ x  bt = (t, xt )⊤ ∈ Rd+1 , together
with exponential matrix kernels seen in Section 2.4, of diagonal form
Kαλ (t, s) := diag(α0 e−λ0 (t−s) , . . . , αd e−λd (t−s) ) ∈ L(Rd+1 , Rd+1 ),   αi ∈ R \ {0},   λi ∈ R+ .
                                                                                                   (3.22)
In the following result we show linear universality for the two cases:
     (i) λ0 = 0, that is the first component of the corresponding Volterra path ztτ =
         Rt λ
          0 Kα (t, s) db
                       xs is time, see also Corollary 3.6.
    (ii) λ0 = · · · = λd > 0 and α0 = · · · = αd ̸= 0, which is equivalent to the scalar-kernel
         case k(t, s) = αe−λ(t−s) , see also Proposition 2.44.
Theorem 3.17. Denote by Kαλ ∈ L∞,1 (∆2 ; L(Rd+1 ; Rd+1 )) the exponential kernel de-
fined in (3.22), such that either (i) or (ii) above holds. Then, for any compact set K ⊂
C 0,1 ([0, T ], Rd ) and continuous functional F : C 0,1 ([0, T ], Rd ) → R, it holds that for all
ε > 0, there exists π ∈ T (Rd+1 ) such that

                                                      x; Kαλ )⟩ < ε.
                                 sup F (x) − ⟨π, VSig(b                                           (3.23)
                                 x∈K

  For the case (ii) above, the proof relies on the following technical lemma, showing that
we can revert the transformation from the classical signature to the Volterra signature in
Proposition 2.44.
Lemma 3.18. Let X be a compact topological space and set C := C 0 ([0, T ]×X; R) equipped
with the supremum norm ∥ · ∥∞ . Further, let λ ∈ R and α > 0 and define, for any g ∈ C ,
                                        Z T
              Ψ[g](t, x) := g(t, x) + λ     eλr g(r, x) dr, t ∈ [0, T ], x ∈ X.
                                              t
Then Ψ is an isomorphism on the topological vector space C .

Proof. It is evident that Ψ is linear and decomposes as Ψ = Id + Φ. One readily esti-
mates ∥Φ◦n [g]∥∞ ≤ n! 1
                        |λ|n en|λ|T T n ∥g∥∞ , implying in particular continuity of Φ and thus
of Ψ. Further, this shows that the Neumann series Ψ−1 = ∞                 n ◦n converges, thus
                                                               P
                                                                  n=0 (−1) Φ
proving that Ψ is an isomorphism.                                                           □

  Now we are ready to prove the theorem for linear approximation via the Volterra signa-
ture with exponential kernels.

Proof of Theorem 3.17. Let us first assume (i) holds true. We first claim that for any
element π ∈ T (Rd+1 ), there exists a ℓ = ℓ(π) ∈ T (Rd+1 ), such that
                               ⟨π, Sig(b                     x; Kαλ )T0,T ⟩.
                                       x)0,T ⟩ = ⟨ℓ(π), VSig(b                                    (3.24)
Assuming the claim (3.24) is true, by universality of the classical signature from time-
augmented paths (e.g. [68, Theorem 5]), we can find π ε ∈ T (Rd+1 ) such that
                                   sup |F (x) − ⟨π ε , Sig(b
                                                           x)0,T ⟩| ≤ ε,
                                   x∈K
                                          THE VOLTERRA SIGNATURE                                               30

and thus in particular supx∈K |F (x) − ⟨ℓ(π ε ), VSig(b     x; Kαλ )⟩| ≤ ε. To show the claim (3.24),
an application of Proposition 2.42, for the choices br = er , Ar = αr e⊤           r er with 0 ≤ r ≤ d
and matrix Λ = diag(λ0 , . . . , λd ), shows that for any i1 , . . . , in ∈ {0, . . . , d}
                                 Z T                                    Z T
            λ i1 ···in ,T                       λ i1 ···in ,s                               i1 ···in−1 ,s
  VSig(b
       x; Kα )0,T         = −λin      VSig(b
                                           x; Kα )0,s         ds + αin      VSig(b  x; Kαλ )0,s            xisn
                                                                                                          db
                                      0                                        0
                                                                  Z T
                                             1 ···in 0,T                                 i ···i   ,s
                                   x; Kαλ )i0,T
                       = −λin VSig(b                     + αin                x; Kαλ )0,s
                                                                         VSig(b        1  n−1
                                                                                               xisn , (3.25)
                                                                                              db
                                                                     0

where the second equality follows from the assumption λ0 = 0 and x           b0t = t. The claim
now easily follows by induction over elements in T n (Rd+1 ) (see definition 2.5), together
with (3.25). Indeed, for n = 1 and single letter π = i ∈ {0, . . . , d}, we have
                                        1                                              
          ⟨i, Sig(b         biT − x
                  x)0,T ⟩ = x     bi0 =     VSig(bx; Kαλ )i,T
                                                          0,T +  λ  i VSig(b
                                                                           x ; K λ i0,T
                                                                                  )
                                                                                 α 0,T
                                        αi
                                                             x; Kαλ ),T
                                               = ⟨ℓ(i), VSig(b       0,T ⟩,                             (3.26)

for ℓ(i) = α1i i(∅ + λi 0). Since we can extend (3.26) linearly to any linear combination of
letters, the claim (3.24) holds for π ∈ T 1 (Rd+1 ). Assuming the claim holds on level n, for
π = i1 · · · in+1 we have
                     Z T                                     Z T
                                                      in+1
  ⟨π, Sig(bx)0,T ⟩ =     ⟨i1 · · · in , Sig(b
                                            x)0,s ⟩ db
                                                     xs    =                            x; Kαλ )s0,s ⟩ db
                                                                 ⟨ℓ(i1 · · · in ), VSig(b               xisn+1 ,
                       0                                         0
where we used the definition of the signature and the induction hypothesis. An application
of (3.25) then shows
   Z T
                              x; Kαλ )s0,s ⟩ db
       ⟨ℓ(i1 · · · in ), VSig(b               xisn+1
    0
                                               D 1                                                        E
                                           =                                                  x; Kαλ )T0,T ,
                                                      ℓ(i1 · · · in )in+1 (∅ + λin+1 0), VSig(b
                                                αin+1
and since we can extend linearly to π ∈ T n+1 (Rd+1 ), the claim (3.24) follows by induction.
   Now suppose (ii) holds, and let Ψ be the operator defined as in lemma 3.18 with X = K .
Let F : C 0,1 ([0, T ]; Rd ) → R be continuous and let ε > 0 be arbitrarily fixed. Define the
function f : [0, T ] × C 0,1 ([0, T ]; Rd ) by f (t, x) := F (xt∨· ), where xt∨r := 1[0,t) (r)xt +
1[t,T ] (r)xr ∈ C 0,1 ([0, T ]; Rd ). We first apply the inverse operator of Ψ from Lemma 3.18 to
f ∈ C to obtain the transformed function g := eλT Ψ−1 [f ] ∈ C . Then, by a time reversed
formulation of the universal approximation theorem for signatures on the stopped paths
space there exists π ∈ T (Rd+1 ) such that
          ∥g − ⟨π, Sig(b                                     x)t,T ⟩ < ∥Ψ∥−1 eλT ε,
                       x)·,T ⟩∥∞ = sup sup g(t, x) − ⟨π, Sig(b
                                          x∈K t∈[0,T ]

where ∥Ψ∥ denotes the operator norm of Ψ on (C , ∥ · ∥∞ ). Indeed, this follows by an
entirely analogous argument to the stopped path space situation (e.g. in [8, Proposition
3.3]) where one verifies that the maps x|[t,T ] 7→ ⟨π, Sig(bx)t,T ⟩, π ∈ T (Rd+1 ), form a point-
separating     unital subalgebra of the continuous functions on the forward-started path space
             0,1 ([t, T ]; Rd ) equipped with the distance
S
  t∈[0,T ] C
                            d(x|[t,T ] , y|[s,T ] ) := |t − s| + ∥x·∨t − y·∨s ∥C 0,1 .
Next note that by Proposition 2.44 and the definition of Ψ in Lemma 3.18 it holds
                         x; Kα,λ )0,T ⟩ := e−λT Ψ[⟨π, Sig(b· )·,T ⟩](0, x),
                ⟨π, VSig(b                                                                x∈K.
                                    THE VOLTERRA SIGNATURE                                           31

Finally, we can estimate

                        x; Kα,λ )0,T ⟩ = sup f (0, x) − ⟨π, VSig(b
   sup F (x) − ⟨π, VSig(b                                        x; Kα,λ )0,T ⟩
  x∈K                                        x∈K
                     −λT
           ≤ sup e         Ψ[g − ⟨π, Sig(b· )·,T ⟩](0, x) ≤ e−λT ∥Ψ∥ ∥g − ⟨π, Sig(b· )·,T ⟩∥∞ ≤ ε.
               x∈K

This concludes the proof of (3.23) in case (ii).                                                     □

3.4. Kernel trick. Kernel methods provide a flexible framework for learning with struc-
tured data by specifying similarity through a positive definite kernel, equivalently an inner
product in an associated reproducing kernel Hilbert space (RKHS) [5, 80]. This viewpoint
underpins classical algorithms such as support vector machines and Gaussian processes
and allows nonlinear learning problems to be treated with linear methods in feature space.
In the context of time series, the signature kernel [62, 79] can be viewed as a canonical
choice when one seeks a positive definite kernel that simultaneously (i) captures sequential
order, (ii) behaves well under high-frequency sampling, and (iii) is invariant under mono-
tone reparametrizations (see [62, Section 5] for a detailed comparison with other popular
kernels for sequential data [25, 18, 35, 71]). However, the (standard) signature kernel does
not by itself enforce a specific memory structure, such as a recency bias. Since the Volterra
signature VSig(x; K) already incorporates the memory profile K at the feature level, we
transfer this structure to kernel methods by defining the Volterra signature kernel as in-
duced by the inner product. In this way, the similarity between two paths is modulated
by K, yielding a positive definite kernel that inherits the temporal weighting of events.
Remark 3.19. We are now facing the embarrassing—but highly intriguing—situation of
having two kernels present on the same stage: a temporal (or memory) kernel K : ∆2 →
L(Rd , Rm ), and an induced kernel on the (Volterra-)path space. To keep these two notions
from stepping on each other’s toes, we denote the latter by κ. Things get even more
intriguing if we further—as suggested in the classical signature setting in [61]—lift the
Volterra path into yet another RKHS feature space. We will find some resolution of this
kernel-within-kernel situation in Remark 3.28 below.

  Recall that the classical signature kernel is defined as the inner product of signatures,
                           Sig(x), Sig(y) T 2 ,    x, y ∈ C 0,1 ([0, T ]; Rd ),
where the inner product on T 2 was introduced in definition 2.7. We extend this construc-
tion to Volterra features by restricting to suitable subspaces of Volterra paths, denoted
V 1 ([0, T ]; Rm ) (see definition 2.18), on which the Volterra signature and the induced inner
product are well-defined.
Definition 3.20. For any 1 ≤ p ≤ ∞ we denote by V 1,p ([0, T ]; Rm ) the space consisting
of Volterra paths
          Z t
    ztτ =     K(τ, s) dxs with x ∈ C 0,1 ([0, T ]; Rd ) and K ∈ L∞,p ([0, T ]; L(Rd ; Rm )),
           0
where the space L∞,p was defined in (2.32). Moreover, for any z ∈ V 1,p we extend the
norm (2.9) by setting
                                           Z t          1/p
                                                dzut p
                        ∥z∥1,p := sup                  du     .                 (3.27)
                                  t∈[0,T ]   0  du

  Note that V 1,1 = V 1 thanks to lemma 2.19, and clearly for any 1 ≤ p ≤ q ≤ ∞ we have
the inclusion V 1,q ⊆ V 1,p . We can now define the Volterra signature kernel.
                                         THE VOLTERRA SIGNATURE                                                              32

Definition 3.21. Let p > 1 and consider two Volterra paths z, y ∈ V 1,p ([0, T ]; Rm ) with
full lifts denoted by z and y, see definition 2.22. The Volterra signature kernel is defined
as the inner product
                              κ(z, y)s,t = ⟨zs0,s , y0,t
                                                     t
                                                         ⟩T 2 ,       (s, t) ∈ [0, T ]2 .                           (3.28)
                                                                               Rt
   In view of remark 2.16, for two paths x, w ∈ C 0,1 ([0, T ]; Rd ) and ztτ = 0 dxs and
      Rt
ytτ = 0 dws , the definition (3.28) coincides with the classical signature kernel of x and
w seen above. The following lemma shows that the generalization to V 1,p in (3.28) is
well-defined.

Lemma 3.22. For any p > 1 and z, y ∈ V 1,p ([0, T ]; Rm ), the Volterra signature ker-
nel (3.28) is well-defined. Specifically, we have
                                                sup         |κ(z, y)s,t | < ∞.
                                            (s,t)∈[0,T ]2

Proof. This is a direct consequence of the Cauchy-Schwarz inequality for the inner product
in Definition 2.7 and the infinite radius of convergence on V 1,p of the Volterra signature,
see Lemma 2.37.                                                                           □

   It was shown in [79] that the classical signature kernel can be characterized as the
unique solution to a hyperbolic Goursat PDE, enabling its computation without explicit
truncation. We now extend this kernel trick to the Volterra setting.

Theorem 3.23. Let p > 1 and consider two Volterra paths z, y ∈ V 1,p ([0, T ]; Rm ). The
Volterra signature kernel κs,t := κ(z, y)s,t in (3.28) uniquely solves
                                        Z sZ t
                            κs,t = 1 +          κu,v ⟨żut , ẏvs ⟩ du dv.         (3.29)
                                                      0      0

Proof. Existence: Recall that from the fundamental linear equation for the Volterra signa-
ture (see (2.20)), we know
                               Z s                         Z t
                   zs0,s = 1 +     zu0,u ⊗ dzus , y0,t
                                                   t
                                                       =1+      v
                                                               y0,v ⊗ dyvt .
                                        0                   0
                                                          τ   ρ
From Lemma 3.22, we also have that the inner product ⟨z0,s , y0,t ⟩ is well-defined. Moreover,
using the bilinearity of the inner product and the fact that the unit tensor 1 ∈ T ((Rm )) is
orthogonal to all tensors of level n ≥ 1, we find
                                        Z s                Z t              
                     s      t                 u       s          v       t
                   ⟨z0,s , y0,t ⟩ = 1 +      z0,u ⊗ żu du,     y0,v ⊗ ẏv dv .                                     (3.30)
                                                    0                     0

Next we use the property that the inner product commutes with the integral and satisfies
the factorization property ⟨A ⊗ a, B ⊗ b⟩ = ⟨A, B⟩⟨a, b⟩ for tensors A, B and vectors a, b
(see Definition 2.7). Specifically, we find
                       Z s                Z t               
    s      t                 u       s          v       t
  ⟨z0,s , w0,t ⟩ = 1 +      z0,u ⊗ żu du,     y0,v ⊗ ẏv dv
                          0                           0
                Z tZ s                                                        Z tZ s
         =1+                  zu0,u ⊗ żus , y0,v
                                              v
                                                  ⊗ ẏvt      du dv = 1 +              zu0,u , y0,v
                                                                                                v
                                                                                                      żus , ẏvt ⟩ du dv.
                  0   0                                                        0   0

By definition, κu,v = ⟨zu0,u , y0,v
                                v ⟩, and substituting this back into (3.30) yields the claimed

integral equation.
                                                   THE VOLTERRA SIGNATURE                                                          33

Uniqueness: Suppose now that there are two continuous solutions to (3.29), and denote
by δ : [0, T ]2 → R their difference. By linearity, δ satisfies the homogeneous equation
                            Z sZ t
                     δs,t =        δu,v ⟨żus , ẏvt ⟩ dv du, (s, t) ∈ [0, T ]2 .
                                       0       0
                                                                               p
Similarly as in Lemma 2.37, we apply Hölder’s inequality with respect to p′ = p−1 (first in
v, then in u) to obtain
                     Z sZ t
           |δs,t | ≤        |δu,v ||żus ||ẏvt | dv du
                      0       0
                     Z s              Z t                        1/p′ Z t                      1/p
                                                        p′
                 ≤         |żus |             |δu,v | dv                           |ẏvt |p dv          du
                      0                    0                                    0
                     Z s                      1/p Z t                        1/p Z s Z t                          1/p′
                                                                                                              p′
                 ≤            |żus |p du                         |ẏvt |p dv                          |δu,v | dv du
                          0                                   0                             0      0
                                               Z s Z t                              1/p′
                                                                      p′
                 ≤ ∥z∥1,p ∥y∥1,p                              |δu,v | dv du                  ,
                                                    0    0
where we recall ∥ · ∥1,p was defined in (3.27).
   Raising the previous inequality to the power p′ and iterating gives, for every n ≥ 1 and
all s, t ∈ [0, T ],
                                                                   ′ n
                                                             ′
                                                                    
                                            ∥z∥∞,p ∥y∥∞,p s1/p t1/p
                    sup         |δu,v | ≤                                    sup         |δu,v |.
              (u,v)∈[0,s]×[0,t]                     (n!)2/p′           (u,v)∈[0,s]×[0,t]

Letting n → ∞ implies sup(u,v)∈[0,s]×[0,t] |δu,v | = 0 for all s, t, hence δ ≡ 0.                                                  □

   Similar to before, depending on the application, one may view the Volterra signature
kernel as being induced by the feature map C 0,1 ∋ x 7→ VSig(x; K), see also (3.1), and
treat the Volterra kernel K as a modeling component. To this end, for any kernel K ∈
L∞,p ([0, T ]; L(Rd ; Rm )) with p > 1, we define for (s, t) ∈ [0, T ]
      κK (x, w)s,t := ⟨VSig(x; K)s0,s , VSig(w; K)t0,t ⟩T 2 ,                                x, w ∈ C 0,1 ([0, T ]; Rd ),      (3.31)
and the following kernel trick is a direct consequence of Theorem 3.23.
Corollary 3.24. Let p > 1 and fix a kernel K ∈ L∞,p ([0, T ]; L(Rd ; Rm )). Then the kernel
κK in (3.31) uniquely solves
                       Z sZ t
             K
            κs,t = 1 +        κK
                               u,v ⟨K(s, u)ẋu , K(t, v)ẏv ⟩ du dv, s, t ∈ [0, T ]2 . (3.32)
                                  0        0

   We conclude this section with a characterization of the Volterra signature kernel (3.31),
restricted to finite state space kernels considered in Section 2.4, that is
                                                    q
                                                    X
                            Λ
                           KA,b (t, s) =                     (1⊤ e−Λ(t−s) br )Ar ∈ L(Rd ; Rm ),                                (3.33)
                                                    r=1

where Λ ∈ RR×R , Ar ∈ Rm×d and br ∈ RR (see Definition 2.39). In Proposition 2.42 we
characterized Volterra signatures VSig(x; KA,b     Λ ) with a system of mean-reverting equations

in the tensor algebra. In the following result we show that the corresponding signature
kernel can be characterized through a system of Goursat-PDEs. To this end, given two
signals x, w ∈ C 0,1 ([0, T ]; Rd ), let us introduce the coefficient matrix
                          γ(s, t) ∈ RR×R ,                        γij (s, t) = ⟨(B.ẋs )i , (B.ẇt )j ⟩,                       (3.34)
                                                  THE VOLTERRA SIGNATURE                                                      34

where we recall that the notation (B.ẋt ) was introduced in (2.38).

Theorem 3.25. Consider the matrix-valued functions K, Ψ, Φ : [0, T ] → RR×R , defined
as solutions to the following PDE system on [0, T ]2
                              ∂ 2 Ks,t
                                       = ηs,t γ(s, t) + ΛKs,t Λ⊤ − ΛΨs,t − Φs,t Λ                                        (3.35)
                               ∂t∂s
                               ∂Ψs,t
                                       = −ΛΨs,t + γ(s, t)ηs,t ,                                                          (3.36)
                                  ∂s
                               ∂Φs,t
                                       = −Φs,t Λ⊤ + ηs,t γ(s, t),                                                        (3.37)
                                  ∂t
where ηs,t := 1 + 1⊤ Ks,t 1 and with the boundary conditions
                    K0,0 = K0,t = Ks,0 = Ψ0,t = Φs,0 = 0,                                     (s, t) ∈ [0, T ]2 ,
where we recall that γ is defined by (3.34). Then, for two paths x, w ∈ C 0,1 ([0, T ]; Rd ), and
a kernel K given by (3.33), the kernel κK in (3.31) can be expressed as
                                                                 κK
                                                                  s,t = ηs,t .                                           (3.38)

Proof. Let us denote by Z (resp. by Y) the lift in Proposition 2.42 with respect to the path
x (resp. the path w). From the latter proposition we know that κs,t = ⟨1 + R          ℓ
                                                                             P
                                                                                ℓ=1 Zs,t , 1 +
PR      ℓ
  ℓ=1 Ys,t ⟩, where Z and Y uniquely solve
                                                        R
                                                               !
                                                       X
                                                             i
                Zs,s = 0, dZs,t = −Λ.Zs,t dt + 1 +         Zs,t ⊗ d(B.xt ).            (3.39)
                                                                                       i=1

and
                                                                                       R
                                                                                                    !
                                                                                       X
                                                                                              i
                   Ys,s = 0,            dYs,t = −Λ.Ys,t dt +                     1+          Ys,t       ⊗ d(B.wt ),      (3.40)
                                                                                       i=1
respectively. Relying on the bi-linearity of the inner product, we write
                                                    R                                        R
                                                                          j                      e ij .
                                                    X                                        X
                                      κs,t = 1 +                ⟨Zi0,s , Y0,t ⟩ =: 1 +           K s,t                   (3.41)
                                                   i,j=1                                 i,j=1

In order to get a more explicit expression for Ke ij above, let us recall (similarly to what we
                                                  s,t
did in the derivation of the integral equation in theorem 3.23) that from (3.39), integrating
against time and using Z0,0 = 0, we obtain the integral form
                  R
                  X           Z t                   Z t             R
                                                                     X          
      Zi0,t = −         Λin           Zn0,v dv +                1+         Zℓ0,v ⊗ d(B.ẋv )i ,             1 ≤ i ≤ R,   (3.42)
                  n=1             0                     0            ℓ=1

and similarly for Y relying on (3.40). Inserting the integral form into the definition
e ij := ⟨Zi , Yj ⟩ and exchanging the inner product with integration (as in the proof
K s,t     0,s   0,t
of theorem 3.23), we find
                              R          Z s                       Z s
  ∂2K
    e ij        D X                                                                       
                                                Zn0,u du +                              ℓ
                                                                               P
         = ∂s ∂t −  Λin                                                   1+         ℓ 0,u ⊗ d(B.ẋu )i ,
                                                                                      Z
  ∂t ∂s                                     0                        0
                          n=1
                                            R           Z t                    Z t                                   E
                                                                  p
                                            X
                                                                                                    ℓ
                                                                                             P
                                        −         Λjp            Y0,v dv +             1+         Y
                                                                                                 ℓ 0,v   ⊗ d(B. ẇv )j  . (3.43)
                                            p=1             0                    0
                                                 THE VOLTERRA SIGNATURE                                                   35

Expanding by bilinearity of the inner product, the above expression can be decomposed
as:
                                      ∂2Ke ij
                                              = T1 + · · · + T4 ,               (3.44)
                                       ∂t ∂s
where the terms T1 , . . . , T4 are respectively defined by
                R                    DZ s          Z t            E
                                                           p
               X
                                            n
      T1 =           Λin Λjp ∂s ∂t        Z0,u du,      Y0,v  dv                (3.45)
                  n,p=1                               0                    0

                       R
                       X                    DZ s                    Z t                                  E
                                                      Zn0,u du,                         ℓ
                                                                                  P
       T2 = −                 Λin ∂s ∂t                                    1+         Y
                                                                                     ℓ 0,v   ⊗ d(B.ẇ v )j            (3.46)
                       n=1                       0                   0
                       R                    DZ s                                                          E
                       X                                      P      ℓ
                                                                                                Rt p
       T3 = −                 Λjp ∂s ∂t                1+         ℓ Z0,u       ⊗ d(B.ẋu )i ,   0 Y0,v dv             (3.47)
                       p=1                       0
                            DZ s                                      R t     P ℓ                E
                                                    ℓ
                                            P
       T4 = ∂s ∂t                      1+         Z
                                                 ℓ 0,u   ⊗ d(B.ẋ  )
                                                                  u i ,  0   1 +   Y
                                                                                  ℓ 0,v ⊗ d(B. ẇ )
                                                                                                 v j   (3.48)
                               0
Now the terms T1 , . . . , T4 can be differentiated in a very similar way. Indeed, differentiating
first in t and then in s, and writing out the k-th components of (B.ẇt )j , we get
          R           m D                       R              E               R     m
                                                        p                                 n,k
          X           X                          X                               X     X
 T2 = −         Λin           Zn0,s ,       1+         Y0,t   ⊗ek (B.ẇt )jk = −   Λin   ψs,t βjk (t), (3.49)
          n=1         k=1                        p=1                                        n=1       k=1

where we used the definitions
                    D         R           E
             n,k                  p
                               X
                       n
            ψs,t := Z0,s , 1 +   Y0,t   ⊗ ek ,                                    and βjk (t) := (B.ẇt )jk .         (3.50)
                                                     p=1

In the same way (leaving the tedious details to the patient reader), we find
            R                                                 R
                                      p                                    e np
            X                                                 X
  T1 =              Λin Λjp ⟨Zn0,s , Y0,t ⟩=                       Λin Λjp K s,t
           n,p=1                                           n,p=1
                R           m D   R                  E                R     m
                                                   p
                                                                                φk,p
                X           X      X                                    X     X
  T3 = −              Λjp       1+   Zn0,s ⊗ ek , Y0,t   (B.ẋs )ik = −   Λjp    s,t αik (s)
                p=1         k=1                n=1                                                   p=1        k=1
                                  
                            e pq ⟨(B.ẋs )i , (B.ẇt )j ⟩ = κs,t γij (s, t),
                      X
  T4 =         1+           K s,t
                      p,q

where we used the notation γij in (3.34), and (3.34))
                             D          R                        E
                φk,p                                           p
                                         X
                 s,t :=            1+            Zn0,s ⊗ ek , Y0,t   ,            and αik (s) := (B.ẋs )ik ,
                                         n=1
                                                                                       P e pq
and where for the computation of T4 we have resorted to the fact that κs,t = 1 + p,q K         s,t
(see (3.41)). Now gathering the terms T1 , . . . , T4 and plugging those expressions into (3.44),
we discover that
                                        R
  ∂2K
    e ij                     X
                                       e np
         = κs,t γij (s, t) +   Λin Λjp K s,t
  ∂t ∂s
                                       n,p=1
                                                              R X
                                                                m                                             
                                                                                n,k
                                                                                    βjk (t) + Λjn φk,n
                                                              X
                                                          −                Λin ψs,t                s,t α ik (s)  . (3.51)
                                                              pn=1 k=1
                                           THE VOLTERRA SIGNATURE                                             36

We still have to find a more explicit expression for the terms ψ n,k and φk,n in (3.51). To
this aim, we apply the same techniques as in the above computations. That is starting
from the definition (3.50) of ψ n,k we get
           * R        Z s            Z s      R                          R
                                                                                       +
                                                                               
     n,k                                                                     p
             X                                X                          X
    ψs,t =       −Λnl     Zℓ0,u du +     (1 +   Zℓ0,u ) ⊗ αn (u) du, 1 +   Y0,t   ⊗ ek
              ℓ=1              0                   0       ℓ=1                                 p=1
             R            Z sD                R           E               Z s
                                                  p
             X                                 X
         =         −Λnℓ            Zℓ0,u , 1 +   Y0,t   ⊗ ek du +                 ηu,t ⟨αn (u), ek ⟩ du
             ℓ=1           0                       p=1                        0

             R            Z s                Z s
                                 ℓ,k
             X
         =         −Λnℓ         ψu,t du +           ηu,t αnk (u) du,
             ℓ=1           0                   0

so that in particular
                                                            R
                           n,k                  n,k                    ℓ,k
                                                            X
                          ψ0,t = 0,         ∂s ψs,t =−            Λnℓ ψs,t + ηs,t αnk (s).                (3.52)
                                                            ℓ=1

Similarly one finds
                                                            R
                           φk,n              ∂t φk,n              Λnℓ φk,ℓ
                                                            X
                            s,0 = 0,             s,t = −               s,t + ηs,t βnk (t).                (3.53)
                                                            ℓ=1

                         e n,j = Pm ψ n,k βjk (t) appearing in (3.49) for 1 ≤ n, j ≤ R, we
Now using (3.52) for the Ψ s,t    k=1 s,t
find
                                   R                        m
                                                           X                       R
e n,j = 0,            e n,j = −              e ℓ,k +ηs,t                                   e ℓ,k +ηs,t γnj (s, t).
                                   X                                                 X
Ψ 0,t              ∂s Ψ s,t              Λnℓ Ψ s,t                αnk (s)βjk (t) = −   Λnℓ Ψ s,t
                                   ℓ=1                     k=1                           ℓ=1

Writing Ψe = (ψen,j )1≤n,j≤R , the last equations show that Ψ e solves (3.36). Applying the
                       p,i     Pm      k,p
same treatment for φ  bs,t :=    k=1 φs,t αik (s) together with (3.53), leads to the solution
Φ = (φ
e        p,i
        e )1≤p,i≤R of (3.37). In particular, we have shown that the triplet (K,     e Ψ,e Φ)
                                                                                           e
indeed solves the system (3.35)-(3.37), and thus that K  e = K. Hence comparing (3.38) and
(3.41), our theorem is proved.                                                              □

  We end this section with several remarks.

Remark 3.26. The system of Goursat PDEs (3.35)–(3.37) generalizes the PDE considered
for classical signatures in [79]. The latter is recovered by choosing R = q = b1 = 1, Λ = 0,
and A = Id, that is, by taking the trivial kernel K(t, s) ≡ Id in (3.33). More importantly,
the numerical schemes and computational ideas developed in [79] can be extended to the
present setting, yielding efficient algorithms for the computation of κK . We refer the
interested reader to the accompanying paper [47] for further details,.

Remark 3.27. Notice that the auxiliary equations (3.36)–(3.37) admit the explicit repre-
sentations
        Z s                                   Z t
              −Λ(s−u)                                            ⊤
Ψs,t =      e         ηu,t γ(u, t) du, Φs,t =     γ(s, u)ηs,u e−Λ (t−u) du, (s, t) ∈ [0, T ]2 .
         0                                                  0

In particular, once a grid of [0, T ]2 is fixed, the auxiliary variables can be propagated along
the grid by using the above integral representations, which leads to efficient finite-difference
schemes, see [47].
                                      THE VOLTERRA SIGNATURE                                   37

Remark 3.28. One of the key advantages of the signature kernel trick introduced in [79]
is that one may first pre-process the data via a feature map Rd → H, where H is a
potentially infinite-dimensional feature space, without losing tractability of the resulting
signature kernel. While referring to [47, Section 5.1] for details, let us now illustrate
how this idea applies to the PDE system in Theorem 3.25. For simplicity, let q = 1
in (3.34) so that K(t, s) = k(t, s)A, where k(t, s) = 1⊤ e−Λ(t−s) b is a scalar kernel and
A : Rd → Rm is a linear map. Now suppose we replace the matrix A by some static
feature map A : Rd → H, where H is an RKHS induced by some kernel κH . Although one
may formally define the Volterra signature associated with the H-valued paths Xt = A(xt )
and scalar kernel k, its direct computation is infeasible, since H is in general very high-
or infinite-dimensional. However, the situation is different for the corresponding kernel
κs,t = ⟨VSig(X; k), VSig(W ; k)⟩. Indeed, arguing as in Proposition 2.42 and Theorem 3.25,
it is natural to expect that the PDE system (3.35)-(3.37) continues to characterize this
quantity, with respect to the coefficients

               γij (s, t) := bi bj ⟨Ẋs , Ẇt ⟩H ,   (s, t) ∈ [0, T ]2 ,   1 ≤ i, j ≤ R,

where we recall that b = b1 ∈ RR arises from the kernel definition (3.33). Assuming
efficient evaluation of κH , any numerical scheme for the PDE system (3.35)-(3.37) can be
transferred directly to the lifted setting, without increasing its numerical complexity. We
introduce a predictor-corrector finite-difference scheme in the accompanying article [47];
see [47, Algorithm 11].


                                           4. Applications

   In this section, we illustrate the versatility of the VSig feature map in several applications
with synthetic and real-world data. All our applications can be formulated as supervised
learning problems with sequential data x = (xt )t∈T , where T denotes the time index set.
More precisely, we observe input-output pairs {(x(i) , y (i) )}M i=1 , which are related through
an unknown function f . We begin with a synthetic experiment in Section 4.1, where f is
the solution map of a stochastic Volterra equation driven by Brownian motion, which is
learned by regularized least-squares regression on the Brownian Volterra signature. Moving
to real-world data, in Section 4.2 we consider the problem of forecasting future S&P500
realized volatility from past daily log-prices. Similar to the first example, this is achieved
by regression on the Volterra signature of the log-prices. Finally, in Section 4.3 we consider
multivariate time-series classification on various UEA datasets [6]. For this, we employ a
support vector machine (SVM) classifier based on the Volterra signature kernel introduced
in Section 3.4.
   As motivated in the introduction, the signature transform x 7→ Sig(x), see remark 2.16,
provides a powerful feature map and has been successfully employed for various statistical
learning problems with sequential data; see, for instance, [30] and the references therein.
The goal of this section is to illustrate that incorporating a kernel K into the lift, namely
considering x 7→ VSig(x; K), is highly beneficial for the learning tasks outlined above. In
the sequel, we denote by VSigK a model built on the feature VSig(·; K) for some given
kernel K, while in the special case K = Id we write Sig.
   For all methods, we split the data into training and test sets, and select the involved
hyperparameters by cross-validation on the training data. The detailed implementa-
tions of the experiments conducted in this article can be found at https://github.
com/lucapelizzari/Volterra_signature_learning. The code relies on the package
                                  THE VOLTERRA SIGNATURE                                     38

tensordev, see also https://github.com/hagerpa/tensordev, which supports all Volterra
signature algorithms presented in the accompanying article [47].

4.1. Linear Volterra SDE dynamics. We begin with a synthetic toy example involv-
ing non-Markovian data. Let k ∈ L∞,1 (∆2 ; R) be a scalar kernel, B a one-dimensional
Brownian signal, and denote by Y the solution to the linear Volterra SDE (see, e.g., [75])
               Z t                           Z t
     Yt = Y0 +     (b0 + b1 Ys )k(t, s) ds +     (σ0 + σ1 Ys )k(t, s) dBs , 0 < t ≤ T, (4.1)
                 0                          0
for some Y0 , b0 , b1 , σ1 , σ2 ∈ R. Given i.i.d. samples of the pairs (B, Y ), we aim to learn
the solution map B 7→ f (B) = Y . To this end, let us further denote by B̄ the piecewise
linear interpolation of (t, Bt ) on a fixed grid T = {0 = t0 < · · · < tN = T } with N ∈ N,
and by Ȳ the corresponding solution to (4.1) driven by B̄. We consider an empirical
risk minimization for linear functionals Ψθ (x) = ⟨θ, x⟩ as discussed before, and a ridge
regression over a subset of grid-points D ⊆ T, that is
                       M
                1   X X  (i)                            2
     argmin              Ȳtn − θ, VSig(B̄ (i) ; K)t0,t
                                                     n
                                                            + η∥θ∥ℓ2 ,        η ≥ 0.      (4.2)
      |θ|≤L |D| × M
                                                       n
                      i=1 tn ∈D

We compare three models for K in (4.2):
     • Sig (K = Id): Expanding classical SDE solution with iterated integrals of time-
       augmented Brownian motion is very natural for k ≡ 1 in (4.1) (e.g. via stochastic
       Taylor expansions [63]), and was recently considered for non-explosive kernel k
       in [56], where the authors show how to explicitly construct infinite expansions for
       linear equations (4.1).
     • VSigk (K = k): In a situation where the underlying kernel k is known, our ex-
       pansion in proposition 2.38 naturally suggests to choose K = k in (4.2). While
       (at least for non-singular kernels) solutions to (4.1) admit expansions in both the
       classical and the Volterra signature, incorporating the kernel into the signature is
       expected to be advantageous when working with low truncation levels.
     • VSigkλ (K = kλ ): In real-world applications k is often not explicitly known, but it
       might still be beneficial to incorporate a kernel weighting the history of the path.
       We illustrate this here for the parametric class {kλ (t, s) = e−λ(t−s) : λ ∈ R+ } (see
       Section 2.4), where λ is treated as a hyperparameter in the learning problem (4.2).
       This approach will be central in Section 4.2 for financial time series, so that we
       already illustrate it here.
   We generate M = 1000 samples paths B̄ on the grid T with T = 2 and N = 1000. We
                                                                           β−1
choose the underlying kernel to be the fractional kernel kβ (t, s) = (t−s)
                                                                       Γ(β)    with β = 1.10,
and along each sample of B̄ we generate a sample of Ȳ using an Euler–Maruyama scheme.
For the model Sig we use the iisignature library [77], while for the Volterra signatures we
implemented algorithms presented in [47, Section 4.2]. Choosing truncation level L = 6,
the optimization (4.2) is then easily solved as a linear least-square regression problem,
where we consider a 90% − 10% training-testing split, and D = [0, 1] ∩ T, that is we only
train on half of the interval. For the model VSigkλ we additionally perform a grid-search
on [0, 10] for the parameter λ.
   In Figure 4.1 we plot one testing-sample path of the solution Y (j) , as well as the three
trained models Sig, VSigk , VSigkλ on the whole interval [0, 2]. As the plot for one sample
suggests – and Table 1 confirms – all three expansions on the testing data fit the dynamics
Y almost perfectly on the same interval the models were trained. The results are slightly
                                            THE VOLTERRA SIGNATURE                                    39



     3.5
                  true SDE
                  VSig expansion
     3.0          Sig expansion
                  VSig expansion
     2.5          training horizon
     2.0
Xt




     1.5

     1.0

     0.5

     0.0

           0.00            0.25      0.50      0.75    1.00    1.25       1.50       1.75      2.00
                                                       time

           Figure 4.1. Volterra signature vs. classical signature expansions, com-
           pared with the fractional SDE solution (4.1) for one testing sample. The
           models were trained with M = 900 training samples and N = 500 time-
           steps on [0, 1] Parameters: Y0 = 1, b0 = 0, b1 = −1, σ0 = 1, σ1 = 0.5,
           signature truncation L = 6.
                                               .

                              Method MSE |[0,1] R2 |[0,1] MSE |[0,2] R2 |[0,2]
                              Sig    2.29 × 10−4 1.000     2.9387    -0.923
                              VSigk  6.30 × 10−5 1.000     0.0012     0.999
                              VSigkλ 1.38 × 10 −4 1.000    0.0124     0.992

           Table 1. Prediction performance of the three feature maps Sig, VSigk ,
           and VSigkλ , evaluated on the intervals [0, 1] and [0, 2]. We report the mean
           squared error (MSE) and the coefficient of determination R2 .


different outside the training interval, where the truncated signature expansion Sig can
visibly not reproduce the dynamics. This does not contradict the explicit expansions
[56] for classical signature, but indicates that deeper levels are necessary. On the other-
hand, VSigk continues to reproduce Y , which again reflects the expansion proposition 2.38
together with the decay of VSig observed in the proof of lemma 2.37. Finally, the model
VSigkλ also performs reasonably well on the whole interval, and thanks to the flexibility
through the parameter λ, presents a serious competitor to VSigk even though we do not
use the true underlying kernel k.

4.2. S&P 500 realized volatility forecasting. In our second numerical experiment, we
apply Volterra signatures to volatility forecasting for the        √ S&P 500 index. We use daily
S&P 500 log-prices and the median realized volatility ( MedRV) from the Oxford-Man
Institute’s realized volatility database [53], covering the period 2000-01-03 to 2018-06-26.1
Given the two time series of daily log-prices x = {xtn : 0 ≤ n ≤ N } and realized volatilities
v = {vtn : 0 ≤ n ≤ N }, we aim to learn
                                                                       
                 xn := (xt0 , . . . , xtn ) 7−→ fq (xn ) := E vtn+q | xn ,  q ∈ N.         (4.3)

     1The data are publicly available; see, for instance, https://github.com/onnokleen/mfGARCH/raw/v0.
1.9/data-raw.
                                               THE VOLTERRA SIGNATURE                                                                40


0.025                                                 realized volatility
                                                      HAR | RMSE=0.001814 | R²=0.591
0.020                                                 VSig | RMSE=0.001687 | R²=0.647

0.015

0.010

0.005

0.000

 0.01
 0.00
         7         0         1         4         7         0         1         4         7         0         1         4         7
     5-0       5-1       6-0       6-0       6-0       6-1       7-0       7-0       7-0       7-1       8-0       8-0       8-0
 201       201       201       201       201       201       201       201       201       201       201       201       201

          Figure 4.2. Next-day forecast of realized S&P 500 volatility using our
          method VSig, compared with the benchmark HAR, on the test set. The
          lower subplot shows the absolute forecast errors |b
                                                            y − y| for both methods,
          where y denotes the realized volatility.

In words, we forecast the realized volatility q trading days ahead, given the past history
of daily S&P 500 log-prices. In particular, our predictors are functions of the price history
only (daily closes), and do not use past realized volatility values as additional inputs.
   As already motivated in the introduction, it has been observed by both practitioners and
researchers that asset-price volatility is history dependent, and Volterra processes provide
a natural framework for modeling such effects. In the sequel, we focus on the following
class of finite state space kernels
                                                  
                   ⊤ −Λ(t−s) α1               λ1 −c
  Kλ,α,c (t, s) = 1 e               , Λ=                   α1 , α2 ∈ R, λ1 , λ2 , c ≥ 0, (4.4)
                               α2              c λ2
which belongs to the general class of finite state-space kernels considered in Section 2.4 for
R = 2 and q = 1. For c = 0, (4.4) are sum-of-exponentials kernels, which have shown to
be effective in volatility modeling, e.g. for Markovian approximations of rough volatility
models [1, 10], and more recently in path-dependent volatility models [46, 41]. We propose
here a more general class of exponential kernels, with additional flexibility through the
coupling/frequency parameter c.
   We define the targets by y (i) := vti+q and for the input x(i) , we use the piecewise     linear
                                                               P
interpolation of the augmented time series x̂ti := xti ,         j≤i |(δx)tj−1 ,tj |, ti , recalling
that time augmentation guarantees linear universality (see Theorem 3.17). We denote
by VSigλ,α,c the resulting method based on a Ridge regression (see (4.5) below) using
the Volterra signature features VSig(x̂(i) ; kλ,α ) and targets y (i) . Here, the parameters
(λ1 , λ2 , c, α1 , α2 ) are treated as hyperparameters: the decay rates λ1 , λ2 encode different
memory scales, the coupling parameter c allows for interactions between the exponential
factors, and the weights α1 , α2 determine their relative contributions. As before, we also
consider the classical signature method Sig for comparison. As a benchmark, we consider
the simple but powerful HAR model [33], i.e. a linear model for vtn+q based on historical
realized volatility such as vtn , vtn−5 , and vtn−22 . We emphasize again that the signature-
based models use only daily historical prices as inputs (rather than historical realized
volatility, which are computed from intraday price information), and thus rely on a different
                                     THE VOLTERRA SIGNATURE                                         41

information set than HAR. Nevertheless, we use HAR forecasts as a standard benchmark for
predictive performance.
Remark 4.1. The model VSig is related to the path-dependent volatility (PDV) model
introduced in [46], where the authorsp empirically learn volatility path-dependence via the
specification vt = β0 + β1 R1,t + β2 R2,t , where
                 X                           X                          St − Stj−1
         R1,t =     K1 (t, tj )rtj ,  R2,t =    K2 (t, tj )rt2j , rtj = j          .
                                                                           Stj−1
                 tj ≤t                              tj ≤t

The features (R1,t , R2,t ) can be interpreted as discretized first-level Volterra signature fea-
tures associated with the kernel K = diag(K1 , K2 ), and already encode history dependence
through weighted past returns and squared returns. Our method VSig therefore extends
such models by lifting these memory states to higher-order Volterra signatures. This adds
flexibility to capture more complex path-dependent interactions, together with our univer-
sality results providing theoretical justification for the resulting expressiveness.

  In the sequel, we compare the signature-based methods on sliding past windows Wnp :=
{tn−p , . . . , tn } of increasing length p ∈ N. More precisely, we consider the Ridge regression
problem
                           tr   N
   ⋆     ⋆              1 X                                        2
 θ = θ (p, q) = argmin          vti+q − θ, VSig(x̂|Wip ; kα,λ )(L)    + η∥θ∥2ℓ2 ,             η > 0,
                 |θ|≤L Ntr       i=1
                                                                                                  (4.5)
where x̂|Wip denotes the piecewise linear interpolation of x̂ restricted to the past window
Wip , i.e. based on the points {x̂ti−p , . . . , x̂ti }. Moreover, L is the signature truncation level,
which we also treat as a hyperparameter. In our experiments, we consider past-window
sizes p ∈ {10, 20, . . . , 250} (in trading days) and forecasting horizons q ∈ {1, 3, 5}. We use
an 80–20% train–test split (i.e. Ntr = 0.8 × N ). The hyperparameters of VSig, as well as
the ridge regularization parameter η > 0 and truncation level L, are tuned on the last 20%
of the training set. For the Sig method, the best results were obtained using truncation
level L = 4, and for VSig already at level L = 3. The learned kernel parameters (rounded
to two digits) for the VSig method are given by
                  λ1 = 22.69,          λ2 = 0.14,           α1 = 0.18,   α2 = 16.02.

   In general, VSig outperforms the classical signature model Sig and, for sufficiently long
histories (i.e. for p large enough), also the benchmark HAR. Given that VSig introduces
additional flexibility through kernel hyperparameters, this improvement might not be sur-
prising. Nevertheless, the results indicate that even simple kernel classes can substantially
enhance the predictive power of signature features. In particular, the added flexibility
appears to be essential for signature-based approaches to match and eventually surpass
the HAR benchmark, as we further illustrate below. As a first illustration, Figure 4.2 shows
next-day forecasts (q = 1 and p = 240) of VSig versus HAR on the test set. Both the
coefficient of determination R2 and the root mean-squared error (RMSE) improve under
VSig. Moreover, the time-series plot suggests that VSig yields the largest gains during
high-volatility periods, consistent with the error subplot.
   In the left panel of Figure 4.3, we compare VSig with the classical signature method
Sig by reporting a linear interpolation of the R2 score as a function of the past-window
length p. On both the training and the test set, Sig deteriorates as p increases, whereas
VSig consistently benefits from incorporating a longer history. This behavior is consistent
with the fact that, while past information is relevant for forecasting volatility, its predictive
                                         THE VOLTERRA SIGNATURE                                                                             42

                                                                                  0.025         HAR (R²=0.591)
     0.80
                                                            TRAIN                               VSig (R²=0.647)
     0.75                                                                         0.020

     0.70




                                                                   predicted RV
            Sig                                                                   0.015
     0.65   VSig
R²




            HAR
     0.60                                                                         0.010
                                                            TEST
     0.55
                                                                                  0.005
     0.50
                   50   100        150    200         250                                        0.005       0.010        0.015   0.020   0.025
                              p                                                                                      true RV

            Figure 4.3. Left: Coefficient of determination R2 as a (linearly interpo-
            lated) function of the past-window size p (days), reported on the training
            and test sets for the methods VSig and Sig, and the (constant) benchmark
            HAR. Right: Scatter plots of realized volatility y versus predictions yb for our
            method VSig and the HAR benchmark.


value is not uniform across time: distant observations typically carry less weight than more
recent ones. In VSig, the kernel is tuned to encode such time decay and to aggregate past
information in a more efficient, memory-aware manner. Some more precise values, also for
larger prediction horizons, are reported in Table 2.
             20               60                110                                       150                     200               240
 q
 1 0.59/0.60/0.60 0.58/0.62/0.60 0.57/0.63/0.60 0.56/0.64/0.60 0.52/0.65/0.60 0.47/0.65/0.60
 3 0.34/0.33/0.38 0.38/0.38/0.38 0.38/0.39/0.38 0.39/0.40/0.38 0.36/0.40/0.38 0.35/0.42/0.38
 5 0.22/0.21/0.25 0.27/0.24/0.25 0.29/0.25/0.25 0.31/0.25/0.25 0.28/0.26/0.25 0.27/0.28/0.25

            Table 2. R2 overview on the test set: (Sig/VSig/HAR) for forecasting
            horizons q ∈ {1, 3, 5} and several past-window sizes p.


4.3. Multivariate time-series classification. Finally, we present a first application of
the Volterra signature kernel (3.31) to support vector machine (SVM) classification on
UEA time-series datasets [6]. The same benchmark was considered in [79, Section 5.1] for
the classical signature kernel, including variants with a linear and an RBF static kernel (cf.
Remark 3.28). We extend this setup to the Volterra signature kernel (3.31), based on the
same finite state-space kernels from before, that is (4.4). In the accompanying paper [47],
we present an efficient and accurate solver ([47, Algorithm 10]) for the system of PDEs
(3.35)–(3.37), which again is supported in tensordev.
  Table 3 reports the baselines from [79, Table 1], including the linear kernel, the RBF
kernel, the global alignment kernel (GAK), and the signature-PDE kernel. We add two
Volterra signature variants: VSig, using a linear static kernel, and VSig-RBF, using an
additional RBF static kernel. For both variants, the parameters in (4.4) are selected by
hyperparameter optimization on the training data.
   In [79], the authors additionally optimize over several data augmentations, including
time augmentation and lead-lag transformations. In our experiments, we use only time
augmentation for the Volterra signature methods. Overall, the results show that the
Volterra signature variants are competitive with both classical signature kernels and stan-
dard time-series baselines. The plain Volterra signature kernel VSig improves over Sig
                                    THE VOLTERRA SIGNATURE                                           43


  Datasets/Kernels                  Linear RBF GAK             Sig    VSig Sig-RBF VSig-RBF
  ArticularyWordRecognition           98.0    98.0     98.0    92.3 98.7        98.3         99.0
  BasicMotions                        87.5    97.5     97.5    97.5 97.5       100.0         97.5
  Cricket                             91.7    91.7     97.2    86.1 90.3        97.2         97.2
  Libras                              73.9    77.2     79.0    81.7 87.8        81.7         86.7
  NATOPS                              90.0    92.2     90.6    88.3 93.9        93.3         92.2
  RacketSports                        76.9    78.3     84.2    80.2 73.0        84.9         90.8
  FingerMovements                     57.0    60.0     61.0    51.0 54.0        58.0         51.0
  Heartbeat                           70.2    73.2     70.2    72.2 71.7        73.6         74.6
  SelfRegulationSCP1                  86.7    87.3     92.4    75.4 80.5        88.7         89.4
  UWaveGestureLibrary                 80.0    87.5     87.5    83.4 85.6        87.0         86.6

        Table 3. Classification accuracies (%) on UCR/UEA datasets. The best
        test accuracy in each row is highlighted in bold.

on most datasets and achieves the best score among all methods on Libras and NATOPS.
This suggests that the additional flexibility of the Volterra kernel can already be benefi-
cial without an additional nonlinear static kernel. The RBF-enhanced variant VSig-RBF
gives the best performance on ArticularyWordRecognition,Cricket, RacketSports, and
Heartbeat. At the same time, standard baselines remain strongest on datasets such as
FingerMovements, UWaveGestureLibrary and SelfRegulationSCP1.

                                             References
 [1] Eduardo Abi Jaber and Omar El Euch. Multifactor approximation of rough volatility models. SIAM
     journal on financial mathematics, 10(2):309–349, 2019. 17, 40
 [2] Eduardo Abi Jaber and Louis-Amand Gérard. Hedging with memory: shallow and deep learning with
     signatures. 2025. 28
 [3] Eduardo Abi Jaber and Shaun Li. Volatility models in practice: Rough, path-dependent, or Markov-
     ian? Mathematical Finance, 2025. 17
 [4] Munawar Ali and Qi Feng. Branched Signature Model. Preprint, arXiv:2511.00018 [math.NA] (2025),
     2025. 4
 [5] Nachman Aronszajn. Theory of reproducing kernels. Transactions of the American Mathematical So-
     ciety, 68(3):337–404, 1950. 31
 [6] Anthony Bagnall, Hoang Anh Dau, Jason Lines, Michael Flynn, James Large, Aaron Bostrom, Paul
     Southam, and Eamonn Keogh. The uea multivariate time series classification archive, 2018. arXiv
     preprint arXiv:1811.00075, 2018. 3, 37, 42
 [7] Hajer Bahouri, Jean-Yves Chemin, and Danchin Raphaël. Fourier Analysis and Nonlinear Partial
     Differential Equations, volume 343 of Grundlehren der mathematischen Wissenschaften, A Series of
     Comprehensive Studies in Mathematics. Berlin, Heidelberg : Springer-Verlag Berlin Heidelberg, 2011.
     28
 [8] Peter Bank, Christian Bayer, Paul P. Hager, Sebastian Riedel, and Tobias Nauen. Stochastic control
     with signatures. SIAM Journal on Control and Optimization, 63(5):3189–3218, 2025. 28, 30
 [9] Ole E. Barndorff-Nielsen, Fred Espen Benth, and Almut E. D. Veraart. Ambit Stochastics, volume 88
     of Probability Theory and Stochastic Modelling. Springer, Cham, 2018. 8
[10] Christian Bayer and Simon Breneis. Markovian approximations of stochastic Volterra equations with
     the fractional kernel. Quantitative Finance, 23(1):53–70, 2023. 17, 40
[11] Christian Bayer, Gonçalo dos Reis, Blanka Horvath, and Harald Oberhauser, editors. Signature Meth-
     ods in Finance: An Introduction with Computational Applications. Springer Finance. Springer, Cham,
     2025. eBook published 07 Nov 2025; © 2026 Springer Nature. 2
[12] Christian Bayer, Peter K. Friz, Paul Gassiat, Jorg Martin, and Benjamin Stemper. A regularity
     structure for rough volatility. Math. Finance, 30(3):782–832, 2020. 4
[13] Christian Bayer, Paul P Hager, Sebastian Riedel, and John Schoenmakers. Optimal stopping with
     signatures. The Annals of Applied Probability, 33(1):238–273, 2023. 28
                                     THE VOLTERRA SIGNATURE                                            44

[14] Christian Bayer, Luca Pelizzari, and Jia-Jie Zhu. Pricing american options under rough volatility
     using signatures. In Conference on Modern Topics in Stochastic Analysis and Applications (in honour
     of Terry Lyons’ 70th birthday), pages 375–398. Springer, 2024. 28
[15] Yoshua Bengio, Patrice Simard, and Paolo Frasconi. Learning long-term dependencies with gradient
     descent is difficult. IEEE Transactions on Neural Networks, 5(2):157–166, 1994. 1
[16] Fred Espen Benth and Paul Krühner. Stochastic Models for Prices Dynamics in Energy and Com-
     modity Markets. Springer Finance. Springer, Cham, November 2023. 8
[17] Martin Bergerhausen, David J. Prömel, and David Scheffels. Neural stochastic Volterra equations:
     Learning path-dependent dynamics. Journal of Machine Learning, 4(4):264–289, December 2025. 2
[18] Donald J. Berndt and James Clifford. Using dynamic time warping to find patterns in time series. In
     KDD Workshop, volume 10, pages 359–370, 1994. 31
[19] Horatio Boedihardjo, Xi Geng, Terry Lyons, and Danyu Yang. The signature of a rough path: unique-
     ness. Advances in Mathematics, 293:720–737, 2016. 24
[20] S. Boyd and L. Chua. Fading memory and the problem of approximating nonlinear operators with
     Volterra series. IEEE Transactions on Circuits and Systems, 32(11):1150–1161, 1985. 1
[21] Fred Brauer, Carlos Castillo-Chavez, and Zhilan Feng. Mathematical models in epidemiology, vol-
     ume 69 of Texts in Applied Mathematics. Springer, New York, 2019. With a foreword by Simon Levin.
     1
[22] Yvain Bruned and Foivos Katsetsiadis. Ramification of Volterra-type rough paths. Electronic Journal
     of Probability, 28:1–25, 2023. 3, 4
[23] S. Burov and E. Barkai. Fractional Langevin equation: overdamped, underdamped, and critical be-
     haviors. Phys. Rev. E (3), 78(3):031112, 18, 2008. 1
[24] René Carmona and Michael Coulon. A survey of commodity markets and structural models for elec-
     tricity prices. In Quantitative energy finance, pages 41–83. Springer, New York, 2014. 1
[25] Antoni B. Chan and Nuno Vasconcelos. Probabilistic kernels for the classification of auto-regressive
     visual processes. In 2005 IEEE Computer Society Conference on Computer Vision and Pattern Recog-
     nition (CVPR’05), volume 1, pages 846–851. IEEE, 2005. 31
[26] Kuo-Tsai Chen. Iterated integrals and exponential homomorphisms. Proc. Lond. Math. Soc. (3), 4:502–
     512, 1954. 8
[27] Kuo-Tsai Chen. Integration of paths, geometric invariants and a Generalized Baker–Hausdorff formula.
     Annals of Mathematics, 65(1):163–178, 1957. 2
[28] Ricky T. Q. Chen, Yulia Rubanova, Jesse Bettencourt, and David Duvenaud. Neural ordinary differen-
     tial equations. In Proceedings of the 32nd International Conference on Neural Information Processing
     Systems, NIPS’18, page 6572–6583, Red Hook, NY, USA, 2018. Curran Associates Inc. 2
[29] Ilya Chevyrev, Andris Gerasimovičs, and Hendrik Weber. Feature engineering with regularity struc-
     tures. J. Sci. Comput., 98(1):28, 2024. Id/No 13. 4
[30] Ilya Chevyrev and Andrey Kormilitzin. A primer on the signature method in machine learning. arXiv
     preprint arXiv:1603.03788, 2016. 25, 37
[31] F. Comte and E. Renault. Long memory continuous time models. Journal of Econometrics, 73(1):101–
     149, 1996. 1
[32] C. Corduneanu. Integral equations and applications. Cambridge: Cambridge University Press, reprint
     of the 1991 hardback ed. edition, 2008. 2
[33] Fulvio Corsi. A simple approximate long-memory model of realized volatility. Journal of financial
     econometrics, 7(2):174–196, 2009. 40
[34] Dan Crisan, Ilya Chevyrev, Thomas Cass, James Foster, Christian Litterer, and Cristopher Salvi,
     editors. Stochastic Analysis and Applications 2025: In Honour of Terry Lyons. Springer Nature
     Switzerland, Cham, January 2026. Hardcover. ISBN-10: 3032039134. xii+436 pp. eBook ISBN:
     9783032039149. 2
[35] Marco Cuturi and Arnaud Doucet. Autoregressive kernels for time series. arXiv preprint
     arXiv:1101.0673, 2011. 31
[36] Tri Dao and Albert Gu. Transformers are SSMs: Generalized models and efficient algorithms through
     structured state space duality. In Proceedings of the 41st International Conference on Machine Learn-
     ing, pages 10041–10071. PMLR, 2024. 1, 20
[37] Joscha Diehl, Kurusch Ebrahimi-Fard, and Nikolas Tapia. Generalized iterated-sums signatures. J.
     Algebra, 632:801–824, 2023. 4
[38] Jeffrey L. Elman. Finding structure in time. Cognitive Science, 14(2):179–211, 1990. 1
                                     THE VOLTERRA SIGNATURE                                           45

[39] Peter K. Friz and Nicolas B. Victoir. Multidimensional stochastic processes as rough paths, volume
     120 of Cambridge Studies in Advanced Mathematics. Cambridge University Press, Cambridge, 2010.
     Theory and applications. 21
[40] Jim Gatheral, Thibault Jaisson, and Mathieu Rosenbaum. Volatility is rough. Quantitative Finance,
     18(6):933–949, 2018. 1
[41] Guido Gazzani and Julien Guyon. Pricing and calibration in the 4-factor path-dependent volatility
     model. Quantitative Finance, 25(3):471–489, 2025. 40
[42] Wulfram Gerstner and Werner M. Kistler. Spiking Neuron Models: Single Neurons, Populations,
     Plasticity. Cambridge University Press, Cambridge, 2002. 1
[43] Gustaf Gripenberg, Stig-Olof Londen, and Olof Staffans. Volterra integral and functional equations.
     Number 34. Cambridge University Press, 1990. 2, 17
[44] Albert Gu and Tri Dao. Mamba: Linear-time sequence modeling with selective state spaces. arXiv
     pre