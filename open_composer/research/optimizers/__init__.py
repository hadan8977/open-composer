"""Lightweight research optimizers used by bounded candidate discovery.

**If you are looking for parameter search, there are two of them and they serve
different layers.** Not knowing that is how this repository grew duplicated
machinery once already -- see ``docs/review-kernel-search-2026-09-01.zh.md``,
whose recurring finding is new mechanisms built without first checking what
already existed.

* This package plus :mod:`open_composer.research.parameter_sweep` operate at the
  **StrategySpec level**: they sweep values declared in a spec file, write
  research artifacts, and enforce the iteration execution gate.
* :mod:`open_composer.research.kernel.parameter_search` operates at the **kernel
  level**: declared-domain grids and bounded mutation over plain parameter
  mappings, with no spec and no artifacts, feeding
  :mod:`open_composer.research.kernel.nested_walk_forward`.

Extend the one that matches your layer. Do not add a third.
"""
