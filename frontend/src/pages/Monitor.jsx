import { useEffect, useMemo, useRef, useState } from 'react'
import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip, useMap } from 'react-leaflet'
import { Link } from 'react-router-dom'
import { fmt, fmt0, useApi } from '../lib.jsx'
import { useLang } from '../i18n.jsx'
import { Icon, Logo, Spinner } from '../ui.jsx'
import '../monitor.css'

// Kür salt-water monitor: live model output, and a simulation that replays real past episodes day by day
// (same model and the same SMS rules as the farmer app), for the municipality, the state and the judges.
const COL = { red: '#FF5A5F', orange: '#F5A524', green: '#2BD49A', unknown: '#64748B' }
const LEVEL = (km, f, next) => (!f ? 'unknown' : km <= f.km ? 'red' : (km <= f.hi || (next && km <= next.km)) ? 'orange' : 'green')
const frontOf = (km) => ({ km, lo: +(km * 0.6).toFixed(1), hi: +Math.min(60, km * 1.6).toFixed(1) })
const MON = { az: ['yanvar', 'fevral', 'mart', 'aprel', 'may', 'iyun', 'iyul', 'avqust', 'sentyabr', 'oktyabr', 'noyabr', 'dekabr'],
  en: ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'] }
const dd = (iso, lang) => { const d = new Date(iso + 'T12:00:00'); return `${d.getDate()} ${MON[lang][d.getMonth()]} ${d.getFullYear()}` }
const short = (iso, lang) => { const d = new Date(iso + 'T12:00:00'); return `${d.getDate()} ${MON[lang][d.getMonth()].slice(0, 3)}` }

const SCENARIOS = [   // windows chosen around the real peaks of the 2020–2026 back-test (strongest first)
  { start: '2024-03-07', n: 16, peak: '2024-03-19', title: { az: 'Mart 2024', en: 'March 2024' },
    sub: { az: 'Ən güclü hadisə: 10 kənddə su duzlu oldu', en: 'The strongest event: salty water in 10 villages' } },
  { start: '2022-03-04', n: 12, peak: '2022-03-10', title: { az: 'Mart 2022', en: 'March 2022' },
    sub: { az: 'Qəzetlər yazdı: dəniz suyu çaya ~30 km girdi', en: 'Newspapers: sea water came ~30 km up the river' } },
  { start: '2023-02-05', n: 21, peak: '2023-02-09', title: { az: 'Fevral 2023', en: 'February 2023' },
    sub: { az: 'Dənizdən güclü külək: iki dalğa, su 34 km girdi', en: 'Strong sea wind: two waves, water came 34 km up' } },
]

const TX = {
  az: { title: 'Kür duzlu su monitoru', live: 'CANLI · BU GÜN', sim: 'KEÇMİŞ HADİSƏ', app: 'Fermer tətbiqi', home: 'Ana səhifə',
    front: 'Dəniz suyu çaya nə qədər girib', range: 'təxminən {lo}–{hi} km arası (dənizdən)', villages: 'Kürün sahilindəki 45 kənd', salty: 'Su duzludur', risk: 'Duz gəlir', fresh: 'Su təmizdir',
    why: 'Niyə belədir?', flow: 'Çayda nə qədər su axır', norm: 'adi gündən', wind: 'Dənizdən əsən külək', push: 'dəniz suyunu çaya itələyir', calm: 'zəifdir, təhlükə yoxdur', swot: 'NASA peyki: çay nə qədər güclüdür',
    phone: 'Fermerin telefonu', phoneLive: '',
    simTitle: 'Keçmişə qayıdaq: bu günlər həqiqətən olub', simSub: 'Sistem o vaxt işləsəydi, nə görərdi və fermerə nə yazardı? Hadisəni seçin, oynat düyməsini basın, xəritəyə və telefona baxın.',
    play: 'Oynat', pause: 'Dayandır', back: 'Bu günə qayıt', speed: 'Sürət', record: '2020–2026: hər gün dəniz suyu çaya nə qədər girib', day: 'Gün',
    n_weak: 'Çayda su az idi: adi gündən {p}% az.', n_ok: 'Çayda su kifayət qədərdir.',
    n_wind: 'Dənizdən güclü külək əsirdi və dəniz suyunu çaya itələyirdi.', n_calm: 'Dənizdən külək zəifdir.',
    n_front: 'Dəniz suyu çaya {km} km girdi: {v} kənddə Kürün suyu ilə sulamaq olmaz.', n_clear: 'Bütün kəndlərdə Kürün suyu təmizdir.',
    sms_warn: 'Field Shift – {v}: {on}{d} dənizin duzlu suyu sizə çata bilər. BU GÜN sulayın, hovuzu doldurun.', sms_salty: 'Field Shift – {v}: Kürün suyu indi DUZLUDUR. Nasosu işlətməyin, yığılmış sudan istifadə edin.',
    sms_salty_until: ' Təxminən {d} su yenə təmiz olacaq.', sms_fresh: 'Field Shift – {v}: Kürün suyu yenə TƏMİZDİR. Sulaya bilərsiniz.',
    alert: 'XƏBƏRDARLIQ', alert_t: '{v} kənddə Kürün suyu duzludur. Nasos işlətmək olmaz.', owner: 'Kimin telefonudur? Kəndi seçin', who: '{v} kəndində yaşayan fermer · dənizdən {km} km', soon: 'yaxın günlərdə',
    none_sim: 'Hələ mesaj yoxdur. Su dəyişəndə fermerə SMS gələcək.', none_live: 'Son 2 həftədə mesaj olmayıb: su təmizdir.',
    more: '+{n} kənd', src: 'NASA SWOT · NASA POWER · NASA GRACE · Landsat · Copernicus GloFAS' },
  en: { title: 'Kür salt-water monitor', live: 'LIVE · TODAY', sim: 'PAST EVENT', app: 'Farmer app', home: 'Home',
    front: 'How far sea water has entered the river', range: 'roughly {lo}–{hi} km from the sea', villages: '45 villages along the Kür', salty: 'Water is salty', risk: 'Salt is coming', fresh: 'Water is clean',
    why: 'Why?', flow: 'How much water the river carries', norm: 'vs a normal day', wind: 'Wind from the sea', push: 'pushes sea water into the river', calm: 'is weak, no danger', swot: 'NASA satellite: how strong the river is',
    phone: 'The farmer’s phone', phoneLive: '',
    simTitle: 'Back in time: these days really happened', simSub: 'If the system had been running then, what would it have seen and texted the farmer? Pick an event, press play, watch the map and the phone.',
    play: 'Play', pause: 'Pause', back: 'Back to today', speed: 'Speed', record: '2020–2026: how far sea water entered the river, every day', day: 'Day',
    n_weak: 'The river was low: {p}% less water than a normal day.', n_ok: 'The river has enough water.',
    n_wind: 'A strong wind from the sea was pushing sea water into the river.', n_calm: 'The wind from the sea is weak.',
    n_front: 'Sea water went {km} km up the river: {v} villages must not water with the Kür.', n_clear: 'The Kür water is clean in every village.',
    sms_warn: 'Field Shift – {v}: salty sea water may reach you {on}{d}. Water your field TODAY, fill your pond.', sms_salty: 'Field Shift – {v}: the Kür water is SALTY now. Do not pump, use stored water.',
    sms_salty_until: ' Clean again around {d}.', sms_fresh: 'Field Shift – {v}: the Kür water is CLEAN again. You can water your field.',
    alert: 'WARNING', alert_t: 'The Kür water is salty in {v} villages. Pumps must stay off.', owner: 'Whose phone? Pick a village', who: 'A farmer in {v} · {km} km from the sea', soon: 'the next days',
    none_sim: 'No messages yet. The farmer gets an SMS when the water changes.', none_live: 'No messages in the last 2 weeks: the water is clean.',
    more: '+{n} villages', src: 'NASA SWOT · NASA POWER · NASA GRACE · Landsat · Copernicus GloFAS' },
}
const OWNERS = ['Bankə', 'Xıllı', 'Surra']

// One farmer's SMS history for a run of days [{date, f}] — the same state machine as the server (alerts._salt):
// warn when salt is due within 2 days, salty when it is here, fresh again only when today and the next 2 days are clear.
function smsTimeline(days, km) {
  const lv = (i) => (days[i] ? LEVEL(km, days[i].f, days[i + 1]?.f) : 'green')
  const out = []
  let state = 'fresh'
  days.forEach((d, i) => {
    if (i >= days.length - 2) return                     // need two days ahead to decide, like the forecast
    const soon = [i + 1, i + 2]
    const level = lv(i)
    let now = level === 'red' ? 'salty' : (level === 'orange' || soon.some((j) => lv(j) === 'red')) ? 'warn' : 'fresh'
    if (state === 'salty' && now === 'warn') now = 'salty'
    if (now === 'fresh' && state !== 'fresh' && soon.some((j) => lv(j) !== 'green')) now = state
    if (now !== state) {
      const firstRed = soon.map((j) => days[j]).find((x, k) => lv(soon[k]) === 'red')?.date || null
      let freshAt = null
      for (let j = i + 1; j < days.length; j++) if (lv(j) === 'green') { freshAt = days[j].date; break }
      out.push({ date: d.date, level: now, firstRed, freshAt })
    }
    state = now
  })
  return out
}

const fill = (s, v) => Object.entries(v).reduce((a, [k, x]) => a.replace(`{${k}}`, x), s)

export default function Monitor() {
  const { lang, setLang } = useLang()
  const T = TX[lang]
  const { data: st } = useApi('/kur/state')
  const { data: geo } = useApi('/kur/geo')
  const { data: daily } = useApi('/kur/daily')
  const [sim, setSim] = useState(null)        // {sc, i, playing}
  const [speed, setSpeed] = useState(1)
  const [owner, setOwner] = useState('Xıllı')
  const [clock, setClock] = useState(new Date())
  useEffect(() => { const id = setInterval(() => setClock(new Date()), 1000); return () => clearInterval(id) }, [])

  const days = useMemo(() => {             // the simulated window, from the back-test
    if (!sim || !daily) return null
    const i0 = daily.findIndex((x) => x.d >= sim.sc.start)
    return daily.slice(i0, i0 + sim.sc.n + 2)
  }, [sim?.sc, daily]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {                        // play
    if (!sim?.playing || !days) return
    if (sim.i >= sim.sc.n - 1) { setSim({ ...sim, playing: false }); return }
    const id = setTimeout(() => setSim((s) => s && { ...s, i: s.i + 1 }), 1400 / speed)
    return () => clearTimeout(id)
  }, [sim, days, speed])

  const view = useMemo(() => {
    if (!st) return null
    if (sim && days) {
      const r = days[sim.i], n1 = days[sim.i + 1], n2 = days[sim.i + 2]
      return { live: false, date: r.d, f: frontOf(r.km), next: n1 ? frontOf(n1.km) : null, next2: n2 ? frontOf(n2.km) : null, q: r.q, u: r.u, wd: r.wd }
    }
    const fc = st.days.filter((d) => d.date > st.today)
    return { live: true, date: st.today, f: st.now.front, next: fc[0]?.front, next2: fc[1]?.front, q: st.now.q, u: st.now.u, wd: st.now.wd, head: st.swot?.head, headDate: st.swot?.date }
  }, [st, sim, days])

  const vill = useMemo(() => (geo && view ? geo.villages.map((v) => ({ ...v, level: LEVEL(v.km, view.f, view.next) })) : []), [geo, view])
  const counts = vill.reduce((a, v) => ({ ...a, [v.level]: (a[v.level] || 0) + 1 }), { red: 0, orange: 0, green: 0 })

  const ownerV = geo?.villages.find((v) => v.name === owner)
  const sms = useMemo(() => {             // the chosen farmer's messages up to the shown day, newest first
    if (!ownerV || !st) return []
    let run, upto
    if (sim && days) { run = days.map((x) => ({ date: x.d, f: frontOf(x.km) })); upto = days[sim.i].d }
    else {
      run = st.days.filter((x) => x.front).map((x) => ({ date: x.date, f: x.front }))
      run = run.slice(Math.max(0, run.findIndex((x) => x.date >= st.today) - 14))
      upto = st.today
    }
    return smsTimeline(run, ownerV.km).filter((m) => m.date <= upto).reverse().map((m) => ({
      ...m, id: m.date + m.level,
      text: m.level === 'warn' ? fill(T.sms_warn, { v: owner, on: m.firstRed ? (lang === 'en' ? 'on ' : '') : (lang === 'en' ? 'in ' : ''), d: m.firstRed ? short(m.firstRed, lang) : T.soon })
        : m.level === 'salty' ? fill(T.sms_salty, { v: owner }) + (m.freshAt ? fill(T.sms_salty_until, { d: short(m.freshAt, lang) }) : '')
          : fill(T.sms_fresh, { v: owner }),
    }))
  }, [ownerV, st, sim?.i, days, lang]) // eslint-disable-line react-hooks/exhaustive-deps

  const start = (sc) => setSim({ sc, i: 0, playing: true })
  const stop = () => setSim(null)

  if (!st || !geo || !view) return <div className="mn mn-load"><Spinner /></div>
  const qn = st.norms?.q || 334
  const qp = Math.round((view.q / qn - 1) * 100)
  const story = [
    qp <= -15 ? fill(T.n_weak, { q: fmt0(view.q), p: Math.abs(qp) }) : fill(T.n_ok, { q: fmt0(view.q) }),
    view.u >= 5 ? fill(T.n_wind, { u: fmt(view.u, 1) }) : T.n_calm,
    counts.red ? fill(T.n_front, { km: fmt0(view.f.km), v: counts.red }) : T.n_clear,
  ]
  const lvlNow = counts.red ? 'red' : counts.orange ? 'orange' : 'green'

  return (
    <div className={`mn mn-${lvlNow}`}>
      <header className="mn-top">
        <Link to="/" className="mn-brand"><Logo s={40} /><div><b>Field Shift</b><span>{T.title}</span></div></Link>
        <div className={`mn-mode ${view.live ? 'live' : 'sim'}`}><i />{view.live ? T.live : T.sim} · {dd(view.date, lang)}</div>
        <div className="mn-right">
          <span className="mn-clock">{clock.toLocaleTimeString('az-AZ', { hour: '2-digit', minute: '2-digit' })} · Bakı</span>
          <button className="mn-pill" onClick={() => setLang(lang === 'az' ? 'en' : 'az')}>{lang === 'az' ? 'EN' : 'AZ'}</button>
          <Link className="mn-pill solid" to="/app">{T.app}</Link>
        </div>
      </header>

      <div className="mn-main">
        <section className="mn-map">
          <RiverMap geo={geo} f={view.f} villages={vill} />
          {counts.red > 0 && <div className="mn-alert" key={`a${counts.red}`}><Icon n="alert" s={20} /><b>{T.alert}</b><span>{fill(T.alert_t, { v: counts.red })}</span></div>}
          <div className="mn-front">
            <div className="mn-k">{T.front}</div>
            <div className="mn-big"><Count v={view.f.km} d={1} /><small>km</small></div>
            <div className="mn-sub">{fill(T.range, { lo: fmt0(view.f.lo), hi: fmt0(view.f.hi) })}</div>
            <div className="mn-gauge"><div style={{ width: `${Math.min(100, view.f.km / 60 * 100)}%` }} /></div>
            <div className="mn-gauge-l"><span>0</span><span>30</span><span>60 km</span></div>
          </div>
          <div className="mn-story" key={view.date}>{story.map((s) => <p key={s}>{s}</p>)}</div>
          <div className="mn-legend"><span><i style={{ background: COL.red }} />{T.salty}</span><span><i style={{ background: COL.orange }} />{T.risk}</span><span><i style={{ background: COL.green }} />{T.fresh}</span></div>
        </section>

        <aside className="mn-side">
          <div className="mn-card">
            <div className="mn-h">{T.villages}</div>
            <div className="mn-counts">
              <div className="c-red"><b><Count v={counts.red} /></b><span>{T.salty}</span></div>
              <div className="c-orange"><b><Count v={counts.orange} /></b><span>{T.risk}</span></div>
              <div className="c-green"><b><Count v={counts.green} /></b><span>{T.fresh}</span></div>
            </div>
            <div className="mn-bar">{['red', 'orange', 'green'].map((k) => <i key={k} className={`c-${k}`} style={{ flex: counts[k] || 0.0001 }} />)}</div>
          </div>

          <div className="mn-card">
            <div className="mn-h">{T.why}</div>
            <div className="mn-why">
              <div><span>{T.flow}</span><b>{fmt0(view.q)} m³/s</b><em className={qp <= -15 ? 'mn-bad' : 'mn-good'}>{qp > 0 ? '+' : ''}{qp}% {T.norm}</em>
                <div className="mn-meter"><i style={{ width: `${Math.min(100, (view.q / qn) * 50)}%` }} className={qp <= -15 ? 'mn-bad' : 'mn-good'} /><s style={{ left: '50%' }} /></div></div>
              <div><span>{T.wind}</span><b><span className="mn-arrow" style={{ transform: `rotate(${(view.wd || 0) + 180}deg)` }}>↑</span>{fmt(view.u, 1)} m/s</b>
                <em className={view.u >= 5 ? 'mn-bad' : 'mn-good'}>{view.u >= 5 ? T.push : T.calm}</em>
                <div className="mn-meter"><i style={{ width: `${Math.min(100, view.u / 10 * 100)}%` }} className={view.u >= 5 ? 'mn-bad' : 'mn-good'} /><s style={{ left: '50%' }} /></div></div>
              {view.live && view.head != null && <div><span>{T.swot}</span><b>{fmt(view.head, 2)} m</b><em className={view.head < 0.8 ? 'mn-bad' : 'mn-good'}>{dd(view.headDate, lang)}</em>
                <div className="mn-meter"><i style={{ width: `${Math.min(100, view.head / 3.4 * 100)}%` }} className={view.head < 0.8 ? 'mn-bad' : 'mn-good'} /><s style={{ left: '50%' }} /></div></div>}
            </div>
          </div>

          <div className="mn-phone">
            <div className="mn-h">{T.phone}</div>
            <div className="mn-owner-l">{T.owner}</div>
            <div className="mn-owner" role="radiogroup" aria-label={T.owner}>{OWNERS.map((o) => {
              const v = geo.villages.find((x) => x.name === o)
              return <button key={o} role="radio" aria-checked={o === owner} className={o === owner ? 'on' : ''} onClick={() => setOwner(o)}>{o}<small>{v ? `${Math.round(v.km)} km` : ''}</small></button>
            })}</div>
            <div className="mn-screen">
              <div className="mn-notch" />
              {ownerV && <div className="mn-who"><Icon n="user" s={13} />{fill(T.who, { v: owner, km: Math.round(ownerV.km) })}</div>}
              <div className="mn-msgs">
                {sms.length ? sms.map((m) => (
                  <div key={m.id} className={`mn-sms s-${m.level}`}>
                    <div className="mn-sms-h"><b><Icon n="msg" s={12} />SMS · Field Shift</b><span>{short(m.date, lang)} · 08:00</span></div>
                    <p>{m.text}</p>
                  </div>)) : <p className="mn-empty">{sim ? T.none_sim : T.none_live}</p>}
              </div>
            </div>
          </div>
        </aside>
      </div>

      <footer className="mn-sim">
        <div className="mn-sim-head">
          <div><div className="mn-h">{T.simTitle}</div><p>{T.simSub}</p></div>
          {sim && <div className="mn-ctrl">
            <button className="mn-play" onClick={() => setSim({ ...sim, playing: !sim.playing, i: !sim.playing && sim.i >= sim.sc.n - 1 ? 0 : sim.i })}>{sim.playing ? <Icon n="pause" s={18} /> : <Icon n="play" s={18} />}</button>
            <div className="mn-speed">{[1, 2, 4].map((x) => <button key={x} className={speed === x ? 'on' : ''} onClick={() => setSpeed(x)}>{x}×</button>)}</div>
            <button className="mn-pill" onClick={stop}>● {T.back}</button>
          </div>}
        </div>
        {!sim ? <div className="mn-scen">
          {SCENARIOS.map((sc) => (
            <button key={sc.start} onClick={() => start(sc)}>
              <span className="mn-scen-play"><Icon n="play" s={16} /></span>
              <div><b>{sc.title[lang]}</b><span>{sc.sub[lang]}</span></div>
            </button>))}
          <Record daily={daily} T={T} />
        </div> : <div className="mn-track">
          <div className="mn-days">
            {days && days.slice(0, sim.sc.n).map((d, i) => (
              <button key={d.d} className={`${i === sim.i ? 'on' : ''} ${i < sim.i ? 'past' : ''} ${d.d === sim.sc.peak ? 'peak' : ''}`}
                onClick={() => setSim({ ...sim, i, playing: false })} title={dd(d.d, lang)}>
                <i style={{ height: `${Math.max(6, Math.min(100, d.km / 55 * 100))}%` }} className={d.km >= 30 ? 'hi' : d.km >= 20 ? 'mid' : ''} />
                <span>{short(d.d, lang)}</span>
              </button>))}
          </div>
          <div className="mn-track-l"><b>{sim.sc.title[lang]}</b> · {T.day} {sim.i + 1} / {sim.sc.n} · {sim.sc.sub[lang]}</div>
        </div>}
        <div className="mn-src">{T.src}</div>
      </footer>
    </div>
  )
}

function Record({ daily, T }) {
  const pts = useMemo(() => {
    if (!daily?.length) return null
    const n = daily.length, step = Math.max(1, Math.floor(n / 500))
    const keep = daily.filter((x, i) => i % step === 0 || x.km >= 28)
    return keep.map((x) => `${((daily.indexOf(x) / (n - 1)) * 600).toFixed(1)},${(70 - Math.min(x.km, 60) / 60 * 64).toFixed(1)}`).join(' ')
  }, [daily])
  if (!pts) return null
  return (
    <div className="mn-rec">
      <span>{T.record}</span>
      <svg viewBox="0 0 600 72" preserveAspectRatio="none"><line x1="0" x2="600" y1={70 - 30 / 60 * 64} y2={70 - 30 / 60 * 64} /><polyline points={pts} /></svg>
    </div>
  )
}

function Count({ v, d = 0 }) {
  const [n, setN] = useState(v)
  const prev = useRef(v)
  useEffect(() => {
    const a = prev.current, b = v, t0 = performance.now()
    let raf
    const step = (t) => { const k = Math.min(1, (t - t0) / 600); setN(a + (b - a) * (1 - (1 - k) ** 3)); if (k < 1) raf = requestAnimationFrame(step); else prev.current = b }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [v])
  return <>{d ? fmt(n, d) : fmt0(n)}</>
}

function Fit({ geo }) {
  const map = useMap()
  useEffect(() => {
    const pts = geo.river.filter((r) => r.stem === 'kur' && r.km <= 95).flatMap((r) => r.line.map((p) => [p[1], p[0]]))
    const fit = () => {
      const w = map.getSize().x
      if (!w) return
      map.fitBounds(pts, w > 820 ? { paddingTopLeft: [360, 40], paddingBottomRight: [40, 60] } : { padding: [24, 24] })
    }
    fit()
    map.on('resize', fit)
    return () => { map.off('resize', fit) }
  }, [geo, map])
  return null
}

function RiverMap({ geo, f, villages }) {
  const { data: sat } = useApi('/satellite')
  const segs = useMemo(() => {
    const out = []
    geo.river.filter((r) => r.stem === 'kur' && r.km <= 170).forEach((r) => {
      let cur = null
      r.line.forEach((p, i) => {
        const km = r.kms[i]
        const c = km <= f.km ? 'red' : km <= f.hi ? 'orange' : 'green'
        const ll = [p[1], p[0]]
        if (!cur || cur.c !== c) { const prev = cur?.pts[cur.pts.length - 1]; cur = { c, pts: prev ? [prev, ll] : [ll] }; out.push(cur) } else cur.pts.push(ll)
      })
    })
    return out
  }, [geo, f])
  return (
    <MapContainer center={[39.5, 49.1]} zoom={9} zoomSnap={0.25} style={{ height: '100%', background: '#06090C' }} zoomControl={false} attributionControl={false}>
      {sat?.truecolor && <TileLayer url={sat.truecolor} maxNativeZoom={9} maxZoom={13} className="mn-tiles" />}
      <Fit geo={geo} />
      {segs.map((s, i) => <Polyline key={`g${i}`} positions={s.pts} pathOptions={{ color: COL[s.c], weight: 18, opacity: 0.16, lineCap: 'round' }} />)}
      {segs.map((s, i) => <Polyline key={`l${i}`} positions={s.pts} pathOptions={{ color: COL[s.c], weight: 5, opacity: 1, lineCap: 'round', className: s.c === 'red' ? 'mn-flow' : '' }} />)}
      {villages.map((v) => (
        <CircleMarker key={v.name + v.km} center={[v.lat, v.lon]} radius={v.level === 'red' ? 6.5 : 4.5}
          pathOptions={{ color: '#06090C', weight: 1.5, fillColor: COL[v.level], fillOpacity: 1, className: v.level === 'red' ? 'mn-ping' : '' }}>
          <Tooltip direction="top" className="mn-tip">{v.name} · {Math.round(v.km)} km</Tooltip>
        </CircleMarker>))}
    </MapContainer>
  )
}
