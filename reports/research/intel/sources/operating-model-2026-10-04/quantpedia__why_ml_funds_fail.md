source: https://quantpedia.com/why-machine-learning-funds-fail/
fetched_utc: 2026-10-04T18:37:51Z

Why Machine Learning Funds Fail | QuantPedia

PricingProductHow it worksAboutBlogResourcesConsultingAwards        

                Sign Up

                Log In

Why Machine Learning Funds Fail

15.September 2017

	An interesting insight into problems associated with an attempts to implement machine learning in trading: 

	Authors: de Prado

	Title: The 7 Reasons Most Machine Learning Funds Fail

	Link: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3031282

	Abstract:

	The rate of failure in quantitative finance is high, and particularly so in financial machine learning. The few managers who succeed amass a large amount of assets, and deliver consistently exceptional performance to their investors. However, that is a rare outcome, for reasons that will become apparent in this presentation. Over the past two decades, I have seen many faces come and go, firms started and shut down. In my experience, there are 7 critical mistakes underlying most of those failures.

	Notable quotations from the academic research paper:

	"

	• Over the past 20 years, I have seen many new faces arrive to the financial industry, only to leave shortly after.

	• The rate of failure is particularly high in machine learning (ML).

	• In my experience, the reasons boil down to 7 common errors:

	1. The Sisyphus paradigm

	2. Integer differentiation

	3. Inefficient sampling

	4. Wrong labeling

	5. Weighting of non-IID samples

	6. Cross-validation leakage

	7. Backtest overfitting

	Pitfall #1:

	The complexities involved in developing a true investment strategy are overwhelming.  Even if the firm provides you with shared services in those areas, you are like a worker at a BMW factory who has been asked to build the entire car alone, by using all the workshops around you. It takes almost as much effort to produce one true investment strategy as to produce a hundred. Every successful quantitative firm I am aware of applies the meta-strategy paradigm. Your firm must set up a research factory where tasks of the assembly line are clearly divided into subtasks, where quality is independently measured and monitored for each subtask, where the role of each quant is to specialize in a particular subtask, to become the best there is at it, while having a holistic view of the entire process.

	Pitfall #2:

	In order to perform inferential analyses, researchers need to work with invariant processes, such as returns on prices (or changes in log-prices), changes in yield, changes in volatility. These operations make the series stationary, at the expense of removing all memory from the original series. Memory is the basis for the model’s predictive power. The dilemma is returns are stationary however memory-less; and prices have memory however they are non-stationary.

	Pitfall #3:

	Information does not arrive to the market at a constant entropy rate. Sampling data in chronological intervals means that the informational content of the individual observations is far from constant. A better approach is to sample observations as a subordinated process of the amount of information exchanged: Trade bars. Volume bars. Dollar bars. Volatility or runs bars. Order imbalance bars. Entropy bars.

	Pitfall #4:

	Virtually all ML papers in finance label observations using the fixed-time horizon method. There are several reasons to avoid such labeling approach: Time bars do not exhibit good statistical properties and the same threshold   is applied regardless of the observed volatility. There are a couple of better alternatives, but even these improvements miss a key flaw of the fixed-time horizon method: the path followed by prices.

	Pitfall #5:

	Most non-financial ML researchers can assume that observations are drawn from IID processes. For example, you can obtain blood samples from a large number of patients, and measure their cholesterol. Of course, various underlying common factors will shift the mean and standard deviation of the cholesterol distribution, but the samples are still independent: There is one observation per subject. Suppose you take those blood samples, and someone in your laboratory spills blood from each tube to the following 9 tubes to their right. Now you need to determine the features predictive of high cholesterol (diet, exercise, age, etc.), without knowing for sure the cholesterol level of each patient. That is the equivalent challenge that we face in financial ML.

	–Labels are decided by outcomes.

	–Outcomes are decided over multiple observations.

	–Because labels overlap in time, we cannot be certain about what observed features caused an effect.

	Pitfall #6:

	One reason k-fold CV fails in finance is because observations cannot be assumed to be drawn from an IID process. Leakage takes place when the training set contains information that also appears in the testing set. In the presence of irrelevant features, leakage leads to false discoveries. One way to reduce leakage is to purge from the training set all observations whose labels overlapped in time with those labels included in the testing set. I call this process purging.

	Pitfall #7:

	Backtest overfitting due to data dredging. Solution – use The Deflated Sharpe Ratio – it computes the probability that the Sharpe Ratio (SR) is statistically significant, after controlling for the inflationary effect of multiple trials, data dredging, non-normal returns and shorter sample lengths.

	"

Are you looking for more strategies to read about? Sign up for our newsletter or visit our Blog or Screener.

Do you want to learn more about Quantpedia Premium service? Check how Quantpedia works, our mission and Premium pricing offer.

Do you want to learn more about Quantpedia Pro service? Check its description, watch videos, review reporting capabilities and visit our pricing offer.

Do you want algorithmic access to the full Quantpedia database via the API? Subscribe to Quantpedia Pro, ask for an API key, and explore the in/out-of-sample statistics, source academic papers, and code snippets — ideal for quantitative research, systematic trading workflows, and AI model training.

Are you looking for historical data or backtesting platforms? Check our list of Algo Trading Discounts.

Or follow us on:

Facebook Group, Facebook Page, Telegram, Twitter, Linkedin, Medium or Youtube
						Share onLinkedInTwitterFacebookRefer to a friend					                

Quantpedia is The Encyclopedia of Quantitative Trading Strategies
We’ve already analysed tens of thousands of financial research papers and identified more than 700 attractive trading systems together with hundreds of related academic papers.Browse Strategies

            Search for:            

Sign up for Quantpedia Newsletter! 

Get updates from our Blog via RSS Feed 

Check offered Algo Trading Discounts!

Blog Sponsor

Recent Posts

					A New Stage, a New Deadline: Quantpedia Awards 2027 Are Here Again!

					Quantpedia Premium Update – September 27th

					Can Weakening Morning Order Flow Predict SPY Reversals?

					Building and Testing Trend-Following Strategies on One-Minute SPY Data

					Do Airline Stocks Take Off Around U.S. Holidays?

Tags
alternative data
asset allocation
asset class picking
cryptocurrencies
diversification
equity long short
factor allocation
factor investing
machine learning
market timing
momentum
momentum in stocks
own-research
reversal
seasonality
smart beta
stock picking
trendfollowing
value
volatility effect

Partners

Links

Alpha Architect

Analyzing Alpha

Build Alpha

Disruption Banking

Dual Momentum

Genovest

Hispatrading

Matthew Smith

Meb Faber

Price Action Lab

Quant Connect

QuantInsti

Quantivity

QuantSavvy

Signal Plot

Spikeet

Trading System Lab

 Join our Facebook Group

                    Subscription Form

Subscribe for Newsletter
 Be first to know, when we publish new content

Select Your ProfessionRetail Trader / Individual InvestorWealth Manager / AdvisorStudent / AcademicsQuant / Trader / Portfolio Manager

I agree that Quantpedia may process my personal information in accordance with Quantpedia Privacy Policy
Subscribe

The Encyclopedia of Quantitative Trading Strategies

Product

Pricing
Screener
Charts
Consulting
Quantpedia Awards            

About us

About us
How it works
Clients & References
FAQ
Blog            

Support

Contact
Privacy Policy
Terms of Service
Affiliate
Links & Tools            

Follow us

                Risk Disclosure: Futures and forex trading contains substantial risk and is not for every investor. An investor could potentially lose all or more than the initial investment. Risk capital is money that can be lost without jeopardizing ones’ financial security or life style. Only risk capital should be used for trading and only those with sufficient risk capital should consider trading. Past performance is not necessarily indicative of future results.

                Hypothetical Performance Disclosure: Hypothetical performance results have many inherent limitations, some of which are described below. No representation is being made that any account will or is likely to achieve profits or losses similar to those shown; in fact, there are frequently sharp differences between hypothetical performance results and the actual results subsequently achieved by any particular trading program. One of the limitations of hypothetical performance results is that they are generally prepared with the benefit of hindsight. In addition, hypothetical trading does not involve financial risk, and no hypothetical trading record can completely account for the impact of financial risk of actual trading. for example, the ability to withstand losses or to adhere to a particular trading program in spite of trading losses are material points which can also adversely affect actual trading results. There are numerous other factors related to the markets in general or to the implementation of any specific trading program which cannot be fully accounted for in the preparation of hypothetical performance results and all which can adversely affect trading results.

                Testimonial Disclosure:  Testimonials appearing on this website may not be representative of other clients or customers and is not a guarantee of future performance or success.

                © 2026 Quantpedia.com. All rights reserved.

                            The Encyclopedia of Quantitative Trading Strategies

                        ×

Log in

           Remember Me

      Forgot Password

Sign-up for free to continue

You’ve reached your limit for viewing up to 5 strategies for free

                        Upgrade your subscription

                        By signing up you agree with our  terms & conditions 

                        Do you have an acount?  Login here. 

                    Close ×

After free sign-up you’ll be able to browse all free strategies in our library for free

We are using cookies to give you the best experience on our website. To learn more, see our Privacy Policy.

			Accept

			Close GDPR Cookie Settings

	Privacy Overview

		Strictly Necessary Cookies

			Powered by  GDPR Cookie Compliance

		Privacy Overview

This website uses cookies so that we can provide you with the best user experience possible. Cookie information is stored in your browser and performs functions such as recognising you when you return to our website and helping our team to understand which sections of the website you find most interesting and useful.

    Strictly Necessary Cookies

Strictly Necessary Cookie should be enabled at all times so that we can save your preferences for cookie settings.

              Enable or Disable Cookies        

                  Enabled
                  Disabled

						Enable All
								Save Settings