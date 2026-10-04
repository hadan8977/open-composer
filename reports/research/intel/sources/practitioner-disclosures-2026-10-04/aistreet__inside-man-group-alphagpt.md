# aistreet__inside-man-group-alphagpt
URL: https://aistreet.beehiiv.com/p/inside-man-group-s-alphagpt
Fetched: 2026-10-04 18:18 UTC (text only, tags stripped)

Inside Man Group’s AlphaGPT: Building AI for Systematic Investing

This website uses cookies
Read our Privacy policy and Terms of use for more information.
AcceptCustomizeDecline

Interviews 
Inside Man Group’s AlphaGPT 

Matt Robinson

Dec 18, 2025
•
8 min read

INTERVIEW

Inside Man Group’s AlphaGPT 

Ziang Fang, senior portfolio manager at Man Numeric, on building AI for systematic investing

Man Group has built an internal AI system that generates trade ideas and subjects them to the same internal review as human research.

The system, AlphaGPT, proposes signals, writes the code, and runs backtests before any human sees the output. Only after that does it enter Man Numeric’s standard research and investment committee process.

The $214 billion hedge fund says the edge is speed and scale. AlphaGPT can produce viable research concepts in minutes rather than days, allowing researchers to evaluate far more investing ideas than would be feasible with a human-only process. 

I spoke with Ziang Fang, Senior Portfolio Manager at Man Numeric, about his recent article detailing AlphaGPT’s architecture, how Man controls for lookahead bias and data mining, and the limits of AI in systematic research.

This interview has been edited for clarity and length.

Q: What has been the reaction to the AlphaGPT article?

A: I think it’s been very well received. The article on Man Institute, What AI Can (and Can't Yet) Do for Alpha, is one of the most read pieces we’ve published recently. At the same time, especially among our client base, larger organizations and allocators are thinking hard about how to adopt AI in their daily workflows.

A lot of people have been using AI as a chatbot for different things. But using it systematically, automating it, and applying it end-to-end is different. Many are interested in how we’ve built the process and how we bring it up to standard for delivering products and research outcomes.

Q: How did Man Group’s AI adoption evolve?

A: We did a really good job making AI accessible to everyone. Once ChatGPT became available, Man Group quickly rolled it out broadly. Once people had access, they started experimenting.

Suddenly, it felt new. You could bounce ideas off it or use it to prototype code. Before, you’d have to search online and dig through posts, which was slow. Now you put your idea in and get a prototype, even if it doesn’t work perfectly.

Last year, we started thinking about bringing everything together. If AI was already used across the research process, why not think about an end-to-end, integrated adoption?

Q: Why does the reasoning model matter for quantitative research?

A: Quant researchers want to show something that works, at least on paper. But you need a lot of vetting to understand the research process versus the final backtest. What matters is whether it works in live trading, not whether it looks good on paper.

The reasoning model gives us full transparency. At every step, when an agent makes a decision, it logs why it made that choice. That level of visibility is something you don’t always get from a human-driven process.

Q: What challenges did you encounter building this system?

A: Along the way we ran into a lot of issues—hallucination, lookahead bias, multiple testing, and many other things. One exciting part about AI is that as humans, we take a lot for granted in our daily work. Now we have to step back and reevaluate everything. You ask, why do we do things this way? It created another opportunity for internal debate about what the right approach actually is.

One interesting thing is that because the language model isn't part of the group, it doesn't develop the same blind spots. When you work alongside            colleagues, you eventually start thinking alike. The model learns from us but doesn't sit next to us, so it can surface angles we might have missed.

Q: How does AI help with both volume and quality of ideas?

A: There’s been an explosion in data availability. No one can realistically go through thousands of alternative datasets, many of which are unstructured.

Previously, a researcher had to manually figure out how to handle all the alternative datasets, which took a long time and many steps are repetitive. LLM-based agentic workflow provides an opportunity to automate those tasks and help systematic teams to process information at much higher volume.

On quality of idea generation, think about a “researcher” that has effectively read every paper, article, and public code base. You’d want to hire that person immediately. But in reality, that person wouldn’t understand your institutional environment or what good quant research looks like. That’s where AlphaGPT comes in. It combines the raw capability of language models with our institutional context to ensure high quality idea generation.

Q: How do AI-generated ideas compare to human research?

A: We tested this by having the model redo research on datasets we already analyzed. It’s much faster, and it also surfaced ideas we hadn’t considered, which is great.

If you didn’t know whether a signal came from AI or a human, you probably couldn’t tell. The main difference is formatting. The AI output is more consistent.

That said, a lot of nuanced research still requires deep market understanding, judgment, and intuition. We’re not at the point where models can fully replace that.

Q: How does the human oversight process work for AI-generated signals?

A: Our view is that AI isn’t a silver bullet, especially in noisy financial markets. Every idea must be hypothesis-driven, with a clear economic rationale. Once you start backtesting, you can’t change the hypothesis without risking data mining.

AI follows the same rules. It has to state its hypothesis, explain why it makes sense, and stick to it. Flipping a signal after seeing results isn’t allowed for humans or AI.

Humans stay in the loop throughout. We review every step, and developers inspect the code line by line before implementation.

Q: What happens after a signal is approved?

A: If the signal passes all evaluation thresholds from the investment committee, it goes into live trading. Then there's a whole suite of monitoring tools comparing live performance to research results and tracking expected decay.

Q: What are the resource constraints and costs involved?

A: In the past, a limited number of researchers ran signals. Now you potentially need massive internal computation. Existing tools weren’t built for that scale.

Token costs from model APIs add up quickly. We intentionally embed a lot of institutional context, which increases usage. The bills are large, and remain a core considerations for us to continue improving our infrastructure and agentic workflows.

Q: How do you manage costs?

A: We built dashboards specifically to monitor the cost of doing research. Our tech stack was rebuilt relatively recently—less than ten years ago, everything in Python—which has been a big enabler. But even that infrastructure needs to be improved for AI agents running at this scale.

Q: Is AlphaGPT built at the application layer or does it involve training custom models?

A: It’s built at the application layer. We haven’t hit the limits of frontier models yet. Some tasks may eventually require fine-tuning or custom models, but the base models keep improving. It’s an ongoing discussion.

Q: How do you see AI changing the nature of work going forward?

A: Knowing how to ask the right questions, think critically, and choose the right framework matters more than pure implementation.

As automation increases, mechanical work becomes less valuable. The real advantage is in learning faster, connecting ideas, and thinking at a higher level. People who adopt AI well are learning at a pace that wasn’t possible before.

Q: What has been the biggest surprise?

A: That we’re even able to do this today. We’re probably underestimating how much this technology will change our lives in systematic research.

Reply

Login or Subscribe to participate

Keep ReadingView more

AI Street
How Wall Street Uses AI | Read at JPMorgan, BlackRock, Citadel and more

Subscribe

I consent to receive newsletters via email. Terms of use and Privacy policy.

© 2026 AI Street Media.
Powered by beehiiv

0