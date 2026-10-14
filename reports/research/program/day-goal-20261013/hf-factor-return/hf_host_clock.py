"""Earliest common observable host close; never skip later missing returns."""

import numpy as np


def first_valid_common_close(common, host, columns):
    if len(common) < 2:
        return None
    complete = np.isfinite(host.loc[common, columns].to_numpy()).all(axis=1)
    starts = np.flatnonzero(complete)
    return common[starts[0]] if len(starts) else None
