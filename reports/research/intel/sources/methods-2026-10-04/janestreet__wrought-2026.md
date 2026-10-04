source: https://blog.janestreet.com/wrought-2026/
fetched_utc: 2026-10-04T18:14:00Z

Jane Street Blog - What the interns have wrought, special jumbo 2026 edition 

              Home

              All Posts

              Machine Learning

              Authors Index

              Jane Street

              Subscribe to email updates

Subscribe to Email Updates

              Featured Reads

                Read more

Using ASCII waveforms to test hardware designs

                Read more

Finding memory leaks with Memtrace

              Tags

async

book

c

camlp4

code-review

comments

compiler

core

hackerschool

hg

incremental

internship

interviewing

machine-learning

ocaml

parallel-programming

performance

ppx

real-world-ocaml

registers

speed

ui

              Get the RSS feed

              Jane Street Open Source

              Join Our Team

What the interns have wrought, special jumbo 2026 edition

            Sep 30, 2026 | 

  9 min read

      Share on Facebook

      Share on Twitter

      Share on LinkedIn

By: James Somers

It’s time again to review some of what Jane Street’s interns built over the summer, though
this year we’re going to try to cover more projects and in more depth. In particular we’re
including projects from teams and roles whose work has historically been hard to talk
about publicly—like ML research and trading desk operations. There’s just been too much
exciting work in these areas to leave them out.

Hopefully the below gives a more complete picture of the kind of stuff interns do here,
with examples from ML Research, Linux Engineering, IT, Strategy & Product, and Trading
Desk Operations Engineers. Even so it’s still a small sample out of hundreds of projects
(and doesn’t talk at all about our trading internship, which is more of a
you-had-to-be-there apprenticeship, and even harder to sum up).

If you’re interested in doing work like what you see below, consider applying! You can
find more details here: Jane Street
Internships. Applications for
our 2027 internship are now open!

Anyway, let’s dive in.

ML Research and Engineering

This year, we had both an ML Research internship, and our first ever ML Engineering
internship class.

Here’s a great example from ML engineering.

Arsh Koneru developed an activation checkpointing scheme that outperformed PyTorch’s in
order to keep model training runs within a tight RAM budget. In activation
checkpointing, you recompute some nodes in a neural network’s backward pass instead of
saving them from the forward pass. This trades off memory for compute. Arsh’s project
involved finding a better set of nodes to recompute. He accomplished this by parsing the
intermediate dynamo graph from torch.compile and greedily picking nodes with the
cheapest recompute cost per byte of peak memory freed. Read the full writeup
here.

Projects on the research side have a different flavor than the engineering projects, in that
they tend to be more exploratory—they are, genuinely, research. Reviewing several
interns’ work logs in preparing this post, I was struck by just how doggedly—and how
quickly!—they perform experiments, often scaling up to serious training runs in the
first week. (I’d have just gotten my editor set up the way I like…) After a month and a
half (interns do two projects each summer) they’re reporting findings that, per the mentor
of one of the projects below, can end up being “very important.”

Kavish created an event-level generative model of market data using autogressive
diffusion. If you could do long rollouts that fooled a classifier, you’d have a source
of synthetic data. But even just the process of training such a model sheds light on a
question that’s long interested us: just how continuous is market data? Read the full
writeup
here.

Monte explored a variety of methods for combating memorization in LLMs. We want LLMs to
make predictions, and in historical benchmarks they often seem quite good at it —but
are they good at it because they’ve memorized the outcomes during pretraining?  This is
one reason such systems often fail on new prediction tasks in production, past the
knowledge cutoff. Using divergence decoding, distillation, natural language
autoencoders, and some prompt engineering, Monte sought to quantify memorization and see
if he could shake it out of a model without hurting out-of-sample performance. Read the
full writeup here.

There were of course so many other cool projects that we couldn’t cover in depth, among
them:

Kohki’s neural network that can answer detailed questions about the future of any
order on the book. Compared to a classical time-series setup, the interface that was
being demanded—per-order predictions across a variable-sized book, all conditioned on a
single shared input sequence—was unusual, and after much experimentation Khoki arrived
at a clever architecture well-suited to it.

Alexander’s sequence model that predicts both stock returns and future input
features, then tests whether tree-search rollouts and self-distillation beat direct
return prediction.

Ritvik’s experiments to speed up prefill on a large model by warming it up with KV
cache distillation.

Dashiell’s attempts to characterize bf16 vs. fp32 hidden-state degradation
in a Mamba model to see if he could develop quantization-aware training.

And others besides!

Software Engineering

Beyond ML, there were a huge number of projects that we could have written up this year,
but given that humans are doing the writing we had to keep it to a manageable number.

Theodor Totev built a performance testing framework and implemented an indexing strategy
to speed up “tip recovery” in Aria, a messaging framework used heavily at Jane Street
for state machine
replication.
When a client is slightly too slow to process messages, the server will still maintain
the connection as long as the client stays within one ring buffer capacity from the
“tip” of the stream. Previously this meant scanning and filtering through all messages
in the ring buffer even if the client was only interested in a much smaller subset of
the total Aria stream—this caused slowness in our servers on several occasions in
production!  Theodor’s code builds up and maintains a dense index from each Aria “topic”
partition into message offsets in the ring buffer, resulting in 30% less CPU utilization
in real-world scenarios and significantly cutting overall latency across clients during
those times. 

Sai Konkimalla developed lib/spmd, an implicit single-program-multiple-data DSL in
OxCaml targeting CPU SIMD instructions, similar to Intel’s ISPC. It takes inspiration
from Halide and Dex by separating schedule from code and reasoning about index
sets. Although Sai didn’t finish the SIMD backend, initial results against hand-written
C intrinsics look promising. 

And just to give a quick shout to a few of the many other projects we would have loved to
write more about:

Mikołaj Kołek wrote an implementation of interning-/hash-consing-based compression of
debug graphs in Datafetcher, a very powerful internal library for abstracting out requests
for external data. Kołek’s project involved dealing with tricky races between multiple
compressors working on the same graph.

Stanislaw Malinowski evaluated ILP/SAT solvers as an alternative to our greedy scheduler
for assigning market data applications to hosts, and got promising results.

Chien-Yu Xiong implemented a better coordination protocol for controlling access to our
Gurobi cluster, for linear programming and optimization problems.

Oscar Xu improved the performance of an important feature engineering library that feeds
into our trading systems. Previously, the system had to consume market data, keep track
of features, and evaluate feature vectors all in one process. Oscar’s work allows some
of this to happen in symbiote processes, exposing accessors to trading systems via
symmetrically double-buffered addrs in shared memory.

Linux Engineering and IT

Linux engineers at Jane Street have a broad remit, working on everything from datacenter
provisioning and orchestration, kernels and drivers delivered through Nix and RPMs, to
production and research storage at scale, managing cloud infrastructure that integrates
cleanly with our on-prem platform, and, in partnership with the IT and Network Engineering
teams, managing Linux desktops on the network. This summer, interns took on a slew of
projects in these areas but we wanted to highlight a few that stood out:

Jacob Root built a resilient kernel log reporter, ensuring that kernel logs would be
available even during disk or network failures. To do this he had to root out surprising
dependencies: even figuring out the host and port to send logs to relies on disk,
because DNS resolution touches /etc/resolv.conf and /etc/hosts. When even the
network is down, Jacob’s tool falls back on Linux’s pstore subsystem, which provides a
bare-bones persistent storage mechanism backed by the same non-volatile memory that
stores system firmware. All this has allowed us to investigate individual crashes in the
kind of depth we like, especially on systems without lights-out management that have
historically been difficult to debug. Read the full writeup here.

Kian Kasad developed an OCaml-native FUSE (filesystem in userspace) library to build a
high-performance read-only FUSE server for an in-house storage system called Depot.
Historically, we’ve been able to rely on off-the-shelf storage products (like Dell
Isilons or VAST Storage), but as dataset sizes have grown, we built Depot as a highly
scalable object store specifically for research workloads. Unfortunately, various
components in our core trading research infrastructure expect to access files via a
regular POSIX filesystem interface, whereas Depot’s client library is all in
OCaml. Kian’s project bridged the gap, and after some patient performance optimization
reached read speeds of 1.3 GiB/s, with room still to improve. Read the full writeup here.

Max Ohm developed a centralized configuration management system for Windows, replacing a
suite of distributed PowerShell scripts that had become hard to reason about. In Max’s
system, a central orchestrator, developed in OCaml, interacts with a stateless F# agent
running on each host. The setup greatly simplifies the client-side logic and helps bring
type safety to the top-level config scripts specifying which host classes to upgrade and
how. One of the neat things about Max’s projects was the careful way it was tested,
where the old and new systems could operate in tandem, with reports of any diffs between
the two. This revealed some subtle bugs that had long lain dormant in the old
system. 

Trading Desk Operations Engineers

Trading Desk Operations Engineers (TDOEs) keep our trading desks running smoothly. They
collaborate deeply with traders, desk developers, and operations teams like finance and
accounting. On a given day a TDOE might investigate an outage in a critical system, write
OCaml code to automate an error-prone process, or sit with a trader to build a dashboard
together. TDOEs must balance steadily making workflows and systems more resilient with the
urgent needs of trading.

This summer’s internship had more projects across more teams than ever before. Interns’
work on the desks ranged from convertible-bond trade analysis with Global Capital Markets
to cash flow reconciliation for exotic options trading.

Read more—with more intern projects!—on the accompanying post: What the TDOE interns have wrought, 2026 edition

Strategy and Product

Strategy and Product Specialists are versatile, cross-functional contributors who drive
forward firmwide initiatives. The role requires a unique combination of big-picture
thinking (“why is this valuable to the business?”) and deep analytical problem-solving.

Full-time SPs work across all areas of the firm: on trading desks, in infrastructure
groups, and with tech teams. SP interns are embedded directly onto a team, paired with a
full-time mentor, and given real-world projects we actually care about getting done.  Some
of this summer’s projects included automating fleetwide Linux kernel upgrades; modeling
the fee expense on several types of loans to better allocate financing costs to different
kinds of trading; and improving how we manage risk limits on unusual dates; and more.

You can read about them here: What the SP interns have wrought.

      #internship

     previous post

    next post 

Subscribe to Email Updates

Signals & Threads Podcast

Listen to the latest episode

Featured Tech Talk

The Algorithm for Precision Medicine

Jane Street YouTube Channel

Featured Reads

                Read more

Using ASCII waveforms to test hardware designs

                Read more

Finding memory leaks with Memtrace

Tags

async

book

c

camlp4

code-review

comments

compiler

core

hackerschool

hg

incremental

internship

interviewing

machine-learning

ocaml

parallel-programming

performance

ppx

real-world-ocaml

registers

speed

ui

RSS

      Get the RSS feed

Jane Street Open Source

      From committing patches to the Linux kernel to releasing our own projects, we’re always looking for ways to participate in the open source community.

Join Our Team

Where FP meets the real world.

If you're interested in working at a place where functional programming meets the real world, then apply for a job at Jane Street.

Learn more

Who We Are

What We Do

Client Offering

The Latest

Culture

Join Jane Street

Contact Us

Disclosures & Policies

              © Copyright 2015-2026 Jane Street Group, LLC. All rights reserved. Services are provided in the U.S. by Jane Street Capital, LLC and Jane Street Execution Services, LLC, each of which is a SEC-registered broker dealer and member of FINRA (www.finra.org). Regulated activities are undertaken in Europe by Jane Street Financial Limited, an investment firm authorized and regulated by the U.K. Financial Conduct Authority, and Jane Street Netherlands B.V., an investment firm authorized and regulated by the Netherlands Authority for the Financial Markets (Autoriteit Financiële Markten), and in Hong Kong by Jane Street Hong Kong Limited, a regulated entity under the Hong Kong Securities and Futures Commission (CE No. BAL548). Each of these entities is a wholly owned subsidiary of Jane Street Group, LLC. This material is provided for informational purposes only and does not constitute an offer or solicitation for the purchase or sale of any security or other financial instrument. | Jane Street and the concentric circle mark are registered trademarks of Jane Street.

                Privacy

                Cookies

    Jane Street Group, LLC uses cookies and similar technologies, including third-party cookies, on this Site to provide basic functionalities and perform analytics. You may accept or decline cookies by selecting “Accept” or “Reject”. For information regarding our cookie practices, see Jane Street’s
    Ad and Cookie Policy.

    Accept All
    Reject All