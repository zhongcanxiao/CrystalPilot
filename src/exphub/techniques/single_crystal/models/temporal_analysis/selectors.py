"""Peak-selection strategies for the live-data tab.

The tab plots a single scalar (``intensity_ratio``) versus time. What that
scalar means depends on the user's pick in the ``Peak Selection`` dropdown.
Each strategy here implements one mapping from (precomputed peak intensities
+ statistics) to a :class:`SelectionResult`.

Selectors may also override the figure titles + y-axis labels by populating
the optional label fields on :class:`SelectionResult`; this lets modes like
``Peak Ratio`` (whose y-axis is no longer "Signal Noise Ratio") render with
their own labels without leaking mode-specific code into :mod:`.figures`.

Adding a new mode = register a class in :data:`SELECTOR_REGISTRY`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol, Sequence

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class SelectionResult:
    """What the figures need to plot, per cycle.

    ``intensity_ratio`` drives the top figure; ``rsig`` drives the bottom
    one. ``aux`` is an open dict that selectors can populate with extra
    per-cycle context (matched peak index, per-peak intensities, ...).
    The four ``*_title`` / ``*_yaxis`` fields, when set, override the
    figures' default labels for this mode.
    """

    intensity_ratio: float
    rsig: float
    aux: dict[str, Any] = field(default_factory=dict)

    # Optional label overrides. None → figures use their defaults.
    intensity_title: Optional[str] = None
    intensity_yaxis: Optional[str] = None
    uncertainty_title: Optional[str] = None
    uncertainty_yaxis: Optional[str] = None


class PeakSelector(Protocol):
    """Strategy interface invoked once per live-reduction cycle.

    Implementations may return ``None`` to signal "skip this cycle" —
    the pipeline will not append to the plot buffers and figures will
    keep their previous frame (or, for explicit placeholder modes,
    the model can substitute a "Waiting for data" figure).
    """

    name: str

    def select(
        self,
        peaks_ws: Any,
        int_array: np.ndarray,
        sig_array: np.ndarray,
        max_peak_idx: int,
        statistics: dict,
    ) -> Optional[SelectionResult]: ...


# ---------- helpers ----------


def _read_peak_row(peaks_ws: Any, i: int) -> Optional[tuple[int, int, int, int, float, float]]:
    """Return ``(idx, h, k, l, I, σ)`` for peak ``i``, or ``None`` on read error."""
    try:
        peak = peaks_ws.getPeak(i)
        ihkl = peak.getIntHKL()
        h, k, l = int(ihkl[0]), int(ihkl[1]), int(ihkl[2])
        I = float(peak.getIntensity())
        s = float(peak.getSigmaIntensity())
        return (i, h, k, l, I, s)
    except Exception:
        return None


def _format_peaks_summary(peaks_ws: Any, limit: int = 50) -> str:
    """Tabular dump of every peak's IntHKL + I + σ in workspace order.

    Used by selectors that need to tell the user *what is available* when
    the requested HKL doesn't match. Truncated past ``limit`` rows so a
    1000-peak workspace doesn't spam the console.
    """
    try:
        n = peaks_ws.getNumberPeaks()
    except Exception:
        return "  <peaks workspace unavailable>"
    if n == 0:
        return "  <empty peaks workspace>"
    lines: list[str] = []
    lines.append(f"  workspace has {n} peaks (showing up to {limit}, in workspace order):")
    lines.append(f"  {'idx':>4}  {'IntHKL':>14}  {'I':>12}  {'σ':>10}  {'I/σ':>8}")
    shown = min(n, limit)
    for i in range(shown):
        row = _read_peak_row(peaks_ws, i)
        if row is None:
            lines.append(f"  {i:>4}  <peak read failed>")
            continue
        _, h, k, l, I, s = row
        isig = (I / s) if s > 0 else float("nan")
        lines.append(f"  {i:>4}  ({h:>3},{k:>3},{l:>3})  {I:>12.2f}  {s:>10.2f}  {isig:>8.2f}")
    if shown < n:
        lines.append(f"  ... ({n - shown} more peaks omitted)")
    return "\n".join(lines)


def _format_smallest_hkl_peaks(peaks_ws: Any, k_show: int = 10) -> str:
    """Show ``k_show`` indexed peaks with the smallest |HKL|.

    Sort key is ``(|h|+|k|+|l|, |h|, |k|, |l|)``. Unindexed peaks (IntHKL
    == (0,0,0)) are filtered out so the user sees genuine candidates they
    can paste into the Individual Peak / Peak Ratio HKL inputs.
    """
    try:
        n = peaks_ws.getNumberPeaks()
    except Exception:
        return "  <peaks workspace unavailable>"
    rows: list[tuple[int, int, int, int, float, float]] = []
    for i in range(n):
        row = _read_peak_row(peaks_ws, i)
        if row is None:
            continue
        _, h, k, l, _, _ = row
        if h == 0 and k == 0 and l == 0:
            continue
        rows.append(row)
    if not rows:
        return "  <no indexed peaks in workspace>"
    rows.sort(key=lambda r: (abs(r[1]) + abs(r[2]) + abs(r[3]), abs(r[1]), abs(r[2]), abs(r[3])))
    lines: list[str] = []
    lines.append(f"  smallest-|HKL| indexed peaks (showing up to {k_show} of {len(rows)}):")
    lines.append(f"  {'idx':>4}  {'IntHKL':>14}  {'I':>12}  {'σ':>10}  {'I/σ':>8}")
    for idx, h, k, l, I, s in rows[:k_show]:
        isig = (I / s) if s > 0 else float("nan")
        lines.append(f"  {idx:>4}  ({h:>3},{k:>3},{l:>3})  {I:>12.2f}  {s:>10.2f}  {isig:>8.2f}")
    return "\n".join(lines)


def _print_peaks_summary(peaks_ws: Any, header: str, limit: int = 50, k_smallest: int = 10) -> None:
    """Print ``header`` + smallest-|HKL| candidates + workspace-order dump."""
    logger.debug(header)
    logger.debug(_format_smallest_hkl_peaks(peaks_ws, k_show=k_smallest))
    logger.debug(_format_peaks_summary(peaks_ws, limit=limit))


def _mnp_is_zero(peak: Any) -> bool:
    """True if a peak's modulation indices (m,n,p) are all zero.

    Tolerates Mantid versions / workspaces that pre-date ``getIntMNP``;
    when the call is unavailable, peaks are treated as Bragg.
    """
    getter = getattr(peak, "getIntMNP", None)
    if getter is None:
        return True
    try:
        mnp = getter()
    except Exception:
        return True
    return all(int(m) == 0 for m in (mnp[0], mnp[1], mnp[2]))


def _find_peak_by_inthkl(peaks_ws: Any, target: Sequence[int]) -> Optional[int]:
    """Linear scan for the peak whose ``getIntHKL`` matches ``target``.

    Returns the workspace-row index, or ``None`` if no match.
    """
    th, tk, tl = int(target[0]), int(target[1]), int(target[2])
    n = peaks_ws.getNumberPeaks()
    for i in range(n):
        peak = peaks_ws.getPeak(i)
        ihkl = peak.getIntHKL()
        if int(ihkl[0]) == th and int(ihkl[1]) == tk and int(ihkl[2]) == tl:
            return i
    return None


def _reduce_mean_isig(
    int_array: np.ndarray,
    sig_array: np.ndarray,
    idxs: Sequence[int],
) -> Optional[tuple[float, float]]:
    """Mean(I/σ) over the indexed subset. Returns ``None`` if empty.

    Output: ``(intensity_ratio, rsig)`` with ``rsig = 100 / intensity_ratio``.
    """
    if not idxs:
        return None
    ints = int_array[list(idxs)]
    sigs = sig_array[list(idxs)]
    # Guard against zero sigmas (peaks with no statistical content)
    mask = sigs > 0
    if not np.any(mask):
        return None
    r = float(np.mean(ints[mask] / sigs[mask]))
    if r == 0:
        return None
    return r, 100.0 / r


# ---------- selector classes ----------


class AllPeaksSelector:
    """Mean I/σ(I) across the indexed peaks workspace.

    Reads the statistics row that the pipeline already produces via
    ``StatisticsOfPeaksWorkspace`` — cheap.
    """

    name = "All Peaks"
    last_skip_reason: str = ""

    def select(
        self,
        peaks_ws: Any,
        int_array: np.ndarray,
        sig_array: np.ndarray,
        max_peak_idx: int,
        statistics: dict,
    ) -> Optional[SelectionResult]:
        self.last_skip_reason = ""
        r = float(statistics["Mean ((I)/sd(I))"])
        return SelectionResult(intensity_ratio=r, rsig=100.0 / r)


class BraggPeaksSelector:
    """Mean I/σ over peaks whose modulation indices are all zero."""

    name = "Bragg Peaks"
    last_skip_reason: str = ""

    def select(
        self,
        peaks_ws: Any,
        int_array: np.ndarray,
        sig_array: np.ndarray,
        max_peak_idx: int,
        statistics: dict,
    ) -> Optional[SelectionResult]:
        self.last_skip_reason = ""
        idxs = [i for i in range(peaks_ws.getNumberPeaks()) if _mnp_is_zero(peaks_ws.getPeak(i))]
        out = _reduce_mean_isig(int_array, sig_array, idxs)
        if out is None:
            self.last_skip_reason = "No Bragg peaks (IntMNP == 0) with σ > 0 in this cycle"
            return None
        r, rsig = out
        return SelectionResult(
            intensity_ratio=r,
            rsig=rsig,
            aux={"n_peaks": len(idxs)},
            intensity_title="Prediction of Mean I/σ (Bragg)",
            intensity_yaxis="Mean I/σ (Bragg)",
            uncertainty_title="Prediction of σ(I)/I (Bragg)",
            uncertainty_yaxis="σ(I)/I (Bragg) (%)",
        )


class SatellitePeaksSelector:
    """Mean I/σ over peaks whose modulation indices are non-zero.

    Requires the pipeline's ``IndexPeaks`` to be configured with modulation
    vectors + ``MaxOrder`` — otherwise every peak has ``IntMNP == (0,0,0)``
    and this selector reports "no satellite peaks indexed yet".
    """

    name = "Satellite Peaks"
    last_skip_reason: str = ""

    def select(
        self,
        peaks_ws: Any,
        int_array: np.ndarray,
        sig_array: np.ndarray,
        max_peak_idx: int,
        statistics: dict,
    ) -> Optional[SelectionResult]:
        self.last_skip_reason = ""
        idxs = [i for i in range(peaks_ws.getNumberPeaks()) if not _mnp_is_zero(peaks_ws.getPeak(i))]
        out = _reduce_mean_isig(int_array, sig_array, idxs)
        if out is None:
            self.last_skip_reason = "No satellite peaks indexed (check ModVector / MaxOrder)"
            return None
        r, rsig = out
        return SelectionResult(
            intensity_ratio=r,
            rsig=rsig,
            aux={"n_peaks": len(idxs)},
            intensity_title="Prediction of Mean I/σ (Satellite)",
            intensity_yaxis="Mean I/σ (Satellite)",
            uncertainty_title="Prediction of σ(I)/I (Satellite)",
            uncertainty_yaxis="σ(I)/I (Satellite) (%)",
        )


class MaxPeakSelector:
    """I/σ of the brightest peak in the current cycle.

    ``max_peak_idx`` is tracked across cycles by the pipeline; this
    selector just reads it.
    """

    name = "Max Peak"
    last_skip_reason: str = ""

    def select(
        self,
        peaks_ws: Any,
        int_array: np.ndarray,
        sig_array: np.ndarray,
        max_peak_idx: int,
        statistics: dict,
    ) -> Optional[SelectionResult]:
        self.last_skip_reason = ""
        if max_peak_idx < 0:
            self.last_skip_reason = "Max-peak index not yet established"
            return None
        if sig_array[max_peak_idx] <= 0:
            self.last_skip_reason = f"Max peak (idx {max_peak_idx}) has σ ≤ 0 — cannot compute I/σ"
            return None
        r = float(int_array[max_peak_idx] / sig_array[max_peak_idx])
        return SelectionResult(intensity_ratio=r, rsig=100.0 / r)


class DiffuseScatteringSelector:
    """Placeholder mode — always returns None (figures show "Waiting for data").

    Real implementation will replace this once the diffuse-scattering
    reduction pipeline is specified.
    """

    name = "Diffuse Scattering"
    last_skip_reason: str = "Diffuse Scattering reduction not yet implemented"

    def select(
        self,
        peaks_ws: Any,
        int_array: np.ndarray,
        sig_array: np.ndarray,
        max_peak_idx: int,
        statistics: dict,
    ) -> Optional[SelectionResult]:
        self.last_skip_reason = "Diffuse Scattering reduction not yet implemented"
        return None


class IndividualPeakSelector:
    """I/σ of the single peak matching the user-entered HKL."""

    name = "Individual Peak"
    last_skip_reason: str = ""

    def __init__(self, hkl: Sequence[int]) -> None:
        self.hkl = (int(hkl[0]), int(hkl[1]), int(hkl[2]))

    def select(
        self,
        peaks_ws: Any,
        int_array: np.ndarray,
        sig_array: np.ndarray,
        max_peak_idx: int,
        statistics: dict,
    ) -> Optional[SelectionResult]:
        self.last_skip_reason = ""
        idx = _find_peak_by_inthkl(peaks_ws, self.hkl)
        if idx is None:
            self.last_skip_reason = f"Peak HKL {self.hkl} not indexed in workspace — pick from listing"
            _print_peaks_summary(
                peaks_ws,
                header=f"IndividualPeakSelector: peak {self.hkl} not found in workspace",
            )
            return None
        if sig_array[idx] <= 0:
            self.last_skip_reason = f"Peak {self.hkl} found (idx {idx}) but σ ≤ 0 — skipping this cycle"
            return None
        r = float(int_array[idx] / sig_array[idx])
        title = f"Prediction of I/σ — peak {self.hkl}"
        return SelectionResult(
            intensity_ratio=r,
            rsig=100.0 / r,
            aux={"matched_idx": idx, "hkl": self.hkl, "I": float(int_array[idx]), "sigma": float(sig_array[idx])},
            intensity_title=title,
            intensity_yaxis=f"I/σ at {self.hkl}",
            uncertainty_title=f"Prediction of σ/I — peak {self.hkl}",
            uncertainty_yaxis=f"σ(I)/I at {self.hkl} (%)",
        )


class PeakRatioSelector:
    """Raw intensity ratio I_a / I_b with propagated relative uncertainty.

    Top figure y = ``I_a / I_b``. Bottom figure y = σ(ratio)/ratio × 100,
    computed as ``√((σ_a/I_a)² + (σ_b/I_b)²)``.
    """

    name = "Peak Ratio"
    last_skip_reason: str = ""

    def __init__(self, hkl_a: Sequence[int], hkl_b: Sequence[int]) -> None:
        self.hkl_a = (int(hkl_a[0]), int(hkl_a[1]), int(hkl_a[2]))
        self.hkl_b = (int(hkl_b[0]), int(hkl_b[1]), int(hkl_b[2]))

    def select(
        self,
        peaks_ws: Any,
        int_array: np.ndarray,
        sig_array: np.ndarray,
        max_peak_idx: int,
        statistics: dict,
    ) -> Optional[SelectionResult]:
        self.last_skip_reason = ""
        ia = _find_peak_by_inthkl(peaks_ws, self.hkl_a)
        ib = _find_peak_by_inthkl(peaks_ws, self.hkl_b)
        if ia is None or ib is None:
            missing = []
            if ia is None:
                missing.append(str(self.hkl_a))
            if ib is None:
                missing.append(str(self.hkl_b))
            missing_str = ", ".join(missing)
            self.last_skip_reason = f"Peak Ratio: HKL(s) not indexed — {missing_str}"
            _print_peaks_summary(
                peaks_ws,
                header=f"PeakRatioSelector: peaks not found: {missing_str}",
            )
            return None
        I_a, s_a = float(int_array[ia]), float(sig_array[ia])
        I_b, s_b = float(int_array[ib]), float(sig_array[ib])
        if I_b == 0 or I_a == 0 or s_a <= 0 or s_b <= 0:
            self.last_skip_reason = (
                f"Peak Ratio: degenerate I/σ — "
                f"{self.hkl_a}: I={I_a:.2f},σ={s_a:.2f}; "
                f"{self.hkl_b}: I={I_b:.2f},σ={s_b:.2f}"
            )
            return None
        ratio = I_a / I_b
        rel_unc = ((s_a / I_a) ** 2 + (s_b / I_b) ** 2) ** 0.5
        return SelectionResult(
            intensity_ratio=ratio,
            rsig=rel_unc * 100.0,
            aux={
                "hkl_a": self.hkl_a,
                "hkl_b": self.hkl_b,
                "I_a": I_a,
                "sigma_a": s_a,
                "I_b": I_b,
                "sigma_b": s_b,
            },
            intensity_title=f"Peak intensity ratio {self.hkl_a} / {self.hkl_b}",
            intensity_yaxis="I_a / I_b",
            uncertainty_title=f"Propagated σ(ratio)/ratio — {self.hkl_a} / {self.hkl_b}",
            uncertainty_yaxis="σ(ratio) / ratio (%)",
        )


SelectorFactory = Callable[..., PeakSelector]

# Adding a new mode = register a class here. Keys must match the dropdown
# option strings in ``TemporalAnalysisModel.data_selection_options``.
SELECTOR_REGISTRY: dict[str, SelectorFactory] = {
    "All Peaks": lambda **_: AllPeaksSelector(),
    "Bragg Peaks": lambda **_: BraggPeaksSelector(),
    "Satellite Peaks": lambda **_: SatellitePeaksSelector(),
    "Max Peak": lambda **_: MaxPeakSelector(),
    "Diffuse Scattering": lambda **_: DiffuseScatteringSelector(),
    "Individual Peak": lambda hkl=(1, 0, 0), **_: IndividualPeakSelector(hkl),
    "Peak Ratio": lambda hkl_a=(1, 0, 0), hkl_b=(0, 1, 0), **_: PeakRatioSelector(hkl_a, hkl_b),
}


def make_selector(name: str, **params: Any) -> Optional[PeakSelector]:
    """Build a selector for the named mode, or return ``None``.

    Unknown names return ``None`` (legacy fall-through behavior for
    dropdown values without a registered handler).
    """
    factory = SELECTOR_REGISTRY.get(name)
    if factory is None:
        return None
    return factory(**params)
