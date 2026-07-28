"""SANS data models (P4.1 skeleton).

Mirror the *structure* of the single-crystal equivalents but in a SANS shape:

- :mod:`.ipts_info` — sample-info fields only (no crystal system / point group /
  centering / UB / d-spacing).
- :mod:`.strategy` — column-flexible, CSV-loadable editable strategy table; the
  only guaranteed column is the beamline-configured group column
  (``BL1A:Mot:Sample:X`` on USANS, legacy ``BL1A:sampleholder`` default),
  which groups rows into Samples.
- :mod:`.iq_reduction` — I(Q) reduction placeholder; the prediction-model
  dropdown stays ``"TBD"`` until a real SANS pipeline is specified.
"""

from .ipts_info import SansIptsInfoModel
from .iq_reduction import SansIQReductionModel
from .root import SansMainModel
from .strategy import GROUP_KEY, SansStrategyModel

__all__ = [
    "GROUP_KEY",
    "SansIptsInfoModel",
    "SansIQReductionModel",
    "SansMainModel",
    "SansStrategyModel",
]
