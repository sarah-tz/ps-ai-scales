#!/usr/bin/env python3
"""Multi-scale design: how much does the psychological safety-team learning
correlation vary across AI-generated measures of psychological safety?

This script simulates the multi-scale design, in which each respondent answers the
established psychological safety scales (Edmondson-like and May-like reference
forms), a team learning behavior scale, and m AI-generated scales drawn at
random from a pool of K. It then

  1. estimates, for each AI scale, its correlation with team learning;
  2. pools those correlations with a random-effects model (REML on Fisher z),
     so that tau, the standard deviation of true correlations across scales,
     separates measure-dependent variation from sampling error (RQ1);
  3. regresses the scale-level correlations on a text-derived index of each
     scale's content overlap with the learning items (RQ2); and
  4. locates the established scales inside the AI distribution.

A Monte Carlo study checks that tau is recovered without bias, that the
heterogeneity test holds its nominal error rate when scales are parallel, and
how much power the design has for realistic amounts of heterogeneity.

Every generating parameter below is a hypothetical researcher assumption. No
participant data and no properties of the actual AI-generated item sets are
used. Responses are 7-point ordinal, produced by thresholding continuous
propensities at standard-normal quantiles.

Item model. Each psychological safety item has communality lambda^2. Its common
part points in a direction that mixes latent safety P with latent learning L:
    common = s * ((1 - w) * P + w * L),  scaled so that Var(common) = lambda^2.
w = 0 is a pure safety item. w > 0 is an item whose content partly describes
learning behavior (e.g., speaking up, asking questions). Raising w changes what
an item measures without changing its reliability, which is the situation in
which a scale can look fine psychometrically while its meaning shifts.

Python 3.10+. Requires numpy, scipy, matplotlib.
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

import numpy as np
from scipy.stats import chi2, norm
from scipy.stats import t as t_dist

SEED = 20261029
THRESHOLDS = norm.ppf(np.arange(1, 7) / 7)
N_ITEMS = 7

# Latent correlations among safety (P), efficacy (E), and learning (L).
# R_PL is set so that the Edmondson-like reference scale correlates about .48
# with the observed learning composite, the mean observed individual-level
# correlation in Frazier et al. (2017, Table 1).
R_PE, R_PL, R_EL = .35, .56, .35
LATENT_CORR = np.array([[1, R_PE, R_PL], [R_PE, 1, R_EL], [R_PL, R_EL, 1]])
LEARN_LOADING = .70
EFF_LOADING = .70
BASE_LOADING = .65

POOL_SIZE = 400          # AI scales per scenario from which each study draws K
N_POPULATION = 100_000   # respondents used to compute each scale's true correlation
INDEX_NOISE_SD = .05     # error in the text-derived overlap index (RQ2)

# Heterogeneity scenarios for the pool of AI scales.
#   sd_scale: SD of a scale's mean loading around BASE_LOADING (precision)
#   sd_item:  SD of item loadings around their scale's mean
#   overlap_beta: Beta(a, b) for the share of a scale's items that overlap
#                 with learning content (None = no overlap)
#   overlap_w: mixing weight w for an overlapping item
SCENARIOS = {
    'none':   dict(sd_scale=.00, sd_item=.00, overlap_beta=None,     overlap_w=.00),
    'low':    dict(sd_scale=.05, sd_item=.04, overlap_beta=(1, 9),   overlap_w=.25),
    'medium': dict(sd_scale=.08, sd_item=.05, overlap_beta=(1, 4),   overlap_w=.35),
    'high':   dict(sd_scale=.10, sd_item=.06, overlap_beta=(1, 1.5), overlap_w=.50),
}

# Designs: (N respondents, K AI scales in the study, m AI scales per respondent)
DESIGNS = [(500, 20, 4), (750, 20, 4), (1000, 20, 4), (750, 20, 3), (750, 10, 4), (750, 30, 4)]
DEMO_DESIGN = (750, 20, 4)
DEMO_SCENARIO = 'high'

# Rough benchmark reconstructed from Frazier et al. (2017, Table 1), individual
# level, psychological safety with learning behavior: k = 15, N = 4,648,
# mean observed r = .48, artifacts account for 7.21% of observed variance.
# The paper does not report SD-rho, so this is an approximation (see README).
FRAZIER = dict(k=15, N=4648, r_bar=.48, pct_artifact=.0721)


# ----------------------------------------------------------------------------
# Data generation
# ----------------------------------------------------------------------------

def latent_sample(n, rng):
    chol = np.linalg.cholesky(LATENT_CORR)
    z = rng.standard_normal((n, 3)) @ chol.T
    return z[:, 0], z[:, 1], z[:, 2]


def to_ordinal(x):
    return np.searchsorted(THRESHOLDS, x, side='right') + 1


def item_weights(loading, w):
    """Return (a, b): coefficients on P and L giving communality loading^2."""
    base = (1 - w) ** 2 + w ** 2 + 2 * w * (1 - w) * R_PL
    s = loading / np.sqrt(base)
    return s * (1 - w), s * w


def scale_composite(loadings, ws, p, l, rng):
    """Mean of 7-point ordinal items for one scale, for the rows in p and l."""
    n = p.shape[0]
    total = np.zeros(n)
    for lam, w in zip(loadings, ws):
        a, b = item_weights(lam, w)
        common_var = a * a + b * b + 2 * a * b * R_PL
        x = a * p + b * l + np.sqrt(1 - common_var) * rng.standard_normal(n)
        total += to_ordinal(x)
    return total / len(loadings)


def single_factor_composite(n_items, loading, factor, rng):
    n = factor.shape[0]
    total = np.zeros(n)
    for _ in range(n_items):
        total += to_ordinal(loading * factor + np.sqrt(1 - loading ** 2) * rng.standard_normal(n))
    return total / n_items


def draw_ai_scale(scn, rng):
    lam_scale = np.clip(BASE_LOADING + scn['sd_scale'] * rng.standard_normal(), .35, .85)
    loadings = np.clip(lam_scale + scn['sd_item'] * rng.standard_normal(N_ITEMS), .30, .90)
    if scn['overlap_beta'] is None:
        ws = np.zeros(N_ITEMS)
    else:
        share = rng.beta(*scn['overlap_beta'])
        ws = np.where(rng.random(N_ITEMS) < share, scn['overlap_w'], 0.)
    return dict(loadings=loadings, ws=ws, overlap_index=float(ws.mean()))


REFERENCE_SCALES = {
    # Edmondson-like: 7 items; one item ("bring up problems and tough issues")
    # given modest overlap with learning content, as an illustration.
    'edmondson_like': dict(loadings=np.repeat(BASE_LOADING, 7), ws=np.array([0, .25, 0, 0, 0, 0, 0.])),
    # May-like: 3 items with loadings implying alpha near .71 (May et al., 2004).
    'may_like': dict(loadings=np.repeat(.67, 3), ws=np.zeros(3)),
}


def build_pool(scn_name, rng):
    """Draw POOL_SIZE AI scales and compute each one's population correlation."""
    scn = SCENARIOS[scn_name]
    p, e, l = latent_sample(N_POPULATION, rng)
    learn = single_factor_composite(N_ITEMS, LEARN_LOADING, l, rng)
    pool = []
    for _ in range(POOL_SIZE):
        sc = draw_ai_scale(scn, rng)
        comp = scale_composite(sc['loadings'], sc['ws'], p, l, rng)
        sc['true_r'] = float(np.corrcoef(comp, learn)[0, 1])
        pool.append(sc)
    refs = {}
    for name, sc in REFERENCE_SCALES.items():
        comp = scale_composite(sc['loadings'], sc['ws'], p, l, rng)
        refs[name] = float(np.corrcoef(comp, learn)[0, 1])
    true_r = np.array([s['true_r'] for s in pool])
    summary = dict(
        scenario=scn_name,
        pool_mean_r=float(true_r.mean()),
        pool_tau_r=float(true_r.std(ddof=1)),
        pool_tau_z=float(np.arctanh(true_r).std(ddof=1)),
        pool_min_r=float(true_r.min()),
        pool_max_r=float(true_r.max()),
        reference_true_r=refs,
    )
    return pool, summary


def simulate_study(pool, n, k, m, rng):
    """One study: n respondents, k AI scales drawn from the pool, m per person."""
    chosen = rng.choice(len(pool), size=k, replace=False)
    scales = [pool[i] for i in chosen]
    p, e, l = latent_sample(n, rng)
    learn = single_factor_composite(N_ITEMS, LEARN_LOADING, l, rng)
    efficacy = single_factor_composite(3, EFF_LOADING, e, rng)
    assign = np.argsort(rng.random((n, k)), axis=1)[:, :m]
    ai = np.full((n, k), np.nan)
    for j, sc in enumerate(scales):
        rows = np.where((assign == j).any(axis=1))[0]
        ai[rows, j] = scale_composite(sc['loadings'], sc['ws'], p[rows], l[rows], rng)
    refs = {name: scale_composite(sc['loadings'], sc['ws'], p, l, rng)
            for name, sc in REFERENCE_SCALES.items()}
    return dict(ai=ai, learn=learn, efficacy=efficacy, refs=refs, scales=scales)


# ----------------------------------------------------------------------------
# Estimation
# ----------------------------------------------------------------------------

def masked_corr(x, y):
    """Column-wise Pearson r of x (n x k, NaN = not administered) with y."""
    mask = ~np.isnan(x)
    xm = np.where(mask, x, 0.)
    ym = mask * y[:, None]
    n = mask.sum(axis=0)
    sx, sy = xm.sum(axis=0), ym.sum(axis=0)
    sxx, syy, sxy = (xm * xm).sum(axis=0), (ym * ym).sum(axis=0), (xm * ym).sum(axis=0)
    cov = sxy - sx * sy / n
    r = cov / np.sqrt((sxx - sx * sx / n) * (syy - sy * sy / n))
    return r, n


def reml(z, v, max_iter=500, tol=1e-12):
    """Random-effects meta-analysis by REML (Fisher scoring)."""
    tau2 = max(0., float(np.var(z, ddof=1) - v.mean()))
    for _ in range(max_iter):
        w = 1 / (v + tau2)
        mu = np.sum(w * z) / np.sum(w)
        new = np.sum(w ** 2 * ((z - mu) ** 2 - v)) / np.sum(w ** 2) + 1 / np.sum(w)
        new = max(0., float(new))
        if abs(new - tau2) < tol:
            tau2 = new
            break
        tau2 = new
    w = 1 / (v + tau2)
    mu = float(np.sum(w * z) / np.sum(w))
    w0 = 1 / v
    mu0 = np.sum(w0 * z) / np.sum(w0)
    q = float(np.sum(w0 * (z - mu0) ** 2))
    df = len(z) - 1
    return dict(mu_z=mu, se_mu_z=float(np.sqrt(1 / np.sum(w))), tau2_z=tau2,
                q=q, df=df, q_p=float(chi2.sf(q, df)), i2=max(0., (q - df) / q) if q > 0 else 0.)


def q_profile_ci(z, v, level=.95):
    """Q-profile confidence interval for tau^2 (Viechtbauer, 2007)."""
    k = len(z)

    def gen_q(t2):
        w = 1 / (v + t2)
        mu = np.sum(w * z) / np.sum(w)
        return float(np.sum(w * (z - mu) ** 2))

    def solve(target):
        if gen_q(0.) <= target:
            return 0.
        lo, hi = 0., 1.
        while gen_q(hi) > target:
            hi *= 2
        for _ in range(100):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if gen_q(mid) > target else (lo, mid)
        return (lo + hi) / 2

    a = 1 - level
    return solve(chi2.ppf(1 - a / 2, k - 1)), solve(chi2.ppf(a / 2, k - 1))


def meta_regression(z, v, x):
    """Mixed-effects meta-regression of z on x (DL residual tau^2, Knapp-Hartung test)."""
    k = len(z)
    X = np.column_stack([np.ones(k), x])
    W0 = np.diag(1 / v)
    XtW0X_inv = np.linalg.inv(X.T @ W0 @ X)
    b_fe = XtW0X_inv @ X.T @ W0 @ z
    q_e = float(np.sum((1 / v) * (z - X @ b_fe) ** 2))
    P = W0 - W0 @ X @ XtW0X_inv @ X.T @ W0
    tau2 = max(0., (q_e - (k - 2)) / np.trace(P))
    w = 1 / (v + tau2)
    W = np.diag(w)
    XtWX_inv = np.linalg.inv(X.T @ W @ X)
    b = XtWX_inv @ X.T @ W @ z
    s2 = float(np.sum(w * (z - X @ b) ** 2) / (k - 2))
    se = float(np.sqrt(s2 * XtWX_inv[1, 1]))
    tstat = float(b[1] / se)
    return dict(slope=float(b[1]), se=se, t=tstat, p=float(2 * t_dist.sf(abs(tstat), k - 2)), tau2_resid_z=tau2)


def analyze(study, rng):
    r, n = masked_corr(study['ai'], study['learn'])
    z, v = np.arctanh(r), 1 / (n - 3)
    re = reml(z, v)
    re['tau2_z_ci'] = q_profile_ci(z, v)
    true_index = np.array([s['overlap_index'] for s in study['scales']])
    obs_index = true_index + INDEX_NOISE_SD * rng.standard_normal(len(true_index))
    mr = meta_regression(z, v, obs_index)
    mu_r = float(np.tanh(re['mu_z']))
    ref_r = {name: float(np.corrcoef(x, study['learn'])[0, 1]) for name, x in study['refs'].items()}
    return dict(r=r, n=n, z=z, v=v, re=re, mr=mr, mu_r=mu_r,
                tau_r=float(np.sqrt(re['tau2_z']) * (1 - mu_r ** 2)),
                obs_index=obs_index, true_index=true_index, ref_r=ref_r)


def bootstrap_tau(study, B, rng):
    """Respondent-level bootstrap of the pooled mean (and tau, for diagnostics).

    The bootstrap distribution of tau is biased upward, because resampling
    respondents adds sampling noise on top of the noise already in the data,
    so the reported interval for tau uses the Q-profile method instead.
    """
    n = study['learn'].shape[0]
    taus, mus = np.empty(B), np.empty(B)
    for b in range(B):
        ids = rng.integers(0, n, n)
        r, nk = masked_corr(study['ai'][ids], study['learn'][ids])
        re = reml(np.arctanh(r), 1 / (nk - 3))
        mus[b] = np.tanh(re['mu_z'])
        taus[b] = np.sqrt(re['tau2_z']) * (1 - mus[b] ** 2)
    return taus, mus


# ----------------------------------------------------------------------------
# Benchmark
# ----------------------------------------------------------------------------

def frazier_benchmark():
    """Approximate between-study SD of observed r implied by Frazier et al. (2017).

    Frazier et al. define %-Acc as the share of variance accounted for by
    sampling error (Table 1 note), so the residual SD on the observed-r metric
    follows from the Hunter-Schmidt sampling-error variance at the average
    study size. Approximate, because it uses the average study size.
    """
    n_bar = FRAZIER['N'] / FRAZIER['k']
    samp_var = (1 - FRAZIER['r_bar'] ** 2) ** 2 / (n_bar - 1)
    obs_var = samp_var / FRAZIER['pct_artifact']
    resid_sd = float(np.sqrt(obs_var - samp_var))
    return dict(mean_n_per_study=round(n_bar, 1), sampling_var=round(samp_var, 5),
                implied_observed_var=round(obs_var, 5), implied_between_study_sd_r=round(resid_sd, 3))


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def run(out, reps, boot):
    out.mkdir(parents=True, exist_ok=True)
    master = np.random.default_rng(SEED)
    t0 = time.time()

    pools, pool_rows = {}, []
    for name in SCENARIOS:
        pools[name], summary = build_pool(name, np.random.default_rng(master.integers(2**63)))
        pool_rows.append(summary)
        print(f"pool {name:9s} mean r {summary['pool_mean_r']:.3f}  tau_r {summary['pool_tau_r']:.3f}  "
              f"refs {summary['reference_true_r']}")

    bench = frazier_benchmark()

    # Monte Carlo
    mc_rows = []
    for name in SCENARIOS:
        truth = next(s for s in pool_rows if s['scenario'] == name)
        for (n, k, m) in DESIGNS:
            rng = np.random.default_rng(master.integers(2**63))
            tau_hat, rej_q, rej_mr, mean_nk, ref_e, mu_hat, covered = [], 0, 0, [], [], [], 0
            for _ in range(reps):
                res = analyze(simulate_study(pools[name], n, k, m, rng), rng)
                tau_hat.append(res['tau_r'])
                mu_hat.append(res['mu_r'])
                rej_q += res['re']['q_p'] < .05
                rej_mr += res['mr']['p'] < .05
                mean_nk.append(res['n'].mean())
                ref_e.append(res['ref_r']['edmondson_like'])
                lo2, hi2 = res['re']['tau2_z_ci']
                covered += lo2 <= truth['pool_tau_z'] ** 2 <= hi2
            tau_hat = np.array(tau_hat)
            mc_rows.append(dict(
                scenario=name, N=n, K=k, m=m, mean_respondents_per_scale=round(float(np.mean(mean_nk)), 1),
                true_tau_r=round(truth['pool_tau_r'], 4),
                mean_tau_hat_r=round(float(tau_hat.mean()), 4),
                bias=round(float(tau_hat.mean() - truth['pool_tau_r']), 4),
                rmse=round(float(np.sqrt(np.mean((tau_hat - truth['pool_tau_r']) ** 2))), 4),
                tau_hat_p05=round(float(np.quantile(tau_hat, .05)), 4),
                tau_hat_p95=round(float(np.quantile(tau_hat, .95)), 4),
                rejection_rate_heterogeneity_Q=round(rej_q / reps, 3),
                rejection_rate_overlap_slope=round(rej_mr / reps, 3),
                tau_ci95_coverage=round(covered / reps, 3),
                mean_pooled_r=round(float(np.mean(mu_hat)), 4),
                mean_edmondson_like_r=round(float(np.mean(ref_e)), 4),
                reps=reps,
            ))
            print(f"MC {name:9s} N={n:5d} K={k:2d} m={m}  tau {truth['pool_tau_r']:.3f} "
                  f"est {tau_hat.mean():.3f}  Q-reject {rej_q/reps:.2f}  slope-reject {rej_mr/reps:.2f}")

    # Demonstration study
    n, k, m = DEMO_DESIGN
    demo_rng = np.random.default_rng(master.integers(2**63))
    study = simulate_study(pools[DEMO_SCENARIO], n, k, m, demo_rng)
    res = analyze(study, demo_rng)
    taus, mus = bootstrap_tau(study, boot, demo_rng)
    truth = next(s for s in pool_rows if s['scenario'] == DEMO_SCENARIO)
    tau = res['tau_r']
    placement = {}
    for name, rr in res['ref_r'].items():
        zz = (np.arctanh(rr) - res['re']['mu_z']) / np.sqrt(res['re']['tau2_z']) if res['re']['tau2_z'] > 0 else 0.
        placement[name] = dict(r=round(rr, 4), percentile_in_ai_distribution=round(float(norm.cdf(zz) * 100), 1))
    demo = dict(
        scenario=DEMO_SCENARIO, N=n, K=k, m=m,
        pooled_r=round(res['mu_r'], 4),
        pooled_r_ci95=[round(float(np.quantile(mus, .025)), 4), round(float(np.quantile(mus, .975)), 4)],
        tau_r=round(tau, 4),
        tau_r_ci95_q_profile=[round(float(np.sqrt(t2) * (1 - res['mu_r'] ** 2)), 4) for t2 in res['re']['tau2_z_ci']],
        true_pool_tau_r=round(truth['pool_tau_r'], 4),
        i2=round(res['re']['i2'], 3), q=round(res['re']['q'], 2), q_df=res['re']['df'], q_p=float(f"{res['re']['q_p']:.3g}"),
        prediction_interval_80_r=[round(float(np.tanh(res['re']['mu_z'] + s * 1.2816 * np.sqrt(res['re']['tau2_z']))), 4)
                                  for s in (-1, 1)],
        share_of_frazier_between_study_variance=round((tau / bench['implied_between_study_sd_r']) ** 2, 3),
        overlap_meta_regression=dict(slope_z_per_unit_index=round(res['mr']['slope'], 3), se=round(res['mr']['se'], 3),
                                     t=round(res['mr']['t'], 2), p=float(f"{res['mr']['p']:.3g}"),
                                     corr_observed_true_index=round(float(np.corrcoef(res['obs_index'], res['true_index'])[0, 1]), 3)),
        established_scales=placement,
        bootstrap_reps_for_pooled_r=boot,
    )
    scale_rows = [dict(scale=f'AI-{j+1:02d}', respondents=int(res['n'][j]), r=round(float(res['r'][j]), 4),
                       ci_low=round(float(np.tanh(res['z'][j] - 1.96 * np.sqrt(res['v'][j]))), 4),
                       ci_high=round(float(np.tanh(res['z'][j] + 1.96 * np.sqrt(res['v'][j]))), 4),
                       true_r=round(study['scales'][j]['true_r'], 4),
                       overlap_index_true=round(float(res['true_index'][j]), 3),
                       overlap_index_observed=round(float(res['obs_index'][j]), 3))
                  for j in range(k)]

    # Checks
    assert all(np.all((x >= 1) & (x <= 7)) for x in [study['learn'], study['efficacy']])
    assert np.isfinite(res['r']).all() and (res['n'] >= 3).all()
    null_rows = [r for r in mc_rows if r['scenario'] == 'none']
    checks = dict(
        null_type1_rates=[r['rejection_rate_heterogeneity_Q'] for r in null_rows],
        null_type1_within_monte_carlo_error=all(r['rejection_rate_heterogeneity_Q'] <= .05 + 2.6 * np.sqrt(.05 * .95 / reps)
                                                 for r in null_rows),
        null_slope_type1_rates=[r['rejection_rate_overlap_slope'] for r in null_rows],
    )

    with open(out / 'pool_scenarios.json', 'w') as f:
        json.dump(pool_rows, f, indent=2)
    with open(out / 'monte_carlo.csv', 'w', newline='') as f:
        wr = csv.DictWriter(f, fieldnames=list(mc_rows[0]))
        wr.writeheader()
        wr.writerows(mc_rows)
    with open(out / 'demo_scales.csv', 'w', newline='') as f:
        wr = csv.DictWriter(f, fieldnames=list(scale_rows[0]))
        wr.writeheader()
        wr.writerows(scale_rows)
    with open(out / 'demo_results.json', 'w') as f:
        json.dump(dict(demo=demo, frazier_benchmark=bench, checks=checks, seed=SEED), f, indent=2)
    write_table_a1(mc_rows, out / 'table_A1.csv')
    plot_demo(scale_rows, demo, out / 'demo_distribution.png')
    plot_demo(scale_rows, demo, out / 'figure_A1.png', titled=False)
    print(json.dumps(dict(demo=demo, frazier_benchmark=bench, checks=checks), indent=2))
    print(f'runtime {time.time() - t0:.1f} s')


TABLE_A1_CELLS = [('none', 750), ('none', 1000), ('low', 750), ('low', 1000), ('medium', 500), ('medium', 750),
                  ('medium', 1000), ('high', 500), ('high', 750), ('high', 1000)]


def write_table_a1(mc_rows, path):
    """Table A1 of the technical appendix: K = 20, m = 4, rounded half up."""
    from decimal import Decimal, ROUND_HALF_UP

    def fmt(x, nd):
        txt = f"{Decimal(str(x)).quantize(Decimal(1).scaleb(-nd), rounding=ROUND_HALF_UP):.{nd}f}"
        return txt[1:] if txt.startswith('0') else txt

    rows = {(r['scenario'], r['N']): r for r in mc_rows if r['K'] == 20 and r['m'] == 4}
    with open(path, 'w', newline='') as f:
        wr = csv.writer(f)
        wr.writerow(['Pool', 'True tau', 'N', 'Mean tau estimate', 'Heterogeneity test', 'Overlap test', 'Tau CI coverage'])
        for name, n in TABLE_A1_CELLS:
            r = rows[(name, n)]
            wr.writerow([name.capitalize(), fmt(r['true_tau_r'], 3), f'{n:,}', fmt(r['mean_tau_hat_r'], 3),
                         fmt(r['rejection_rate_heterogeneity_Q'], 2), fmt(r['rejection_rate_overlap_slope'], 2),
                         fmt(r['tau_ci95_coverage'], 2)])


def plot_demo(rows, demo, path, titled=True):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    surface, ink, ink2, grid = '#fcfcfb', '#0b0b0b', '#52514e', '#e4e3df'
    ai_col, ref_col = '#2a78d6', '#eb6834'
    rows = sorted(rows, key=lambda r: r['r'])
    refs = [('Edmondson-like (all respondents)', demo['established_scales']['edmondson_like']['r'], demo['N']),
            ('May-like (all respondents)', demo['established_scales']['may_like']['r'], demo['N'])]

    fig, ax = plt.subplots(figsize=(7.2, 6.4), dpi=200)
    fig.patch.set_facecolor(surface)
    ax.set_facecolor(surface)
    mu, lo80, hi80 = demo['pooled_r'], *demo['prediction_interval_80_r']
    n_rows = len(rows) + len(refs) + 1
    ax.axvspan(lo80, hi80, color=grid, alpha=.7, lw=0, zorder=0)
    ax.axvline(mu, color=ink2, lw=1.2, zorder=1)

    for i, r in enumerate(rows):
        ax.plot([r['ci_low'], r['ci_high']], [i, i], color=ai_col, lw=2, solid_capstyle='round', zorder=2)
        ax.plot(r['r'], i, 'o', ms=6, color=ai_col, mec=surface, mew=1.5, zorder=3)
    for j, (label, rr, n) in enumerate(refs):
        y = len(rows) + 1 + j
        z, se = np.arctanh(rr), 1 / np.sqrt(n - 3)
        ax.plot([np.tanh(z - 1.96 * se), np.tanh(z + 1.96 * se)], [y, y], color=ref_col, lw=2, solid_capstyle='round', zorder=2)
        ax.plot(rr, y, 'D', ms=6.5, color=ref_col, mec=surface, mew=1.5, zorder=3)

    labels = [r['scale'] for r in rows] + [''] + [r[0] for r in refs]
    ax.set_yticks(range(n_rows))
    ax.set_yticklabels(labels, fontsize=7.5, color=ink2)
    ax.set_ylim(-1, n_rows)
    ax.set_xlabel('Correlation with team learning behavior (95% CI)', fontsize=9, color=ink2)
    ax.tick_params(axis='x', labelsize=8, colors=ink2)
    ax.tick_params(axis='y', length=0)
    for s in ('top', 'right', 'left'):
        ax.spines[s].set_visible(False)
    ax.spines['bottom'].set_color(grid)
    ax.grid(axis='x', color=grid, lw=.6, zorder=0)
    ax.set_axisbelow(True)

    ax.text(mu, len(rows) - .2, f'  pooled r = {mu:.2f}', fontsize=7.5, color=ink2, va='bottom')
    ax.text(hi80, -0.9, ' 80% prediction interval\n across AI scales', fontsize=7, color=ink2, va='bottom')
    if titled:
        fig.suptitle('Simulated: correlation with team learning across 20 AI-generated scales',
                     x=.02, ha='left', fontsize=10.5, color=ink, y=.985)
        ax.set_title(f"Hypothetical parameters, no real data. N = {demo['N']}; each respondent answers {demo['m']} of "
                     f"{demo['K']} AI scales.\nEstimated tau = {demo['tau_r']:.3f} (true value in the simulated pool "
                     f"{demo['true_pool_tau_r']:.3f}).",
                     loc='left', fontsize=7.5, color=ink2, pad=8)
    fig.tight_layout()
    fig.savefig(path, facecolor=surface, metadata={'Software': None})
    plt.close(fig)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out', type=Path, default=Path('results'))
    ap.add_argument('--reps', type=int, default=400, help='Monte Carlo replications per cell')
    ap.add_argument('--boot', type=int, default=500, help='bootstrap replications in the demonstration')
    args = ap.parse_args()
    run(args.out, args.reps, args.boot)
