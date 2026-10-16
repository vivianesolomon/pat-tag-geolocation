"""Build the seven-animal track animation shown at the top of the README.

Not standalone. This is the code from sections 29a and 29b of
notebooks/jws_geolocation_filters.ipynb, exported verbatim. It needs a
finished session of that notebook: the loaded cohort (COH), the frozen
configuration, and run_pf. Run the notebook top to bottom, then exec this.

It selects nothing. It re-runs the configuration the report ends on -
halved process noise, cleaned temperature channel, each animal with its own
leave-one-out offset - once per animal at a single seed, and draws the
result against GPE3 and the Argos fixes. The running medians printed in
each panel come from the same scorer as Table II.

Writes figs/cohort_tracks.gif and figs/cohort_tracks.png.
"""

# ---- 29a. Re-run the final configuration once per animal, keep the tracks ---
# Nothing here selects anything. It is the configuration the paper ends on -
# halved process noise, cleaned temperature channel, each animal's own
# leave-one-out offset - run at a single seed so I have a trajectory to draw
# next to GPE3 and the Argos fixes.

from pathlib import Path
VIZ_SEED = 11

def load_gpe3_for(shark):
    cands = []
    for tag in COHORT[shark]:
        cands += sorted(Path('jws/unpacked', tag).glob('*GPE3.csv'))
    if not cands:
        return None
    p = cands[0]
    hdr = next(i for i, ln in enumerate(open(p, errors='replace'))
               if ln.startswith('DeployID'))
    g = read_csv_robust(p, skiprows=hdr)
    g.columns = [c.strip() for c in g.columns]
    g['t'] = parse_times(g['Date'])
    g = (g.rename(columns={'Most Likely Latitude': 'lat',
                           'Most Likely Longitude': 'lon'})
           .loc[:, ['t', 'lat', 'lon']]
           .dropna().sort_values('t').reset_index(drop=True))
    return g

VIZ, _t0 = {}, time.time()
for _s, A in COH.items():
    _aid = make_sst_aid(A, 'clean', LOO_BIAS[_s])
    _ev  = A['ev'][A['ev'].t <= A['truth'].t.max()].reset_index(drop=True)
    with release_state(A), velocity_scale(0.5), depth_window(A):
        _tk, _dbg, _cl = run_pf(events=_ev, n=8_000, sst_aid=_aid,
                                feas=feasible,
                                rng=np.random.default_rng(VIZ_SEED))
    _g3 = load_gpe3_for(_s)
    VIZ[_s] = {'mine': _tk[['t', 'lat', 'lon']].copy(),
               'gpe3': _g3,
               'truth': A['truth'][['t', 'lat', 'lon']].copy()}
    _m = score_against(_tk, A['truth'])['med']
    _gm = score_against(_g3, A['truth'])['med'] if _g3 is not None else float('nan')
    print(f"  {_s}: {len(_tk):3d} filter days, GPE3 {0 if _g3 is None else len(_g3):4d} rows,"
          f"  mine {_m:6.1f} km   GPE3 {_gm:6.1f} km   ({time.time()-_t0:4.0f} s)")

with open('/content/CKPT/section29_viz.pkl', 'wb') as f:
    pickle.dump(VIZ, f)
print('checkpointed /content/CKPT/section29_viz.pkl')


# ---- 29b. The animation ----------------------------------------------------
# Seven panels, one per animal, all on the same clock: days since release.
# Grey rings are the independent Argos fixes as they arrive, orange is GPE3,
# blue is my filter. The numbers in each panel are running medians over the
# fixes revealed so far, so the gap on screen is the gap in Table II.
# A fix that falls outside a track's own time span scores nothing for that
# track rather than counting as zero error.

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from PIL import Image
from pathlib import Path

FIG_DIR = Path('jws/figs'); FIG_DIR.mkdir(parents=True, exist_ok=True)

C_MINE, C_GPE3, C_TRUTH = '#1f6feb', '#e8820c', '#2b3137'
N_FRAMES, FPS, HOLD = 120, 11, 16

PAN = {}
for s, v in VIZ.items():
    m, g, tr = v['mine'], v['gpe3'], v['truth']
    t0  = min(m.t.min(), g.t.min(), tr.t.min())
    day = lambda ts: (ts - t0).dt.total_seconds().values / 86400.0
    la_m, lo_m = interp_track(m, tr.t)
    la_g, lo_g = interp_track(g, tr.t)
    PAN[s] = dict(
        dm=day(m.t),  mlat=m.lat.values,  mlon=m.lon.values,
        dg=day(g.t),  glat=g.lat.values,  glon=g.lon.values,
        dt=day(tr.t), tlat=tr.lat.values, tlon=tr.lon.values,
        em=haversine_km(tr.lat.values, tr.lon.values, la_m, lo_m),
        eg=haversine_km(tr.lat.values, tr.lon.values, la_g, lo_g),
        dur=float(max(day(m.t).max(), day(tr.t).max())))

def running(err, shown):
    ok = shown & np.isfinite(err)
    return float(np.median(err[ok])) if ok.sum() else np.nan

DMAX  = max(p['dur'] for p in PAN.values())
ORDER = sorted(PAN, key=lambda s: -PAN[s]['dur'])

fig = plt.figure(figsize=(11.0, 5.7), dpi=100)
fig.patch.set_facecolor('white')
gs  = fig.add_gridspec(2, 4, left=.035, right=.985, top=.875, bottom=.045,
                       hspace=.28, wspace=.22)

art = {}
for i, s in enumerate(ORDER):
    p  = PAN[s]
    ax = fig.add_subplot(gs[i // 4, i % 4])
    lo = np.concatenate([p['mlon'], p['glon'], p['tlon']])
    la = np.concatenate([p['mlat'], p['glat'], p['tlat']])
    padx = max(.55, .09 * (lo.max() - lo.min()))
    pady = max(.55, .09 * (la.max() - la.min()))
    x0, x1, y0, y1 = lo.min()-padx, lo.max()+padx, la.min()-pady, la.max()+pady
    jx = np.where((BLON >= x0-1) & (BLON <= x1+1))[0]
    jy = np.where((BLAT >= y0-1) & (BLAT <= y1+1))[0]
    sub = BELEV[np.ix_(jy, jx)]
    ax.contourf(BLON[jx], BLAT[jy], sub, levels=[0, 1e4], colors=['#ece7df'])
    ax.contour(BLON[jx], BLAT[jy], sub, levels=[0], colors=['#b4ac9e'], linewidths=.7)
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1)
    ax.set_aspect(1 / np.cos(np.deg2rad(la.mean())))
    ax.set_facecolor('#f6fafd')
    ax.tick_params(labelsize=6, length=2, pad=1, colors='#8b949e')
    for sp in ax.spines.values(): sp.set_color('#d3dae1')
    ax.plot(p['mlon'][0], p['mlat'][0], marker='*', ms=10, mfc='#ffd43b',
            mec='#7a6300', mew=.6, zorder=9, ls='none')
    ax.set_title(f"{s}    {p['dur']:.0f} days    {len(p['dt'])} fixes",
                 fontsize=8.2, pad=3, color='#24292f')
    art[s] = dict(
        tp=ax.plot([], [], ls='none', marker='o', ms=3.0, mfc='none',
                   mec=C_TRUTH, mew=.75, zorder=3)[0],
        gl=ax.plot([], [], '-', color=C_GPE3, lw=1.5, zorder=5, alpha=.95)[0],
        ml=ax.plot([], [], '-', color=C_MINE, lw=1.0, zorder=4, alpha=.8)[0],
        gh=ax.plot([], [], marker='o', ms=4.6, color=C_GPE3, ls='none', zorder=7)[0],
        mh=ax.plot([], [], marker='o', ms=4.6, color=C_MINE, ls='none', zorder=8)[0],
        txt=ax.text(.035, .035, '', transform=ax.transAxes, fontsize=7.4,
                    va='bottom', ha='left', family='DejaVu Sans Mono',
                    bbox=dict(fc='white', ec='#dde3e9', alpha=.9, pad=2.0)))

axl = fig.add_subplot(gs[1, 3]); axl.axis('off')
axl.legend(handles=[Line2D([], [], color=C_MINE, lw=2, label='my particle filter'),
                    Line2D([], [], color=C_GPE3, lw=2, label='GPE3 (tag maker)'),
                    Line2D([], [], ls='none', marker='o', mfc='none', mec=C_TRUTH,
                           label='Argos fix (reference)'),
                    Line2D([], [], ls='none', marker='*', mfc='#ffd43b',
                           mec='#7a6300', ms=10, label='release')],
           loc='upper left', frameon=False, fontsize=8.4, handlelength=1.7,
           bbox_to_anchor=(-.04, 1.04))
coh = axl.text(-.04, .44, '', transform=axl.transAxes, fontsize=8.8, va='top',
               family='DejaVu Sans Mono', color='#24292f')

sup = fig.text(.035, .958, '', fontsize=13.5, weight='bold', va='center')
fig.text(.035, .916,
         'light-level geolocation scored against independent Argos fixes'
         '   -   seven white sharks, one frozen configuration',
         fontsize=8.6, color='#57606a', va='center')
bar_bg = fig.add_artist(plt.Rectangle((.70, .951), .265, .012, fc='#e6ebf0',
                                      ec='none', transform=fig.transFigure))
bar_fg = fig.add_artist(plt.Rectangle((.70, .951), .0, .012, fc=C_MINE,
                                      ec='none', transform=fig.transFigure))

def draw(d):
    mm, gg = [], []
    for s in ORDER:
        p, a = PAN[s], art[s]
        i, j, k = p['dm'] <= d, p['dg'] <= d, p['dt'] <= d
        a['ml'].set_data(p['mlon'][i], p['mlat'][i])
        a['gl'].set_data(p['glon'][j], p['glat'][j])
        a['tp'].set_data(p['tlon'][k], p['tlat'][k])
        a['mh'].set_data(p['mlon'][i][-1:], p['mlat'][i][-1:])
        a['gh'].set_data(p['glon'][j][-1:], p['glat'][j][-1:])
        over = d > p['dur']
        for h in ('ml', 'gl', 'mh', 'gh'):
            a[h].set_alpha(.35 if over else (.8 if h == 'ml' else .95))
        em, eg = running(p['em'], k), running(p['eg'], k)
        if np.isfinite(em): mm.append(em)
        if np.isfinite(eg): gg.append(eg)
        f = lambda x: f'{x:5.0f}' if np.isfinite(x) else '    -'
        a['txt'].set_text(f'mine {f(em)} km\nGPE3 {f(eg)} km')
    sup.set_text(f'Day {d:.0f} after release')
    bar_fg.set_width(.265 * d / DMAX)
    coh.set_text('cohort median error\n(mean over animals)\n\n'
                 f'  mine   {np.mean(mm):5.0f} km\n'
                 f'  GPE3   {np.mean(gg):5.0f} km'
                 if mm and gg else '')

frames = []
for d in np.linspace(0, DMAX, N_FRAMES):
    draw(float(d))
    fig.canvas.draw()
    frames.append(np.asarray(fig.canvas.buffer_rgba())[:, :, :3].copy())

draw(DMAX)
fig.savefig(FIG_DIR / 'cohort_tracks.png', dpi=220, facecolor='white')
plt.close(fig)

pal  = Image.fromarray(frames[-1]).convert('P', palette=Image.ADAPTIVE, colors=64)
imgs = [Image.fromarray(f).quantize(palette=pal, dither=Image.NONE) for f in frames]
imgs += [imgs[-1]] * HOLD
gif  = FIG_DIR / 'cohort_tracks.gif'
imgs[0].save(gif, save_all=True, append_images=imgs[1:], loop=0,
             duration=int(1000 / FPS), optimize=True, disposal=1)
print(f'{len(imgs)} frames  {imgs[0].size[0]}x{imgs[0].size[1]}  '
      f'{gif.stat().st_size/1e6:.2f} MB  -> {gif}')

# the numbers the last frame is claiming, printed so they can be checked
for s in ORDER:
    p = PAN[s]; k = np.ones(len(p['dt']), bool)
    print(f"  {s}  mine {running(p['em'], k):6.1f} km   GPE3 {running(p['eg'], k):6.1f} km"
          f"   ({np.isfinite(p['em']).sum()}/{len(p['dt'])} fixes inside my span)")
