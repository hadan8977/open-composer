# numerai__docs-models
URL: https://docs.numer.ai/numerai-tournament/models
Fetched: 2026-10-04 18:20 UTC (text only, tags stripped)

Models | Numerai Docs

Skip to content

SearchK

Appearance

Menu
Return to top

Models ​
The best way to learn about building models on our data is through our tutorials:
Tournament Basics
Optimize Your Models
Your Models ​
You have one Numerai account, and within it you create models. A model within a tournament has submissions, scores, stake, payouts, and model-level rank. Your account also has an account-level rank, which is aggregated across your models.
Model slots ​
Each model occupies a "slot" in a tournament. You can run several models at once and most participants do - running genuinely different ideas in parallel is one of the most effective things you can do, since you can compare them on live scores instead of guessing.
Slots are counted per tournament. Models in Numerai, Signals, and Crypto are separate.
How many slots you get depends on your Grandmasters tier for that tournament, so slot limits increase as you earn titles. Your current limit is shown on your models page.
If you need more slots than your tier allows, contact support - additional slots can be granted per tournament.
Benchmark Models ​
Numerai Benchmark Models are a set of standard models that the Numerai team built. Their predictions are then given out every round so that anyone can easily submit them and stake on them if they want. These models are an easy way to compare your model to the current state-of-the-art.
The list of models and their recent performance is here: numer.ai/~benchmark_models
Download ​
The validation and live predictions are available through NumerAPI.
pythonfrom numerapi import NumerAPI
napi = NumerAPI()
VERSION = "v5.3"
napi.download_dataset(f"{VERSION}/train_benchmark_models.parquet", "train_benchmark_models.parquet")
napi.download_dataset(f"{VERSION}/validation_benchmark_models.parquet", "validation_benchmark_models.parquet")
napi.download_dataset(f"{VERSION}/live_benchmark_models.parquet", "live_benchmark_models.parquet")
How they are made ​
Walk Forward Cross Validation
All predictions are made using a Walk-Forward framework. This means all predictions are made using models which were trained only on data which was available prior to the date of the prediction being made.
Specifically, the data is split up into chunks of 156 eras. Then for each chunk of eras, the predictions are given by a model which is trained up to first_era_of_chunk - purge_eras. The number of purge_eras is always 8 for 20D targets, and 16 for 60D targets.
WindowTrain StartTrain EndVal StartVal End
11148157312
21304313468
31460469624
41616625780
...............
Standard Large LGBM params
Most models use the following LGBM parameters:
pythonstandard_large_lgbm_params = {
 "n_estimators": 20000,
 "learning_rate": 0.001,
 "max_depth": 6,
 "num_leaves": 2**6,
 "colsample_bytree": 0.1,
}
Deep LGBM params ​
We've found that having more trees can be helpful, and we've found that having fewer trees with more depth can also achieve similar results with lower compute requirements. You can read more about this hyper-parameter research in this forum post.
After the release of v5 data, we announced the higher performance "deep" parameters we used to train the v5 benchmark models:
pythondeep_lgbm_params = {
 "n_estimators": 30000,
 "learning_rate": 0.001,
 "max_depth": 10,
 "num_leaves": 1024,
 "colsample_bytree": 0.1,
 "min_data_in_leaf": 10000
}
Ensembles
All of the ensembles use the following steps:
gaussianize each of the predictions on a per-era basis
standardize to standard deviation 1
dot-product the predictions with a weights vector representing the desired weight on each model
gaussianize the resulting vector
(if applicable) neutralize the vector
Steps 1 through 4 look something like this:
pythonfrom numerai_tools.scoring import tie_kept_rank

def rank_gauss_pow1(s: pd.Series) -> pd.Series:
 # Rank while preserving ties, missing values, and row order
 s_rank = tie_kept_rank(s.sort_index()).reindex(s.index)

 # gaussianize
 s_rank_norm = pd.Series(stats.norm.ppf(s_rank), index=s_rank.index)

 # Standardize to 1 std
 result_series = s_rank_norm / s_rank_norm.std()

 return result_series

ensemble_cols = ["V4_LGBM_NOMI20", "V42_RAIN_ENSEMBLE"]
weight_vector = [0.1, 0.9]
for col in X[ensemble_cols]:
 if "era" in X.columns:
 X[col] = X.groupby("era", group_keys=False)[col].transform(lambda s1: rank_gauss_pow1(s1))
 else:
 # check X contains only a single era
 assert 1800 < X.shape[0] < 6000
 X[col] = rank_gauss_pow1(X[col])
return X[ensemble_cols].dot(weight_vector)
Neutralization
A couple of the models have some neutralization involved. This is basically doing a regression to find out your predictions' exposures to each feature, and then subtracting those exposures from your predictions vector such that the result is a vector which is orthogonal to all of those features.
Here's the code to neutralize some set of vectors (columns) by some list of features (neutralizers):
pythonfrom numerai_tools.scoring import tie_kept_rank

def neutralize(
 df, columns, neutralizers=None, proportion=1.0, era_col="era"
):
 if neutralizers is None:
 neutralizers = []
 unique_eras = df[era_col].unique()
 computed = []
 for u in unique_eras:
 df_era = df[df[era_col] == u]
 scores = df_era[columns].values
 scores2 = []
 for x in scores.T:
 x = pd.Series(x)
 x = tie_kept_rank(x)
 x = stats.norm.ppf(x)
 scores2.append(x)
 scores = np.array(scores2).T
 exposures = (
 df_era[neutralizers]
 .fillna(df_era[neutralizers].median())
 .fillna(0.5)
 .values
 )

 scores -= proportion * exposures.dot(
 np.linalg.pinv(exposures.astype(np.float32), rcond=1e-6).dot(
 scores.astype(np.float32)
 )
 )

 scores /= pd.DataFrame(scores).std(ddof=0, axis=0, skipna=True).values

 computed.append(scores)

 return pd.DataFrame(np.concatenate(computed), columns=columns, index=df.index)
What are they? ​
The naming formula for many benchmarks is as follows:
{data_version}_LGBM_{target}
There are many models that have some combination of a data version (V2, V3, V4, V41, V42, V43, V5) and a target (e.g. cyrusd_20, teager2b_20, etc.). These are models trained in the standard walk-forward way, with standard LGBM parameters, using the specified data version and target. That's all!
There are also unique models we created that don't have that naming scheme:
V5_LGBM_CT_BLEND (coming soon)
This is a simple 50/50 blend of V5_LGBM_TEAGER2B20 and V5_LGBM_CYRUSD20
The following models are on the Benchmark Models page, but their predictions aren't present in the predictions files because they are easily reproducible:
INTEGRATION_TEST - Submits our favorite model at the time. This has transitioned through V2, V3, and V4 example predictions. It is now v5_lgbm_ct_blend.
NB_BASIC - Submits the model created by the default Tournament Basics notebook.
NB_FEATURE_NEUTRAL - Submits the model created by the feature neutralization tutorial notebook.
NB_TARGET_ENSEMBLE - Submits the model created by the target ensemble tutorial notebook.
NB_EXAMPLE_MODEL - Submits the model created by the barebones example_model notebook.
Community Models ​
The Numerai community has also developed NumerBay, a website to buy and sell predictions built by and for the Numerai community. You can only buy from participants who choose to list predictions for sale, and you submit and stake what you buy under your own model. NumerBay is an independent, community-operated platform. Numerai does not endorse, review, verify, or guarantee the performance, accuracy, or reliability of any model listed on NumerBay. Any performance information is provided by third parties and may not be indicative of future results. Participation involves risk, and users are solely responsible for their decisions and due diligence.