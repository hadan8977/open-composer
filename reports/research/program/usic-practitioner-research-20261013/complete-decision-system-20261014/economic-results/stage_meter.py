"""Isolated timing only; records inclusive nested costs, preserves return/errors."""

import time
from collections import defaultdict


class StageMeter:
    def __init__(self):
        self.totals = defaultdict(lambda: dict(CPU_ns=0, calls=0, raised=0))

    def wrap(self, callback, label):
        def call(*args, **kwargs):
            key = label(*args, **kwargs) if callable(label) else label
            start = time.process_time_ns()
            raised = False
            try:
                return callback(*args, **kwargs)
            except BaseException:
                raised = True
                raise
            finally:
                row = self.totals[key]
                row["CPU_ns"] += time.process_time_ns() - start
                row["calls"] += 1
                row["raised"] += int(raised)

        return call

    def install(self, strategy, policy):
        strategy.on_data = self.wrap(
            strategy.on_data, lambda data: policy + ":on_data:" + str(data.stage)
        )
        strategy.policy.step = self.wrap(strategy.policy.step, policy + ":policy_step")
        strategy._view = self.wrap(strategy._view, policy + ":book_view")
        strategy._cash = self.wrap(strategy._cash, policy + ":native_cash")
        strategy.frame_decoder.decode = self.wrap(
            strategy.frame_decoder.decode, policy + ":Frame_decode"
        )

    def report(self):
        return {
            k: dict(
                CPU=v["CPU_ns"] / 1e9, calls=v["calls"], raised=v["raised"], inclusive_nested=True
            )
            for k, v in sorted(self.totals.items())
        }
