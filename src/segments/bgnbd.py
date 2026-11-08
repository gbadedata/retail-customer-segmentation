"""BG/NBD model (Fader, Hardie and Lee, 2005), implemented from the paper.

Used as a per-customer reference: how much predictive accuracy does a handful
of segments give up compared with a model that scores every customer
individually? The implementation is checked in the tests against the
published CDNOW estimates (r=0.243, alpha=4.414, a=0.793, b=2.426).

Inputs per customer, in weeks: x = repeat purchases, t_x = time of last
purchase since the first, T = time from first purchase to the snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import optimize, special


@dataclass
class BGNBD:
    r: float
    alpha: float
    a: float
    b: float
    log_likelihood: float

    def expected_purchases(self, t: float, x: np.ndarray, t_x: np.ndarray, T: np.ndarray) -> np.ndarray:
        """E[purchases in (T, T+t] | x, t_x, T] - equation (10) of the paper."""
        r, alpha, a, b = self.r, self.alpha, self.a, self.b
        x, t_x, T = (np.asarray(v, dtype=float) for v in (x, t_x, T))
        z = t / (alpha + T + t)
        hyp = special.hyp2f1(r + x, b + x, a + b + x - 1, z)
        num = (a + b + x - 1) / (a - 1) * (1 - ((alpha + T) / (alpha + T + t)) ** (r + x) * hyp)
        den = 1 + (x > 0) * (a / np.maximum(b + x - 1, 1e-12)) * ((alpha + T) / (alpha + t_x)) ** (r + x)
        return num / den

    def p_alive(self, x: np.ndarray, t_x: np.ndarray, T: np.ndarray) -> np.ndarray:
        r, alpha, a, b = self.r, self.alpha, self.a, self.b
        x, t_x, T = (np.asarray(v, dtype=float) for v in (x, t_x, T))
        odds = (a / np.maximum(b + x - 1, 1e-12)) * ((alpha + T) / (alpha + t_x)) ** (r + x)
        return np.where(x > 0, 1 / (1 + odds), 1.0)


def log_likelihood(params: np.ndarray, x: np.ndarray, t_x: np.ndarray, T: np.ndarray) -> np.ndarray:
    """Per-customer log-likelihood - equation (6) of the paper, in log space."""
    r, alpha, a, b = params
    ln_a1 = special.gammaln(r + x) - special.gammaln(r) + r * np.log(alpha)
    ln_a2 = special.gammaln(a + b) + special.gammaln(b + x) - special.gammaln(b) - special.gammaln(a + b + x)
    ln_a3 = -(r + x) * np.log(alpha + T)
    with np.errstate(divide="ignore", invalid="ignore"):
        ln_a4 = np.where(
            x > 0,
            np.log(a) - np.log(np.maximum(b + x - 1, 1e-12)) - (r + x) * np.log(alpha + t_x),
            -np.inf,
        )
    return ln_a1 + ln_a2 + np.logaddexp(ln_a3, ln_a4)


def fit(x: np.ndarray, t_x: np.ndarray, T: np.ndarray) -> BGNBD:
    x, t_x, T = (np.asarray(v, dtype=float) for v in (x, t_x, T))
    if np.any(t_x > T + 1e-9) or np.any(x < 0):
        raise ValueError("need 0 <= t_x <= T and x >= 0")

    def nll(theta: np.ndarray) -> float:
        return -float(np.sum(log_likelihood(np.exp(theta), x, t_x, T)))

    best = None
    for start in ([0.0, 0.0, 0.0, 0.0], [-1.0, 1.0, -0.5, 1.0]):
        res = optimize.minimize(nll, x0=np.array(start), method="Nelder-Mead",
                                options={"maxiter": 20000, "xatol": 1e-8, "fatol": 1e-8})
        if best is None or res.fun < best.fun:
            best = res
    r, alpha, a, b = np.exp(best.x)
    return BGNBD(float(r), float(alpha), float(a), float(b), float(-best.fun))
