source: https://arxiv.org/pdf/2006.00873
fetched_utc: 2026-10-04T18:39:12Z
bytes_raw: 513545

A Generalised Signature Method for Multivariate Time Series Feature
                                                                          Extraction


                                                            James Morrill 1 2 * Adeline Fermanian 3 * Patrick Kidger 1 2 * Terry Lyons 1 2


                                                                 Abstract                                 dimensional, as both the number of channels d and the
                                                                                                          length of the series n may be large, the values xi are
                                             The ‘signature method’ refers to a collection
arXiv:2006.00873v2 [cs.LG] 6 Feb 2021




                                                                                                          correlated, and the different channels may interact. Finally,
                                             of feature extraction techniques for multivariate
                                                                                                          the inputs may be of different length and the data may be
                                             time series, derived from the theory of controlled
                                                                                                          irregularly sampled.
                                             differential equations. There is a great deal
                                             of flexibility as to how this method can be                  One approach is to construct models that directly accept
                                             applied.     On the one hand, this flexibility               some of these issues; for example recurrent neural
                                             allows the method to be tailored to specific                 networks handle correlated inputs with varying lengths.
                                             problems, but on the other hand, can make                    A second option is to use feature extraction techniques,
                                             precise application challenging. This paper                  which normalise the data so that other techniques may
                                             makes two contributions. First, the variations on            then be applied. Methods such as the shapelet transform
                                             the signature method are unified into a general              (Ye & Keogh, 2009; Grabocka et al., 2014; Kidger et al.,
                                             approach, the generalised signature method, of               2020), Gaussian process adapters (Li & Marlin, 2016;
                                             which previous variations are special cases. A               Futoma et al., 2017; Moor et al., 2020), and in particular
                                             primary aim of this unifying framework is to                 the signature method (Levin et al., 2013), all fit into this
                                             make the signature method more accessible to                 category.
                                             any machine learning practitioner, whereas it is
                                                                                                          The approach taken by the signature method, coming from
                                             now mostly used by specialists. Second, and
                                                                                                          rough path theory (Lyons et al., 2007; Friz & Victoir,
                                             within this framework, we derive a canonical
                                                                                                          2010), is to interpret a multivariate time series as a
                                             collection of choices that provide a domain-
                                                                                                          discretisation of an underlying continuous path. The
                                             agnostic starting point. We derive these choices
                                                                                                          signature transform, also known as the path signature or
                                             as a result of an extensive empirical study on
                                                                                                          signature, can then be applied, which produces a vector of
                                             26 datasets and go on to show competitive
                                                                                                          real-valued features that are known to characterise the path.
                                             performance against current benchmarks for
                                             multivariate time series classification. Finally,            Benefits of the signature method include: a high degree
                                             to ease practical application, we make our                   of flexibility, making it possible to customise the method
                                             techniques available as part of the open-source              to specific datasets; strong theoretical guarantees; an
                                             [redacted] project.                                          interpretable feature set; ease of handling irregularly
                                                                                                          sampled and/or partially observed data; and it being well-
                                                                                                          defined for some highly irregular processes such as ARMA,
                                        1. Introduction                                                   Gaussian processes or even Brownian motion. Also,
                                                                                                          signature features do not need to learned, which can make
                                        A multivariate time series is obtained by observing d             them particularly effective on (but not limited to) low
                                        quantities evolving with time, which can be written as an         sample datasets.
                                        array x = (x1 , . . . , xn ), where n is the length of the
                                        series, and xi ∈ Rd for each i ∈ {1, . . . , n}. These data       The flexibility of the signature method has made it possible
                                        are common in various fields (finance, health, energy...)         to be tailored to specific applications and achieve state-
                                        and offer several specific challenges: they are often highly      of-the-art performance in wide range of problem domains,
                                                                                                          such as handwriting recognition (Wilson-Nunn et al., 2018;
                                           *
                                             Equal contribution 1 Mathematical Institute, University of   Yang et al., 2016b), action recognition (Yang et al., 2016a;
                                        Oxford, UK 2 The Alan Turing Institute, British Library, UK       2017), and medical time series prediction tasks (Morrill
                                        3
                                          Sorbonne Université.    Correspondence to: James Morrill
                                        <morrill@maths.ox.ac.uk>.
                                                                                                          et al., 2019; 2020b). However, this flexibility comes at the
                                                                                                          cost of additional complexity in the model search space.
                                        A preprint.
                        A Generalised Signature Method for Multivariate Time Series Feature Extraction

                                           Signature                                 Log-signature
                          X2                                             X2



                                                        S (1,2)
                                                                                                     A+
                                                                  ∆X 2             A−                          ∆X 2
                                         (2,1)
                                     S

                                                 ∆X 1                                     ∆X 1
                                                                   X1                                            X1

Figure 1. Geometric depiction of the depth-2 signature and log-signature. The depth-1 term of both transforms equate to the
displacements of the path over the interval in each coordinate, these being ∆X 1,2 . Left: The signature. Depth-2 terms S (1,2) , S (2,1)
correspond to the areas of the blue and orange regions respectively. Right: The log-signature. Only one depth-2 term which is given by
the signed area A+ − A− . This is known as the Lévy area of the path.


To the best of our knowledge, no comprehensive studies                    Definition 1. Let d ∈ N, we denote the space of time series
exist that collate and combine the most common method                     over Rd as
variations found in the literature and assemble them under
a common mathematical framework. Additionally, no                              S(Rd ) = {(x1 , . . . , xn ) | xi ∈ Rd , n ∈ N, n ≥ 1}.
baseline signature model has ever been tested against other
time series classification baselines. Our goal will be to                 If d = 1, then x is a univariate time series, whereas
address both of these issues, alongside the development of                if d > 1, x is a multivariate time series. Given x =
an open source implementation, so as to make the methods                  (x1 , . . . , xn ) ∈ S(Rd ), n is called the length of x and d
more accessible to a wider audience.                                      its dimension or number of channels. We assume that in
                                                                          addition to the array of values x ∈ S(Rd ), we have access
Contributions We introduce a generalised signature                        to a vector of increasing time stamps t = (t1 , . . . , tn ).
method that contains the many existing variations as special              If the data is regularly sampled, then t can be set to t =
cases. In doing so we are able to understand their                        (1, . . . , n), which will often be the case.
conceptual groupings into what we term augmentations,
                                                                          We consider a dataset to be a collection of such samples.
windows, transforms and rescalings. This involves a
                                                                          Note that the time stamps t for each sample may be
comprehensive review of the existing variations across the
                                                                          different, and the sample lengths n can vary. That is,
literature. By understanding their commonality, we are
                                                                          we accept varying length and irregular sampling without
then able to combine different variations, and propose new
                                                                          modification. We are now in a position to define the
options that fit into this framework.
                                                                          signature of a time series.
We go on to examine which choices within this framework                   Definition 2. Let x ∈ S(Rd ) and t = (t1 , . . . , tn ) its
are most important to success by performing an extensive                  associated timestamps. Let X = (Xt1 , . . . , Xtd )t∈[t1 ,tn ]
empirical study across 26 datasets. To the best of our                    be a piecewise linear interpolation of x such that for any
knowledge this is the first study of this type.                           i ∈ {1, . . . , n}, Xti = xi . Then the depth-N signature
In doing so, we are then able to produce a canonical                      transform of x is the vector defined by
signature pipeline. This represents a domain agnostic
starting point that may then be adapted for the task at                       SigN (x) = {S(x)(i) }di=1 ,
hand. We show that the performance of this canonical                                         {S(x)(i,j) }di,j=1 ,
pipeline is comparable to current state-of-the-art classifiers                               ...,
for multivariate time series classification, including deep
                                                                                                                                   dN +1 −1
                                                                                             {S(x)(i1 ,...,iN ) }di1 ,...,iN =1 ∈ R d−1
                                                                                                                               
recurrent and convolutional neural networks. This has led
to the implementation of this generalised approach in the
open source [redacted] package.                                           where for any (i1 , . . . , ik ) ∈ {1, . . . , d}k ,
                                                                                                     Z       Z
2. Context                                                                  S(x)(i1 ,...,ik ) =          ···         dXui11 . . . dXuikk ∈ R.
                                                                                                 t1 ≤u1 <···<uk ≤tn
2.1. Background theory
We begin with a few mathematical definitions necessary                    While this definition may seem somewhat technical, there
throughout the article.                                                   are several intuitions that can be made with regard to the
                        A Generalised Signature Method for Multivariate Time Series Feature Extraction

signature features. We present a geometric interpretation            is (dN +1 −1)/(d−1) so the memory cost is independent of
of the first two levels of the signature and log-signature           the series length n, which is a huge advantage when dealing
in Figure 1. The depth-1 terms, S(x)(i) , equate to                  with high frequency time series. Note that small values of
the displacement of the path over the interval in the ith            N already show a good performance—for example N = 3
coordinate, denoted by ∆X i in Figure 1. The depth-2                 in the baseline algorithm—so the exponential dependence
terms, S(x)(i,j) , have interpretations in areas generated           on N is not a huge computational bottleneck.
over the interval.
                                                                     Logsignature transform The signature contains some
From a statistical point of view, the signature can be
                                                                     redundant information: for example we can see in the left
thought of as the equivalent of a moment-generating
                                                                     panel of Figure 1 that the sum of the blue and orange areas
function for time series. Let Z be a random variable, then
                                                                     is equal to the product of displacements ∆X 1 ∆X 2 :
the moment-generating function of Z is the function
                                  ∞ k                                         S(x)(1,2) + S(x)(2,1) = S(x)(1) S(x)(2) .
                                  X t
                 t 7→ E[etz ] =              E[Z k ]
                                        k!                           The logsignature transform is essentially the signature with
                                  k=0
                                                                     these redundancies removed. For example, the logsignature
and, if well-defined, it characterizes the distribution of           encodes the blue and orange areas from the left panel
Z. Assume that X is a random time series (that is                    with the orange signed area in the right panel. However,
a stochastic process), its signature now has the same                the logsignature does not have a universal nonlinearity
properties as a moment-generating function: the powers of            property such as equation 1. We refer the reader to Morrill
Z are replaced by integrals of products of coordinates and           et al. (2020a) or Liao et al. (2019, Section 2) for a precise
Chevyrev & Lyons (2016) show that the expected signature             definition of the logsignature.
characterizes the law of X.
                                                                     A pedagogical introduction to the background theory of
Moreover, we have the following two properties that make             signatures is Lyons et al. (2007), whilst a comprehensive
the signature a good feature set in a machine-learning               textbook is Friz & Victoir (2010). For introductions to
context—precise statements may be found in Bonnier et al.            the signature method, we recommend Bonnier et al. (2019,
(2019, Appendix A).                                                  Appendix A) and Chevyrev & Kormilitzin (2016).

Uniqueness Hambly & Lyons (2010) show that under                     2.2. Related work
mild assumptions, the full collection of features Sig(x) =
limN →∞ SigN (x) uniquely determines x up to translations            The signature transform has been used in a wide range
and reparametrizations.                                              of applications in machine learning predictive tasks. For
                                                                     example, as mentioned in the introduction, the signature
Universal nonlinearity Linear functionals on the                     has been used as a feature extraction layer in classifiers for
signature are dense in the set of functions on x. Suppose            both Arabic (Wilson-Nunn et al., 2018) and Chinese (Yang
we wish to learn the function f that maps data x to labels           et al., 2016b) handwriting recognition. Similarly, it was
y, the universal nonlinearity property states that, under            successfully used in human action recognition by Li et al.
some assumptions, for any ε > 0, there exists a linear               (2017); Yang et al. (2017); Liao et al. (2019) and in the
function L such that                                                 medical domain as part of the top performing model at the
                                                                    Physionet 2019 challenge for prediction of sepsis (Reyna
                kf (x) − L Sig(x) k ≤ ε.               (1)           et al., 2019; Morrill et al., 2019; 2020b). Other applications
                                                                     involve finance (Lyons et al., 2014; Perez Arribas, 2018),
Note that contrary to Fourier or wavelet basis, signatures           mental health (Kormilitzin et al., 2017; Arribas et al.,
provide a natural basis for functions of the time series             2018), and emotion recognition (Wang et al., 2019; 2020).
rather than for the time series itself—equation 1 concerns
                                                                     In almost all these applications, the method has been
f (x) and not x. In the context of time series classification
                                                                     utilised in different ways.         Many authors consider
this shift of perspective is particularly well-suited since the
                                                                     transformations of the input time series before application
object of interest is not the time series itself but its link to a
                                                                     of the signature (Levin et al., 2013; Flint et al., 2016; Lyons
label.
                                                                     & Oberhauser, 2017; Yang et al., 2017; Liao et al., 2019;
From a computational point of view, computing the depth-             Kidger & Lyons, 2020; Wu et al., 2020a). People have
N signature of a time series x ∈ S(Rd ) of length n                  also explored different windows over which the signature
has a complexity of O(ndN ), which can be done with                  transform should be taken, so as to extract information over
high performance software (Reizenstein & Graham, 2018;               different scales (Yang et al., 2017; Bonnier et al., 2019).
Kidger & Lyons, 2020). The size of the depth-N signature             Additionally a choice must be made between the signature
                      A Generalised Signature Method for Multivariate Time Series Feature Extraction

and logsignature transforms, as must choices for the scaling    For some e, p ∈ N, we define an augmentation as a map
of the terms in the signature (Chevyrev & Kormilitzin,
2016; Lai et al., 2017).                                                            φ : S(Rd ) → S(Re )p .

The differences between some of these choice have been          There are many pre-signature operations which have been
shown by Fermanian (2019) to significantly impact the           proposed in the literature, and which we categorise as
performance of the methodology. However this study used         augmentations. We refer the reader to Appendix A for
a small collection of datasets and considered only some         full details of the many such operations proposed in the
of the most common variations that exist in the literature.     literature, but will focus on several important examples
There is therefore a need for a comprehensive study and         here.
unification of all these different choices.
                                                                Let us give some examples in the first group of sensitivity-
                                                                inducing augmentations. For any vector of increasing
3. The generalized signature method                             timestamps t, we call time augmentation (Levin et al.,
                                                                2013) the operation φt : S(Rd ) 7→ S(Rd+1 ) defined by
In this section we collate the modifications to the signature
transform that have been proposed in signature literature to
                                                                                                                    
                                                                             φt (x) = (t1 , x1 ), . . . , (tn , xn ) .   (2)
date. We will show that each can be categorised into one of
the following groups:                                           This transformation, which basically consists in adding
                                                                the timestamps as an extra coordinate, has two key
  • Augmentations These describe the transformation             properties: it guarantees the uniqueness of the signature
    of a time series into one or more new series, in order      (Hambly & Lyons, 2010) and it adds information about the
    to return different information in the signature features   parametrization of the time series.
    and deal with dimensionality issues.
                                                                Another example is the basepoint augmentation (Kidger &
  • Windows Splitting the time series over different            Lyons, 2020), which is the map φb : S(Rd ) 7→ S(Rd )
    subsequences (or windows), so that signatures may be        defined by
    applied locally.                                                           φb (x) = (0, x1 , . . . , xn ),       (3)
  • Transform The choice between the signature or the           which simply adds a zero at the beginning of the time
    logsignature transform.                                     series—note that this zero could also be put at the end. This
                                                                transformation makes the signature sensitive to translations
  • Rescaling      Ways of normalising the terms in the
                                                                of the time series. The invisibility-reset transformation
    signature.
                                                                (Yang et al., 2017; Wu et al., 2020b) also adds translation
                                                                sensitivity, but does so by increasing the dimension.
We then go on to show that these groupings can themselves
be synergised into a single mathematical framework that         In the second group of augmentations for dimensionality
we term the generalised signature method. For clarity, we       reduction, we consider random projections (Lyons &
will begin by discussing each of these individually, and        Oberhauser, 2017), which consist in applying multiple
then afterwards show how they may be combined.                  random linear maps to the time series, or coordinate
                                                                projections, which project along (multiple subsets of) the
As before, assume that we observe some collection of
                                                                coordinate axes.
sequences x ∈ S(Rd ) with timestamps t ∈ S(R).
                                                                In the third group, the lead-lag augmentation (Chevyrev
3.1. Augmentations                                              & Kormilitzin, 2016; Flint et al., 2016; Yang et al., 2017)
                                                                captures the quadratic variation by transforming the time
We define an augmentation to be a transform of an initial       series to
sequence x ∈ S(Rd ) into one or several new sequences.
Augmentations have several different uses:                       φ(x) = (x1 , x1 ), (x2 , x1 ), (x2 , x2 ), (x3 , x2 ), (x3 , x3 ),
                                                                        . . . , (xn , xn ) ∈ S(R2d ).
                                                                                          
 1. Remove the signature invariance to translation and/or
    reparametrization.                                          Another important example of this kind of augmentation
 2. Lower the dimension d of the time series, so that           are the stream preserving neural networks of Bonnier et al.
    higher orders of the signature are reachable—recall         (2019), who learn a map φ from the data. They map
    that the depth-N signature is of size O(dN ).               a time series in Rd to another series in Re by setting φ
                                                                to some neural network, typically either convolutional or
 3. Preprocess the time series prior to the signature map       recurrent. We extend this idea by defining the multi-headed
    so that information is more easily extracted.               stream preserving augmentation, which simply consists in
                        A Generalised Signature Method for Multivariate Time Series Feature Extraction

stacking p such transformations. To our knowledge, this is          3.3. The signature and logsignature transforms
the first time that such learned augmentations are compared
                                                                    Central to the signature methodology is of course the
to ‘handcrafted’ ones such as time, basepoint and lead-lag
                                                                    signature transform itself. Two choices must be made;
augmentations.
                                                                    whether to use the signature or logsignature transform, and
Importantly, these various augmentations may be combined            what depth to calculate the transform to—that is, what
together. For example, in order to add sensitivity to both          depth N in Definition 2 to use. Choosing a logsignature
parametrization and translation, the time and basepoint             lowers the feature vector dimension at the cost of loosing
augmentations may be combined: first apply the time                 linear approximation properties. There is no consensus on
augmentation, which gives a sequence φt (x) ∈ S(Rd+1 ),             which one should be favored for a machine learning task.
and then the basepoint augmentation, which yields
                                                                    3.4. Rescaling
       φb ◦ φt (x) = (0, 0), (t1 , x1 ), . . . , (tn , xn ) .
                                                           
                                                              (4)
                                                                    The depth-k term in the signature is of size O(1/k!).
3.2. Windows                                                        Typically, rescaling these terms to O(1) will aid in
                                                                    subsequent learning procedures. To this end, we can apply
The second step is to choose a windowing operation.
                                                                    pre-signature scaling whereby we scale the path before
Much like the window functions used with a short time
                                                                    signature computation, or post-signature where we scale
Fourier transform, this localises the signature computation
                                                                    the signature terms themselves. Specifics on how this is
to extract information over particular time intervals.
                                                                    done in practice are given in Appendix B.
We define a window to be a map
                                                                    3.5. Putting the pieces together
                   W : S(Re ) → S(Re )w ,
                                                                    Let φ : S(Rd ) → S(Re )p be the final       augmentation
for some w ∈ N. In short, W maps a time series in Re into
                                                                    function, φ : x 7→ φ1 (x), . . . , φp (x) , which can be
w new time series in the same space. The simplest possible
                                                                    a composition of augmentations such as equation 4. Let
window is the global window, defined by                                                                                         
                                                                    W : S(Re ) → S(Re )w , W : x 7→ W 1 (x), . . . , W w (x) ,
                         W (x) = (x),                        (5)    be the window map, such that W j (x) ∈ S(Re ) for any
                                                                    1 ≤ j ≤ w. Let S N represent either the signature or
which outputs the time series itself. To get finer-scale            logsignature transform of depth N . Let ρpre and ρpost
information, we consider three other types of windows:              represent the different types of features rescaling. Then
sliding, expanding and hierarchical dyadic windows. For             given an input x ∈ S(Rd ), the general framework for
x = (x1 , . . . , xn ) ∈ S(Re ) and 1 ≤ i ≤ j ≤ n, let              extracting signature features is given by the collection of
xi:j = (xi , . . . , xj ) ∈ S(Re ) be a subsequence of x. Then,
a sliding window of length ` and step l is defined by
                                                                             zi,j = (ρpost ◦ S N ◦ ρpre ◦ W j ◦ φi )(x)         (6)
         W (x) = (x1:` , xl+1:l+` , x2l+1:2l+` , . . .),
and an expanding window of initial length ` and step l by           over all i ∈ {1, . . . , p}, j ∈ {1, . . . , w}. We refer to the
                                                                    procedure of computing x 7→ (zi,j ) as the generalised
            W (x) = (x1:` , x1:l+` , x1:2l+` , . . .).              signature method.
The expanding window produces time series of increasing             This final procedure is a little involved, but is simply a
length, and is analogous to the history processes of                combination of different elementary operations used to
stochastic analysis whereas the sliding window produces             impact the final feature set. The overall procedure now
time series of fixed length but shifted in time.                    offers a degree of flexibility and generality which has, to
                                                                    our knowledge, never been achieved for signature methods.
Finally we consider a hierarchical dyadic window, which
captures information at different scales. Let q ∈ N be fixed        The collection of features (zi,j ) may then be fed into any
and assume for simplicity that 2q−1 divides n. Then, the            later machine learning algorithm, which will depend on the
hierarchical dyadic window of depth q consists of q sliding         application. In general, the zi,j will be stacked together
windows W 1 , . . . , W q , where W i has length and step both      and considered as a vector. However, if one wants to
equal to n2−(i−1) . This yields w = 2q − 1 time series of           use a sequential algorithm such as a recurrent network,
length n, n/2, n/4, . . . , n/2q−1 . The larger the value of        it is possible to turn the features zi,j into a sequence by
q, the finer the scale on which the information is extracted.       choosing a sliding or expanding window. Indeed, these
If the other window functions are analogous to the short            windows induce an ordering in the features: the terms zi,1
time Fourier transform, then hierarchical dyadic windows            will correspond to the first values of x, the terms zi,2 to the
are analogous to the multi-scale nature of wavelets.                following values, and so on.
                      A Generalised Signature Method for Multivariate Time Series Feature Extraction

4. Empirical study                                              considered, to reflect the fact that different models are
                                                                better suited for different problems. We then follow the
We perform a first-of-its-kind empirical study across 26        methodology of Demšar (2006); Benavoli et al. (2016);
datasets to determine the most important aspects of this        Ruiz et al. (2020) to compare the variations across the
framework.                                                      multiple datasets. We first perform a Friedman test to
                                                                reject the null hypothesis that all methods are equivalent.
4.1. Methodology                                                If it is rejected, we perform pairwise Wilcoxon signed-
Datasets The datasets used are the Human Activities             rank tests to form cliques of not-significant methods, and
and Postural Transitions dataset provided by Reyes-Ortiz        use critical difference plots to visualize the performance of
et al. (2016), the Speech Commands dataset provided by          each signature method.
Warden (2018), and 24 datasets from the UEA time series         A critical difference plot shows the different variations
classification archive, provided by Bagnall et al. (2018).      ordered by their average rank: for example, in Figure
A few datasets from the UEA archive were excluded due           2, the best variation is “Time + Basepoint” with an
to their high number of channels resulting in too large a       average rank of 2.5. Then, a thick line indicates that
computational burden.                                           the Wilcoxon test between variations inside the clique
                                                                is not rejected at significance threshold of 5%, subject
Baseline We begin by defining a single baseline                 to Bonferroni’s multiple testing correction. In Figure 2
procedure, representing a simple and straightforward            there are two groups of significantly different variations:
collection of choices for the generalised signature method.     one with “Basepoint” and “None” and one with all other
This baseline is to take the augmentation φ as appending        variations.
time as defined by equation 2, W as the global window
defined by equation 5, have the transform be a signature        We refer the reader to Appendix C for further details on
transform of depth 3, and to use pre-signature scaling of the   the methodology, such as precise architectural choices,
path. This means that the input features are the collection     learning rates, and so on.

                 z = Sig3 ◦ ρpre ◦ φt (x).                      4.2. Results
                                                                Due to the large number of variations and datasets
Individual variations With respect to this baseline             considered, we present only the critical difference plots in
procedure, we then consider, in turn, the groups described      the main paper. See Appendix D for all the tables of the
in Section 3. These were augmentations, windows,                underlying numerical values.
transform, and rescaling. For each group we modify the
baseline by implementing each option in the group one-by-
one. Each such variation defines a particular form of the
generalised signature method as in equation 6. Example
variations are to switch to using a logsignature transform
of depth 5, or to use a sliding window instead of a global
window. We discuss the precise variations below.                Figure 2. Performance of invariance-removing augmentations.

Models On top of every variation, we then consider
                                                                Augmentations We split the augmentations into two
four different models: logistic regression, random forest,
                                                                categories.       The first category consists of those
Gated Recurrent Unit (GRU) (Cho et al., 2014), and a
                                                                augmentations which remove the signature’s invariance
residual Convolutional Neural Network (CNN) (He et al.,
                                                                to translation (basepoint augmentation, invisibility-reset
2015). We test nearly every combination of dataset,
                                                                augmentation) or reparameterisation (time augmentation).
variation of the generalised signature method, and model.
                                                                We see in Figure 2 that augmenting with time, and either
Different datasets and variations produce different numbers
                                                                basepoint or invisibility-reset, are both typically important.
of features zi,j , so to reduce the computational burden
                                                                This is expected; in general a problem need not be invariant
we omit those cases for which the number of features
                                                                to either translation or reparametersiation.
is greater than 105 . Of the 9984 total combinations
of dataset, variation, and model, this leaves out 1415
combinations. See Appendix C.2 for a break down of the
omitted combinations by different cases.

Analysis We define the performance of a variation on
a dataset as the best performance across the four models                Figure 3. Performance of other augmentations.
                        A Generalised Signature Method for Multivariate Time Series Feature Extraction

The second category consists of those augmentations which          basepoint augmentations should a priori be used, that
either seek to reduce dimensionality or introduce additional       the lead-lag performs well but not significantly better
information. We see in Figure 3 that most augmentations            than no additional augmentation, and that the hierarchical
actually do not help matters, except for lead-lag which            dyadic window performs significantly better than the
usually represents a good choice. We posit that the best           sliding and global ones. The poor performance of deep
augmentation is likely to be dataset dependent, so we break        learning approaches for augmentation is also notable and
this down by dataset characteristics in Table 6.                   an additional motivation for this work: although slightly
                                                                   technical, the augmentations tailored to the signature
Table 1. Average ranks for different augmentations by data type.
                                                                   transform are a significant addition in a machine learning
Lower is better. CP (2) stands for coordinate projections with     pipeline and cannot be easily replaced by neural networks.
pairs and LP for Learnt projections.
                               Augmentation                        4.3. Further results
    Data type    None    Lead-lag   CP (2)    LP     MHSP          See Appendix D for further results, in particular on
    EEG          4.88      4.83      3.13     2.75      2.75       the running times, the different types of rescaling,
    HAR          2.25      1.78      3.50     6.50      6.50       augmentations broken down by dataset characteristics,
    MOTION       2.63      1.75      4.50     7.33      5.00       an additional study on signature depth, and the precise
    OTHER        2.88      3.92      2.63     6.00      5.21       numerical results for each individual test considered here.

Here we indeed see that there is generally a better
choice than doing nothing at all, but that this better
                                                                   5. The canonical signature pipeline
choice is dependent on some characteristic of the dataset.         In this section we define the canonical signature pipeline.
For example, learnt projections and multi-headed stream            Using the results from Section 4 we evaluate the top
preserving transformations do substantially better on EEG          performing options over all the datasets so as to provide a
datasets, while lead-lag is better for human action and            domain-agnostic starting point for any dataset, from which
motion recognition.                                                other variations can be easily explored. We show that this
                                                                   pipeline shows competitive performance against traditional
                                                                   benchmarks and even against deep neural networks.

                                                                   5.1. Definition
                                                                   In a nutshell, the pipeline consists in applying the basepoint
          Figure 4. Performance of different windows.              and time augmentations, a hierarchical dyadic window
                                                                   and a signature transform, which can be written as a
Windows We consider the possibility of global, sliding,            particular case of equation 6 as follows. Let W be a
expanding, and dyadic windows. The results are shown               hierarchical dyadic window of depth q, φt and φb be
in Figure 4. We see that the dyadic and expanding                  the time and basepoint augmentations, then the canonical
windows are significantly better than sliding and global           signature pipeline may be written as
windows. The poor performance of sliding windows is
a little surprising, but tallies with the observations of           zj = S N ◦ W j ◦ φb ◦ φt (x),     j ∈ {1, . . . , 2q − 1}. (7)
Fermanian (2019). This is an important finding, as global
and sliding windows tend to be commonly used with                  We give a graphical depiction of this in Figure 5. Signature
signature methods.                                                 and window depths (N , q) must be optimised for the
                                                                   problem (typically via cross-validation). We note that
Signature versus logsignature transforms We consider               this canonical method may be adapted to the problem
the signature and logsignature transforms with depths              at hand in two ways: if the problem is known to be
ranging from 1 to 6. As higher depths always produce               parametrization invariant, as is the case for example
more information, we define the performance of the                 for characters recognition, then the time augmentation
(log)signature transform as the best performance across            should not be applied. Moreover, if the problem is
all depths. With this metric, the signature transform is           translation-invariant, then the basepoint augmentation is
significantly better than the logsignature transform, with a       not applied. We emphasise that this pipeline does not
p-value of 0.01 for the Wilcoxon signed-rank test.                 represent a best option for every application, but is meant
                                                                   to represent a compromise between broad applicability,
The key results To conclude, these results show that               ease of implementation, computational cost, and good
invariance-removing transformations such as time and               performance.
                        A Generalised Signature Method for Multivariate Time Series Feature Extraction

                                 Augmentations, φb ◦ φt                          Window, W j                            Transform, S N                   Stack
         Input, x                        Add time & basepoint           Hierarchical dyadic, with j optimised.   Signature features, with N optimised.

                                                                Tim
                                                                    e
                                                                                                                                ...
                                                                                                                                ...




                                                                                                                                                         ...
                                                                                                                                ...
                                                                                                                                                                  Black box




                                                                                                                                                         ...
O
                                                                                                                                ...                              ML classifier
                             Basepoint                                                                                          ...




                                                                                                                                                         ...
                                                                                                                                ...
                                                                                                                                ...



Figure 5. Pictorial representation of the canonical signature pipeline. First, we apply the time and basepoint augmentations to the input
paths, then we compute the signature features over dyadic windows, and finally compute the signature features over each dyadic window.
These features can now be compiled together and fed into any standard machine learning classifier.


5.2. Performance                                                                           pipeline are MUSE and HIVE-COTE. It is worth noting
                                                                                           that MUSE is very memory intensive—Ruiz et al. (2020)
We validate the performance of the pipeline against the
                                                                                           report that it could not finish on 5 of the 26 UEA datasets
26 datasets in the multivariate UEA archive1 . To our
                                                                                           on a computer with 500GB of memory—whilst HIVE-
knowledge, the most recent benchmarks for the UEA
                                                                                           COTE is an ensemble of several sub-classifiers, and thus
archive are the results from Ruiz et al. (2020). We
                                                                                           has very high training and inference costs. On the other
compare their results to the canonical signature pipeline
                                                                                           hand, all experiments for the canonical signature pipeline
with a random forest classifier—see Appendix C.3 for more
                                                                                           were completed with no memory errors on a computer with
details.
                                                                                           less memory, and are significantly faster to run than HIVE-
The benchmarks include variants on classical Dynamic                                       COTE—see Appendix D.
Time Wrapping (DTWI, DTWD and DTWA); an ensemble
                                                                                           The canonical signature pipeline is meant to be a sensible
of univariate classifiers, HIVE COTE (Bagnall et al., 2020),
                                                                                           starting point from which the user can propose additional
known to be highly perfromant in the univariate case; a
                                                                                           variations following the structure defined in equation 6, but
random shapelet forest (Karlsson et al., 2016), denoted
                                                                                           as a standalone classifier this pipeline performs comparably
gRSF, and a bag of words based algorithm, MUSE (Schäfer
                                                                                           to state-of-the-art classifiers, on the UEA data, whilst being
& Leser, 2017); two deep learning methods, TapNet (Wang
                                                                                           less computationally demanding.
et al., 2017) and MLCN (Karim et al., 2019). The MLCN
architecture combines long short term memory layers
(LSTM) and convolutional layers while TapNet combines                                      6. Conclusion
3 blocks: random projections on the different dimensions,
                                                                                           We introduce a generalised signature method as a
convolutional layers and a final attention block to compare
                                                                                           framework to capture recently proposed variations on the
candidate time series representations.
                                                                                           signature method. We go on to perform a first-of-its-kind
                                                                                           extensive empirical investigation as to which elements of
                                                                                           this framework are most important for performance in a
                                                                                           domain-independent setting. In particular, we highlight
                                                                                           the performance of hierarchical dyadic windows and
                                                                                           signature-tailored augmentations such as lead-lag, time
                                                                                           and basepoint. As a result, we are able to present
                                                                                           a canonical signature pipeline that represents a best-
            Figure 6. Performance on UEA datasets.                                         practices domain-agnostic starting point, which shows
                                                                                           competitive performance against state-of-the-art classifiers
                                                                                           for multivariate time series classification.
Figure 6 shows the critical difference plot of this
comparison. The signature pipeline is in the first clique,
that is the group of classifiers that achieve the best accuracy                            References
while not being significantly different from one another.                                  Arribas, I. P., Goodwin, G. M., Geddes, J. R., Lyons, T.,
The two algorithms with a better rank than the signature                                     and Saunders, K. E. A signature-based machine learning
    1
      This is not to be confused with the UCR archive which is a                             model for distinguishing bipolar disorder and borderline
collection of 128 univariate datasets.                                                       personality disorder. Translational psychiatry, 8:1–7,
                      A Generalised Signature Method for Multivariate Time Series Feature Extraction

  2018.                                                        Greff, K., Klein, A., Chovanec, M., Hutter, F., and
                                                                 Schmidhuber, J.       The sacred infrastructure for
Bagnall, A., Dau, H. A., Lines, J., Flynn, M., Large,
                                                                 computational research. In Proceedings of the Python
  J., Bostrom, A., Southam, P., and Keogh, E. The
                                                                 in Science Conferences-SciPy Conferences, 2017.
  uea multivariate time series classification archive, 2018.
  arXiv:1811.00075, 2018.                                      Hambly, B. M. and Lyons, T. J. Uniqueness for the
Bagnall, A. J., Flynn, M., Large, J., Lines, J., and             signature of a path of bounded variation and the reduced
  Middlehurst, M. A tale of two toolkits, report the third:      path group. Annals of Mathematics, 171:109–167, 2010.
  on the usage and performance of hive-cote v1. 0. CoRR,
                                                               He, K., Zhang, X., Ren, S., and Sun, J. Deep Residual
  2020.
                                                                 Learning for Image Recognition. arXiv:1512.03385,
Benavoli, A., Corani, G., and Mangili, F. Should we really       2015.
  use post-hoc tests based on mean-ranks? The Journal of
  Machine Learning Research, 17:152–161, 2016.                 Karim, F., Majumdar, S., Darabi, H., and Harford, S.
                                                                 Multivariate lstm-fcns for time series classification.
Bonnier, P., Kidger, P., Perez Arribas, I., Salvi, C., and       Neural Networks, 116:237–245, 2019.
  Lyons, T. Deep Signature Transforms. In Advances in
  Neural Information Processing Systems, pp. 3099–3109,        Karlsson, I., Papapetrou, P., and Boström, H. Generalized
  2019.                                                          random shapelet forests. Data mining and knowledge
                                                                 discovery, 30(5):1053–1085, 2016.
Chevyrev, I. and Kormilitzin, A. A primer on the signature
  method in machine learning. arXiv:1603.03788, 2016.
                                                               Kidger, P. and Lyons, T.     Signatory: differentiable
Chevyrev, I. and Lyons, T. Characteristic functions of           computations of the signature and logsignature
  measures on geometric rough paths. The Annals of               transforms, on both CPU and GPU. arXiv:2001.00706,
  Probability, 44(6):4049–4082, 2016.                            2020.             URL    https://github.com/
                                                                 patrick-kidger/signatory.
Cho, K., van Merrienboer, B., Gulcehre, C., Bougares,
  F., Schwenk, H., and Bengio, Y.             Learning         Kidger, P., Morrill, J., and Lyons, T.    Generalised
  Phrase Representations using RNN Encoder-Decoder for           Interpretable Shapelets for Irregular Time Series.
  Statistical Machine Translation. EMNLP 2014, 2014.             arXiv:2005.13948, 2020.
Demšar, J. Statistical comparisons of classifiers over
                                                               Kingma, D. P. and Ba, J.         Adam: A method for
  multiple data sets.     Journal of Machine learning
                                                                 stochastic optimization. In Proceedings of International
  research, 7:1–30, 2006.
                                                                 Conference on Learning Representations, 2015.
Fermanian, A. Embedding and learning with signatures.
  arXiv:1911.13211, 2019.                                      Kormilitzin, A., Saunders, K., Harrison, P., Geddes, J.,
                                                                 and Lyons, T. Application of the signature method
Flint, G., Hambly, B., and Lyons, T. Discretely sampled          to pattern recognition in the cequel clinical trial.
   signals and the rough Hoff process. Stochastic Processes      arXiv:1606.02074, 2016.
   and their Applications, 126:2593–2614, 2016.
                                                               Kormilitzin, A., Saunders, K. E., Harrison, P. J., Geddes,
Friz, P. K. and Victoir, N. B.     Multidimensional
                                                                 J. R., and Lyons, T. Detecting early signs of depressive
  Stochastic Processes as Rough Paths: Theory and
                                                                 and manic episodes in patients with bipolar disorder
  Applications, volume 120 of Cambridge Studies in
                                                                 using the signature-based model.         arXiv preprint
  Advanced Mathematics. Cambridge University Press,
                                                                 arXiv:1708.01206, 2017.
  Cambridge, 2010.
Futoma, J., Hariharan, S., and Heller, K. Learning to detect   Lai, S., Jin, L., and Yang, W. Online signature verification
  sepsis with a multitask Gaussian process RNN classifier.       using recurrent neural network and length-normalized
  In Proceedings of the 34th International Conference on         path signature descriptor. In Proceedings of the 14th
  Machine Learning, pp. 1174–1182, 2017.                         IAPR International Conference on Document Analysis
                                                                 and Recognition (ICDAR), volume 1, pp. 400–405.
Grabocka, J., Schilling, N., Wistuba, M., and Schmidt-           IEEE, 2017.
  Thieme, L.      Learning time-series shapelets.   In
  Proceedings of the 20th ACM SIGKDD international             Levin, D., Lyons, T., and Ni, H. Learning from the
  conference on Knowledge discovery and data mining,             past, predicting the statistics for the future, learning an
  pp. 392–401, 2014.                                             evolving system. arXiv:1309.0260, 2013.
                      A Generalised Signature Method for Multivariate Time Series Feature Extraction

Li, C., Zhang, X., and Jin, L. LPSNet: a novel log                Journal of Machine Learning Research, 12:2825–2830,
  path signature feature based hand gesture recognition           2011.
  framework. In Proceedings of the IEEE International
  Conference on Computer Vision, pp. 631–639, 2017.             Perez Arribas, I. Derivatives pricing using signature
                                                                  payoffs. arXiv, pp. arXiv–1809, 2018.
Li, S. C.-X. and Marlin, B. M. A scalable end-to-end
                                                                Reizenstein, J. and Graham, B. The iisignature library:
  Gaussian process adapter for irregularly sampled time
                                                                  efficient calculation of iterated-integral signatures and
  series classification. In Advances in Neural Information
                                                                  log signatures. arXiv:1802.08252, 2018.
  Processing Systems, pp. 1804–1812, 2016.
                                                                Reyes-Ortiz, J.-L., Oneto, L., Samà, A., Parra, X., and
Liao, S., Lyons, T., Yang, W., and Ni, H. Learning
                                                                  Anguita, D. Transition-aware human activity recognition
  stochastic differential equations using RNN with log
                                                                  using smartphones. Neurocomputing, 171:754–767,
  signature features. arXiv:1908.08286, 2019.
                                                                  2016.
Lyons, T. and Oberhauser, H. Sketching the order of events.
                                                                Reyna, M. A., Josef, C., Seyedi, S., Jeter, R., Shashikumar,
  arXiv:1708.09708, 2017.
                                                                  S. P., Westover, M. B., Sharma, A., Nemati, S., and
Lyons, T., Ni, H., and Oberhauser, H. A feature set for           Clifford, G. D. Early prediction of sepsis from clinical
  streams and an application to high-frequency financial          data: the physionet/computing in cardiology challenge
  tick data. In Proceedings of the 2014 International             2019. In 2019 Computing in Cardiology (CinC), pp.
  Conference on Big Data Science and Computing, pp. 5.            Page–1. IEEE, 2019.
  ACM, 2014.                                                    Ruiz, A. P., Flynn, M., and Bagnall, A. Benchmarking
Lyons, T. J., Caruana, M., and Lévy, T. Differential              multivariate time series classification algorithms. arXiv
  Equations driven by Rough Paths, volume 1908 of                 preprint arXiv:2007.13156, 2020.
  Lecture Notes in Mathematics. Springer, Berlin, 2007.         Schäfer, P. and Leser, U. Fast and accurate time series
Moor, M., Horn, M., Bock, C., Borgwardt, K., and Rieck,           classification with weasel. In Proceedings of the 2017
 B. Path Imputation Strategies for Signature Models.              ACM on Conference on Information and Knowledge
 arXiv:2005.12359, 2020.                                          Management, pp. 637–646, 2017.

Morrill, J., Kormilitzin, A., Nevado-Holgado, A.,               Tange, O. Gnu parallel - the command-line power tool. The
 Swaminathan, S., Howison, S., and Lyons, T. The                  USENIX Magazine, 36:42–47, 2011.
 signature-based model for early detection of sepsis from       Wang, B., Liakata, M., Ni, H., Lyons, T., Nevado-Holgado,
 electronic health records in the intensive care unit.           A. J., and Saunders, K. A path signature approach for
 International Conference in Computing in Cardiology,            speech emotion recognition. In Interspeech 2019, pp.
 2019.                                                           1661–1665. ISCA, 2019.
Morrill, J., Kidger, P., Salvi, C., Foster, J., and Lyons, T.   Wang, B., Wu, Y., Taylor, N., Lyons, T., Liakata, M.,
 Neural CDEs for Long Time-Series via the Log-ODE                Nevado-Holgado, A. J., and Saunders, K. E. Learning
 Method. arXiv:2009.08295, 2020a.                                to detect bipolar disorder and borderline personality
                                                                 disorder with language and speech in non-clinical
Morrill, J. H., Kormilitzin, A., Nevado-Holgado, A. J.,
                                                                 interviews. arXiv preprint arXiv:2008.03408, 2020.
 Swaminathan, S., Howison, S. D., and Lyons, T. J.
 Utilization of the signature method to identify the            Wang, Z., Yan, W., and Oates, T. Time series classification
 early onset of sepsis from multivariate physiological           from scratch with deep neural networks: A strong
 time series in critical care monitoring. Critical Care          baseline. In 2017 International joint conference on
 Medicine, 48(10):e976–e981, 2020b.                              neural networks (IJCNN), pp. 1578–1585. IEEE, 2017.
Paszke, A., Gross, S., Chintala, S., Chanan, G., Yang, E.,      Warden, P. Speech commands: A dataset for limited-
  DeVito, Z., Lin, Z., Desmaison, A., Antiga, L., and            vocabulary speech recognition. arXiv:1804.03209,
  Lerer, A. Automatic differentiation in PyTorch. 2017.          2018.
Pedregosa, F., Varoquaux, G., Gramfort, A., Michel,             Wilson-Nunn, D., Lyons, T., Papavasiliou, A., and Ni, H.
  V., Thirion, B., Grisel, O., Blondel, M., Prettenhofer,        A path signature approach to online arabic handwriting
  P., Weiss, R., Dubourg, V., Vanderplas, J., Passos,            recognition. In 2018 IEEE 2nd International Workshop
  A., Cournapeau, D., Brucher, M., Perrot, M., and               on Arabic and Derived Script Analysis and Recognition
  Duchesnay, E. Scikit-learn: Machine learning in Python.        (ASAR), pp. 135–139. IEEE, 2018.
                     A Generalised Signature Method for Multivariate Time Series Feature Extraction

Wu, Y., Ni, H., Lyons, T., and Hudson, R.
 Signature features with the visibility transformation.
 arXiv:2004.04006, 2020a.
Wu, Y., Ni, H., Lyons, T. J., and Hudson, R. L.
 Signature features with the visibility transformation.
 arXiv preprint arXiv:2004.04006, 2020b.

Yang, W., Jin, L., and Liu, M. Deepwriterid: An end-to-
  end online text-independent writer identification system.
  IEEE Intelligent Systems, 31:45–53, 2016a.
Yang, W., Jin, L., Tao, D., Xie, Z., and Feng,
  Z.      Dropsample:     A new training method to
  enhance deep convolutional neural networks for large-
  scale unconstrained handwritten chinese character
  recognition. Pattern Recognition, 58:190–203, 2016b.
Yang, W., Lyons, T., Ni, H., Schmid, C., Jin, L., and
  Chang, J. Developing the path signature methodology
  and its application to landmark-based human action
  recognition. arXiv:1707.03993, 2017.
Ye, L. and Keogh, E. Time series shapelets: a new
  primitive for data mining. In Proceedings of the 15th
  ACM SIGKDD international conference on Knowledge
  discovery and data mining, pp. 947–956, 2009.
                      A Generalised Signature Method for Multivariate Time Series Feature Extraction


                                     Supplementary material
A. Augmentations
We recall that an augmentation is a map

                                                     φ : S(Rd ) → S(Re )p

We give below the precise definition of the different augmentations considered in the study, which are summarized in
Table 2. These augmentations were not typically introduced using such language, so this serves as a reference for how the
existing literature may be interpreted through the generalised signature method.
Throughout the section, we consider a sequence x = (x1 , . . . , xn ) ∈ S(Rd ) and timestamps t = (t1 , . . . , tn ) ∈ S(R). We
recall that if x is regularly sampled then t is usually set to t = (1, . . . , n).

Time augmentation       We recall the definition of the time augmentation:

                                       φ(x) = (t1 , x1 ), . . . , (tn , xn ) ∈ S(Rd+1 ).
                                                                            

It ensures uniqueness of the signature transformation and removes the parametrization invariance (Levin et al., 2013).

Invisibility-reset augmentation First introduced by Yang et al. (2017), the invisibility-reset augmentation consists in
adding a coordinate to the sequence x that is constant equal to 1 but drops to 0 at the last time step, i.e.,

                           φ(x) = (1, x1 ), . . . , (1, xn−1 ), (1, xn ), (0, xn ), (0, 0) ∈ S(Rd+1 ).
                                                                                          

This augmentation adds information on the initial position of the path, which is otherwise not included in the signature as
it is a translation-invariant map.

Basepoint augmentation Introduced by Kidger & Lyons (2020), the basepoint augmentation has the same goal as the
invisibility-reset augmentation: removing the translation-invariant property of the signature. It simply adds the point 0 at
the beginning of the sequence:
                                            φ(x) = (0, x1 , . . . , xn ) ∈ S(Rd ).
The main difference compared to the invisibility-reset augmentation is that the signature of x is contained in the signature
of the invisibility-reset augmented path, whereas it is not in the signature of the basepoint augmented path. The price paid
is that the invisibility-reset augmentation introduces redundancy into the signature, and is more computationally expensive
due to the additional channel. (Recall that the signature method scales as O(dN ), where d is the input channels and N is
the depth of the (log)signature.)

Lead-lag augmentation The lead-lag augmentation, introduced by Chevyrev & Kormilitzin (2016) and Flint et al. (2016)
has been used in several applications (see for example Lyons et al. (2014); Kormilitzin et al. (2016); Yang et al. (2017)). It
adds lagged copies of the path as new coordinates. This then explicitly captures the quadratic variation of the underlying
process (Flint et al., 2016). As many different lags as desired may be added. If there is a single lag of a single timestep,
then this corresponds to
                               φ(x) = ((x1 , x1 ), (x2 , x1 ), (x2 , x2 ), . . . , (xn , xn )) ∈ S(R2d ).

Coordinate projections For multidimensional streams, one may want to compute the signature of a subset of coordinates
individually, rather than the signature of the whole stream; doing so restricts the interaction considered by the signature to
just those between the projected coordinates. Let x1 , . . . , xd ∈ S(R) denote the different coordinates of x ∈ S(Rd ).
Then we define the singleton coordinate projection as

                                     φ(x) = (t, x1 ), (t, x2 ), . . . , (t, xd ) ∈ S(R2 )d ,
                                                                                

whilst considering all possible pairs of coordinates yields the augmentation

                           φ(x) = (t, x1 , x2 ), (t, x1 , x3 ), . . . , (t, xd , xd−1 ) ∈ S(R3 )d(d−1) ,
                                                                                       
                      A Generalised Signature Method for Multivariate Time Series Feature Extraction


                                            Table 2. Summary of the different augmentations
                                                           e         p               Property
           Fixed augmentations
           None                                            d         1
           Time                                            d+1       1               sensitivity to parametrization,
                                                                                     uniqueness of the signature map
           Invisibility-reset                              d+1       1               sensitivity to translation
           Basepoint                                       d         1               sensitivity to translation
           Lead-lag                                        2d        1               information about quadratic variation,
                                                                                     uniqueness of the signature map
           Coordinates projection                                                    dimensionality reduction
               with singletons                             2         d
               with pairs                                  3         d(d − 1)
               with triplets                               4         d(d2 − 1)
           Random projections                              e         p               dimensionality reduction
           Learnt augmentations
           Learnt projections                              e         p               data-dependent and linear
           Stream-preserving neural network                e         1               data-dependent
           Multi-headed stream-preserving NN               e         p               data-dependent

and all possible triples yields the augmentation
                                                                                                           2
                    φ(x) = (t, x1 , x1 , x2 ), (t, x1 , x1 , x3 ), . . . , (t, xd , xd , xd−1 ) ∈ S(R4 )d(d −1) .
                                                                                               


The decision to always include a time dimension is a somewhat arbitrary one, and it may alternatively be excluded if
desired. (This is done so as to make sense of singleton coordinate projections; otherwise the result is a collection of
univariate time series, for which the signature extracts only the increment due to the tree-like equivalence property.)

Random projections When the dimension of the input path is very large, Lyons & Oberhauser (2017) have proposed to
project it into a smaller space by taking multiple random projections. Let e < d and let Ai : Rd → Re be random affine
transformations indexed by i ∈ {1, . . . , p}. Then φ is defined as
                                φ(x) = ((A1 x1 , . . . , A1 xn ), . . . , (Ap x1 , . . . , Ap xn )) ∈ S(Re )p .

Learnt projections Rather than taking random projections, Liao et al. (2019) learn it from the data. This takes exactly
the same form as the random projections, except that the Ai are learnt.

Stream-preserving neural network Bonnier et al. (2019) introduce arbitrary learnt sequence-to-sequences maps prior
to the signature transform, and refer to such maps, when parameterised as neural networks, as stream-preserving neural
networks. For example these may be standard convolutional or recurrent architectures. In general this may be any learnt
transformation
                                                 φ : S(Rd ) → S(Re ).

Multi-headed stream-preserving neural network A straightforward extension of stream-preserving neural networks is
to use multiple such networks, so as to avoid a potential bottleneck through the single signature map that it is eventually
used in. Letting φ1 , . . . , φp be p different stream-preserving neural networks, then this gives an augmentation
                                              φ(x) = (φ1 (x), . . . , φp (x)) ∈ (S(Re ))p .

B. Rescaling
The signature transform can be written as a sequence of tensors, indexed by k ∈ {1, . . . , N }. The k-th term is of size
O(1/k!), as it is computed by an integral over a k-dimensional simplex. It is typical that rescaling these terms to be O(1)
                      A Generalised Signature Method for Multivariate Time Series Feature Extraction

will aid subsequent learning procedures.
One option is to simply multiply the k-th term by k!, which we call post-signature scaling.
However, it is possible that the previous option may suffer from numerical stability issues. Thus we also explore the
performance of an option, called pre-signature scaling, which may alleviate this, which is to multiply the input x by some
                                                                   k
scaling factor α ∈ R. Then the k-th term will be of size O(α /k!), and so by taking α = (N !)1/N the N -th term in
the signature will be O(1); the trade-off is that Stirling’s approximation then shows that the N/2-th term will be of size
O(2N/2 ).

C. Implementation details
C.1. General notes
Code    All the code for this project is available at [redacted for anonymity].

Libraries The machine learning framework used was PyTorch (Paszke et al., 2017) version 1.3.1. Signatures and
logsignatures were computed using the Signatory library (Kidger & Lyons, 2020) version 1.1.6. Scikit-learn (Pedregosa
et al., 2011) version 0.22.1 was used for the logistic regression and random forest models. The experiments were tracked
using the Sacred framework (Greff et al., 2017) version 0.8.1.

Normalisation Every dataset was normalised so that each channel has mean zero and unit variance.

Architectures Two different GRU models were used on every dataset; a ‘small’ one with 32 hidden channels and 2
layers, and a ‘large’ one with 256 hidden channels and 3 layers.
Likewise, two different Residual CNN models were considered. The ‘small’ one used 6 blocks, each composed of batch
normalisation, ReLU activation, convolution with 32 filters and kernel size 4, batch normalisation, ReLU activation, and
a final convolution with 32 filters and kernel size 4, so that there are also 32 channels along the ‘residual path’. A final
two-hidden-layer neural network with 256 neurons was placed on the output. The ‘large’ is similar, except that it used 128
filters in both the blocks and the residual path, had 8 blocks, used a kernel size of 8, and the final neural network had 1024
neurons.
The logistic regression was performed three times with different amounts of L2 regularisation, with scaling
hyperparameters of 0.01, 0.2 and 1; for every experiment the regularization hyperparameter achieving the best accuracy on
the test set was used.
The random forest used the default Scikit-learn implementation with a maximum depth of 6 and 100 trees.

Optimiser The GRU and CNN were optimised using Adam (Kingma & Ba, 2015). The learning rate was 0.01 for the
GRU, and 0.001 for the residual CNN. The small models were trained for a maximum of 500 epochs; the large models were
trained for a maximum of 1000 epochs. The learning rate was decreased by a factor of 10 if validation loss did not improve
over a plateau of 10 epochs. Early stopping was used if the validation loss did not improve for 30 epochs. After training
the parameters were always rolled back to those that demonstrated the best validation loss over the course of training. The
batch size used varied by dataset; in each it was taken to be the power of two that meant that the number of batches per
epoch was closest to 40.

Computing infrastructure Experiments were run on an Amazon AWS G3 Instance (g3.16xlarge) equipped with 4 Tesla
M60s, parallelized using GNUParallel (Tange, 2011).

C.2. Analysis of variations of the signature method
Splits The UEA archive comes with a pre-defined train-test split, which we respect. We take an 80%/20% train/validation
split in the training data, stratified by class label. For the Human Activities and Postural Transitions dataset, we
take a 60%/15%/25% train/validation/test split from the whole dataset. For the Speech Commands dataset, we take a
68%/17%/15% train/validation/test split from the whole dataset. (These somewhat odd choices corresponding to taking
either 25% or 15% of the dataset as test, and then splitting the remaining 80%/20% between train and validation.) These
                      A Generalised Signature Method for Multivariate Time Series Feature Extraction

train/validation splits are only used for the training of the GRU and CNN classifiers.



Combinations In total we tested 8569 different combinations.
The variations tested are divided into groups. The first group consists of the sensitivity-adding augmentations, namely time,
basepoint and invisibility-reset. Relative to the baseline model, we test every possible combination of these. (Including
using none of them.)
The second group consists of those other augmentations, namely the lead-lag, singleton coordinate projection, pair
coordinate projection, triplet coordinate projection, random projections, learnt projections, and multi-headed stream
preserving neural networks, and finally also the case of no additional augmentation.
For the random projections, we consider four possibilities, with e ∈ {3, 6} and p ∈ {2, 5}, all relative to the baseline
model.
For no additional augmentation, lead-lag, coordinate projections, learnt projections, and the multi-headed stream preserving
neural networks, we compose them with the time, time+basepoint and time+invisibility-reset augmentations (the clear best
three from the first group), all relative to the baseline model.
For the learnt projections, we consider four different possibilities corresponding to e ∈ {3, 6} and p ∈ {2, 5}; together
with the time/time+basepoint/time+invisibility-reset cases this yields a total of twelve possibilities.
For the multi-headed stream-preserving neural networks, we again consider four different possibilities corresponding to
e ∈ {3, 6} and p ∈ {2, 5}, for a total of twelve possible augmentation strategies. In each the neural network operates
elementwise, so as to map one sequence to another, and is given by a feedforward neural network of three hidden layers
separated by ReLU activation functions. When e = 3 the hidden layers have 16 neurons each, and when e = 6 they have
32 neurons each.
For both the learnt projections and multi-headed stream-preserving neural networks, training these requires
backpropagating through the model, so these were only considered for the GRU and residual CNN model. (The logistic
regression model would in principle be possible as well, except that we ended up implementing this through Scikit-learn
rather than PyTorch.)
We note that there are a great many possible ways of doing stream preserving neural networks, of which these are a small
fraction. Their relatively weak performance here may likely be improved upon with greater tuning on an individual task,
or the selection of better final models than were considered here.
The third group consisted of the different windows. Recall that the baseline model used a global window; we then consider
varying this to two possible sliding windows, two possible expanding windows, and three possible dyadic windows. The
two possible sliding/expanding windows are chosen so that either 5 or 20 windows are applied across the full length of the
dataset. The three possible dyadic windows are depths 2, 3, 4. Thus in total there are 8 possible window combinations we
consider.
The fourth group consists of rescaling options, namely no rescaling, pre-signature rescaling, and post-signature rescaling.



Omissions For the empirical study on the variations on the signature method, we excluded those UEA datasets with
a dimension d over 60, so as to reduce the computational cost. This results removes 6 of the 30 datasets from the
study, namely DuckDuckGeese, FaceDetection, Heartbeat, InsectWingbeat, MotorImagery, and PEMS-SF. These were
nonetheless used in the demonstration of performance of the canonical signature method in Figure 6. Furthermore those
combinations of dataset/variation/model which produced more than 105 signature features were omitted, to keep the
computation managable. See Table 3.

C.3. The canonical signature pipeline
For each dataset, we implement the following steps. First, the sequences are augmented with time and basepoint
augmentations. Then, we consider every combination of signature depth in {1, 2, 3, 4, 5, 6} and hierarchical dyadic window
depth in {2, 3, 4}. For each of these choices, we perform a randomized grid search on a random forest classifier to optimize
                      A Generalised Signature Method for Multivariate Time Series Feature Extraction


                            Table 3. Summary of the number of combinations considered and omitted.
 Variations                            # Variations     # Classifiers    # Omitted           # Total
                                                                        Combinations       Combinations
 Basic augmentations (Figure 2)              6               6                54                 936
 Other augmentations (Figure 3)
 Lead-lag/ None                              3               6              100/27               468
 Coordinates projection (1)/(2)/(3)          3               6             12/12/54             468
 Random projections                          4               6                32                624
 Learnt projections / MHSP                  12               4             348/176              1248
 Windows (Figure 4)                          8               6                227               1248
 Signature/Logsignature transform           12               6                361               1872
 Rescalings (Figure 8)                       3               6                12                 468
  Total                                                                      1415               9984

its number of trees and maximal depth parameters. We test 20 combinations randomly sampled from the following grids:

                                      n_trees = [50, 100, 500, 1000],
                                 max_depth = [2, 4, 6, 8, 12, 16, 24, 32, 45, 60, 80, None].

Note that a maximal depth set to ‘None’ means that the trees are expanded until all leaves contain exactly one sample.
Finally, we choose the combination of signature and hierarchical dyadic window depths which maximise the out-of-bag
score.

D. Additional results
D.1. Analysis of variations of the signature method
Running time To get a sense of the cost of each augmentation or window, we present the run times of each
augmentation/model combination, and each window/model combination. (The times for varying between signature and
logsignature, and between different rescalings, are largely insignificant.) See Table 4.
The run times are averaged over every UEA dataset. As the datasets are of very different sizes this thus represents quite a
crude statistic, and in particular produces very large variances, so these are most meaningful simply with respect to each
other.

Sensitivity-inducing augmentations broken down by dataset type Table 5 shows the average rank of each of the first
group of augmentations (that add sensitivity to certain kinds of perturbation) by dataset type, where the types are taken
from Bagnall et al. (2018). (This may be regarded as a companion to Table 6.)
It is interesting to note that for EEG data, it seems better not to consider the time augmentation, whereas it is the case for
other applications. In particular the combination of time and basepoint augmentations achieve the best ranks for human
action and motion recognition (HAR and MOTION in Table 5). Recognizing an action may not be translation-invariant
nor invariant by time reparametrization.

Other augmentations broken down by dataset characteristichs               Table 6presents the average ranks of the other
augmentations borken down by some characteristics of the datasets.
Here we see that there is generally a better choice than doing nothing at all, but that this better choice. For example
on long or high-dimensional datasets, coordinate projections often perform well, whilst multi-headed stream preserving
transformations do substantially better on EEG datasets. Lead-lag remains a strong choice in many cases.

Depth study on the signature transform In the main text we focused on the difference between the signature and
logsignature transforms, and stated that larger depths must be chosen by a bias-variance tradeoff. Here we consider varying
                      A Generalised Signature Method for Multivariate Time Series Feature Extraction


            Table 4. Average run time (in seconds) for various experiments. mean (std), averaged over all UEA datasets.
                                                                                      Classifier
                                                                                                 Logistic       Random
                                                                 CNN                GRU
                                                                                                regression       forest
         Time augment & Global window (Baseline)             69.8 (98.0)       22.2 (31.8)      2.67 (7.09)    2.23 (4.84)
         Augmentation
         None                                                 48.1 (63.5)       16.8 (33.6)     3.55 (9.91)    66.3 (321)
         Lead-lag                                           48.58 (69.99)       15.2 (18.1)     5.76 (11.7)    3.35 (6.04)
         Coordinates projection (1)                          32.8 (31.49)       13.4 (17.8)      1.37 (4.2)    12.2 (59.3)
         Coordinates projection (2)                           41.5 (51.4)       22.6 (62.3)     3.01 (8.54)    42.3 (203)
         Coordinates projection (3)                           41.3 (39.9)       19.1 (24.5)     5.41 (9.76)     6.3 (14.1)
         Random projection                                    62.2 (70.1)       21.1 (31.2)     0.86 (1.25)     1.4 (2.47)
         Learnt projection                                    917 (1288)         752 (972)           –               –
         Multi-headed stream-preserving                      1051 (1677)       1758 (4442)           –               –
         Window
         Sliding                                              90.6 (120)       79.4 (175)       10.1 (27.4)     6.4 (16.0)
         Expanding                                            102 (133)        68.7 (115)       9.98 (27.2)    7.17 (19.0)
         Dyadic                                               725 (868)        56.9 (65.1)      12.5 (33.2)    7.59 (18.3)


                        Table 5. Average ranks for different augmentations by type of data. Lower is better.
                                                                Augmentation
                                                                                    Time +         Time +
               Data type     None      Time     Basepoint      Invisibility-reset
                                                                                    Basepoint      Invisibility-reset
               EEG           3.88      3.50     4.00           2.00                 4.00           3.63
               HAR           5.00      2.95     4.85           3.65                 2.00           2.55
               MOTION        5.25      2.75     5.75           3.88                 1.50           1.88
               OTHER         4.43      3.31     4.88           3.19                 2.87           2.31

the depth together with the choice of signature or logsignature, and taking the best transform for each depth. See Figure 7.
We see that larger depths do indeed generally correspond to increased performance, up to a point. The optimal depth will
depend on the complexity of the task, as the number of features increases exponentially with the depth.




                            Figure 7. Critical differences plot for the depth study on the UEA datasets.


Rescaling critical difference diagram In Figure 8, we see that pre-signature rescaling performs significantly worse than
the other two options and that no significant difference between post-rescaling and no rescaling is found.

D.2. Complete results
We present in Tables 7, 8, 9, 10, 11 and 12 the performance of the different signature variations on each dataset. The tables
were obtained by maximizing the test accuracy of the signature method over the different classifiers considered. Recall
that some values are omitted due to the large number of signature features that would be obtained.
                       A Generalised Signature Method for Multivariate Time Series Feature Extraction


                   Table 6. Average ranks for different augmentations by dataset characteristics. Lower is better.
                                                                    Augmentation
                                                    Coordinates projection       Random             Learnt
             Characteristic    None     Lead-lag                                                                 MHSP
                                                    (1)    (2)       (3)        Projection        Projection
             Data type
             EEG               4.88       4.83      6.50    3.13     5.67          4.38              2.75            2.75
             HAR               2.25       1.78      7.20    3.50     2.90          4.75              6.50            6.50
             MOTION            2.63       1.75      7.00    4.50     2.13          5.00              7.33            5.00
             OTHER             2.88       3.92      5.44    2.63     3.29          4.69              6.00            5.21
             Series length
             <50               3.20       2.20      7.40    3.20     2.70          5.10              7.00            5.20
             50-100            2.20       1.33      6.00    4.10     2.75          6.20              4.80            5.10
             100-500           2.28       2.57      7.28    3.50     2.63          4.17              6.63            5.33
             >500              4.00       4.00      5.28    2.64     4.57          4.07              4.40            5.60
             Dimension d
             2                 4.67        3.5      6.33    4.33      4.0          2.83              6.67            3.67
             3-5                2.5       2.21      6.36    3.43     3.14          4.64              6.67            6.83
             6-8               3.25       2.5       6.94     3.0     3.56           5.0              5.29             6.0
             >8                2.25       3.75      6.31    3.19      2.5          5.19              5.29            4.19




                                           Figure 8. Performance of different rescalings

D.3. Canonical signature method
In Table 13 we give the full results for our canonical signature method on all UEA datasets, together with the results of
Ruiz et al. (2020) used in Figure 6.
Finally, we give in Table 14 the hyperparameters that were selected for each dataset in the signature pipeline model.
   A Generalised Signature Method for Multivariate Time Series Feature Extraction




                Table 7. Accuracy of sensitivity-inducing augmentations per dataset
                                                               Augmentation
                                                                                      Time +              Time +
Dataset                     None      Time      Basepoint      Invisibility-reset
                                                                                     Basepoint       Invisibility-reset
ArticularyWordRecognition    96.0    96.3        95.7               96.3               97.7               97.0
AtrialFibrillation            46.7    46.7        40.0               33.3               40.0               40.0
BasicMotions                 100.0   100.0       100.0              100.0              100.0              100.0
CharacterTrajectories         88.3    93.2        86.4               88.7               93.8               93.7
Cricket                      91.7    94.4        94.4               97.2               97.2                95.8
ERing                        80.0    92.6        77.4               89.6               91.9                92.2
EigenWorms                   72.5    79.4        74.8               76.3               87.0                81.7
Epilepsy                     84.8    89.9        91.3               91.3               97.1                94.9
EthanolConcentration         27.8    29.3        33.5               41.8               34.6                41.4
FingerMovements               55.0    52.0        57.0               58.0               55.0               56.0
HandMovementDirection        29.7    33.8        32.4               33.8               36.5                32.4
Handwriting                  21.9    30.8        23.6               24.6               30.6                28.7
JapaneseVowels                85.4    85.1        97.3               98.1               97.3               98.1
LSST                          42.0    47.4        44.0               44.4               50.9               48.7
Libras                        72.8    84.4        65.0               75.0               80.0               77.2
NATOPS                        81.7    88.3        79.4               79.4               91.1               92.2
PenDigits                     91.1    97.1        88.3               93.1               96.8               97.1
PhonemeSpectra                4.7     8.2         4.3                5.7               10.0                 8.1
RacketSports                 78.9    80.3        78.9               82.9               82.9                81.6
SelfRegulationSCP1           81.6    83.3        76.8               84.0               75.4                85.0
SelfRegulationSCP2           57.2    56.7        56.1               56.7               56.1                55.0
SpokenArabicDigits           82.5    85.5        80.5               88.0               85.1                90.1
StandWalkJump                60.0    46.7        40.0               46.7               40.0                46.7
UWaveGestureLibrary          84.1    87.5        79.7               82.8               87.5                83.4
Human Activity                73.0    76.6        92.3               92.2               93.0               93.8
Speech Commands              71.4    75.9        74.7               74.9               79.7                79.5
Average rank                 4.69     3.12        4.87               3.29                  2.5                2.54




                       Table 8. Accuracy of other augmentations per dataset
                                                               Augmentation
                                                  Coordinates projection         Random            Learnt
Dataset                     None     Lead-lag                                                                    MHSP
                                                  (1)     (2)       (3)         projection       projection
ArticularyWordRecognition   97.7      96.3       83.3       95.7      97.0          95.3           73.7              80.3
AtrialFibrillation           46.7      40.0      53.3        53.3      46.7          66.7          46.7              53.3
BasicMotions                100.0     100.0      80.0       100.0     100.0         100.0          97.5              87.5
CharacterTrajectories        93.8      95.3      43.9        93.2      93.8          93.3          89.6              91.1
Cricket                      97.2      98.6      90.3        97.2      95.8          88.9          69.4              56.9
ERing                        92.6      94.8      79.3        89.3      91.9          74.4          62.2              61.1
EigenWorms                   87.0      87.8      50.4        84.0      89.3          78.6            –                 –
Epilepsy                     97.1      97.1      55.8        95.7      95.7          81.9          67.4              65.9
EthanolConcentration        41.4      39.9       42.2       43.3      42.2          30.4           32.3              30.0
FingerMovements              56.0       –        59.0        58.0       –            55.0          60.0              65.0
HandMovementDirection        36.5      31.1      31.1        40.5      37.8          37.8          33.8              44.6
Handwriting                  30.8      33.5      11.3        27.8      30.0          21.6          12.6              13.2
JapaneseVowels               98.1      97.6      94.1        97.8      97.6          84.1          95.4              95.9
LSST                         50.9      55.6      43.5        51.7      52.8          43.7          34.4              39.8
Libras                       84.4      86.7      47.8        83.9      85.0          86.7          73.3              81.1
NATOPS                       92.2       –        33.3        90.6      91.1          85.6          83.9              81.7
PenDigits                    97.1      98.3      60.2        96.8      97.2          96.7          96.5              97.4
PhonemeSpectra               10.0       –         4.5         9.4      10.6           8.9           7.2               7.7
RacketSports                 82.9      82.2      53.3        85.5      84.2          75.7          73.7              75.0
SelfRegulationSCP1           85.0      86.0      61.8        85.0      84.0          81.6          86.7              84.6
SelfRegulationSCP2           56.7      57.2      55.6        58.9      55.6          60.6          59.4              57.8
SpokenArabicDigits           90.1      96.6      58.5        86.0      90.0          83.0          88.0              86.0
StandWalkJump                46.7      40.0      40.0        53.3      40.0          53.3            –                 –
UWaveGestureLibrary          87.5      88.8      50.6        85.6      87.5          86.2          74.1              75.6
Human Activity               93.8      93.6      75.8        93.2      93.6          69.2          91.3              91.5
Speech Commands             79.7        –        14.9        77.1       –            70.2            –               76.1
Average ranks                2.9       2.77      6.52       3.33      3.23          4.71           5.83              5.31
A Generalised Signature Method for Multivariate Time Series Feature Extraction




                        Table 9. Accuracy of windows per dataset
                                                             Window
            Dataset                       Global     Sliding    Expanding      Dyadic
            ArticularyWordRecognition      96.3      89.3         99.0         99.0
            AtrialFibrillation              46.7      46.7         46.7         60.0
            BasicMotions                   100.0     100.0        100.0        100.0
            CharacterTrajectories           93.2      94.6         96.9         97.1
            Cricket                         97.2      93.1         97.2         95.8
            ERing                          90.7      88.5         91.9         94.8
            EigenWorms                     80.2      74.8         78.6         76.3
            Epilepsy                        89.9      92.8         92.0         94.2
            EthanolConcentration           30.4      38.8         30.0         35.7
            FingerMovements                 50.0       –            –            –
            HandMovementDirection           33.8      33.8         36.5         33.8
            Handwriting                    30.1      21.5         30.2         27.2
            JapaneseVowels                  85.1      76.5         88.1         89.2
            LSST                            47.8      43.1         48.3         46.6
            Libras                          83.3      85.6         91.1         90.0
            NATOPS                          93.3      84.4         90.6          –
            PenDigits                       95.8       –            –           97.6
            PhonemeSpectra                  8.6       9.2          9.6         10.4
            RacketSports                    82.2      80.3         84.2         88.2
            SelfRegulationSCP1             82.6      87.4         84.0         86.7
            SelfRegulationSCP2             56.7      60.6         54.4         56.1
            SpokenArabicDigits              85.5      91.5         93.7         96.6
            StandWalkJump                  46.7      53.3         46.7         53.3
            UWaveGestureLibrary             86.6      79.4         89.1         89.7
            Human Activity                  76.1      73.0         80.4         81.7
            Speech Commands                75.9      76.5         82.3         83.0
            Average ranks                  2.83       3.04         2.17         1.73




      Table 10. Accuracy of signature and logsignature transforms per dataset.
                                                            Transform
                      Dataset                      Signature    Logsignature
                      ArticularyWordRecognition     97.7           97.3
                      AtrialFibrillation             60.0           53.3
                      BasicMotions                  100.0          100.0
                      CharacterTrajectories         93.8           93.8
                      Cricket                       100.0          100.0
                      ERing                          90.0           89.3
                      EigenWorms                     79.4           81.7
                      Epilepsy                       93.5           91.3
                      EthanolConcentration          31.9           30.0
                      FingerMovements               59.0           56.0
                      HandMovementDirection         40.5           40.5
                      Handwriting                    35.3           24.5
                      JapaneseVowels                 85.9           86.8
                      LSST                           52.0           46.4
                      Libras                         90.6           87.8
                      NATOPS                         89.4           91.7
                      PenDigits                      97.8           97.5
                      PhonemeSpectra                  8.9            7.6
                      RacketSports                   85.5           84.9
                      SelfRegulationSCP1             84.0           83.3
                      SelfRegulationSCP2             57.2           56.1
                      SpokenArabicDigits            87.5           85.8
                      StandWalkJump                  53.3           53.3
                      UWaveGestureLibrary            90.0           86.9
                      Human Activity                 78.7           78.3
                      Speech Commands               75.9           76.3
                      Average ranks                  1.25             1.75
A Generalised Signature Method for Multivariate Time Series Feature Extraction




                   Table 11. Accuracy of rescaling choices per dataset
                                                              Rescaling
                      Dataset                         None          Post          Pre
                      ArticularyWordRecognition       97.3        97.0          97.7
                      AtrialFibrillation               53.3        53.3          46.7
                      BasicMotions                    100.0       100.0         100.0
                      CharacterTrajectories           94.6        94.6          94.6
                      Cricket                          98.6        97.2          97.2
                      ERing                            93.7        93.7          93.0
                      EigenWorms                       80.9        80.9          79.4
                      Epilepsy                         92.0        92.0          91.3
                      EthanolConcentration            31.2        31.6          30.0
                      FingerMovements                 54.0         54.0          50.0
                      HandMovementDirection           35.1        32.4          29.7
                      Handwriting                      36.6        36.4          37.1
                      JapaneseVowels                   87.3        85.9          85.7
                      LSST                             55.8        55.6          55.4
                      Libras                           85.0        86.1          84.4
                      NATOPS                           92.8        92.8          91.7
                      PenDigits                        96.6        96.7          96.7
                      PhonemeSpectra                    8.0         8.1           8.2
                      RacketSports                     84.2        84.2          83.6
                      SelfRegulationSCP1               79.5        83.3          84.6
                      SelfRegulationSCP2               56.1        57.2          56.7
                      SpokenArabicDigits              90.5         90.5          90.2
                      StandWalkJump                    46.7        53.3          46.7
                      UWaveGestureLibrary              87.5        87.2          87.2
                      Human Activity                   85.0        84.6          85.1
                      Speech Commands                 77.0         75.7          75.9
                      Average ranks                   1.73          1.92          2.35




               Table 12. Accuracy of (log)signature depth per dataset.
                                                                  Depth
         Dataset                        1         2           3             4             5      6
         ArticularyWordRecognition    83.3    96.0        97.3         97.7             95.3     –
         AtrialFibrillation           40.0     40.0        60.0         33.3             40.0   53.3
         BasicMotions                 70.0    100.0       100.0        100.0            100.0   92.5
         CharacterTrajectories        42.3     88.0        93.2         93.8             92.9   93.8
         Cricket                      30.6     93.1        97.2         98.6            100.0    –
         ERing                        77.0     89.6        90.0         89.3             88.9   84.8
         EigenWorms                   46.6     81.7        79.4         79.4              –      –
         Epilepsy                     50.7     78.3        89.9         93.5             93.5   93.5
         EthanolConcentration         25.5    30.8        30.0         31.2             31.9    27.4
         FingerMovements              57.0     58.0        59.0          –                –      –
         HandMovementDirection        40.5     36.5        37.8         39.2             32.4    –
         Handwriting                   7.3     22.4        32.4         33.3             35.3   32.7
         JapaneseVowels               78.9     85.9        86.8         84.3             81.4    –
         LSST                         40.9     45.6        47.6         50.6             52.0   44.7
         Libras                       51.7     77.2        85.0         87.8             88.9   90.6
         NATOPS                       35.0     86.7        91.7          –                –      –
         PenDigits                    60.0     90.4        96.9         97.7             97.4   97.8
         PhonemeSpectra                4.1      7.6         8.9          –                –      –
         RacketSports                 44.1     77.0        78.9         84.9             85.5   82.2
         SelfRegulationSCP1           53.6     80.2        84.0         83.3             81.9    –
         SelfRegulationSCP2           56.1     55.0        56.7         54.4             57.2    –
         SpokenArabicDigits           52.1     85.8        85.5         87.5              –      –
         StandWalkJump                46.7     46.7        46.7         46.7             53.3   46.7
         UWaveGestureLibrary          49.4     83.1        86.6         87.8             90.0   88.1
         Human Activity               47.7     78.3        76.0         78.7             78.6    –
         Speech Commands              14.8    69.6        76.3           –                –      –
         Average ranks                4.73    3.44           2.62          2.48          2.38   3.04
                           A Generalised Signature Method for Multivariate Time Series Feature Extraction




                                                                                Classification method
                                                                                                                                 Signature
           Dataset                     DTWD       DTWA    DTWI        HIVE COTE       MLCN       MUSE      TapNet      gRSF
                                                                                                                                 Pipeline
           ArticularyWordRecognition   98.7       98.7    98.0          99.0            95.7     99.3      95.7        98.3            97.7
           AtrialFibrillation           20.0       26.7    26.7          13.3           33.3      40.0      20.0        26.7            46.7
           BasicMotions                 97.5      100.0   100.0         100.0           87.5     100.0     100.0       100.0           100.0
           Cricket                     100.0      100.0    98.6          98.6           91.7      98.6     100.0        98.6            95.8
           Epilepsy                     96.4       97.8    97.8         100.0           73.2      99.3      95.7        97.8            95.7
           EthanolConcentration         32.3       31.6    30.4          79.1           37.3      47.5      30.8        34.6            43.3
           ERing                        91.5       92.6    91.9          97.0           94.1      97.4      90.4        95.2            94.8
           FaceDetection               52.9       52.8    51.3          65.6            55.5     63.1      60.3        54.8             61.4
           FingerMovements              53.0       51.0    52.0          55.0           58.0      55.0      47.0        58.0            52.0
           HandMovementDirection        18.9       20.3    29.7          44.6           52.7      36.5      33.8        41.9            20.3
           Handwriting                  60.7       60.7    50.9          48.2           30.9      52.2      28.1        37.5            37.9
           Heartbeat                    71.7       69.3    65.9          72.2           38.0      71.2      79.0        76.1            69.8
           Libras                       87.2       88.3    89.4          90.0           85.0      89.4      87.8        69.4            93.9
           LSST                        55.1       56.7    57.5          57.5            52.8     64.0      51.3        58.8             56.9
           NATOPS                      88.3       88.3    85.0          88.9            90.0     90.6      81.1        84.4             92.2
           PenDigits                    97.7       97.7    93.9          93.4           97.9      96.7      85.6        93.5            97.4
           Racketsports                 80.3       84.2    84.2          88.8           84.2      92.8      87.5        88.2            90.8
           SelfRegulationSCP1          77.5       78.5    76.5          85.3            90.8     69.6      93.5        82.3             78.8
           SelfRegulationSCP2          53.9       52.2    53.3          46.1            50.6     52.8      48.3        51.7             50.6
           StandWalkJump                20.0       33.3    33.3          33.3           40.0      26.7      13.3        33.3            46.7
           UWaveGestureLibrary         90.3       90.0    86.9          89.1            85.9     93.1      90.0        89.7             90.9
           Average Ranks                5.6        5.2      5.9          4.0            5.6        3.2      6.4          4.8            4.3


Table 13. Results of the signature canonical pipeline along with a selection of classifiers from Ruiz et al. (2020) (including the top
performing MUSE algorithm) with a Random Forest for the UEA archive.




                                                  Signature hyperparmeters           RF hyperparameters                 Other
                      Dataset                     Depth     Dyadic depth         Max depth     Num estimators      Training time (s)
                      ArticularyWordRecognition     2             2                 45              500                  60.3
                      AtrialFibrillation            1             2                None               50                  35.9
                      BasicMotions                  2             2                 24               100                  19.3
                      CharacterTrajectories         4             2                 80               500                 181.4
                      Cricket                       2             4                  6               500                 249.0
                      DuckDuckGeese                 1             2                 16               100                 140.9
                      ERing                         2             3                  8              1000                  16.7
                      EigenWorms                    3             3                 12               100                 250.1
                      Epilepsy                      2             3                  8              1000                  42.8
                      EthanolConcentration          2             4                 24              1000                 454.2
                      FaceDetection                 1             4                  8              1000                1816.2
                      FingerMovements               1             2                  4               100                  30.8
                      HandMovementDirection         2             2                None               50                  66.3
                      Handwriting                   6             2                 32              1000                 280.3
                      Heartbeat                     1             4                None               50                  45.1
                      InsectWingbeat                1             3                 45              1000                5367.5
                      JapaneseVowels                2             3                  6              1000                  95.4
                      LSST                          4             2                 60              1000                1590.5
                      Libras                        6             2                None              100                  28.4
                      MotorImagery                  1             3                 24                50                 347.1
                      NATOPS                        2             3                 32              1000                  37.8
                      PEMS-SF                       1             3                 80              1000                 252.3
                      PenDigits                     3             2                 80              1000                 302.3
                      PhonemeSpectra                2             4                 45              1000                2188.7
                      RacketSports                  3             2                None              500                  13.9
                      SelfRegulationSCP1            3             2                None              100                 186.6
                      SelfRegulationSCP2            3             2                  6                50                 138.1
                      SpokenArabicDigits            2             3                 45              1000                1204.0
                      StandWalkJump                 1             3                  2                50                 101.5
                      UWaveGestureLibrary           2             2                 60               500                  21.8


                             Table 14. Hyperparameters used for each dataset in the signature pipeline model.