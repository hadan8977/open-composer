"""Scientific invariants affected by this component's timestamp/rank binding."""
import pandas as pd
import numpy as np
from research.peer_earnings_increment_20261103.prepare import reaction_positions, rank_roles, identity_rows

def test_acceptance_at_early_close_cannot_use_that_close_or_weekend():
    # Thanksgiving Friday closes at 18:00 UTC, then the weekend has no close.
    closes = pd.to_datetime(['2024-11-29T18:00:00Z', '2024-12-02T21:00:00Z', '2024-12-03T21:00:00Z'])
    accepted = pd.to_datetime(['2024-11-29T17:59:59Z','2024-11-29T18:00:00Z',
                              '2024-11-29T19:00:00Z','2024-11-30T12:00:00Z'])
    assert reaction_positions(accepted,closes).tolist()==[0,1,1,1]

def test_identical_information_has_identical_joint_price_control():
    f = pd.DataFrame({'ff48':[1,1,2,2], 'E':[.1,.1,-.1,-.1], 'P':[.1,.1,-.1,-.1],
                      'M':[.2,.1,.4,.3], 'L':[4.,3.,2.,1.]},index=['A','B','C','D'])
    r, unavailable = rank_roles(f)
    np.testing.assert_array_equal(r.ME,r.MP)
    assert not unavailable
    assert r.E.iloc[0]==r.E.iloc[1]
    assert r.MX.idxmax()=='C'

def test_missing_or_ambiguous_identity_never_becomes_known_other_industry():
    sic = pd.DataFrame({'symbol':['A','B','B'], 'cik':[1,2,3], 'sic':[None,100,200],
        'ff48':[48,1,2], 'link_first_date':pd.to_datetime(['2024-01-01']*3),
        'link_last_date':pd.to_datetime(['2024-12-31']*3)})
    known,ambiguous = identity_rows(sic,pd.Timestamp('2024-05-01'))
    assert known.empty and set(ambiguous)=={'A','B'}
    known,ambiguous = identity_rows(sic,pd.Timestamp('2025-01-01'))
    assert known.empty and ambiguous==[]
