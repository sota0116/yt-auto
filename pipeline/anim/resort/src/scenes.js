// =====================================================================
//  SCENES — job rank swap (手順書 §5): one board in the top 75% (y < 810), no captions,
//  names / numbers / ranks >= 44px, the source 34px, Noto Sans JP. All values come from DATA.
//  DATA.jobs[i] = { name, inc, wage, r1, r2, mark }  (r1 = 年収の順位, r2 = 時給の順位, 1-based; listed in r1 order)
//  DATA.focus  = names in the order the narration takes them (rank_swap "jobs")
// =====================================================================
const JOBS = DATA.jobs, N = JOBS.length;
const SX = (r) => 960 + (r - (N - 1) / 2) * 312;   // slot of 0-based rank r
const BASE = 430, H0 = 200, PW = 120, FEET = 620, PS = 0.75, FS = 44;
const NAVYP = '#25294f';
const INC_MAX = Math.max(...JOBS.map((j) => j.inc)), WAGE_MAX = Math.max(...JOBS.map((j) => j.wage));
const fmt = (n) => Math.round(n).toLocaleString('en-US');
const segOf = (t) => (t < SEG0 ? -1 : Math.min(DATA.focus.length - 1, Math.floor((t - SEG0) / SEGL)));
const segT = (k) => SEG0 + k * SEGL;

function boardBg() {
  darkWorld('wall');
  woodSurface(20, 12, 1900, 800, 'frame', {});
  ink(box(20, 12, 1880, 788), { closed: true, w: 4, key: 'framerim' });
  paint(box(48, 38, 1824, 736), {
    fill: C.paper, key: 'parch', w: 3,
    tex: [{ k: 'pencil', c: '#e8d6b0', al: 0.5, per: 260 },
          { k: 'hatch', a: 0.8, gap: 6, al: 0.16, dens: (x, y) => clamp(Math.max(Math.abs(x - 960) / 912, Math.abs(y - 406) / 368) * 3 - 2.2) }],
  });
  ink([[70, BASE + 2], [1850, BASE + 2]], { w: 2.4, color: 'rgba(58,36,23,0.45)', key: 'shelf' });
}
function pawnPts(x, y) {
  const L = [], R = [];
  for (let k = 0; k <= 12; k++) { const u = k / 12, yy = y - 140 + 140 * u, hw = 30 + 38 * u ** 1.6; L.push([x - hw, yy]); R.push([x + hw, yy]); }
  return [...L, ...R.reverse()];
}
function emblem(kind, x, y, key) {
  paint(ellipsePts(x, y, 24, 24, 0, 28), { fill: C.cream, key: key + 'em', w: 2.4 });
  const o = { w: 3, key: key + 'mk' };
  if (kind === 'wheel') { ink(ellipsePts(x, y, 13, 13, 0, 24), { ...o, closed: true }); for (const a of [-Math.PI / 2, Math.PI / 6, Math.PI * 5 / 6]) ink([[x, y], [x + Math.cos(a) * 13, y + Math.sin(a) * 13]], { ...o, key: key + 'sp' + a }); }
  else if (kind === 'lamp') { paint(rrectPts(x - 13, y - 9, 26, 12, 4), { fill: C.yellow, key: key + 'lp', w: 2.4 }); ink([[x - 16, y + 7], [x + 16, y + 7]], o); }
  else if (kind === 'plus') { paint([[x - 4, y - 14], [x + 4, y - 14], [x + 4, y - 4], [x + 14, y - 4], [x + 14, y + 4], [x + 4, y + 4], [x + 4, y + 14], [x - 4, y + 14], [x - 4, y + 4], [x - 14, y + 4], [x - 14, y - 4], [x - 4, y - 4]], { fill: C.red, key: key + 'pl', w: 2 }); }
  else if (kind === 'flower') { for (let i = 0; i < 5; i++) { const a = i / 5 * TAU - Math.PI / 2; paint(ellipsePts(x + Math.cos(a) * 9, y + Math.sin(a) * 9, 6, 6, 0, 12), { fill: C.roseL, key: key + 'pt' + i, w: 1.6 }); } paint(ellipsePts(x, y, 5, 5, 0, 10), { fill: C.yellow, key: key + 'fc', w: 1.6 }); }
  else if (kind === 'check') { ink([[x - 12, y], [x - 3, y + 10], [x + 13, y - 11]], { ...o, w: 4, color: C.green }); }
  else if (kind === 'heart') { const P = []; for (let i = 0; i < 32; i++) { const a = i / 32 * TAU, hx = 16 * Math.sin(a) ** 3, hy = 13 * Math.cos(a) - 5 * Math.cos(2 * a) - 2 * Math.cos(3 * a) - Math.cos(4 * a); P.push([x + hx * 0.8, y - hy * 0.8 - 1]); } paint(P, { fill: C.red, key: key + 'ht', w: 2 }); }
  else paint(ellipsePts(x, y, 9, 9, 0, 16), { fill: C.sky, key: key + 'dt', w: 2 });
}
function pawn(j, x, y, hero, nameAl) {
  const key = 'pw' + j.r1;
  ctx.save(); ctx.translate(x, y); ctx.scale(PS, PS);
  paint(ellipsePts(10, 4, 78, 13, 0, 30), { fill: 'rgba(58,36,23,0.25)', line: false, key: key + 'sh', tex: [{ k: 'hatch', a: 0.8, gap: 4, al: 0.5 }] });
  paint(pawnPts(0, 0), { fill: hero ? C.terra : NAVYP, key: key + 'b', w: 3.6, tex: hero ? [{ k: 'cross', c: C.orangeD, al: 0.45, gap: 6 }] : [{ k: 'hatch', c: '#0c0d1c', a: 0.8, gap: 6, al: 0.45, dens: (px) => clamp((px + 20) / 60) }] });
  paint(ellipsePts(0, 0, 70, 12, 0, 30), { fill: hero ? C.orangeD : '#1a1d3c', key: key + 'base', w: 3 });
  paint(ellipsePts(0, -172, 34, 34, 0, 30), { fill: C.cream, key: key + 'h', w: 3.4, tex: [{ k: 'hatch', a: 0.8, gap: 5, al: 0.3, dens: (px, py) => clamp((px + py + 172) / 40) }] });
  emblem(j.mark, 0, -78, key);
  if (hero) SPARK_AT = toScreen(0, -120);
  ctx.restore();
  if (nameAl > 0.01) { const nw = handW(j.name, FS, 700); handText(j.name, x - nw / 2, y + 66, FS, C.ink, { key: key + 'n', weight: 700, al: nameAl }); }
}
function crownPts(x, y, s) { return [[-30, 0], [-36, -36], [-15, -14], [0, -42], [15, -14], [36, -36], [30, 0]].map(([a, b]) => [x + a * s, y + b * s]); }
function crown(x, y, s, rot, key) {
  if (s <= 0.01) return;
  ctx.save(); ctx.translate(x, y); ctx.rotate(rot);
  paint(crownPts(0, 0, s * 0.8), { fill: C.yellow, key, w: 3, tex: [{ k: 'hatch', c: C.woodD, a: 0.8, gap: 5, al: 0.45 }] });
  ctx.restore();
}
function pillar(x, h, fill, key) {
  if (h < 2) return;
  paint(box(x - PW / 2, BASE - h, PW, h), { fill, key, w: 3, tex: [{ k: 'hatch', a: 0.8, gap: 6, al: 0.35, dens: (px) => clamp((px - x) / (PW * 0.5) + 0.3) }, { k: 'pencil', c: '#fff6e0', al: 0.3, per: 90 }] });
}
function valueLabel(str, x, y, size, color, key) { const w = handW(str, size, 700); handText(str, x - w / 2, y, size, color, { key, weight: 700 }); }

function sceneBoard() {
  const slam = T_SLAM, k = segOf(TT), focus = k >= 0 ? JOBS.find((j) => j.name === DATA.focus[k]) : null;
  boardBg();
  const title = TT < slam ? '年収（万円）' : '時給に直した額（円）';
  handText(title, 80, 104, 58, C.ink, { key: 'ttl' + title, weight: 700, frac: TT < slam ? 1 : ev(slam + 0.1, 0.5) });
  const fs = '年収 ÷（1か月の時間×12）＝ 時給', fw = handW(fs, FS, 700);
  handText(fs, 1840 - fw, 102, FS, C.red, { key: 'form', weight: 700, frac: ev(0.3, 0.8) });

  const P = JOBS.map((j) => {
    const i = j.r1 - 1, t2 = j.r2 - 1, moves = t2 !== i;
    const x = springTrack([[0, SX(i)], [slam + (moves ? i * 0.04 : 0), SX(t2)]], SPRING.smooth);
    const hop = moves ? -Math.sin(Math.PI * seg(TT, slam + i * 0.04, slam + 0.55 + i * 0.04)) * 50 : 0;
    return { j, x, y: FEET + hop };
  });
  if (focus && focus.r1 !== focus.r2) {   // the focused job's slide on the floor: old slot -> new slot
    const k0 = segT(k), x0 = SX(focus.r1 - 1), x1 = SX(focus.r2 - 1), dir = Math.sign(x1 - x0);
    planInk([[x0, FEET + 14], [x1 - dir * 70, FEET + 14]], { key: 'slide' + k, frac: ev(k0 + 0.2, 0.6), w: 3.4 });
    if (ev(k0 + 0.2, 0.6) >= 1) ink([[x1 - dir * 92, FEET + 2], [x1 - dir * 70, FEET + 14], [x1 - dir * 92, FEET + 26]], { w: 3.4, color: C.red, key: 'slideh' + k });
  }
  P.forEach(({ j, x }) => {
    const key = 'pl' + j.r1;
    const gi = springMove(0.05 + (j.r1 - 1) * 0.06, 0, 1, SPRING.heavy) * (1 - EZ.i2(seg(TT, slam - 0.1, slam + 0.15)));
    if (gi > 0.01) {
      const h = j.inc / INC_MAX * H0 * gi;
      pillar(x, h, C.yellow, key + 'i');
      if (TT < slam - 0.1 && h > 120) valueLabel(j.inc.toFixed(1), x, BASE - h - 12, FS, C.ink, key + 'iv');
    }
    const gw = springMove(slam + 0.05 + (j.r2 - 1) * 0.05, 0, 1, SPRING.playful);
    if (TT >= slam && gw > 0.01) {
      const h = j.wage / WAGE_MAX * H0 * gw, hot = focus && focus.name === j.name;
      pillar(x, h, hot ? C.terra : C.yellow, key + 'w');
      if (TT >= slam + 0.85 && h > 120) valueLabel(fmt(j.wage) + '円', x, BASE - h - 12, FS, hot ? C.red : C.ink, key + 'wv');
    }
  });
  if (TT < slam - 0.1 || TT >= slam + 0.85) for (let r = 0; r < N; r++) {   // ranks, fixed per slot, in the foot of the pillars
    const red = focus && focus.r2 - 1 === r;
    valueLabel((r + 1) + '位', SX(r), BASE - 14, FS, C.ink, 'rk' + r);
    if (red) ink(ellipsePts(SX(r), BASE - 30, 52, 30, -0.05, 30), { closed: true, w: 3.4, color: C.red, key: 'rkc' + k, frac: ev(segT(k) + 0.1, 0.4) });
  }
  const moving = TT >= slam && TT < slam + 0.8, nameAl = moving ? 0 : TT >= slam && TT < slam + 1.0 ? ev(slam + 0.8, 0.2) : 1;
  [...P].sort((a, b) => (focus && a.j.name === focus.name) - (focus && b.j.name === focus.name))
    .forEach(({ j, x, y }) => pawn(j, x, y, focus && focus.name === j.name, nameAl));
  // the crown: on 年収1位 -> falls at the slam -> onto 時給1位 (when the narration reaches it, else soon after the slam)
  const top1 = P.find((p) => p.j.r1 === 1), w1 = P.find((p) => p.j.r2 === 1);
  const kw = DATA.focus.indexOf(w1.j.name), tHop = kw >= 0 ? segT(kw) + 0.3 : slam + 1.2;
  if (TT < slam) crown(top1.x, top1.y - 206 * PS + 4, 1, -0.08, 'crown');
  else if (TT < slam + 0.7) { const u = seg(TT, slam, slam + 0.7); crown(SX(0) - 110 * u, FEET - 206 * PS + 4 + 160 * EZ.i2(u), 1 - u * 0.6, u * 2.4, 'crownF'); }
  if (TT >= tHop) crown(w1.x, w1.y - 206 * PS + 4, popS(tHop), 0.06, 'crown2');
  if (focus) {   // the stamp, top right under the formula: 年収X位 → 時給Y位
    const s = popS(segT(k) + 0.1), str = `年収${focus.r1}位 → 時給${focus.r2}位`, w = handW(str, FS, 700) + 44;
    ctx.save(); ctx.translate(1840 - w / 2, 160); ctx.rotate(-0.03); ctx.scale(s, s);
    paint(rrectPts(-w / 2, -34, w, 66, 10), { fill: C.paper, line: C.red, w: 4, key: 'stamp' + k, tex: [{ k: 'hatch', c: C.red, a: 0.8, gap: 7, al: 0.12 }] });
    handText(str, -w / 2 + 22, 15, FS, C.red, { key: 'stampt' + k, weight: 700 });
    ctx.restore();
  }
  handText('出典：' + DATA.src, 72, 762, 34, 'rgba(58,36,23,0.8)', { key: 'src', weight: 700 });
}
