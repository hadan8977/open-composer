source: https://www.risk.net/2479713
fetched_utc: 2026-10-04T18:39:14Z
bytes_raw: 131378

Quant of the year: Jean-Philippe Bouchaud - Risk.net

    Skip to main content

Jean-Philippe Bouchaud: "It is really more of a physics approach, to let the data speak"

        By Risk.net staff

            @riskdotnet

25 Jan 2017

        Tweet

        Facebook

        LinkedIn

          Save this article

        Send to

        Print this page

Topics

          Awards

          Black-Scholes

          Modern portfolio theory

          Econophysics

          Correlation matrix

More

Less

Finance theory is full of appealing-looking shortcuts – unified theories such as the efficient market hypothesis and modern portfolio theory, or razzle-dazzle equations that will spit out a plausible number for a specific need. The problem is that when they don't work, there's not much to fall back on: it's not always clear why they haven't worked or how to fix them.
The alternative is to go the long way round. Jean-Philippe Bouchaud wins this year's award – chosen by authors and referees of Risk's technical papers – for doing exactly this.
"It is really more of a physics approach, to let the data speak," says Bouchaud. "Very often, many economic theories – such as the principle of efficient markets – seem to be more inspired by some kind of underlying political agenda than a strict understanding of what is going on in the markets. Similarly, a lot of models used in mathematical finance seem to be more driven by their convenience and the possibility to answer a question with a number, rather than taking the time and thinking about the problem."

This has not slowed Bouchaud down. The Paris-born physicist has authored more than 400 papers on physics and finance. He is also chairman and head of research at France's largest quantitative investment managers, Capital Fund Management (CFM) – a real-world anchor that helps him focus on the practical problems encountered by market participants.
His empirically motivated work is always relevant and influential; as it's shown from the multiple references to his publications
Ramon Verastegui, Societe Generale  
"His work is a mix of theory and empirical analysis, and much of it has strong appeal to practitioners," says Leif Andersen, the global co-head of the quantitative strategies group at Bank of America Merrill Lynch (BAML) in New York, who sees Bouchaud as a leading light in the so-called econophysics movement of the 1990s, which saw a surge in quants applying physics concepts and ideas to economics and finance.
"Jean-Philippe has successfully leveraged his expertise in disordered systems to make impressive strides in a large variety of problems in finance and economics," he adds.
Fellow researchers respect Bouchaud's work.
"He is very widely read and cited among practitioners," says Ramon Verastegui, a New York-based head of flow strategy and solutions for the Americas at Societe Generale. "His empirically motivated work is always relevant and influential; as it's shown from the multiple references to his publications."
Data, data, data
Because of his strong focus on empirical analysis, Bouchaud's work often collides with cherished financial concepts that are still taught at universities across the world. This is true for many of his papers published in Risk, including his most recent work, Cleaning correlation matrices, where Bouchaud, along with Joel Bun, a PhD student at Université Paris-Saclay at the Léonard de Vinci Pôle Universitaire, and Marc Potters, co-chief executive and head of research at CFM, present a way to estimate correlation matrices more accurately in portfolio optimisation – a problem many quants have struggled with for decades while applying Harry Markowitz's optimisation to large portfolios.
When portfolios have a large number of assets, one would need an extremely large dataset to reliably estimate the correlation matrix. For instance, for a portfolio tracking the S&P 500, the matrix would be of the dimension 500 by 500. This means years of data would be required to generate a reasonably accurate correlation matrix.
"Trading universes are humongous. So if you expand to moderately liquid stocks, it can go very quickly to 2,000 or 3,000. To measure the correlation matrix with a universe of 500 stocks you need, at the very least, 500 days," says Bouchaud.
Without the right number of data points, the estimated correlation matrix will be erroneous or noisy, which in turn can negatively impact portfolio optimisation.
Both Bouchaud and Potters spent nearly two decades looking at ways to solve this by applying random matrix theory, a field in which many consider them to be the leaders, but what Bouchaud calls the "miracle" solution only came after Olivier Ledoit and Sandrine Péché published a key mathematical result in 2011.
"As soon as we saw that paper it was clear there was a theoretical breakthrough there," says Bouchaud.
To get as close as possible to the true correlation matrix, or the one that is error-free, the quants first take the empirical correlation matrix of their portfolio, or the ‘noisy' one built using available data.
Both these matrices can be decomposed into characteristic entities called Eigen values and Eigen vectors. By keeping the direction the same for the Eigen vectors of the true correlation and empirical correlation matrices, one can still tweak the Eigen values.
Financially, these outliers are extremely important because they concern the large volatility moves in the market
Jean-Philippe Bouchaud
In their 2011 paper, Ledoit and Péché calculated a formula that gives the overlap between the Eigen vectors of the empirical matrix and the true correlation matrix. This ultimately unlocks the door to the Eigen values of the true correlation matrix, but the original maths was not exactly engineered for application in finance, so Bouchaud, Potters and Bun had to add their own tweaks to the model to be able to apply it, and also extended it to accommodate outliers.
"Financially, these outliers are extremely important because they concern the large volatility moves in the market," says Bouchaud.
Bouchaud and his co-authors tested the performance of their extension of the Ledoit-Péché method against four other commonly used methods, including the shrinkage technique, which tries to pull the extreme coefficients in the matrix towards more central values. The extension outperformed all, giving the lowest realised risk among all five methods considered. As a rule of thumb, one would require only twice the number of data points as there are assets to get a good correlation matrix with the extension.
Alex Lipton, a New York-based Connection Science and Engineering fellow at the Massachusetts Institute of Technology (MIT), admires the technique. "People have been thinking about how to clean this matrix for quite some time. This is a very important question and it has been solved with a very elegant and strong method resulting from a large body of literature developed in physics," he says.
Timely paper
Another recent paper that demonstrates Bouchaud's influence is Tail risk premiums versus pure alpha, published in April last year. He co-wrote the paper with Yves Lempérière and four other quants from CFM.
For many years, investors have assumed more volatile investment should yield more returns in the long run, thereby earning a higher premium for the risk taken. Bouchaud and his co-authors show this is not the case, revealing a strong relationship between the risk premium earned on an investment, and negative skewness – reflecting the asymmetry of the distribution of the underlying. The quants do this by analysing a large number of common trading strategies using a new definition for skewness they propose.
"This paper was very timely due to the compression of risk premia by recent monetary policies, and the surge of systematic strategies based on risk premia in past years. It is also very insightful, as it addresses the link between risk premia and skewness and discriminates between risk premia strategies and market anomalies," says Societe Generale's Verastegui.
The result helps identify strategies that are market anomalies and those with a genuine risk premium, so funds can focus on strategies that can actually make money in the long run.
"It is a way to see through the jungle of strategies and say ‘this is going to make me money' ... if it is really risk premium, maybe it is going to persist in the future. If it is an anomaly, then the jury is out on whether it will survive when the whole industry becomes quantitative or if it will slowly die out," says Bouchaud.
The physics behind finance
Most of those who voted for Bouchaud this year credit him with helping build the research machinery at CFM that was able to produce many effective papers as a result of its heavy focus on academic research, often applying physics concepts to finance.
Bouchaud's fascination for combining physics with finance started soon after he completed his PhD in theoretical physics from Ecole Normale Superieure in Paris in 1985, when his papers on rare events started catching the attention of quants. In 1994, he met the late Jean-Pierre Aguilar, who founded CFM in 1991. Aguilar was very receptive to Bouchaud's idea of merging the two disciplines, which encouraged the two to start a quantitative research company together.
"It was love at first sight," says Bouchaud, on their business relationship. "He was a terrific guy and right away understood it would be interesting to have a research arm to the company and we should be bringing in physics experts."
The pair founded Science & Finance the same year, which started functioning as a sister company carrying out quantitative research for CFM. Potters was the first employee at Science & Finance, which merged with CFM in 2000 to become the investment manager's dedicated in-house research arm.
Bouchaud and Potters have been heading the research team since 1995, and have written several papers together, many of which have made a strong impact.
Creative idea man
"The way we work together is Bouchaud is the one with a lot of creative ideas – it is essential for research, because you can't censor all your ideas too quickly. But this means many ideas end up being wrong. I am the one who is always doubtful and would try to convince him he is wrong. Once in a while, I am not able to convince him an idea is wrong – and that is when we would write a paper," says Potters.
Together, the quants have published more than 40 papers and a book. During that time, CFM has ballooned in size as well; growing to be the biggest quantitative investment management firms in Continental Europe with $7 billion in assets under management.
The firm has around 40 researchers, most with PhDs in physics – the research team makes up a large part of the company. The strength of the team allowed Bouchaud to co-write many influential papers, including one on capturing the skew and curvature of volatility smiles better than existing models and another one attempting to replace fair value accounting with a valuation method that accounts for liquidation impact – a method CFM currently uses to size their strategies.
Bouchaud's current and future projects, he says, will attempt to understand the market from the bottom up. This includes market microstructure, behavioural anomalies and the impact of trading one asset on another asset's price, called cross-impact.
MIT's Lipton argues this bottom-up understanding is vital for the industry's future: "I think these are all extremely important questions and the time has come to truly address them in earnest, because otherwise, we would really find the entire field of quantitative asset management and investment very naked – intellectually and practically."
Considering Bouchaud's research output rate, the discipline should be well-clothed in no time.

Only users who have a paid subscription or are part of a corporate subscription are able to print or copy content.
To access these options, along with all other subscription benefits, please contact info@risk.net or view our subscription options here: http://subscriptions.risk.net/subscribe

You are currently unable to print this content. Please contact info@risk.net to find out more.

You are currently unable to copy this content. Please contact info@risk.net to find out more.

Copyright Infopro Digital Limited. All rights reserved.
As outlined in our terms and conditions, https://www.infopro-digital.com/terms-and-conditions/subscriptions/ (point 2.4), printing is limited to a single copy.
If you would like to purchase additional rights please email info@risk.net

Copyright Infopro Digital Limited. All rights reserved.
You may share this content using our article tools. As outlined in our terms and conditions, https://www.infopro-digital.com/terms-and-conditions/subscriptions/ (clause 2.4), an Authorised User may only make one copy of the materials for their own personal use. You must also comply with the restrictions in clause 2.5.
If you would like to purchase additional rights please email info@risk.net

                  Awards

  Regulatory capital calculation product of the year: Regnology

                          Regnology’s cloud-native platform helps banks streamline regulatory capital calculation while strengthening strategic decision-making

              04 Aug 2026

        Sponsored content

                  Awards

  Prudential regulation reporting system of the year: Regnology

                          Regnology’s cloud-native platform helps firms unify risk, regulatory reporting and finance on a single data foundation, using AI‑ready architecture to support future innovation

              04 Aug 2026

        Sponsored content

                  Awards

  CTRM software house of the year: Hitachi Energy

                          Energy Risk Awards 2026: Software developer’s portfolio approach meets changing needs of energy market participants

              09 Jul 2026

                  Awards

  Climate risk service of the year: First Street

                          First Street helps institutions translate climate science into asset-level intelligence that supports investment, lending and risk decisions

              01 Jul 2026

        Sponsored content

                  Awards

  Integrated risk management software of the year: TS Imagine

                          TS Imagine’s integrated risk platform helps clients monitor exposures across markets, counterparties and asset classes amid increasingly complex trading environments

              01 Jul 2026

        Sponsored content

                  Awards

  Life and pensions ALM system of the year: Fentics Technology

                          Fentics’ ALM and capital platform helps insurers and pension providers manage balance sheets by bringing assets, liabilities and capital together within a single modelling framework

              01 Jul 2026

        Sponsored content

                  Awards

  Best in-house ALM technology: EFG Bank

                          The EFG ALM Risk Suite has shifted ALM from a retrospective reporting exercise into a forward-looking, strategic discipline

              01 Jul 2026

        Sponsored content

                  Awards

  Best use of AI: Moody’s

                          Moody’s Banking Decision Intelligence solution uses AI to bring together credit, liquidity, capital, profitability and other insights

              01 Jul 2026

        Sponsored content

    Most read articles loading...

    Back to Top

You need to sign in to use this feature. If you don’t have a Risk.net account, please register for a trial.
        Sign in

You need to sign in to use this feature. If you don’t have a Risk.net account, please register for a trial.
  Sign in

You are currently on corporate access.

To use this feature you will need an individual account. If you have one already please sign in.
Sign in.

Alternatively you can request an individual account here