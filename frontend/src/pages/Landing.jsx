import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib.jsx'
import { useLang } from '../i18n.jsx'
import { Icon, Logo } from '../ui.jsx'
import '../landing.css'

// Cinematic story landing: one full-screen scene at a time, the "next" card expands into the next scene.
// Every number comes from the app's own data (data/kur/*, NASA SWOT / POWER / GRACE, GloFAS) or is fetched live.
const IMG = '/img/land/'

const SCENES = [
  {
    id: 'xezer', img: 'caspian', credit: { az: 'NASA Terra MODIS · Xəzər dənizi · 3 sentyabr 2025', en: 'NASA Terra MODIS · Caspian Sea · 3 September 2025' },
    title: { az: 'Xəzər', en: 'Caspian' }, kicker: { az: 'Problem', en: 'The problem' },
    lead: { az: 'Dəniz suyu çaya geri girir. Fermer bunu görmür.', en: 'Sea water is flowing back into the river. Farmers cannot see it.' },
    facts: {
      az: [['Duz', 'Xəzər suyunun hər litrində 12–13 qram duz var.'], ['Bitki üçün', 'Suvarma üçün yararlı həddən 7 dəfə duzludur (~20 dS/m, FAO həddi 3).'],
        ['Gizlidir', 'Duzlu su ağırdır və çayın dibi ilə gedir. Üstdən su şirin görünür.'], ['Nəticə', 'Bir dəfə duzlu su ilə suvarılan sahədə məhsul yanır, torpaq illərlə duzlu qalır.']],
      en: [['Salt', 'Every litre of Caspian water carries 12–13 g of salt.'], ['For crops', 'Seven times saltier than irrigation can bear (~20 dS/m vs the FAO limit of 3).'],
        ['Hidden', 'Salt water is heavier and creeps along the river bed. The surface still looks fresh.'], ['Result', 'One irrigation with it burns the crop and leaves the soil salty for years.']],
    },
  },
  {
    id: 'kur', img: 'delta', credit: { az: 'NASA Terra MODIS · Kür deltası · 3 sentyabr 2025', en: 'NASA Terra MODIS · Kür delta · 3 September 2025' },
    title: { az: 'Kür', en: 'Kür' }, kicker: { az: 'Çay zəifləyir', en: 'A weakening river' },
    lead: { az: 'Kür güclü olanda dənizi geri itələyir. Zəifləyəndə dəniz içəri girir.', en: 'A strong Kür holds the sea back. A weak one lets it in.' },
    facts: {
      az: [['Su ehtiyatı', 'Azərbaycanın su ehtiyatı son 4 quraq ildə 25%-dən çox azalıb.'], ['Axın', 'Kürün ağzında orta axın saniyədə 334 m³-dir. Bundan aşağı düşəndə risk başlayır.'],
        ['Ərazi', 'Kürün son 160 km-i: Neftçala və Salyanda 45 kənd.'], ['2 gün əvvəl', 'Yuxarıda azalan su dənizə 2 günə çatır. Biz bunu əvvəlcədən görürük.']],
      en: [['Water', 'Azerbaijan’s water resources fell by more than 25 % over four dry years.'], ['Flow', 'Median flow at the mouth is 334 m³/s. Below it, the risk begins.'],
        ['Where', 'The last 160 km of the Kür: 45 villages in Neftçala and Salyan.'], ['2 days ahead', 'A drop upstream reaches the sea in about 2 days. We see it coming.']],
    },
  },
  {
    id: 'grace', chart: 'grace', credit: { az: 'NASA GRACE / GRACE-FO · Kür–Araz hövzəsi · 2002–2022', en: 'NASA GRACE / GRACE-FO · Kür–Araz basin · 2002–2022' },
    title: { az: 'Qravitasiya', en: 'Gravity' }, kicker: { az: 'NASA GRACE', en: 'NASA GRACE' },
    lead: { az: 'Su ağırdır. Harada su azalırsa, orada Yerin cazibəsi zəifləyir. NASA bunu kosmosdan ölçür.', en: 'Water has weight. Where water disappears, gravity gets weaker. NASA measures it from space.' },
    facts: {
      az: [['Necə', 'İki peyk 220 km aralı uçur. Su azalanda aralarındakı məsafə mikron qədər dəyişir.'], ['Nə gördü', 'Kür–Araz hövzəsi 2002–2022-də 22.5 sm su itirib.'],
        ['Hər il', 'Orta hesabla ildə 1.48 sm.'], ['Mənası', 'Bütün hövzə su itirir. Kürün zəifləməsinin fonu budur.']],
      en: [['How', 'Two satellites fly 220 km apart. Less water below changes their distance by micrometres.'], ['What it saw', 'The Kür–Araz basin lost 22.5 cm of water from 2002 to 2022.'],
        ['Every year', '1.48 cm on average.'], ['Meaning', 'The whole basin is drying. That is the background of a weaker Kür.']],
    },
  },
  {
    id: 'swot', img: 'river', credit: { az: 'NASA HLS (Landsat + Sentinel-2), 30 m · Salyan yaxınlığında Kür · 11 oktyabr 2025', en: 'NASA HLS (Landsat + Sentinel-2), 30 m · the Kür near Salyan · 11 October 2025' },
    title: { az: 'SWOT', en: 'SWOT' }, kicker: { az: 'Kosmosdan çayın gücü', en: 'River strength from space' },
    lead: { az: 'NASA-nın SWOT peyki çayın su səviyyəsini kosmosdan santimetr dəqiqliyi ilə ölçür.', en: 'NASA’s SWOT satellite measures the river’s water level from space, to the centimetre.' },
    facts: {
      az: [['Ölçmə', 'Kürün 13-cü və 51-ci km-i arasındakı səviyyə fərqi çayın gücünü göstərir.'], ['Normal', '1.7 metr. Çay dənizə doğru axır və onu itələyir.'],
        ['10 mart 2024', 'Cəmi 0.26 metr. Çay demək olar ki, düzləşmişdi və dənizi itələyə bilmirdi.'], ['Tezlik', 'Peyk 21 gündə bir keçir. 17 ölçmə modelə daxil edilib.']],
      en: [['Measurement', 'The level drop between km 13 and km 51 shows how hard the river pushes.'], ['Normal', '1.7 m: the river runs downhill and pushes the sea back.'],
        ['10 March 2024', 'Only 0.26 m. The river had almost gone flat and could not push the sea.'], ['Revisit', 'Every 21 days. 17 passes are in the model.']],
    },
  },
  {
    id: 'wind', img: 'event2022', credit: { az: 'NASA Aqua MODIS · 10 mart 2022 · bulud zolaqları küləyin izidir', en: 'NASA Aqua MODIS · 10 March 2022 · cloud streets trace the wind' },
    title: { az: 'Külək', en: 'Wind' }, kicker: { az: 'Dəniz itələyir', en: 'The sea pushes' },
    lead: { az: 'Şimal-şərq küləyi Xəzərin suyunu Kürün ağzına yığır və çaya itələyir.', en: 'A north-east wind piles Caspian water at the mouth and drives it into the river.' },
    facts: {
      az: [['Bu şəkil', '10 mart 2022: duzlu suyun Kürə ~30 km girdiyi gün. Bulud zolaqları küləyin istiqamətini göstərir.'], ['Həmin gün', 'Külək saniyədə 7.5 m, 39.5° istiqamətdən. Çayın axını saniyədə 219 m³.'],
        ['Data', 'NASA POWER: 2020-dən bu günə hər günün küləyi.'], ['Proqnoz', 'Gələn 16 günün küləyi hər 3 saatdan bir yenilənir.']],
      en: [['This image', '10 March 2022: the day salt water reached ~30 km up the Kür. The cloud streets show the wind.'], ['That day', 'Wind 7.5 m/s from 39.5°. River flow 219 m³/s.'],
        ['Data', 'NASA POWER: the wind of every day since 2020.'], ['Forecast', 'The next 16 days of wind, refreshed every 3 hours.']],
    },
  },
  {
    id: 'proof', chart: 'backtest', credit: { az: 'Field Shift modeli · hər gün yenidən hesablanıb · 2020–2026', en: 'Field Shift model · every day re-computed · 2020–2026' },
    title: { az: 'Sübut', en: 'Proof' }, kicker: { az: 'Keçmişi yoxladıq', en: 'We tested the past' },
    lead: { az: 'Model 2020-dən bu günə qədər hər gün üçün yenidən hesablandı.', en: 'The model was re-run for every single day since 2020.' },
    facts: {
      az: [['2,506 gün', '2020-ci ilin yanvarından bu günə hər gün.'], ['Mart 2022', 'Mətbuat duzlu suyun ~30 km girdiyini yazdı. Model 29.6 km göstərdi.'],
        ['Mart 2024', 'Model 52.8 km göstərdi. SWOT həmin ay çayın düzləşdiyini ölçdü.'], ['2023', 'Duzlu su 8 gün 30 km-dən uzağa getdi.']],
      en: [['2,506 days', 'Every day from January 2020 to today.'], ['March 2022', 'The press reported ~30 km. The model gave 29.6 km.'],
        ['March 2024', 'The model gave 52.8 km. SWOT measured a flat river that month.'], ['2023', 'Salt water went beyond 30 km on 8 days.']],
    },
  },
  {
    id: 'alert', img: 'fields', live: true, credit: { az: 'NASA HLS, 30 m · Neftçala tarlaları · 11 oktyabr 2025', en: 'NASA HLS, 30 m · fields near Neftçala · 11 October 2025' },
    title: { az: 'Xəbərdarlıq', en: 'Warning' }, kicker: { az: 'Hər gün, hər nasos üçün', en: 'Every day, every pump' },
    lead: { az: 'Hər nasosun yerinə görə bir cavab: bu gün Kürdən su çəkmək olar, ya yox.', en: 'One answer for every pump: can you draw water from the Kür today?' },
    facts: {
      az: [['Şirin', 'Su şirindir. Suvar, hovuzu doldur.'], ['Diqqət', 'Duzlu su gəlir. Bu gün sula, ehtiyat yığ.'],
        ['Duzlu', 'Nasosu işlətmə. Yığılmış sudan istifadə et.'], ['SMS', 'Yalnız vəziyyət dəyişəndə, 1–2 gün əvvəldən. 16 günlük proqnoz.']],
      en: [['Fresh', 'Water is fresh. Irrigate, fill the pond.'], ['Caution', 'Salt water is coming. Irrigate today, store water.'],
        ['Salty', 'Do not pump. Use stored water.'], ['SMS', 'Only when the status changes, 1–2 days ahead. 16-day outlook.']],
    },
  },
  {
    id: 'start', img: 'delta', end: true, credit: { az: 'NASA Terra MODIS · Kür deltası', en: 'NASA Terra MODIS · Kür delta' },
    title: { az: 'Field Shift', en: 'Field Shift' }, kicker: { az: 'Başla', en: 'Start' },
    lead: { az: 'Telefon nömrəsi və kənd: 1 dəqiqə. Qalanını peyklər edir.', en: 'A phone number and a village: one minute. Satellites do the rest.' },
    facts: {
      az: [['Torpaq', 'Landsat (30 m) hər kəndin torpaq duzunu 5 ildir izləyir.'], ['Bitki', '27 bitkinin duza dözümlülüyü (FAO): nə əkmək olar, nə yox.'],
        ['Suvarma', 'Nə vaxt və nə qədər sulamaq lazımdır (FAO-56), duzlu günlərdən yan keçərək.'], ['Fermer kömək edir', '"Suyum necə idi?" Hər ölçmə modeli dəqiqləşdirir.']],
      en: [['Soil', 'Landsat (30 m) has tracked the soil salt of every village for 5 years.'], ['Crops', 'Salt tolerance of 27 crops (FAO): what can grow, what cannot.'],
        ['Irrigation', 'When and how much to irrigate (FAO-56), around the salty days.'], ['Farmers help', '"How was my water?" Every report sharpens the model.']],
    },
  },
]

const UI = {
  az: { next: 'Növbəti', story: 'Hekayə', monitor: 'Monitor', app: 'Tətbiq', open: 'Tətbiqə keç', live: 'CANLI', today: 'Bu gün Xəzərin suyu Kürə', km: 'km girib',
    flow: 'Kürün axını', wind: 'Dəniz küləyi', demo: 'Demo fermer kimi bax', monitorBtn: 'Canlı monitor', scroll: 'Sürüşdür və ya kartı bas', loading: 'Peyk datası yüklənir',
    g_title: 'Su ehtiyatı, sm (GRACE)', b_title: 'Duzlu suyun Kürə girdiyi məsafə, km (hər gün)', b_press: 'mətbuat ~30 km', b_swot: 'SWOT: çay düzdür', startOver: 'Əvvələ qayıt', cm: 'sm' },
  en: { next: 'Next', story: 'Story', monitor: 'Monitor', app: 'App', open: 'Open the app', live: 'LIVE', today: 'Today Caspian water reaches', km: 'km up the Kür',
    flow: 'Kür flow', wind: 'Sea wind', demo: 'Look around as a demo farmer', monitorBtn: 'Live monitor', scroll: 'Scroll or tap the card', loading: 'Loading satellite data',
    g_title: 'Water storage, cm (GRACE)', b_title: 'How far salt water entered the Kür, km (every day)', b_press: 'press ~30 km', b_swot: 'SWOT: flat river', startOver: 'Back to start', cm: 'cm' },
}

const bg = (s) => (s.img ? `${IMG}${s.img}.jpg` : null)
const thumb = (s) => (s.img ? `${IMG}${s.img}_s.jpg` : null)
const num = (i) => `[${String(i + 1).padStart(2, '0')}]`

export default function Landing() {
  const { lang, setLang } = useLang()
  const u = UI[lang]
  const [idx, setIdx] = useState(0)
  const [fly, setFly] = useState(null)          // {to, from: rect, go: bool}
  const [ready, setReady] = useState(0)          // preload progress 0..100
  const [tilt, setTilt] = useState({ x: 0, y: 0 })
  const [live, setLive] = useState(null)
  const [grace, setGrace] = useState(null)
  const [daily, setDaily] = useState(null)
  const portal = useRef(null)
  const touch = useRef(null)
  const s = SCENES[idx]
  const nextI = (idx + 1) % SCENES.length
  const nx = SCENES[nextI]

  useEffect(() => {   // preload every background, count progress
    const srcs = [...new Set(SCENES.flatMap((x) => (x.img ? [bg(x), thumb(x)] : [])))]
    let done = 0
    srcs.forEach((src) => { const im = new Image(); im.onload = im.onerror = () => { done += 1; setReady(Math.round((done / srcs.length) * 100)) }; im.src = src })
    api('/kur/state').then((st) => setLive(st?.now ? { km: st.now.front?.km, q: st.now.q, u: st.now.u, at: st.updated } : null)).catch(() => {})
    api('/kur/grace').then(setGrace).catch(() => {})
    api('/kur/daily?start=2020-01-01').then(setDaily).catch(() => {})
  }, [])

  const go = (to) => {
    if (fly || to === idx) return
    const r = portal.current?.getBoundingClientRect()
    const from = r && r.width ? r : { left: innerWidth / 2 - 80, top: innerHeight / 2 - 90, width: 160, height: 180 }
    setFly({ to, from, go: false })
    requestAnimationFrame(() => requestAnimationFrame(() => setFly((f) => f && { ...f, go: true })))
    setTimeout(() => { setIdx(to); setFly(null) }, 1150)
  }
  const step = (d) => go((idx + d + SCENES.length) % SCENES.length)

  useEffect(() => {
    let last = 0
    const wheel = (e) => { const t = Date.now(); if (t - last < 1300 || Math.abs(e.deltaY) < 25) return; last = t; step(e.deltaY > 0 ? 1 : -1) }
    const key = (e) => { if (['ArrowDown', 'ArrowRight', 'PageDown', ' '].includes(e.key)) step(1); if (['ArrowUp', 'ArrowLeft', 'PageUp'].includes(e.key)) step(-1) }
    addEventListener('wheel', wheel, { passive: true }); addEventListener('keydown', key)
    return () => { removeEventListener('wheel', wheel); removeEventListener('keydown', key) }
  })

  const move = (e) => {
    const r = portal.current?.getBoundingClientRect()
    if (!r) return
    setTilt({ x: ((e.clientY - (r.top + r.height / 2)) / innerHeight) * -14, y: ((e.clientX - (r.left + r.width / 2)) / innerWidth) * 18 })
  }
  const title = s.title[lang]
  const tref = useRef(null)
  useLayoutEffect(() => {   // fit the giant title to its column: as big as possible, never wrapped or clipped
    const fit = () => {
      const el = tref.current
      if (!el) return
      const max = Math.min(innerWidth * 0.19, innerHeight * 0.3)
      el.style.fontSize = `${max}px`
      const room = el.parentElement.clientWidth
      if (el.scrollWidth > room) el.style.fontSize = `${Math.floor(max * room / el.scrollWidth)}px`
    }
    fit()
    document.fonts?.ready.then(fit)
    addEventListener('resize', fit)
    return () => removeEventListener('resize', fit)
  }, [idx, lang])
  const flyTo = fly ? SCENES[fly.to] : null

  return (
    <main className={`land ${fly ? 'is-flying' : ''} ${ready >= 100 ? 'is-ready' : ''}`} onMouseMove={move}
      onTouchStart={(e) => { touch.current = e.touches[0].clientY }} onTouchEnd={(e) => {
        const d = touch.current - e.changedTouches[0].clientY; if (Math.abs(d) > 50) step(d > 0 ? 1 : -1)
      }}>
      <div className="land-bgs" aria-hidden="true">
        {SCENES.map((x, i) => (x.img
          ? <img key={x.id} src={bg(x)} alt="" className={`land-bg ${i === idx ? 'on' : ''}`} />
          : <div key={x.id} className={`land-bg void ${i === idx ? 'on' : ''}`} />))}
      </div>
      <div className="land-shade" aria-hidden="true" />

      {flyTo && <div className={`land-fly ${fly.go ? 'go' : ''}`} style={{
        '--t': `${fly.from.top}px`, '--l': `${fly.from.left}px`, '--r': `${innerWidth - fly.from.left - fly.from.width}px`, '--b': `${innerHeight - fly.from.top - fly.from.height}px`,
        backgroundImage: flyTo.img ? `url(${bg(flyTo)})` : 'none' }} />}

      <div className={`land-pre ${ready >= 100 ? 'done' : ''}`} aria-hidden={ready >= 100}>
        <Logo s={68} />
        <div className="land-count">{ready}<small>%</small></div>
        <div className="land-pre-t">{u.loading}</div>
      </div>

      <header className="land-head land-chrome">
        <Link to="/" className="land-brand"><Logo s={36} />Field Shift</Link>
        <div className="land-actions">
          <nav className="land-nav">
            <a className="on" href="#story">{u.story}</a><Link to="/monitor">{u.monitor}</Link><Link to="/app">{u.app}</Link>
          </nav>
          <button className="land-lang" onClick={() => setLang(lang === 'az' ? 'en' : 'az')}>{lang === 'az' ? 'EN' : 'AZ'}</button>
          <Link className="land-cta" to="/app">{u.open}</Link>
        </div>
      </header>

      <aside className="land-list land-chrome" aria-label="Scenes">
        {SCENES.map((x, i) => <button key={x.id} className={i === idx ? 'on' : ''} onClick={() => go(i)}>{x.title[lang]}</button>)}
      </aside>

      {s.chart && <div className="land-chart land-chrome" key={`c${idx}${lang}`}>
        {s.chart === 'grace' ? <GraceChart g={grace} u={u} /> : <BacktestChart d={daily} u={u} />}
      </div>}

      {s.live && live && <div className="land-live land-chrome" key={`l${idx}${lang}`}>
        <div className="land-live-k"><i />{u.live} · {live.at}</div>
        <div className="land-live-v">{u.today} <b>{live.km?.toFixed(1)}</b> {u.km}</div>
        <div className="land-live-s">{u.flow}: {live.q} m³/s · {u.wind}: {live.u?.toFixed(1)} m/s</div>
      </div>}

      {!s.end && <section className="land-portal-wrap land-chrome" aria-label={u.next}>
        <div className="land-portal-head"><span>{u.next}:</span><span>{num(nextI)} <b>{nx.title[lang]}</b></span></div>
        <button ref={portal} className="land-portal" onClick={() => go(nextI)} aria-label={`${u.next}: ${nx.title[lang]}`}
          style={{ transform: `perspective(900px) rotateX(${tilt.x}deg) rotateY(${tilt.y}deg)`, backgroundImage: nx.img ? `url(${thumb(nx)})` : 'none' }}>
          {!nx.img && <span className="land-portal-chart">{nx.chart === 'grace' ? `−22.5 ${u.cm}` : '2,506'}</span>}
        </button>
        <div className="land-hint">{u.scroll}</div>
      </section>}

      {s.end && <section className="land-end land-chrome" key={`e${lang}`}>
        <Link className="land-cta big" to="/app">{u.open} <Icon n="chev" s={16} /></Link>
        <Link className="land-ghost" to="/monitor">{u.monitorBtn}</Link>
        <button className="land-ghost" onClick={() => go(0)}>{u.startOver}</button>
      </section>}

      <section className="land-content land-chrome" key={`s${idx}${lang}`}>
        <div className="land-left">
          <div className="land-kicker">{num(idx)} {s.kicker[lang]}</div>
          <p className="land-lead">{s.lead[lang]}</p>
          <h1 ref={tref} className="land-title">{title}</h1>
        </div>
        <dl className="land-facts">
          {s.facts[lang].map(([k, v], i) => <div key={k} className="land-fact" style={{ animationDelay: `${0.25 + i * 0.09}s` }}><dt>{k}</dt><dd>{v}</dd></div>)}
        </dl>
      </section>
      <div className="land-credit land-chrome">{s.credit[lang]}</div>
      <div className="land-progress land-chrome"><b>{String(idx + 1).padStart(2, '0')}</b> / {String(SCENES.length).padStart(2, '0')}</div>
    </main>
  )
}

function GraceChart({ g, u }) {
  const pts = useMemo(() => {
    if (!g?.series?.length) return null
    const s = g.series, t0 = Date.parse(s[0].date), t1 = Date.parse(s[s.length - 1].date)
    const lo = Math.min(...s.map((p) => p.cm)), hi = Math.max(...s.map((p) => p.cm))
    const X = (d) => 40 + ((Date.parse(d) - t0) / (t1 - t0)) * 900, Y = (v) => 30 + ((hi - v) / (hi - lo)) * 300
    return { line: s.map((p) => `${X(p.date).toFixed(1)},${Y(p.cm).toFixed(1)}`).join(' '), Y, X, lo, hi, s }
  }, [g])
  if (!pts) return null
  const a = pts.s[0], b = pts.s[pts.s.length - 1]
  return (
    <figure className="land-fig">
      <figcaption>{u.g_title}</figcaption>
      <svg viewBox="0 0 980 380" role="img" aria-label={u.g_title}>
        <line x1="40" x2="940" y1={pts.Y(0)} y2={pts.Y(0)} className="ax" />
        <polyline points={`40,${pts.Y(pts.lo)} ${pts.line} 940,${pts.Y(pts.lo)}`} className="area" />
        <polyline points={pts.line} className="ln" />
        <text x="40" y="372" className="lb">{a.date.slice(0, 4)}</text>
        <text x="940" y="372" textAnchor="end" className="lb">{b.date.slice(0, 4)}</text>
        <text x="940" y={pts.Y(b.cm) + 34} textAnchor="end" className="big">{g.change_cm} {u.cm}</text>
      </svg>
    </figure>
  )
}

function BacktestChart({ d, u }) {
  const pts = useMemo(() => {
    if (!d?.length) return null
    const t0 = Date.parse(d[0].d), t1 = Date.parse(d[d.length - 1].d)
    const X = (s) => 40 + ((Date.parse(s) - t0) / (t1 - t0)) * 900, Y = (v) => 330 - (Math.min(v, 60) / 60) * 300
    const step = Math.max(1, Math.floor(d.length / 700))
    const line = d.filter((_, i) => i % step === 0 || d[i].km >= 30).map((p) => `${X(p.d).toFixed(1)},${Y(p.km).toFixed(1)}`).join(' ')
    const years = []
    for (let y = Number(d[0].d.slice(0, 4)); y <= Number(d[d.length - 1].d.slice(0, 4)); y++) years.push(y)
    return { X, Y, line, years }
  }, [d])
  if (!pts) return null
  return (
    <figure className="land-fig">
      <figcaption>{u.b_title}</figcaption>
      <svg viewBox="0 0 980 380" role="img" aria-label={u.b_title}>
        {[20, 30].map((v) => <g key={v}><line x1="40" x2="940" y1={pts.Y(v)} y2={pts.Y(v)} className="ax dash" /><text x="36" y={pts.Y(v) + 4} textAnchor="end" className="lb">{v}</text></g>)}
        <polyline points={pts.line} className="ln thin" />
        <circle cx={pts.X('2022-03-10')} cy={pts.Y(29.6)} r="7" className="dot" />
        <text x={pts.X('2022-03-10')} y={pts.Y(29.6) - 16} textAnchor="middle" className="lb hl">{u.b_press}</text>
        <circle cx={pts.X('2024-03-19')} cy={pts.Y(52.8)} r="7" className="dot" />
        <text x={pts.X('2024-03-19')} y={pts.Y(52.8) - 16} textAnchor="middle" className="lb hl">{u.b_swot}</text>
        {pts.years.map((y) => <text key={y} x={pts.X(`${y}-07-01`)} y="372" textAnchor="middle" className="lb">{y}</text>)}
      </svg>
    </figure>
  )
}
