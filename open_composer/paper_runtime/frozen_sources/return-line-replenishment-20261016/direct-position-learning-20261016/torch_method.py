"""Paper-grounded small LSTM and differentiable funded training-only objective.

Independent implementation, not copied from the unlicensed reference repository.
Actual account ledgers use the existing accepted fractional_account reference.
"""

import numpy as np
import torch
from torch import nn


class PositionLSTM(nn.Module):
    def __init__(self, hidden=20):
        super().__init__()
        self.rnn = nn.LSTM(8, hidden, num_layers=1)
        self.head = nn.Linear(hidden, 1)

    def forward(self, x, state=None):
        y, state = self.rnn(x, state)
        return self.head(y).squeeze(-1), state


def weights(raw, vol, kind):
    if kind == "FCAST":
        signal = (raw > 0).to(raw.dtype)
    else:
        signal = torch.sigmoid(raw)
    q = torch.clamp(signal.to(torch.float64) * (0.15 / (np.sqrt(252) * vol)) / 10.0, max=0.20)
    return q / torch.clamp(q.sum(-1, keepdim=True), min=1)


def funded_period_returns(q, r, cost, prior=None):
    q = q.to(torch.float64)
    r = r.to(torch.float64)
    if prior is None:
        prior = torch.zeros_like(q[0])
    prior = prior.to(torch.float64)
    drift = q[:-1] * (1 + r[:-1]) / (1 + (q[:-1] * r[:-1]).sum(-1, keepdim=True))
    before = torch.cat([prior[None], drift], dim=0)
    z = torch.ones(q.shape[0], dtype=torch.float64, device=q.device)
    for _ in range(8):
        z = 1 - cost * torch.abs(z[:, None] * q - before).sum(-1)
    net = z * (1 + (q * r).sum(-1)) - 1
    carried = q[-1] * (1 + r[-1]) / (1 + (q[-1] * r[-1]).sum())
    return net, carried, z
