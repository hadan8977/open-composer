# gdocs__optiver-trading-at-the-close-slides
URL: https://docs.google.com/presentation/d/1C6eS-og4hsXxU47HZJNA90A4Y6jZf_6M/htmlpresent
Fetched: 2026-10-04 18:23 UTC (text only, tags stripped)

Quant Optiver Trading at the close.pptx - Google Slides

1 of 10

Optiver - Trading at the Close 

By: Matthew Durai, Reetom Gangopadhyay, Ryan Gilbert

Quant ML Competition

Premier academic organization for aspiring finance professionals.

2 of 10

Competition Overview

Develop a model capable of predicting stock closing price movements using data from the order book and the closing auction of stocks. 
Information from the auction can be used to adjust prices, assess supply and demand dynamics, and identify trading opportunities.

Optiver - Trading at the Close 

2

Premier academic organization for aspiring finance professionals.

3 of 10

Competition Overview cont.

Active training phase and a second period where models will be run against new market data
5.24 million rows of orderbook info for the closing 10 minutes of NASDAQ stocks, predict future move relative to synthetic index
Target move in basis points (0.01%), Leaderboard MAE 
~4,000 teams

Optiver - Trading at the Close

3

Premier academic organization for aspiring finance professionals.

4 of 10

Data

Optiver - Trading at the Close

4

Columns: 

Imbalance size
Reference price
Match size
Bid/Ask prices

Imbalance direction
Seconds in bucket
Far/Near price
Bid/Ask sizes

Premier academic organization for aspiring finance professionals.

5 of 10

Feature Engineering

Combinations of order book information
Windowed features
Rolling averages, standard deviations
Mean, standard deviation, skew, kurtosis for price features
Time related features

Optiver - Trading at the Close

5

Premier academic organization for aspiring finance professionals.

6 of 10

LightGBM

LightGBM is a framework developed to implement a Gradient Boosting Machine. 
Advantages: lightweight, fast, supports training distribution, built-in features to reduce overfitting.
Disadvantages: Highly sensitive to hyperparameter tuning, difficult to interpret results, highish memory usage.
​
In general, LightGBM had the strongest performance out of all of the models we tried such as XGBoost and CatBoost.

Optiver - Trading at the Close

6

Premier academic organization for aspiring finance professionals.

7 of 10

CV Strategy and Ensemble Approach

CV strategy: Purged 5-Fold
Find optimal hyperparameters
Early stopping to prevent overfit
Performance based on MAE
​
Ensemble approach: 
Rerun Purged 5-Fold
Run model on complete dataset
Combine forecasts of all 6 models
​

Weights on forecasts based on performance on validation set.
​
Bates-Granger Equation:
​
​
� Modified Equation:
�

Optiver - Trading at the Close
​

, where is 1/MSE

, where is 1/MAE2

7

Premier academic organization for aspiring finance professionals.

8 of 10

Results & Limitations

MAE: 5.3364, Rankings: 187/4034

Limitations:
Optimization difficulties
Runtime limits (9 hr)
Hardware limits (RAM)
Kaggle GPU limits (30hr/week)
API limitations (lags of target not available)
​

Optiver - Trading at the Close
​

8

Premier academic organization for aspiring finance professionals.

Note ranking was at time of presentation creation

9 of 10

Reflections & What’s Next

​
Real world problem, competing against professionals
Memory optimization
Working with bigger datasets

​
Neural network, RNN, …
Hyperparameter tuning
Feature engineering with importances

Optiver - Trading at the Close
​

9

Premier academic organization for aspiring finance professionals.

10 of 10

Optiver - Trading at the Close

10

Q+A

Premier academic organization for aspiring finance professionals.