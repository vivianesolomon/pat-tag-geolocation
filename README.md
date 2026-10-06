# pat-tag-geolocation

Reconstructing the track of a juvenile white shark from an archival tag that
recorded only **light, pressure and temperature**, and scoring the result
against **122 independent Argos satellite fixes** from a second tag on the same
animal.

The interesting part is not the error number. It is that I held out the last 30
days of the ground truth before building anything, and most of what the first
version of this project claimed did not survive contact with it.

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/vivianesolomon/pat-tag-geolocation/blob/main/notebooks/jws_geolocation_filters.ipynb)

---

## The result, stated honestly

Median great-circle error against Argos, in km. *Tune* is the window I made
every modelling decision on. *Lock* is the final 30 days, scored once, never
looked at beforehand.

| Method | All | Tune | Lock |
|---|---:|---:|---:|
| Naive daily inversion | 513.8 | 570.5 | 473.7 |
| EKF | 347.2 | 285.2 | 413.0 |
| UKF | 356.6 | 291.2 | 417.1 |
| Bootstrap particle filter (light + depth) | 316.9 | 240.2 | 391.0 |
| EKF + RTS smoother | 285.7 | 169.4 | 359.0 |
| EKF + RTS, QC events | 279.9 | 169.5 | **319.4** |
| PF + SST | 198.4 | 114.9 | 498.4 |
| Grid HMM | 163.9 | 130.1 | 569.2 |
| PF + SST + seafloor | 152.8 | 123.2 | 452.4 |
| Two-filter cloud fusion (my best) | 117.4 | **84.9** | 543.9 |
| GPE3 HMM smoother (*not mine*) | 72.0 | 71.1 | 118.4 |

My best configuration gets within 14 km of the manufacturer's proprietary
smoother **on the window I tuned on**, and is 4.6x worse than it **on the 30
days I never looked at**. The estimator that generalises here is the one I did
not write.

## Four things the audit found

**1. The headline was a tuning-window number.** 117 km on the full evaluation
window, 544 km on the lockbox. The full window carries 64 of its 84 matched
events inside the tuning period, so quoting it as an accuracy is close to
quoting a training error.

**2. Seed noise was bigger than the reported gains.** Ten seeds of one
configuration at 120,000 particles spread by 29 km on the full window and 90 km
on the lockbox. The ablation ladder I had built reported 1-5 km improvements per
step. Those steps were noise, and two seeds would have told me so.

**3. Tuning-window skill barely transfers.** Across 75 pipeline variants the
Spearman correlation between tuning error and lockbox error is only rho = +0.30.
The variant that looks best while tuning ranks **54th of 75** out of sample.

**4. A recalibration that improved its own fit tripled the held-out error.**
Refitting the twilight threshold model on raw light curves cut the
calibration-window residual RMS from ~12 min to 4.80 min. On identical events,
filter and seed it moved evaluation error from 124 km to 364 km. The reason is
identifiability: the depth coefficient comes out +0.0085 on one set of twilight
times and +0.89 on the other, two orders of magnitude apart for the same
physical quantity, because the calibration window spans 0-94 m of twilight depth
and the lockbox reaches 182 m.

### And one fix that failed

The diagnosis is concrete: evaluated at the *true* Argos position, the twilight
residual is antisymmetric (dawn +12 min, dusk -71 min in the lockbox), which
compresses apparent day length and therefore biases latitude. So I added a
threshold-bias state to the particle filter and selected its one hyperparameter
by tuning-window marginal likelihood alone, never touching the lockbox.

It raised tuning-window 1-sigma coverage from 22% to 38% and left held-out error
unchanged to worse (+83 km, 2.7 standard errors). It is in the repo because it
failed. Selecting the same hyperparameter on the lockbox would have let me
report a 109 km improvement that meant nothing.

## Why this problem is hard

A PAT tag has no receiver, so position has to be inferred from the astronomy of
the light curve. Local apparent noon gives longitude robustly. Latitude comes
only from day length, and d(day length)/d(latitude) goes to zero at an equinox.
This deployment runs straight through the March 2008 equinox, so for weeks the
inverse problem is locally rank deficient in latitude. Independent aiding is
what rescues it: SST cuts the March error from 522 km to 109 km, not because it
is accurate but because its information is orthogonal to day length.

## What's in here

```
notebooks/jws_geolocation_filters.ipynb   the whole pipeline, top to bottom
report/main.tex                           IEEE-format technical report
requirements.txt                          pinned versions for local runs
```

## Reproducing it

Open the notebook in Colab (badge above) and Runtime > Run all. There are no
manual steps and nothing to upload: the tag archives are fetched at run time
from the [ATN Data Assembly Center](https://portal.atn.ioos.us/) by stable UUID,
so a cold start gets byte-identical inputs. A full run is about 75 minutes, most
of it the ten-seed headline runs at 120,000 particles. Every seed is fixed in
code.

Locally:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
jupyter lab notebooks/jws_geolocation_filters.ipynb
```

To build the report, the notebook writes its figures to `figs/`; copy that
directory next to `report/main.tex` and run `pdflatex main.tex` twice.

## Method summary

- **State** `[lat, lon, vE, vN]`, damped random walk in velocity (tau = 3 days).
- **Twilight likelihood** Student-t, nu = 4, on the residual in minutes between
  observed and predicted twilight time, with a depth-dependent threshold
  `h0(z) = h0 + beta*log(1+z)`.
- **Aiding** daily 0.25 deg OI sea-surface temperature, and a seafloor-depth
  feasibility term `log Phi((d_max(p) - z)/sigma_B)` from ETOPO.
- **Estimators** naive inversion, EKF, UKF, RTS and unscented RTS smoothers,
  bootstrap PF with systematic resampling and roughening, two-filter particle
  smoother, cloud-level fusion of two PFs, and a 0.25 deg grid HMM.
- **Scoring** median great-circle error to interpolated Argos fixes, plus
  1-sigma coverage, over three date-blocked windows (calibration / tuning /
  lockbox).

One ablation worth singling out, because it reorders the usual story: run all
four combinations of {Student-t, Gaussian} x {box, no box} through the same
particle-filter code path and the heavy tails are worth 101 km while the
feasibility box is worth 9 km. A Gaussian PF is 84 km *worse* than the EKF. The
win was the likelihood, not the non-Gaussian posterior representation.

## What I would do differently

- Hold out a block of ground truth before writing any model code. A block at the
  end, scored once, not a random split.
- Report seed variance on every stochastic result, and refuse to interpret any
  difference smaller than it.
- Treat calibration *support* as a first-class check. For every fitted sensor
  parameter, compare the range of its regressors in the calibration window
  against the range expected at deployment. A goodness-of-fit plot cannot show
  you an unidentifiable parameter; a support check can.
- Keep calibration constants out of module-level mutable state. An earlier
  version of this audit ran the raw-light filters outside the block that
  installs the right constants and silently produced numbers three times better
  than they were. The notebook now wraps them in a context manager and opens
  with an equivalence test.

## Data and limitations

Tag data for deployment `07_05` are published through the Animal Telemetry
Network Data Assembly Center and are **not redistributed here**; the notebook
downloads them. GPE3 reference tracks were produced by the tag manufacturer's
software and are treated as an external black-box baseline.

This is one animal, one deployment, one ground-truth track. The lockbox holds 20
matched events, so its medians carry wide intervals. Nothing here is a general
ranking of nonlinear filters; it is a statement about what this data set can
resolve, which is less than I first claimed.

## License

Code and report are MIT licensed (see `LICENSE`). The underlying tag data are
the property of their originators and are subject to ATN DAC terms.
