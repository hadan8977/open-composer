# signalsandthreads__episode-index
URL: https://signalsandthreads.com/
Fetched: 2026-10-04 18:23 UTC (text only, tags stripped)

Signals and Threads

 All Episodes

Listen in on Jane Street’s Ron Minsky as he has conversations with engineers working on everything from clock synchronization to reliable multicast, build systems to reconfigurable hardware. Get a peek at how Jane Street approaches problems, and how those ideas relate to tech more broadly.

Listen and subscribe:

 Hardware

 Machine Learning

 Performance

 Programming Languages

 Systems Design

 Trading and Research

 UI/UX

 Ways of Working

Learning Goals and the Goals of Learning: Teaching in the Age of AI

with Aaron Bauer

 Episode 30   |  

 September 23rd, 2026

 Ways of Working

 UI/UX

 Programming Languages

Aaron Bauer is a software engineer and one of Jane Street’s few developer educators—a role
that splits his time between writing code and teaching other people how to write it.
Before joining the firm, he taught computer science at Carleton College, including four
straight terms online during the pandemic. In this episode, Ron and Aaron discuss what it
takes to teach engineering inside a company with its own language, its own version
control, and its own editors, and what changes when an LLM can do the exercise for you.
Along the way, they consider the underrated power of a live lecture; why the text editor
is still the software engineer’s home base; using editor telemetry to find out how AI is
actually changing developer workflows; and how Jane Street rebuilt its intern curriculum
around testing, design, and code review now that producing the code is the easy part.

 Go to Episode Page

Wrestling the World into Rows

with Eric Mannes

 Episode 29   |  

 September 2nd, 2026

 Machine Learning

 Systems Design

“Alternative data” is Wall Street’s name for information that comes from non-traditional
sources: satellite photos of parking lots, credit card panels, weather forecasts. Eric Mannes
has spent over a decade at Jane Street, first as a commodities trader and now helping lead
the firm’s alternative data team. In this episode, Eric and Ron talk about what it takes
to turn messy external data into datasets a trading strategy can rely on. Along the way,
they cover the day oil futures settled at a negative price and the systems that broke as a
result; the years when the commodities desk’s risk system was one very large Excel
spreadsheet; the hard question of what a company even is; and why better ML models raise
the value of careful data engineering.

 Go to Episode Page

Building a Data Warehouse from Scratch

with Jacob Baskin

 Episode 28   |  

 June 24th, 2026

 Systems Design

 Performance

 Machine Learning

In university Jacob Baskin studied at the intersection of computer science and economics,
thinking about systems that incentivize people to express their true preferences. He put
those ideas into practice at Google, where he worked on ad serving, before joining Jane
Street’s database infrastructure team. In this episode, Ron and Jacob discuss Superstore,
a distributed columnar database now central to Jane Street’s tech stack that Jacob began
building practically the day he started. How do you support wide-ranging analytical
queries while transactional writes stream in at the speed of trading systems? And what’s
it like when your first design doc leads to an eight-figure hardware purchase? After
building Superstore Jacob has since gone back to his roots, thinking about schemes for
bidding on compute time as he works to optimize usage of the Hive, Jane Street’s massive
compute cluster for research.

 Go to Episode Page

The Network as a Program

with Nate Foster

 Episode 27   |  

 June 1st, 2026

 Hardware

 Programming Languages

 Systems Design

Nate Foster is a professor at EPFL in Switzerland in the Networked Systems Abstractions
Lab, and a visiting researcher at Jane Street on the Networking team. In this episode, he
and Ron consider what happens when you bring a software mindset to network
engineering. Can you use programming language theory and formal methods to realize the
dream of software-defined networks? Along the way, they discuss how hyperscalers have
shaped networking hardware; the return (or not) of multicast; the ways ML workloads are
reshaping the networking layer; and the success Jane Street has had using a foundational
Internet protocol, BGP, together with a more declarative high-level specification
language.

 Go to Episode Page

Why Testing is Hard and How to Fix it

with Will Wilson

 Episode 26   |  

 March 16th, 2026

 Ways of Working

 Systems Design

Will Wilson is the founder and CEO of Antithesis, which is trying to change how people
test software. The idea is that you run your application inside a special hypervisor
environment that intelligently (and deterministically) explores the program’s state space,
allowing you to pinpoint and replay the events leading to crashes, bugs, and violations of
invariants. In this episode, he and Ron take a broad view of testing, considering not just
“the unreasonable effectiveness of example-based tests” but also property-based testing,
fuzzing, chaos testing, type systems, and formal methods. How do you blend these
techniques to find the subtle, show-stopper bugs that will otherwise wake you up at 3am?
As Will has discovered, making testing less painful is actually a tour of some of computer
science’s most vexing and interesting problems.

 Go to Episode Page

Why ML Needs a New Programming Language

with Chris Lattner

 Episode 25   |  

 September 3rd, 2025

 Machine Learning

 Programming Languages

Chris Lattner is the creator of LLVM and led the development of the Swift language at
Apple. With Mojo, he’s taking another big swing: How do you make the process of getting
the full power out of modern GPUs productive and fun? In this episode, Ron and Chris
discuss how to design a language that’s easy to use while still providing the level of
control required to write state of the art kernels. A key idea is to ask programmers to
fully reckon with the details of the hardware, but making that work manageable and
shareable via a form of type-safe metaprogramming. The aim is to support both
specialization to the computation in question as well as to the hardware platform.
“Somebody has to do this work,” Chris says, “if we ever want to get to an ecosystem where
one vendor doesn’t control everything.”

 Go to Episode Page

The Thermodynamics of Trading

with Daniel Pontecorvo

 Episode 24   |  

 July 25th, 2025

 Ways of Working

 Hardware

Daniel Pontecorvo runs the “physical engineering” team at Jane Street. This group blends
architecture, mechanical engineering, electrical engineering, and construction management
to build functional physical spaces. In this episode, Ron and Dan go deep on the challenge
of heat exchange in a datacenter, especially in the face of increasingly dense power
demands—and the analogous problem of keeping traders cool at their desks. Along the way
they discuss the way ML is changing the physical constraints of computing; the benefits of
having physical engineering expertise in-house; the importance of monitoring; and whether
you really need Apollo-style CO2 scrubbers to ensure your office gets fresh air.

 Go to Episode Page

Building Tools for Traders

with Ian Henry

 Episode 23   |  

 May 28th, 2025

 Programming Languages

 Trading and Research

 UI/UX

Ian Henry started his career at Warby Parker and Trello, building consumer apps for
millions of users. Now he writes high-performance tools for a small set of experts on Jane
Street’s options desk. In this episode, Ron and Ian explore what it’s like writing code at
a company that has been “on its own parallel universe software adventure for the last
twenty years.” Along the way, they go on a tour of Ian’s whimsical and sophisticated side
projects—like Bauble, a playground for rendering trippy 3D shapes using signed distance
functions—that have gone on to inform his work: writing typesafe frontend code for users
who measure time in microseconds and prefer their UIs to be “six pixels high.”

 Go to Episode Page

Finding Signal in the Noise: Machine Learning and the Markets

with In Young Cho

 Episode 22   |  

 March 10th, 2025

 Machine Learning

 Trading and Research

In Young Cho thought she was going to be a doctor but fell into a trading internship at
Jane Street. Now she helps lead the research group’s efforts in machine learning. In this
episode, In Young and Ron touch on the porous boundaries between trading, research, and
software engineering, which require different sensibilities but are often blended in a
single person. They discuss the tension between flexible research tools and robust
production systems; the challenges of ML in a low-data, high-noise environment subject to
frequent regime changes; and the shift from simple linear models to deep neural networks.

 Go to Episode Page

The Uncertain Art of Accelerating ML Models

with Sylvain Gugger

 Episode 21   |  

 October 14th, 2024

 Machine Learning

 Performance

Sylvain Gugger is a former math teacher who fell into machine learning via a MOOC and
became an expert in the low-level performance details of neural networks. He’s now on the
ML-infra team at Jane Street, where he helps traders speed up their models. In this
episode, Sylvain and Ron go deep on learning rate schedules; the subtle performance bugs
PyTorch lets you write; how to keep a hungry GPU well-fed; and the importance of
reproducibility in training runs. They also discuss some of the unique challenges of doing
ML in the world of trading, like the unusual size and shape of market data and the need to
do inference at very low latencies.

 Go to Episode Page

Solving Puzzles in Production

with Liora Friedberg

 Episode 20   |  

 October 7th, 2024

 Ways of Working

Liora Friedberg is a Production Engineer at Jane Street with a background in economics and
computer science. In this episode, Liora and Ron discuss how production engineering blends
high-stakes puzzle solving with thoughtful software engineering, as the people doing
support build tools to make that support less necessary. They also discuss how Jane Street
uses both tabletop simulation and hands-on exercises to train Production Engineers; what
skills effective Production Engineers have in common; and how to create a culture where
people aren’t blamed for making costly mistakes.

 Go to Episode Page

From the Lab to the Trading Floor: Designing for Expert Users

with Erin Murphy

 Episode 19   |  

 July 10th, 2024

 Ways of Working

 UI/UX

Erin Murphy is a UX designer at Jane Street, and before that, she worked at NASA’s Jet
Propulsion Laboratory building user interfaces for space missions. She’s also an
illustrator with her own quarterly journal. In this episode, Erin and Ron discuss the
challenge of doing user-centered design in an organization where experts are used to
building tools for themselves. How do you bring a command-line interface to the web
without making it worse for power users? They also discuss how beauty in design is more
about utility than aesthetics; what Jane Street looks for in UX candidates; and how to
help engineers discover what their users really want.

 Go to Episode Page

Performance Engineering on Hard Mode

with Andrew Hunter

 Episode 18   |  

 November 28th, 2023

 Performance

Andrew Hunter likes making code go fast. Before joining Jane Street,
he worked for seven years at Google on multithreaded architecture, and
was a tech lead for tcmalloc, Google’s world-class scalable malloc
implementation. In this episode, Andrew and Ron discuss how,
paradoxically, in some ways it’s easier to optimize systems at
hyperscale because of the impact that even miniscule changes can
have. Finding performance wins in trading systems, which operate at a
smaller scale, but which have bursty, low-latency workloads, is often
trickier. Andrew explains how he approaches the problem, including his
favorite profiling techniques and visualization tools; the unique
challenges of optimizing OCaml versus C++; and when you should and
shouldn’t care about nanoseconds. They also touch on the joys of
musical theater, and how to pass an interview when you’re
sleep-deprived.

 Go to Episode Page

A Poet's Guide to Product Management

with Peter Bogart-Johnson

 Episode 17   |  

 August 14th, 2023

 Ways of Working

Peter Bogart-Johnson was one of Jane Street’s first program managers,
and helped bring the art of PMing—where that “P” variously stands for
“project,” “product,” or some blend of the two—to the company at
large. He’s also a poet and the former editor of a literary
magazine. In this episode, Peter and Ron discuss the challenge of
gaining trust as an outsider: how do you teach teams a new way of
doing things while preserving what’s already working? The key, Peter
says, is you listen; a good PM is an anthropologist. They also discuss
how paying down technical debt isn’t something you do instead of
serving customers; what Jane Street looks for in PM candidates; and
how to help teams coordinate in times of great change.

 Go to Episode Page

The Future of Programming

with Richard Eisenberg

 Episode 16   |  

 May 17th, 2023

 Programming Languages

Richard Eisenberg is one of the core maintainers of Haskell. He
recently joined Jane Street’s Tools and Compilers team, where he hacks
on the OCaml compiler. He and Ron discuss the powerful language
feature that got him into PL design in the first place—dependent
types—and its role in a world where AIs can (somewhat) competently
write your code for you. They also discuss the differences between
Haskell and OCaml; the perils of trying to make a language that works
for everybody; and how best a company like Jane Street can collaborate
with the open source community.

 Go to Episode Page

Swapping the Engine out of a Moving Race Car

with Ella Ehrlich

 Episode 15   |  

 September 12th, 2022

 Systems Design

Ella Ehrlich has been a developer at Jane Street for close to a
decade. During much of that time, she’s worked on Gord, one of Jane
Street’s oldest and most critical systems, which is responsible for
normalizing and distributing the firm’s trading data. Ella and Ron
talk about how to grow and modernize a legacy system without
compromising uptime, why game developers are the “musicians of
software,” and some of the work Jane Street has done to try to hire a
more diverse set of software engineers.

 Go to Episode Page

State Machine Replication, and Why You Should Care

with Doug Patti

 Episode 14   |  

 April 20th, 2022

 Systems Design

Doug Patti is a developer in Jane Street’s Client-Facing Tech team,
where he works on a system called Concord that undergirds Jane
Street’s client offerings. In this episode, Doug and Ron discuss how
Concord, which has state-machine replication as its core abstraction,
helps Jane Street achieve the reliability, scalability, and speed that
the client business demands. They’ll also discuss Doug’s involvement
in building a successor system called Aria, which is designed to deliver
those same benefits to a much wider audience.

 Go to Episode Page

Memory Management

with Stephen Dolan

 Episode 13   |  

 January 5th, 2022

 Programming Languages

 Performance

Stephen Dolan works on Jane Street’s Tools and Compilers team where he
focuses on the OCaml compiler. In this episode, Stephen and Ron take a
trip down memory lane, discussing how to manage computer memory
efficiently and safely. They consider trade-offs between reference
counting and garbage collection, the surprising gains achieved by
prefetching, and how new language features like local allocation and
unboxed types could give OCaml users more control over their memory.

 Go to Episode Page

What is an Operating System?

with Anil Madhavapeddy

 Episode 12   |  

 November 3rd, 2021

 Programming Languages

 Systems Design

Anil Madhavapeddy is an academic, author, engineer, entrepreneur, and
OCaml aficionado. In this episode, Anil and Ron consider the evolving
role of operating systems, security on the internet, and the pending
arrival (at last!) of OCaml 5.0. They also discuss using Raspberry Pis
to fight climate change; the programming inspiration found in British
pubs and on Moroccan beaches; and the time Anil went to a party, got
drunk, and woke up with a job working on the Mars Polar Lander.

 Go to Episode Page

Building a UI Framework

with Ty Overby

 Episode 11   |  

 October 6th, 2021

 UI/UX

 Systems Design

Ty Overby is a programmer in Jane Street’s web platform group where he
works on Bonsai, our OCaml library for building interactive
browser-based UIs. In this episode, Ty and Ron consider the functional
approach to building user interfaces. They also discuss Ty’s
programming roots in Neopets, what development features they crave on
the web, the unfairly maligned CSS, and why Excel is “arguably the
greatest programming language ever developed.”

 Go to Episode Page

Writing, Technically

with James Somers

 Episode 10   |  

 September 1st, 2021

 Ways of Working

James Somers is Jane Street’s writer-in-residence, splitting his time
between English and OCaml, and helping to push forward all sorts of
efforts around knowledge-sharing at Jane Street. In this episode,
James and Ron talk about the role of technical writing in an
organization like Jane Street, and how engineering software relates to
editing prose.

 Go to Episode Page

More Signals & Threads coming soon!

with Ron Minsky

 August 24th, 2021

Signals & Threads is back, and we have a fun season of topics lined
up. We hope you’ll join us! The first episode drops September 1st.

An inside look at Jane Street's tech internship

with Jeanne Van Briesen, Matt Else, and Grace Zhang

 Episode 9   |  

 November 4th, 2020

 Ways of Working

In this week's episode, the season 1 finale, Ron speaks with Jeanne, Matt, and Grace, three former tech interns at Jane Street who have returned as full-timers. They talk about the experience of being an intern at Jane Street, the types of projects that interns work on, and how they've found the transition to full-time work.

 Go to Episode Page

Building a functional email server

with Dominick LoBraico

 Episode 8   |  

 October 28th, 2020

 Systems Design

 Despite a steady stream of newcomers, email still reigns supreme as the chief communication mechanism for the Information Age. At Jane Street, it’s just as critical as anywhere, but there’s one difference: the system at the heart of our email infrastructure is homegrown. This week, Ron talks to Dominick LoBraico, an engineer working on Jane Street’s technology infrastructure, about how and why we built Mailcore, an email server written and configured in OCaml. They delve into questions around how best to represent the configuration of a complex system, when you should build your own and when you shouldn’t, and the benefits of bringing a code-focused approach to solving systems problems. 

 Go to Episode Page

Language Design

with Leo White

 Episode 7   |  

 October 21st, 2020

 Programming Languages

Equal parts science and art, programming language design is very much an unsolved problem. This week, Ron speaks with Leo White, from Jane Street's Tools & Compilers team, about cutting-edge language features, future work happening on OCaml, and Jane Street's relationship with the broader open-source community. The conversation covers everything from the paradox of language popularity, to advanced type system features like modular implicits and dependent types. Listen in, no programming languages PhD required!

 Go to Episode Page

Clock Synchronization

with Chris Perl

 Episode 6   |  

 October 14th, 2020

 Systems Design

Clock synchronization, keeping all of the clocks on your network set to the “correct” time, sounds straightforward: our smartphones sure don’t seem to have trouble with it. Next, keep them all accurate to within 100 microseconds, and prove that you did -- now things start to get tricky. In this episode, Ron talks with Chris Perl, a systems engineer at Jane Street about the fundamental difficulty of solving this problem at scale and how we solved it.

 Go to Episode Page

Python, OCaml, and Machine Learning

with Laurent Mazare

 Episode 5   |  

 October 7th, 2020

 Machine Learning

 Programming Languages

A conversation with Laurent Mazare about how your choice of programming language interacts with the kind of work you do, and in particular about the tradeoffs between Python and OCaml when doing machine learning and data analysis. Ron and Laurent discuss the tradeoffs between working in a text editor and a Jupyter Notebook, the importance of visualization and interactivity, how tools and practices vary between language ecosystems, and how language features like borrow-checking in Rust and ref-counting in Swift and Python can make machine learning easier. 

 Go to Episode Page

Compiler Optimization

with Greta Yorsh

 Episode 4   |  

 September 30th, 2020

 Programming Languages

 Performance

It’s a software engineer’s dream: A compiler that can take idiomatic high-level code and output maximally efficient instructions. Ron’s guest this week is Greta Yorsh, who has worked on just that problem in a career spanning both industry and academia. Ron and Greta talk about some of the tricks that compilers use to make our software faster, ranging from feedback-directed optimization and super-optimization to formal analysis.

 Go to Episode Page

Multicast and the Markets

with Brian Nigito

 Episode 3   |  

 September 23rd, 2020

 Trading and Research

 Performance

 Systems Design

Electronic exchanges like Nasdaq need to handle a staggering number of transactions every second. To keep up, they rely on two deceptively simple-sounding concepts: single-threaded programs and multicast networking. In this episode, Ron speaks with Brian Nigito, a 20-year industry veteran who helped build some of the earliest electronic exchanges, about the tradeoffs that led to the architecture we have today, and how modern exchanges use these straightforward building blocks to achieve blindingly fast performance at scale.

 Go to Episode Page

Build Systems

with Andrey Mokhov

 Episode 2   |  

 September 16th, 2020

 Systems Design

Most software engineers only think about their build system when it breaks; and yet, this often unloved piece of software forms the backbone of every serious project. This week, Ron has a conversation with Andrey Mokhov about build systems, from the venerable Make to Bazel and beyond. Andrey has a lot of experience in this field, including significant contributions to the replacement for the Glasgow Haskell Compiler’s Make-based system and Build Systems à la carte, a paper that untangles the complex ecosystem of existing build systems. Ron and Andrey muse on questions like why every language community seems to have its own purpose-built system and, closer to home, where Andrey and the rest of the build systems team at Jane Street are focusing their efforts.

 Go to Episode Page

Programmable Hardware

with Andy Ray

 Episode 1   |  

 September 9th, 2020

 Hardware

 The ever-widening availability of FPGAs has opened the door to solving a broad set of performance-critical problems in hardware. In this episode, Ron speaks with Andy Ray, who leads Jane Street’s hardware design team. Andy has a long career prior to Jane Street shipping hardware designs for things like modems and video codecs. That work led him to create Hardcaml, a domain-specific language for expressing hardware designs. Ron and Andy talk about the current state-of-the-art in hardware tooling, the economics of FPGAs, and how the process of designing hardware can be improved by applying lessons from software engineering. 
 Hardcaml itself is open-source software available on Github, along with a collection of associated libraries and tools. Andy has also given a talk on Hardcaml called OCaml All The Way Down, and has a post on Jane Street's blog about some of the testing techniques used with Hardcaml. 

 Go to Episode Page

Introducing Signals and Threads

with Ron Minsky

 September 2nd, 2020

TECH TALKS

Watch Tech Talks 

JANE STREET BLOG

Read The Blog 

JANE STREET TECH

Learn More 

JOIN OUR TEAM

Apply 

TECH TALKS

Watch Tech Talks 

TECH BLOG

Read The Tech Blog 

JANE STREET TECH

Learn More 

JOIN OUR TEAM

Apply 

© Copyright 2020- Jane Street Group, LLC. All rights reserved.

Jane Street and the concentric circle mark are registered trademarks of Jane Street.

 Ad and Cookie Policy
   |  
 Privacy Policy

Jane Street is an Equal Opportunity Employer