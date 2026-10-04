# man__ai-agents-trend
URL: https://www.man.com/insights/ai-agents-trend
Fetched: 2026-10-04 18:18 UTC (text only, tags stripped)

A Trend Following Deep Dive: AI, Agents and Trend | Man Group

 ETFs & Funds

 ETFs & Funds

 ETFs

 Document centre

 Capabilities

 Investment capabilities

 Asset classes

 Client solutions

 Investment themes

 Strategies in focus

 Alternatives

 Credit

 Equities

 Multi-asset

 Insurance

 Solutions

 Responsible investment

 Trend-following

 Insights

 Insights

 Insights hub

 Global outlook

 Technology

 About us

 About us

 About Man

 Careers

 Diversity, equity & inclusion

 Corporate sustainability

 Media

 News center

 Contact us

 Get in touch

 Search Man Group

 ETFs & Funds

 Capabilities

 Insights

 Technology

 About us

 ETFs & Funds

 ETFs

 Document centre

 Capabilities

 Asset classes

 Alternatives

 Credit

 Equities

 Multi-asset

 Client solutions

 Insurance

 Solutions

 Investment themes

 Responsible investment

 Trend-following

 Strategies in focus

 Insights

 Insights hub

 Global outlook

 About us

 About Man

 Careers

 Diversity, equity & inclusion

 Corporate sustainability

 News center

 Get in touch

 United States

 Public

 Contact

 Careers

 News center

 Shareholders

 Shareholder relations

 Results centre

 AGM

 Dividends

 Corporate Governance

 Login

Thank you for subscribing to Man Insights!

Please check your email to confirm your subscription.

 Back

View investments and research available in your location

Confirm your region
 Americas

 Confirm your region

 Americas 

Confirm your country
 United States

Confirm your country
 United States

Select your role
 Institutional InvestorFinancial Professional

 Select your role

 Institutional Investor

I consult or invest on behalf of a financial institution.

 Financial Professional

I manage investments on behalf of my clients.

 Remember my choice

Decline

 If your country is not listed, visit our global website to learn more about Man Group 

You are now leaving Man Group’s website

You are leaving Man Group’s website and entering a third-party website that is not controlled, maintained, or monitored by Man Group. Man Group is not responsible for the content or availability of the third-party website. By leaving Man Group’s website, you will be subject to the third-party website’s terms, policies and/or notices, including those related to privacy and security, as applicable.

 Continue to third-party site

 Cancel

You are now leaving Man Group’s website

You are leaving Man Group’s website and entering a third-party website that is not controlled, maintained, or monitored by Man Group. Man Group is not responsible for the content or availability of the third-party website. By leaving Man Group’s website, you will be subject to the third-party website’s terms, policies and/or notices, including those related to privacy and security, as applicable.

 Continue to third-party site

 Cancel

You are now leaving Man Group’s website

You are leaving Man Group’s website and entering a third-party website that is not controlled, maintained, or monitored by Man Group. Man Group is not responsible for the content or availability of the third-party website. By leaving Man Group’s website, you will be subject to the third-party website’s terms, policies and/or notices, including those related to privacy and security, as applicable.

 Continue to third-party site

 Cancel

You are now leaving Man Group’s website

Stai per uscire dal sito web di Man Group in lingua italiana. Proseguendo, accederai ai contenuti disponibili sul sito web di Man Group in lingua inglese per gli utenti in Italia.

 Continue to third-party site

 Cancel

Can agentic AI help to accelerate trend-following strategy design?

Key takeaways:

Off-the-shelf large language models have several limitations that reduce their utility for quantitative researchers

Enter the Alpha Assistant, an agentic AI model, that bridges the gap between generic LLM responses and fully integrated, actionable research output

We demonstrate how this technology can be effectively employed to accelerate research on trend-following strategy design

Introduction

Since ChatGPT burst onto the scene in November 2022, AI has rapidly advanced beyond simple conversational interfaces toward autonomous “agentic AI”. While off-the-shelf large language models (LLMs) lack the contextual awareness and environmental integration needed to execute research tasks effectively, agentic AI systems can function as autonomous toolkits that bridge this gap. These systems can access proprietary data, write code using internal libraries, and run specialised analytical tools through natural language instructions. These advancements represent a significant opportunity to accelerate quantitative research.

In the first in a two-part series exploring the application of agentic AI to trend-following strategy design, we introduce the 'Alpha Assistant', an integrated AI-powered coding agent that helps researchers conduct proprietary quantitative analysis. We first outline what a baseline output from an off-the-shelf LLM looks like when instructed to write code for a trend strategy. We go on to demonstrate how agentic AI enables the transition from this generic and plausible – but ultimately inactionable – script to a fully integrated, actionable trend-following research output.

The limitations of off-the-shelf LLMs in quant research

Let’s first establish a baseline: how far can a standalone LLM get without access to proprietary context or tools?

In Figure 1a, we ask an off-the-shelf LLM to write code for a trend strategy. To note, we added a generic system prompt to establish behaviour, tone and scope, specifying, “you’ll often be asked questions about finance, markets or economics. Answer these in detail and with precision, as if you are a seasoned financial analyst.”

Figure 1a: Input to a standard off-the-shelf LLM (Anthropic’s Claude 4.0 Sonnet)

The output, shown in Figure 1b, and produced using publicly available information only, is a conceptually plausible, runnable snippet – typically on synthetic data – that a researcher could paste into a Python console and point at a local price series.

While the output generated by the LLM may appear sophisticated to a casual observer, closer examination reveals numerous shortcomings rendering it unsuitable. It is, by design, unaware of internal portfolio construction and simulation methods, as well as the code required to use them. It also fails to pull in proprietary data sources, requiring the researcher to manually input this information.

Furthermore, the output fails to adhere to standard best practice for research, such as in-sample/out-of-sample testing protocols and accurate signal normalisation, as well as refined internal models for essential components like volatility estimation and turnover reduction. In addition, it has no knowledge of the firm's specific execution assumptions, including trading costs and slippage models, which are essential for realistic backtesting.

 Figure 1b: Output of a standard off-the-shelf LLM (Anthropic’s Claude 4.0 Sonnet)

 Click to expand

Source: Man Group.

The LLM, acting in isolation, cannot validate signals against our performance criteria, debug code within our specific research environment, or generate the standardised analytics and reports required for evaluation. In short, the resulting output, while demonstrating a basic understanding of the request, is inactionable without significant manual re-engineering. It is precisely this gap – between a generic, plausible script and a fully integrated, actionable research output – that agentic systems are designed to bridge.

Enter the Alpha Assistant: An agentic approach

A quantitative researcher’s workflow is inherently iterative, cycling through three distinct phases: ideation (“what analysis should be performed?”), implementation (“write and debug the code”), and evaluation (“what do the results imply?”). While all three phases are critical, implementation often represents the largest time investment. The tailored Alpha Assistant, an AI agent hosted on a central architecture, can help to reduce this bottleneck. The researcher defines the analytical objective in natural language, and the Assistant handles the implementation, delivering results for evaluation. This enables human researchers to focus on evaluating output and formulating subsequent hypotheses.

Design of an agentic AI

At its core, the Alpha Assistant is a primary 'orchestrator' or 'chief brain' agent, which operates with system prompts containing core principles, conventions, and general context that researchers utilise daily. It maintains awareness of the internal proprietary code base, has access to modular tools, and is designed to orchestrate complex analytical tasks from natural language prompts (Figure 2). This central agent is supported by a collection of specialised tools (ranging from deterministic code functions to sub-agents, which are separate LLMs with specialised prompts), and can select the optimal tool for each specific sub-task.

The agent's knowledge comes from its system prompt, which typically extends to:

General behavioural and stylistic guidelines

Firm-specific terminology (e.g., market, predictor, strategy, market weight)

Protocols for accessing market data libraries

Definitions of core functions and time series objects

Specifications for key analytical components (e.g., exponentially weighted moving average, volatility, momentum)

Configuration details for proprietary strategy frameworks

General best practices regarding missing data handling, lookahead bias, and data resampling

A set of negative constraints specifying actions the agent must avoid

Figure 2: Schematic illustration of an AI assistant setup. Agentic setup with tools, sub-agents, and complex system prompts to embed knowledge and allow actions to be taken

Source: Man Group.

From prompt to execution

The quality of the Alpha Assistant's output is directly related to the quality of the input brief. Think of the prompt as detailed instructions given to a new analyst. For example, a well-defined prompt specifies the exact signals to be tested (e.g., one-month, three-months, 12-months return momentum using an existing function called 'backreturn'), any additional parameters (50-day volatility scaling, ±2 signal cap), the investment universe, the simulation framework, and the backtesting period. It should also clearly articulate the required outputs, such as account curves, summary statistics, and correlation matrices, and their desired format. Failure to provide this specificity might result in an answer which looks sensible, but which misses a fundamental concept, a typical manifestation of hallucination.

Figure 3. Example of an AI Assistant output (input prompt)

Source: Man Group. P1 = internal price data library, pweights = internal market weights.

In response to the input brief, the Assistant initiates a 'thinking' phase. As shown in Figure 4, it restates the objective, extracts the requirements, flags constraints, and identifies the necessary internal components. This 'thinking' phase then generates a structured list of tasks. A typical plan involves loading the market set and weights, fetching and aligning price data, constructing the specified signals, running the backtest simulation, and generating the requested analytics before compiling the final report. Each step explicitly declares the tool to be called and the expected output, incorporating safeguards to ensure data integrity and prevent lookahead bias. This plan is presented to the user for approval before execution.

Figure 4. Example of the 'thinking' and 'planning' phases

Think tool: for reasoning

To do list tool: for planning

Source: Man Group. P1 = internal price data library, pweights = internal market weights.

The Alpha Assistant possesses knowledge of internal systems and capabilities, enabling it to default to proprietary libraries over generic ones, and to both write and execute firm-specific code snippets in its output, as shown in Figure 5.

Figure 5. Example of AI Assistant’s utilisation of internal capabilities

Search AHL components tool: Search over extensive AHL documentation code

Run Python tool: Tailored to the researcher's proprietary environment

Source: Man Group. P1 = internal price data library, pweights = internal market weights.

The result, shown below, is a clearly presented report comparing three momentum strategies suggested by the user, containing methods, metrics, and visualisations, all tailored to the initial specifications without requiring any manual coding.

Figure 6. Example of report produced by the AI Assistant

Source: Man Group.

Challenges remain

Clearly, the Alpha Assistant’s capabilities are impressive and benefit quantitative research, but it is not without limitations. The Assistant cannot be entrusted with end-to-end research projects requiring deep thinking, creative hypothesis generation and nuanced analysis. This limitation stems from two constraints inherent to current LLM architectures.

First, there is a critical trade-off between scope and precision. While one might assume that loading the Assistant with every internal document and tool would improve results, this approach ultimately leads to 'attention dilution' – the model's ability to focus on relevant details degrades as context expands. Counterintuitively, providing excessive information can be as problematic as providing too little, causing the Assistant to overlook crucial specifications or fail to apply appropriate methodologies.

Second, LLMs have a fixed 'attention span': there is a limit to the number of tokens they spend reasoning about any given query. For complex research projects, where the amount of thinking requires hours, days, or even weeks of work, additional frameworks need to be added to enable LLMs to operate effectively over longer, more difficult problems.

Conclusion: Should we replace our research teams with the Alpha Assistant? Not yet.

The Alpha Assistant is by no means a replacement for the human researcher; it is not designed to generate novel ideas. Rather, it is an effective tool for research acceleration, acting as a coding assistant with knowledge of how to conduct quantitative research within the firm’s ecosystem. As we have shown, it can execute complex tasks and produce relevant, precise analysis, freeing researchers to focus on ideation and evaluation. Even so, there are areas where this technology still falls short, not least the trade-off between scope and precision and LLMs’ fixed 'attention span'.

Is there a better approach to overcome current model limitations? Possibly. We'll explore this challenge – and potential solutions – in the second part of this series.

This paper was authored by Martin Luk (Senior Quant Researcher, Man AHL), Tarek Abou Zeid (Partner and Head of Client Portfolio Management, Man AHL), and Otto van Hemert (Senior Advisor, Man Group).

For further clarification on the terms which appear here, please visit our Glossary page.

Author(s)

 Martin Luk 
 Head of Applied AI, Systematic, Man Group

 Tarek Abou Zeid 
 Partner and Head of Client Portfolio Management, Systematic, Man Group

 Trend Following

 Discover it

You might be interested in...

 Article

 14 min

 Sep 2025

 A Trend Following Deep Dive: The Dynamics of Dispersion

 What drives performance dispersion among trend followers?

 Related insights

 Video

 5 min

 Sep 2026

 Why Now for Quantitative Investing?

 The growth of alternative data and advanced data science techniques within Emerging Markets provides fertile ground for quantitative approaches.

 Article

 6 min

 Aug 2026

 Why Trend Following Seems the Obvious Choice in Uncertain Times

 Beta and alpha. Why settle for one when you can have both?

 Article

 17 min

 Aug 2026

 Portable Alpha: Ask the Hard Questions

 Five questions to ask when allocating to portable alpha.

 View all

 Important information
 Important information

This information is communicated and/or distributed by the relevant Man entity identified below (collectively the "Company") subject to the following conditions and restriction in their respective jurisdictions.

Opinions expressed are those of the author and may not be shared by all personnel of Man Group plc (‘Man’). These opinions are subject to change without notice, are for information purposes only and do not constitute an offer or invitation to make an investment in any financial instrument or in any product to which the Company and/or its affiliates provides investment advisory or any other financial services. Any organisations, financial instrument or products described in this material are mentioned for reference purposes only which should not be considered a recommendation for their purchase or sale. Neither the Company nor the authors shall be liable to any person for any action taken on the basis of the information provided. Some statements contained in this material concerning goals, strategies, outlook or other non-historical matters may be forward-looking statements and are based on current indicators and expectations. These forward-looking statements speak only as of the date on which they are made, and the Company undertakes no obligation to update or revise any forward-looking statements. These forward-looking statements are subject to risks and uncertainties that may cause actual results to differ materially from those contained in the statements. The Company and/or its affiliates may or may not have a position in any financial instrument mentioned and may or may not be actively trading in any such securities. Unless stated otherwise all information is provided by the Company. Past performance is not indicative of future results. The value of an investment and any income derived from it can go down as well as up and investors may not get back their original amount invested. Alternative investments can involve significant additional risks.

Unless stated otherwise this information is communicated by the relevant entity listed below.

United States: To the extent this material is distributed in the United States, it is communicated and distributed by Man Investments, Inc. (‘Man Investments’). Man Investments is registered as a broker-dealer with the SEC and is a member of the Financial Industry Regulatory Authority (‘FINRA’). Man Investments is also a member of the Securities Investor Protection Corporation (‘SIPC’). Man Investments is a wholly owned subsidiary of Man Group plc. The registration and memberships described above in no way imply a certain level of skill or expertise or that the SEC, FINRA or the SIPC have endorsed Man Investments. Man Investments Inc, 1345 Avenue of the Americas, 21st Floor, New York, NY 10105.

This material is proprietary information and may not be reproduced or otherwise disseminated in whole or in part without prior written consent. Any data services and information available from public sources used in the creation of this material are believed to be reliable. However accuracy is not warranted or guaranteed. © Man 2026

User Country: United States (237)

User Language: 

User Role: Public (Guest) (1)

 User Access Groups:

Global All (1)

North America All (3)

Global Non Employees (64)

All Unauthenticated Users (68)

North America Unauthenticated (87)

Global (ex AU) (121)

Global (ex Individuals) (123)

Global ex EEA, CH & UK (165)

Global All (ex UK) (232)

Global All (ex HK) (239)

Rest of the World All (ex CH) (241)

United States All (248)

United States Public (250)

North America (Unauth.) - Man.com only (254)

Global (ex. Individuals, Retail) (272)

North America Public (275)

Wealth Insights (Public & Fin. prof) (300)

Institutional Insights (Employees & Public & Insti) (301)

Node Access Groups: 1