import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, fmt, fmt0, useApi, useAuth } from '../lib.jsx'
import { useLang } from '../i18n.jsx'
import { Icon, Logo, Spinner } from '../ui.jsx'
import { FarmModal, ObsModal, RiverMap, SignupModal } from './Kur.jsx'
import '../app-dark.css'

// Field Shift as a phone app: sign up → add the field → one screen per field (concept §4), map, SMS, profile.
const LVL = { green: 'g', orange: 'o', red: 'r', unknown: 'u' }
const CROP = { az: { arpa: 'arpa', pambiq: 'pambıq', 'seker-cugunduru': 'şəkər çuğunduru', bugda: 'buğda', pomidor: 'pomidor', qargidali: 'qarğıdalı', yemis: 'yemiş', uzum: 'üzüm', sogan: 'soğan', kartof: 'kartof', gunebaxan: 'günəbaxan' },
  en: { arpa: 'barley', pambiq: 'cotton', 'seker-cugunduru': 'sugar beet', bugda: 'wheat', pomidor: 'tomato', qargidali: 'maize', yemis: 'melon', uzum: 'grape', sogan: 'onion', kartof: 'potato', gunebaxan: 'sunflower' } }
const cn = (id, lang) => CROP[lang][id] || id
const MON = { az: ['yanvar', 'fevral', 'mart', 'aprel', 'may', 'iyun', 'iyul', 'avqust', 'sentyabr', 'oktyabr', 'noyabr', 'dekabr'], en: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'] }
const niceDate = (iso, lang) => { const d = new Date(iso + 'T12:00:00'); return `${d.getDate()} ${MON[lang][d.getMonth()]}` }
const WEEK = { az: ['B.', 'B.e.', 'Ç.a.', 'Ç.', 'C.a.', 'C.', 'Ş.'], en: ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'] }

const QS = new URLSearchParams(typeof window !== 'undefined' ? window.location.search : '')
const EMBED = QS.get('embed') === '1'

export default function KurApp() {
  const { user, ready, login } = useAuth()
  useEffect(() => {   // dark theme for the app and its modals (portalled to <body>)
    document.body.classList.add('app-dark')
    return () => document.body.classList.remove('app-dark')
  }, [])
  useEffect(() => {   // inside the monitor's phone frame: open the shared demo farmer
    if (EMBED && ready && !user) api('/auth/demo', { method: 'POST' }).then((r) => login(r.token)).catch(() => {})
  }, [ready, user, login])
  const [tab, setTab] = useState('home')
  const [sim, setSim] = useState(null)       // real past days re-run through the model, for demonstrations
  const [toasts, setToasts] = useState([])
  const [simSms, setSimSms] = useState([])
  const pushSms = (m) => {
    const id = Math.random()
    setSimSms((x) => [m, ...x].slice(0, 30))
    setToasts((x) => [...x, { ...m, id }])
    setTimeout(() => setToasts((x) => x.filter((y) => y.id !== id)), 4200)
  }
  useEffect(() => { if (!sim) setSimSms([]) }, [sim])
  useEffect(() => {   // ?sim=YYYY-MM-DD: replay 16 real days starting there (used by the monitor)
    const d = QS.get('sim')
    if (!d || !user) return
    api(`/kur/replay?day=${d}&n=16`).then((r) => setSim({ ...r, i: 0, playing: true, ep: { start: d, n: 16 } })).catch(() => {})
  }, [user])
  const { data: mine, reload } = useApi(user ? '/me/kur' : null)
  useEffect(() => { const id = setInterval(() => reload(), 5 * 60 * 1000); return () => clearInterval(id) }, [reload])
  const { data: geo } = useApi('/kur/geo')
  if (!ready) return <div className="app app-solo"><Spinner /></div>
  if (!user) return <Welcome />
  if (!mine) return <div className="app app-solo"><Spinner /></div>
  if (!mine.farms.length) return <Setup geo={geo} onDone={reload} />
  return (
    <div className={`app ${EMBED ? 'embed' : ''}`}>
      <Player sim={sim} setSim={setSim} farms={mine.farms} onSms={pushSms} />
      <Toasts items={toasts} />
      <div className="app-body">
        {tab === 'home' && <div className="home-grid">
          <div className="home-main"><Home mine={mine} reload={reload} sim={sim} onSms={() => setTab('sms')} /></div>
          <aside className="home-map"><HomeMap geo={geo} mine={mine} sim={sim} /></aside>
        </div>}
        {tab === 'map' && <MapTab geo={geo} mine={mine} sim={sim} />}
        {tab === 'sms' && <SmsTab mine={mine} reload={reload} simSms={sim ? simSms : null} />}
        {tab === 'profile' && <Profile geo={geo} mine={mine} reload={reload} />}
      </div>
      <Tabs tab={tab} setTab={setTab} />
    </div>
  )
}

/* ---------------------------------------------------------------- simulation: real past salt episodes, played day by day */

export function levelAt(km, f, next) {
  if (!f) return 'unknown'
  if (km <= f.km) return 'red'
  if (km <= f.hi || (next && km <= next.km)) return 'orange'
  return 'green'
}

function simView(sim) {
  const days = sim.days.slice(sim.i)
  return { date: days[0].date, front: days[0].front, days, u: days[0].u, q: days[0].q }
}

function simStatus(km, sim) {
  const v = simView(sim)
  const days = v.days.map((d, k) => ({ date: d.date, level: levelAt(km, d.front, v.days[k + 1]?.front), u: d.u, fc: k > 0 }))
  const level = days[0].level
  return { level, model_level: level, front: v.front, days, reported: 0,
    fresh_again: level !== 'green' ? days.find((d, k) => k > 0 && d.level === 'green')?.date || null : null }
}

// same rule as the server: tell the farmer only when the situation changes
function smsState(st) {
  if (st.level === 'red') return 'salty'
  if (st.level === 'orange' || st.days.slice(1, 3).some((d) => d.level === 'red')) return 'warn'
  return 'fresh'
}

function Player({ sim, setSim, farms, onSms }) {
  const { t, lang } = useLang()
  const last = useRef({})
  useEffect(() => {
    if (!sim?.playing) return
    const id = setTimeout(() => {
      if (sim.i >= sim.days.length - 1) setSim({ ...sim, playing: false })
      else setSim({ ...sim, i: sim.i + 1 })
    }, 1300)
    return () => clearTimeout(id)
  }, [sim, setSim])
  useEffect(() => {                          // SMS when a farm's state changes during the replay
    if (!sim) return
    const day = simView(sim).date
    farms.filter((f) => f.farm.pump_km != null).forEach((f) => {
      const st = simStatus(f.farm.pump_km, sim)
      let now = smsState(st)
      const before = last.current[f.farm.id] ?? 'fresh'
      if (before === 'salty' && now === 'warn') now = 'salty'      // after "salty" the next message is only "fresh again"
      if (now === 'fresh' && before !== 'fresh' && st.days.slice(1, 3).some((d) => d.level !== 'green')) now = before   // same rule as the server: no flip-flop
      if (now !== before) {
        const when = st.days.find((d) => d.level === 'red')?.date
        const text = now === 'salty' ? t('sms_salty', { f: f.farm.name })
          : now === 'warn' ? t('sms_warn', { f: f.farm.name, d: niceDate(when || day, lang) }) : t('sms_fresh', { f: f.farm.name })
        onSms({ day, text, level: now })
      }
      last.current[f.farm.id] = now
    })
  }, [sim?.i, sim?.date]) // eslint-disable-line react-hooks/exhaustive-deps
  if (!sim) return null   // replays live on the monitor only; the farmer's app shows real days
  const v = simView(sim)
  return (
    <div className="sim on">
      <div className="sim-top">
        <button className="sim-pp" onClick={() => setSim({ ...sim, playing: !sim.playing, i: !sim.playing && sim.i >= sim.days.length - 1 ? 0 : sim.i })}>{sim.playing ? <Icon n="pause" s={16} /> : <Icon n="play" s={16} />}</button>
        <div className="sim-txt"><b>{niceDate(v.date, lang)} {v.date.slice(0, 4)}</b><span>{t('sim_label', { km: fmt0(v.front.km) })}</span></div>
        <button className="sim-x" onClick={() => setSim(null)}>{t('sim_off')}</button>
      </div>
      <input type="range" min="0" max={sim.days.length - 1} value={sim.i} onChange={(e) => setSim({ ...sim, i: +e.target.value, playing: false })} />
    </div>
  )
}

function Toasts({ items }) {
  return <div className="toasts">{items.map((x) => <div key={x.id} className={`toast t-${x.level}`}><b><Icon n="msg" s={12} />SMS</b>{x.text}</div>)}</div>
}

function Tabs({ tab, setTab }) {
  const { t } = useLang()
  const items = [['home', 'sprout', t('tab_home')], ['map', 'map', t('tab_map')], ['sms', 'msg', 'SMS'], ['profile', 'users', t('tab_profile')]]
  return (
    <nav className="app-tabs">
      <div className="app-brand"><Logo s={34} />Field Shift</div>
      <Link className="app-mon" to="/monitor"><Icon n="chart" s={18} />{t('monitor_btn')}</Link>
      {items.map(([k, ic, l]) => <button key={k} className={tab === k ? 'on' : ''} onClick={() => { setTab(k); window.scrollTo(0, 0) }}><Icon n={ic} s={20} /><span>{l}</span></button>)}
    </nav>
  )
}

/* ---------------------------------------------------------------- welcome / sign in */
function Welcome() {
  const { t } = useLang()
  const { login } = useAuth()
  const [mode, setMode] = useState(null)
  const demo = async () => { const r = await api('/auth/demo', { method: 'POST' }); await login(r.token) }
  return (
    <div className="welcome-wrap">
    <div className="welcome-art"><div><h2>{t('hero_1')} {t('hero_2')} {t('hero_3')}</h2><p>NASA Terra MODIS · {t('delta')}</p></div></div>
    <div className="app app-welcome">
      <div className="app-logo-wrap"><Logo s={68} /></div>
      <h1>Field Shift</h1>
      <p>{t('app_tag')}</p>
      {!mode ? <div className="app-welcome-btns">
        <button className="k-btn" onClick={() => setMode('new')}>{t('r_new')}</button>
        <button className="k-btn ghost" onClick={() => setMode('login')}>{t('r_login')}</button>
        <div className="app-or">{t('or')}</div>
        <button className="k-btn ghost" onClick={demo}>{t('demo_btn')}</button>
        <Link className="k-btn dark" to="/monitor">{t('monitor_btn')}</Link>
      </div> : <div className="app-card"><SignupModal inline startMode={mode} /></div>}
      <div className="app-foot">NASA SWOT · NASA POWER · Landsat</div>
    </div>
    </div>
  )
}

function Setup({ geo, onDone }) {
  const { t } = useLang()
  return (
    <div className="app app-solo">
      <div className="app-body">
        <h2 className="app-title">{t('setup_title')}</h2>
        <p className="app-sub">{t('setup_sub')}</p>
        <div className="app-card">{geo ? <FarmModal inline geo={geo} onSaved={onDone} /> : <Spinner />}</div>
      </div>
    </div>
  )
}

/* ---------------------------------------------------------------- home: the farmer's screen (concept §4) */
function Home({ mine, reload, onSms, sim }) {
  const { t, lang } = useLang()
  const [obs, setObs] = useState(null)
  return (
    <>
      <div className="app-head"><h2 className="app-title">{t('tab_home')}</h2>
        {sim ? <span className="live sim-b">{t('sim_badge')}</span> : <span className="live"><i />{t('live')} · {mine.updated ? mine.updated.slice(11, 16) : ''}</span>}</div>
      <TodayStrip sim={sim} />
      {mine.farms.map((f) => <FieldScreen key={f.farm.id} f={sim && f.farm.pump_km != null ? { ...f, status: simStatus(f.farm.pump_km, sim) } : f}
        smsOn={mine.sms_on && !!mine.phone} onSms={onSms} onObs={() => setObs(f.farm)} />)}
      {obs && <ObsModal farm={obs} onClose={() => setObs(null)} onSaved={() => { setObs(null); reload() }} />}
    </>
  )
}

function TodayStrip({ sim }) {
  const { t, lang } = useLang()
  const { data: st } = useApi('/kur/state')
  const v = sim ? simView(sim) : st?.now ? { date: st.today, front: st.now.front, q: st.now.q, u: st.now.u } : null
  if (!v?.front) return null
  const az = lang === 'az'
  return (
    <div className="ah">
      <div className="ah-k"><span className="live"><i /></span>{sim ? t('sim_badge') : `${t('live')} · ${niceDate(v.date, lang)}`}</div>
      <div className="ah-v">{fmt(v.front.km, 1)}<small>km</small></div>
      <div className="ah-t">{az ? 'Xəzərin duzlu suyu bu gün Kürə bu qədər girib (dənizdən).' : 'How far salty Caspian water has entered the Kür today (from the sea).'}</div>
      <div className="ah-s">
        {v.q != null && <span>{az ? 'Kürün axını' : 'Kür flow'}: {fmt0(v.q)} m³/s</span>}
        {v.u != null && <span>{az ? 'Dəniz küləyi' : 'Sea wind'}: {fmt(v.u, 1)} m/s</span>}
        <span>NASA SWOT · POWER · GloFAS</span>
      </div>
    </div>
  )
}

function FieldScreen({ f, smsOn, onSms, onObs }) {
  const { t, lang } = useLang()
  const [showCrops, setShowCrops] = useState(false)
  const { farm, status, soil, crops, tolerant } = f
  const lvl = status?.level || 'unknown'
  const today = [...(status?.days || [])].reverse().find((d) => !d.fc)?.date || status?.days?.[0]?.date
  const tomorrow = status?.days.find((d) => d.fc)
  const ec = soil.ec
  const sat = soil.satellite
  const sLvl = ec == null ? null : ec < 2 ? 'g' : ec < 4 ? 'o' : 'r'
  const salty = (ec != null && ec >= 2) || sat?.trend === 'up'
  const sensitive = crops.filter((c) => c.ece != null && c.ece < (ec != null ? Math.max(ec, 4) : 4)).map((c) => c.id)
  const better = tolerant.filter((id) => !farm.crops.includes(id)).slice(0, 2)
  const todo = []
  if (status?.reported && status.model_level === 'green') todo.push(t('do_check'))
  if (lvl === 'red') todo.push(t('do_stored'))
  else todo.push(salty ? t('do_pond_wash') : t('do_pond_now'))
  if (salty && sensitive.length && better.length) todo.push(t('plant_x', { a: better.map((c) => cn(c, lang)).join(lang === 'az' ? ' və ya ' : ' or '), b: sensitive.map((c) => cn(c, lang)).join(', ') }))
  return (
    <div className={`fs fs-${LVL[lvl]}`}>
      <div className="fs-where"><Icon n="pin" s={16} />{farm.name} · Kür, {fmt0(farm.pump_km)}{lang === 'az' ? '-ci km' : ' km'}</div>

      <div className="fs-sec">
        <div className="fs-h">{t('water_today')}</div>
        <div className="fs-status"><i />{t(`st_${lvl}`)}</div>
        <p>{status?.reported && status.model_level === 'green' ? t(status.reported >= 2 ? 'reported_many' : 'reported_one')
          : lvl === 'red' ? t('st_red_say', { km: fmt0(status?.front?.km) }) : lvl === 'orange' ? t('st_orange_say') : t('st_green_say')}</p>
        {tomorrow && tomorrow.u >= 5 && <p className="fs-muted">{t('tomorrow_wind')}</p>}
        {lvl !== 'green' && status?.fresh_again && <p className="fs-muted">{t('fresh_again', { d: niceDate(status.fresh_again, lang) })}</p>}
        <div className="fs-week">{(status?.days || []).filter((d) => d.date >= (today || '')).slice(0, 7).map((d, i) => (
          <span key={d.date} className={`fs-d fs-${LVL[d.level]}`} title={d.date}><b />{i === 0 ? t('today') : WEEK[lang][new Date(d.date + 'T12:00:00').getDay()]}</span>))}</div>
      </div>

      <div className="fs-sec">
        <div className="fs-h">{t('soil_title')}<button className="fs-link" onClick={() => setShowCrops(!showCrops)}>{t('crops_table')}</button></div>
        {sLvl ? <div className={`fs-status sm fs-${sLvl}`}><i />{t(`soil_lvl_${sLvl === 'g' ? 'ok' : sLvl === 'o' ? 'mid' : 'bad'}`)}{sat ? <span> · {t(`trend_${sat.trend}`)}</span> : null}</div>
          : <p className="fs-muted">{sat ? `${t('sat_says')}: ${t(`trend_${sat.trend}`)}. ` : ''}{t('soil_unmeasured')}</p>}
        {showCrops && <CropTable ec={ec} />}
      </div>

      <div className="fs-sec">
        <div className="fs-h">{t('what_do')}</div>
        <ul>{todo.map((x) => <li key={x}>{x}</li>)}</ul>
      </div>

      <div className="fs-btns">
        <button className={`k-btn ${smsOn ? 'ghost' : ''}`} onClick={onSms}><Icon n="msg" s={16} />{smsOn ? t('sms_active') : t('sms_get')}</button>
        <button className="k-btn ghost" onClick={onObs}><Icon n="drop" s={16} />{t('obs_how')}</button>
      </div>
    </div>
  )
}

function CropTable({ ec }) {
  const { t, lang } = useLang()
  const { data } = useApi('/kur/crops')
  const keep = ['arpa', 'pambiq', 'seker-cugunduru', 'bugda', 'pomidor', 'qargidali', 'sogan']
  return (
    <div className="fs-crops">
      <p className="fs-muted">{t('crops_help')}</p>
      {(data || []).filter((c) => keep.includes(c.id)).map((c) => (
        <div key={c.id} className={`fs-crop ${ec != null ? (c.ece > ec ? 'ok' : 'bad') : ''}`}>
          <span>{lang === 'az' ? c.name_az : c.name}</span><b>~{c.ece} dS/m</b>
        </div>))}
    </div>
  )
}

function HomeMap({ geo, mine, sim }) {
  const { t } = useLang()
  const { data: st } = useApi('/kur/state')
  const front = sim ? simView(sim).front : st?.now?.front
  const marks = mine.farms.filter((f) => f.farm.lat).map((f) => ({ pos: [f.farm.lat, f.farm.lon], c: '#0F172A', r: 7, label: f.farm.name }))
  return (
    <div className="hm">
      <div className="hm-head"><b>{front ? t('front_today', { km: fmt0(front.km) }) : '…'}</b></div>
      <div className="hm-map">{geo && front ? <RiverMap geo={geo} front={front} marks={marks} /> : <Spinner />}</div>
      <div className="k-legend"><i style={{ background: '#E5484D' }} />{t('st_red')}<i style={{ background: '#F5A524' }} />{t('st_orange')}<i style={{ background: '#12A594' }} />{t('st_green')}</div>
    </div>
  )
}

/* ---------------------------------------------------------------- map (municipality view) */
function MapTab({ geo, mine, sim }) {
  const { t, lang } = useLang()
  const { data: st } = useApi('/kur/state')
  const { data: obs } = useApi('/kur/obs?days=7')
  const [pick, setPick] = useState(null)
  const [live, setLive] = useState(null)
  const front = sim ? simView(sim).front : st?.now?.front
  useEffect(() => {
    if (!pick || sim) { setLive(null); return }
    api(`/kur/km/${pick.km}`).then(setLive).catch(() => setLive(null))
  }, [pick, sim])
  const status = pick ? (sim ? simStatus(pick.km, sim) : live) : null
  const marks = [
    ...(obs || []).filter((o) => o.kind === 'water' && o.salty != null).map((o) => ({ pos: [o.lat, o.lon], c: o.salty ? '#E5484D' : '#12A594', r: 5 })),
    ...mine.farms.filter((f) => f.farm.lat).map((f) => ({ pos: [f.farm.lat, f.farm.lon], c: '#0F172A', r: 7, label: f.farm.name })),
  ]
  const lvl = status?.level
  return (
    <>
      <h2 className="app-title">{t('tab_map')}</h2>
      <p className="app-sub">{front ? t('front_today', { km: fmt0(front.km) }) : '…'} {t('map_tap')}</p>
      <div className="app-map">{geo && front ? <RiverMap geo={geo} front={front} sel={pick} marks={marks}
        onPick={(p) => setPick({ km: p.km, label: `Kür · ${fmt0(p.km)} km` })} onVillage={(v) => setPick({ km: v.km, label: v.name })} /> : <Spinner />}</div>
      <div className="k-legend"><i style={{ background: '#E5484D' }} />{t('st_red')}<i style={{ background: '#F5A524' }} />{t('st_orange')}<i style={{ background: '#12A594' }} />{t('st_green')}</div>
      {pick && <div className={`sheet fs-${LVL[lvl || 'unknown']}`}>
        <div className="fs-where"><Icon n="pin" s={16} />{pick.label} · Kür, {fmt0(pick.km)} km</div>
        {!status ? <Spinner /> : <>
          <div className="fs-status"><i />{t(`st_${lvl}`)}</div>
          <p>{lvl === 'red' ? t('st_red_say', { km: fmt0(status.front?.km) }) : lvl === 'orange' ? t('st_orange_say') : t('st_green_say')}</p>
          {status.fresh_again && <p className="fs-muted">{t('fresh_again', { d: niceDate(status.fresh_again, lang) })}</p>}
        </>}
      </div>}
    </>
  )
}

/* ---------------------------------------------------------------- SMS */
function SmsTab({ mine, reload, simSms }) {
  const { t } = useLang()
  const { user, refresh } = useAuth()
  const on = mine.sms_on && !!mine.phone
  const turnOn = async () => {
    await api('/me', { method: 'PUT', body: { name: user.name, phone: user.phone || '', bio: user.bio || '', whatsapp: user.whatsapp || '', telegram: user.telegram || '', show_phone: !!user.show_phone, sms_alerts: true } })
    await refresh(); reload()
  }
  return (
    <>
      <h2 className="app-title">SMS</h2>
      <div className="app-card sms-state">
        {on ? <><b>{t('sms_on')}</b><span>{mine.phone}</span></> : <><b>{t('sms_off_short')}</b><button className="k-btn sm" onClick={turnOn}>{t('sms_get')}</button></>}
        <p className="fs-muted">{t('sms_when')}</p>
      </div>
      {simSms && <><h3 className="app-h3">{t('sim_sms')}</h3>{simSms.length ? simSms.map((m, i) => <div key={i} className={`k-bubble t-${m.level}`}>{m.text}<small>{m.day}</small></div>) : <p className="fs-muted">{t('sim_sms_none')}</p>}<h3 className="app-h3">{t('real_sms')}</h3></>}
      {mine.sms?.length ? mine.sms.map((m, i) => <div key={i} className="k-bubble">{m.body}<small>{m.created_at?.slice(0, 16)}</small></div>)
        : <p className="fs-muted" style={{ marginTop: 16 }}>{t('sms_none')}</p>}
    </>
  )
}

/* ---------------------------------------------------------------- profile */
function Profile({ geo, mine, reload }) {
  const { t, lang, setLang } = useLang()
  const { user, logout } = useAuth()
  const [add, setAdd] = useState(false)
  const del = async (id) => { await api(`/me/farms/${id}`, { method: 'DELETE' }); reload() }
  useEffect(() => { setAdd(false) }, [mine])
  return (
    <>
      <h2 className="app-title">{t('tab_profile')}</h2>
      <div className="pf-grid"><div>
      <div className="app-card">
        <div className="pf-row"><span>{t('r_name')}</span><b>{user.name}</b></div>
        <div className="pf-row"><span>{t('r_phone')}</span><b>{user.phone || '—'}</b></div>
        <div className="pf-row"><span>{lang === 'az' ? 'Dil' : 'Language'}</span><button className="k-btn ghost sm" onClick={() => setLang(lang === 'az' ? 'en' : 'az')}>{lang === 'az' ? 'English' : 'Azərbaycanca'}</button></div>
      </div>
      <h3 className="app-h3">{t('my_farms')}</h3>
      <div className="app-card">
        {mine.farms.map(({ farm }) => (
          <div key={farm.id} className="pf-row"><span className="pf-farm"><Icon n="pin" s={15} />{farm.name} · {fmt0(farm.pump_km)} km · {farm.crops.map((c) => cn(c, lang)).join(', ')}</span>
            <button className="k-btn ghost sm" onClick={() => del(farm.id)}>{t('delete')}</button></div>))}
        {add ? <FarmModal inline geo={geo} onSaved={reload} /> : <button className="k-btn ghost sm" onClick={() => setAdd(true)}><Icon n="plus" s={14} />{t('add_farm')}</button>}
      </div>
      </div><div>
      <MyObs />
      <h3 className="app-h3">{t('sources_title')}</h3>
      <div className="app-card">
        {[['NASA SWOT', 'src_swot'], ['NASA POWER', 'src_power'], ['NASA GPM', 'src_gpm'], ['NASA GRACE', 'src_grace'], ['Landsat', 'src_landsat'], ['SoilGrids', 'src_soilgrids'], ['GloFAS', 'src_glofas']].map(([n, k]) => (
          <div key={n} className="pf-row"><b>{n}</b><span>{t(k)}</span></div>))}
      </div>
      <button className="k-btn ghost" style={{ marginTop: 18, width: '100%' }} onClick={logout}>{t('logout')}</button>
      </div></div>
    </>
  )
}

function MyObs() {
  const { t, lang } = useLang()
  const { data, reload } = useApi('/me/obs')
  const del = async (id) => { await api(`/me/obs/${id}`, { method: 'DELETE' }); reload() }
  return <>
    <h3 className="app-h3">{t('my_obs')}</h3>
    <div className="app-card">
      {!data ? <Spinner /> : data.length ? data.map((o) => (
        <div key={o.id} className="pf-row">
          <span>{niceDate(o.observed_at, lang)} · {o.kind === 'water' ? t('o_water') : t('o_soil')}{o.km != null ? ` · ${fmt0(o.km)} km` : ''} · <b className={o.salty ? 'bad' : 'good'}>{o.ec != null ? `${fmt(o.ec, 1)} dS/m` : o.salty ? t('o_salty') : t('o_fresh')}</b></span>
          <button className="k-btn ghost sm" onClick={() => del(o.id)}>{t('delete')}</button>
        </div>)) : <p className="fs-muted">{t('my_obs_none')}</p>}
    </div>
  </>
}

export const fmtKm = (v) => fmt(v, 0)
