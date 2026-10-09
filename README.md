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

## The result

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

One change has been made since that table was built: the process
noise was fitted on the one month the animal was migrating, and halving it - a
decision taken on the tuning window alone - moves the forward filter's lockbox
median from 412 to 313 km. Finding 8 has the details.

## Eight things the audit found

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

**5. The fix I built could not have worked, for a structural reason.** A day of
twilight data is exactly two numbers, a dawn time and a dusk time. Position is
exactly two unknowns. The measurement Jacobian is therefore square, so *any*
extra parameter entering through those same two numbers is a linear combination
of a latitude shift and a longitude shift. A threshold bias is confounded with
position by construction, not by bad luck. Solving for the exchange rate at the
true positions: **one minute of common-mode bias is observationally identical to
25.4 km of longitude**, and one minute of antisymmetric bias to 112 km of
latitude, rising to 390 km/min in March at the equinox.

**6. Smoothing proves the rest of the error is bias, not variance.** Finding 5
rules out patching the measurement model, but it says nothing about smoothing,
which adds no parameter at all - it just lets the estimate at time *t* use the
observations after *t*. On the same forward pass (hard seafloor set, SST,
12,000 particles, five seeds) a particle smoother cuts tuning-window error from
**119.0 +/- 1.4 km to 68.6 +/- 4.4 km**, a gap of 10.9 standard errors and the
largest single improvement in the project. On the lockbox it does nothing
measurable: 404.2 +/- 2.9 to 388.2 +/- 22.8 km, 0.7 standard errors, with the
signed error still ~370 km too far south. A smoother removes variance; it cannot
remove a bias in the measurement model, and that is exactly the pattern observed.

I ran two smoothers that share no backward machinery - forward-filtering
backward-simulation, and a generalised two-filter smoother fusing the particle
clouds rather than Gaussian moments - and they agree to about 1 km on both
windows. The backward pass is weighted so that its importance ratio is provably
one, and the code asserts it (largest |log ratio| over 241 steps: 1.3e-12).
The posterior also narrows to 0.65 of its former spread while 95% coverage on
the tuning window *rises* from 92.2% to 93.8%; on the lockbox coverage is stuck
at 37.5% either way, which is what an interval centred in the wrong place looks
like.

The part I find most useful is that I had already talked myself out of this.
An earlier step rejected backward simulation after correctly calculating that
only ~3.5 of 12,000 particles lie within one standard deviation of a backward
target. The arithmetic was right; the conclusion was not, because each
trajectory draws its own ancestor, so concentrated weights pin one trajectory
instead of collapsing the ensemble (306 of 400 trajectories stay distinct).
One unchecked inference cost 50 km.

**7. A satellite product said "land" where the shark actually was.** The SST
likelihood compares the tag's dawn temperature to NOAA OISST at each candidate
position, and it mapped a missing reference value to a log-likelihood of minus
infinity. On 19 of the 95 scorable dawn events - 20% of them, and 14 of the 18
in the lockbox - OISST is missing *at the shark's own Argos fix*. Seventeen of
those nineteen are water by this project's own bathymetry (median depth 103 m):
they sit in the Gulf of California, where a quarter-degree land mask swallows a
narrow sea. So on one day in five the filter was assigning the true position
zero probability, and across the map that term was deleting 35% of all
candidate positions. A second, smaller defect sits next to it: the residual
spread on the tuning window is 1.110 C against the filter's assumed 0.689 C,
and it scales with the tag's own mixed-layer depth (0.54 / 0.75 / 1.07 / 1.69 C
across MLD quartiles). The tag was recording when to distrust it and I was not
reading that file.

Fixing both moves the median *up*, 118.5 to 138.8 km, while moving the mean
down, 166.9 to 143.8 km, and the 75th percentile down hard, 273.1 to 191.0 km
(3.5 standard errors). The error rotates rather than shrinks. The land mask was
an unwritten push offshore and the cold reference was a push north, and
together they were cancelling part of the twilight southward bias; the bearing
of the median error swings from 245 to 205 degrees. One degree of latitude is
worth 1.07 C of sea surface temperature along this track, so a free temperature
offset would buy 103 km of free latitude - Finding 5's confounding arriving
through a different channel. Under a smoother the whole thing washes out
(tuning -2.0 km, 0.5 standard errors; lockbox 20 km *worse*). I am reporting it
because the defect is real, the fix is correct, and the median - the statistic
this project quotes nearly everywhere - was the one number blind to a flaw that
ruined one day in five.

**8. A habitat prior that works better when you invert it.** The last thing on
my list was the motion model and a weak preference for plausible habitat. Two
results came out of it and they point in opposite directions.

The first is Finding 2's mistake again, in a parameter I had not thought to
check. SIGMA_V, the process noise, was fitted on net daily displacement over
the calibration window. Argos says the animal covered 68 km per root-day in
that window and 16 km per root-day over the rest of the tuning window, a factor
of 4.2, because the calibration window is exactly when it was running south
from Monterey. Letting the motion model run free across the 47 real Argos gaps
gives a median displacement of 78 km against 32 km observed (KS p < 0.0001),
and the scale that matches is 0.40. Halving SIGMA_V improves all four
tuning-window statistics, so it is chosen without the lockbox being touched,
and it carries: lockbox median 412 -> 313 km.

The second is the one I would lead with. I built a weak habitat prior - the
seafloor depth under the 91 tuning-window Argos fixes, binned into 18
log-depth bins, smoothed, added to the log-likelihood with a small weight.
Eighteen numbers, and nothing in any of them about position. It improved all
eight statistics at once and took the lockbox median from 433 to 291 km, the
largest single lockbox gain in the project.

Then I ran the control. Same weight, same machinery, preference *inverted* so
the prior pushes the animal towards exactly the depths it avoids. It scored
240 km on the lockbox, better than the correct prior. Three of five randomly
shuffled priors also beat the published filter by more than 140 km.

The mechanism is confinement, not knowledge. Across the seven priors, how much
ocean each one deletes correlates with lockbox error at +0.95; hold that fixed
and how close the prior's centre of mass sits to the animal correlates the
*wrong* way. Every one of these priors, including the two that help most, has
its centre of mass more than 1000 km from the animal.

Why that is possible is in the same section. On a 351x351 grid at 0.1 degrees,
with the filter removed entirely, the best position obtainable from one solar
day of light and temperature is 372 km from the animal on the tuning window and
533 km in the lockbox. One day of data rules out most of the ocean and locates
nothing inside what is left; all the accuracy this project reports comes from
the motion model stitching a hundred vague days together. When the likelihood
is that flat, anything that narrows the posterior looks like skill, and the
only way I found to tell the difference was to build a deliberately wrong
version of the same term and check whether it worked too.

Combining the two - halved process noise and the depth prior - gives the best
lockbox numbers in the project by a factor of 2.6 (median 165 km, mean 159 km).
I am not adopting it. On the tuning window that same configuration has a 99th
percentile of 872 km and a worst day of 903 km, and its tuning mean and RMS are
worse than the published filter's: excellent four days in five and badly wrong
on the fifth. My own rule says choose on the tuning window, so it is rejected.
The rule that stops me adopting it is the same rule that would have stopped me
ever finding it, which is a fair statement of what held-out evaluation costs as
well as what it buys.

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

Finding 5 explains why. I widened the bias state to three dimensions
(antisymmetric, common mode, depth coefficient) and re-ran the *identical*
selection rule over 96 combinations. It picks a common-mode bias every time -
the dimension that is confounded with longitude - and lands at 1165 km on the
tuning window against 274 km for no bias state at all. Across all 96
configurations the rank correlation between tuning-window log evidence and
tuning-window error is **rho = +0.76**: higher evidence reliably means worse.
Running the selected filter and correlating its estimated common-mode bias
against its own signed longitude error gives rho = +0.94. It is not measuring
the sensor, it is relabelling its own position error.

The lesson I did not have before: *selection hygiene is necessary and not
sufficient*. A rule that never sees held-out data can still be the wrong rule.
Mine was safe in the original sweep only because the family was one-dimensional
and small.

## Why this problem is hard

A PAT tag has no receiver, so position has to be inferred from the astronomy of
the light curve. Local apparent noon gives longitude robustly. Latitude comes
only from day length, and d(day length)/d(latitude) goes to zero at an equinox.
This deployment runs straight through the March 2008 equinox, so for weeks the
inverse problem is locally rank deficient in latitude. Independent aiding is
what rescues it: SST cuts the March error from 522 km to 109 km, not because it
is accurate but because its information is orthogonal to day length.

The compiled report is at [`report/main.pdf`](report/main.pdf).

## What's in here

```
notebooks/jws_geolocation_filters.ipynb   the whole pipeline, top to bottom
report/main.pdf                           the report, compiled (13 pp.)
report/main.tex                           IEEE-format technical report, LaTeX source
requirements.txt                          pinned versions for local runs
```

## Reproducing it

Open the notebook in Colab (badge above) and Runtime > Run all. There are no
manual steps and nothing to upload: the tag archives are fetched at run time
from the [ATN Data Assembly Center](https://portal.atn.ioos.us/) by stable UUID,
so a cold start gets byte-identical inputs. A full run is about two and a half hours,
most of it the ten-seed headline runs at 120,000 particles and the smoother,
temperature and prior experiments. Every seed is fixed in
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

- Open every file in the data archive before modelling, not just the ones the
  pipeline needs. The vertical temperature profiles that explain the SST
  heteroscedasticity were sitting unused in the same download for the whole
  project.
- Report more than one error statistic. A median hides a defect that ruins a
  fifth of the days; the mean, the RMS and the 75th percentile all saw it.
- Prior-predictive check every fitted process parameter. Simulating the motion
  model at the real observation gaps and comparing it to the Argos track takes
  a few lines and never looks at error at all.
- Run the wrong version of anything that helps. If a term improves a score by
  shrinking the posterior rather than by adding information, an inverted or
  shuffled copy of it will improve the score too. That one control is what
  separated Finding 8's real result from its apparent one.

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
