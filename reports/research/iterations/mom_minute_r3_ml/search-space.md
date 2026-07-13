# Search Space: mom_minute_r3_ml

The fixed budget is eight trials: Logistic `C={0.1,1.0}` and LightGBM
`num_leaves={7,15}`, each with probability threshold `{0.5,0.6}`. Features are
strictly index-minus-one and the decision unit is a complete frozen-rule entry
episode. Three expanding validation folds use episode-end purge and a 13-bar
embargo. A family must win at least two folds before any reserved holdout can be
opened. The corrected run opens no holdout and adds no candidates.
