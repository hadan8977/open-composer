source: https://www.quantconnect.com/research/18987/portfolio-construction-using-topological-data-analysis/p1
fetched_utc: 2026-10-04T18:44:11Z
bytes_raw: 194034

Portfolio Construction Using Topological Data Analysis - QuantConnect.com

                Platform

            Pricing

                Research 

                Strategies 

            Datasets

            Documentation

            Algorithm Lab

SIGN IN

                            Sign in

                        Don't have an account? Join QuantConnect Today

                            Sign up for Free

Portfolio Construction Using Topological Data Analysis

                            Research
                Announcements
                Lean

                    COMMUNITY
                    COMMUNITY FEED

                        |

                    Announcements
                    Lean
                    Data Issues

Quant League Is Moving Forward as Strategies

Quant League is evolving into Strategies, our new home for sharing, discovering, and exploring trading strategies, with improved organization and a better overall experience. Q4-2025 will be the final Quant League.
    Explore Strategies

    OPEN LEAGUE 
    PRO LEAGUE 

                    No Results

Radically Open-Source Algorithmic Trading Engine

LEAN is the open-source algorithmic trading engine powering QuantConnect.
                        Founded in 2012 LEAN has been built by a global community of 180+                        engineers and powers more than 300+ hedge funds today.

Join Our Discord Channel

Join QuantConnect's Discord server for real-time support, where a vibrant community of traders and developers awaits to help you with any of your QuantConnect needs.

                            pending review
                            This research is under review. To publish this research attract three community upvotes.

 0">

Draft Discussions

 0">

Bookmarked Discussions

                Loading...

                 Share New Research 

Refer to our Research Guidelines for high quality research posts.

                 Start New Discussion 

                Sign up 

SEARCH DISCUSSIONS

             -->
             0 -->

TOP 5 Research Publications

                         - 

549,300 Quants.
                                    Become a Quant 

Online Now

 20">

                Code of Conduct

VOTE FOR UPCOMING FEATURES

Share your input and vote on our future direction.
                LEAN Roadmap

Create an account on QuantConnect for the latest  delivered to your inbox.
                    Sign Up Today

Answers

Backtests

Comments

Live Traded

            Research
            Announcements
            Lean

                COMMUNITY
                COMMUNITY FEED

                        |

                    Announcements
                    Lean
                    Data Issues

                                pending review
                                This research is under review. To publish this research attract three community upvotes.

                                draft post
                                This discussion is a draft. Click here to publish this discusison.

Portfolio Construction Using Topological Data Analysis                            

Introduction
This research diversifies SPY by clustering its top 200 weighted constituents using topological data analysis (TDA). The strategy aims to minimize correlation risk by employing KepplerMapper for projection, Principal Component Analysis (PCA) and Uniform Manifold Approximation and Projection (UMAP) for dimensionality reduction, and Density-Based Spatial Clustering of Applications with Noise (DBSCAN) for clustering. The resulting clusters are then used to construct a portfolio with equal weighting by clusters and subclusters. This method is expected to enhance portfolio diversification, reduce its correlation with SPY, and reduce the drawdown.
Background
Topological Data Analysis (TDA) is a field of data analysis that explores and quantifies the shape and structure of data. TDA can reveal hidden patterns and relationships in high-dimensional data, allowing us to cluster securities with less obvious non-linear correlations.
The Mapper Algorithm is a tool used in TDA to project high-dimensional data into a lower-dimensional space while preserving the combinatorial representations of the topological structure. It clusters the data more computationally efficiently in the topological space.
Principal Component Analysis (PCA) is a dimension reduction method that transforms data into a new set of linear combinations of the original variables by dropping the new variables with low variance. It can preserve most of the information in the dataset while removing noise and dimension quickly to facilitate the upcoming processes' speed and accuracy.
Uniform Manifold Approximation and Projection (UMAP) is a non-linear dimensionality reduction technique that further projects high-dimensional data in a lower-dimensional space. It was chosen for its ability to preserve local and global data structures, which is essential for accurate clustering while being computationally efficient.
Density-Based Spatial Clustering of Applications with Noise (DBSCAN) is a clustering algorithm that groups closely packed projected points, making it robust to outliers. DBSCAN with correlation distance is applied to identify clusters based on the similarity of stock returns so that we can evenly dissipate the non-systematic risk.
The highly correlated projected points by the Mapper Algorithm would create small clusters, which can be represented as nodes in a graph. Correlated small clusters would connect by edges in the graph, and each connected structure would be considered a large cluster. The overall graph is called a simplicial complex, which represents the underlying topological structure of the data.
Since the clusters have low correlations, we can split the capital equally between clusters and subclusters and within subclusters to dissipate the capital risk evenly.
Implementation
To implement this strategy, we start by selecting SPY's top 200 weighted constituents in the initialize method with a TopologicalGraphUniverseSelectionModel class. 
universe_model = TopologicalGraphUniverseSelectionModel(
            "SPY",
            history_lookback,
            recalibrate_period,
            lambda u: [x.symbol for x in sorted(
                [x for x in u if x.weight],
                key=lambda x: x.weight,
                reverse=True
            )[:200]]
        )
In the TopologicalGraphUniverseSelectionModel class, we use a KepplerMapper to project the log returns into a lower-dimensional space using PCA and UMAP. We then apply DBSCAN to cluster the projected data using correlation distance.
prices = algorithm.history(self.universe.selected, lookback_window, Resolution.DAILY).unstack(0).close
log_returns = np.log(prices / prices.shift(1)).dropna().T

mapper = km.KeplerMapper()
projected_data = mapper.fit_transform(log_returns, projection=[PCA(n_components=0.8, random_state=1), UMAP(n_components=1, random_state=1, n_jobs=-1)])
graph = mapper.map(projected_data, log_returns, clusterer=DBSCAN(metric='correlation', n_jobs=-1))
The resulting clusters are analyzed to identify giant clusters (connected simplicial complexes) and small clusters (grouped nodes). We then construct the portfolio by assigning equal weights to each giant cluster, each small cluster, and stocks within small clusters in the weight_distribution method of the EqualClustersWeightingPortfolioConstructionModel class.
def weight_distribution(self, clustered_symbols):
    weights = {}
    def assign_weights(nested_list, level=1):
        num_elements = len(nested_list)
        weight_per_element = 1 / num_elements
        for item in nested_list:
            if isinstance(item, list):
                assign_weights(item, level + 1)
            else:
                weights[item] = weights.get(item, 0) + weight_per_element / (2 ** (level - 1))
    assign_weights(clustered_symbols)
    return pd.Series(weights) / sum(weights.values())
Results
The strategy was backtested from March 2020 to March 2025 on QuantConnect. The benchmark was buy-and-hold SPY and a normalized top 200 weighted SPY constituents strategy. The strategy yielded the following performance metrics over the backtest period.

TDA Portfolio (Proposed)Normalized Top 200 Weighted SPY ConstituentsBuy-and-Hold SPY

Sharpe Ratio0.8370.8170.807

Beta0.8950.9261 (Reference)

Annualize Variance0.020.0180.021

Maximum Drawdown17.2%24.5%26.3%

We ran a parameter optimization job to test the sensitivity of the chosen parameters. We tested a historical data lookback window of 50 weeks to 350 weeks in steps of 50 weeks and a simplicial complex reconstruction period of 25 days to 250 days in steps of 25 days. Of the 70 parameter combinations, 8/70 (11.4%) have a higher Sharpe Ratio than the benchmark, 65/70 (92.9%) produced a lower Beta than the benchmark, and 70/40 (100%) made a smaller maximum drawdown than the benchmark.
The red circle in the preceding image identifies the parameters we chose as the strategy's default. We chose a historical data lookback window of 150 weeks and a 125-day simplicial complex reconstruction because they produced the best risk-adjusted return while maintaining a low drawdown level and low correlation with the benchmark. We yielded a 0.018 Alpha, demonstrating the potential of using TDA and clustering techniques to enhance risk-adjusted return while lowering the correlation with the benchmark.
References
Carlsson, G. (2009). Topology and data. Bulletin of the American Mathematical Society, 46(2), 255-308.
McInnes, L., Healy, J., & Melville, J. (2018). UMAP: Uniform Manifold Approximation and Projection for Dimension Reduction. arXiv preprint arXiv:1802.03426.
Ester, M., Kriegel, H. P., Sander, J., & Xu, X. (1996). A density-based algorithm for discovering clusters in large spatial databases with noise. KDD, 96, 226-231.

                                 Update Backtest 

                                        Project

                                        Backtest

                                Cancel

                                 person upvoted this

                                 1 -->
                                 people upvoted this

                                    Louis Szeto

                                     | 

                                                                                                             | 
                                    Accepted Answer

                                        Permalink

                                 Update Backtest 

                                        Project

                                        Backtest

                                Cancel

                                         Notebook

                                Remove

                                Disclaimer

The material on this website is provided for informational purposes only and does not constitute an offer to sell, a solicitation to buy, or a recommendation or endorsement for any security or strategy, nor does it constitute an offer to provide investment advisory services by QuantConnect. In addition, the material offers no opinion with respect to the suitability of any security or specific investment. QuantConnect makes no guarantees as to the accuracy or completeness of the views expressed in the website. The views are subject to change, and may have become unreliable for various reasons, including changes in market conditions or economic circumstances. All investments involve risk, including loss of principal. You should consult with an investment professional before making any investment decisions.

                                             Twitter

                                             Facebook

                                             LinkedIn

                                             Copy Link

                    Dibakar Sigdel

                    384
                                             Pro
                                        ,

Thanks for sharing! 

                    Ogdn Ames

                    565
                                             Pro
                                        ,

This research takes a really interesting and creative approach to building a portfolio by using Topological Data Analysis (TDA) on the top 200 stocks in the SPY index. Instead of just relying on traditional measures like correlation, it uses tools like KeplerMapper, PCA, UMAP, and DBSCAN to find hidden patterns and group stocks into low-correlation clusters. Then it spreads the investments evenly across these clusters to reduce risk. The results are pretty solid — better Sharpe Ratio, lower drawdowns, and less exposure to overall market swings compared to just holding SPY or its top components. That said, the paper could be a bit clearer, especially when explaining the more technical stuff like simplicial complexes and graph projections. It also doesn’t touch much on practical challenges like trading costs or how fast this could run in real time. Still, it’s a fresh take that shows real potential. If the method holds up across different market conditions and asset classes, it could be a smart way to build more resilient portfolios.

                    Louis Szeto
                    INVESTOR

                     | 

                    Permalink

                 Update Backtest 

                        Project

                        Backtest

                Cancel

                         Notebook

                Accept Answer

                Disclaimer

The material on this website is provided for informational purposes only and does not constitute an offer to sell, a solicitation to buy, or a recommendation or endorsement for any security or strategy, nor does it constitute an offer to provide investment advisory services by QuantConnect. In addition, the material offers no opinion with respect to the suitability of any security or specific investment. QuantConnect makes no guarantees as to the accuracy or completeness of the views expressed in the website. The views are subject to change, and may have become unreliable for various reasons, including changes in market conditions or economic circumstances. All investments involve risk, including loss of principal. You should consult with an investment professional before making any investment decisions.

                        Reply

                 person upvoted this

                 1 -->
                 people upvoted this

                                 |

                             person upvoted this

                             1 -->
                             people upvoted this

                            Reply

        Loading...

        Load More

                To unlock posting to the community forums please complete at least 30% of Boot Camp.
 You can
                continue your Boot Camp training progress from the terminal. We
                hope to see you in the community soon!

Allocate to this Strategy

Institutional clients can contact the author and allocate capital to this strategy.
                Learn More

Organization

                Organization Website

             0 && discussion.Competition.type != 'pro' -->

Team

             10" onclick="$(this).parent().find('.member-row').show();$(this).hide();">Show More

Clone Strategy

Copy this strategy code to your QuantConnect account and deploy it live with your brokerage.
            Clone

 0">

Previous Ranking

Browse strategies and organization entries from previous quarter's competitions.

                Author: 

IN THIS RESEARCH

         0 -->

PARTICIPANTS

         0 -->

Discussion Awards
             0">

SHARE RESEARCH

SHARE DISCUSSION

SHARE ARTICLE

SHARE

Actions

                View in Strategy Explorer

                Award Discussion

                Print Research

                Comments

                            What is an Award? 

            Research
            Announcements
            Lean

                COMMUNITY
                COMMUNITY FEED

                        |

                    Data Issues

        Send Message

Join QuantConnect for Free
            Sign Up

                QuantConnect™ 2026. All Rights Reserved

                        Technology

Algorithm Lab

Documentation

Research

Build vs. Buy

Tutorials

Data Library

Learning Articles

System Status

Settings

Discussions List

                        Company

About

Affiliates

Our Blog

Contact

Pricing

Integration Partners

QuantConnect Swag

Terms & Conditions

Privacy Policy

                            LEAN

                                    Fork

                                    5,000                                

                                    Star

                                    22,000