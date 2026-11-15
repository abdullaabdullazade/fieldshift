import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip, useMap, useMapEvents } from 'react-leaflet'
import { api, fmt, fmt0, useApi, useAuth } from '../lib.jsx'
import { useLang } from '../i18n.jsx'
import { ErrorBox, Icon, Modal, Select, Seg, Spinner } from '../ui.jsx'
import { inPoly } from './Account.jsx'
import { useGeo } from './MapPage.jsx'

const C = { red: '#E5484D', orange: '#F5A524', green: '#12A594', unknown: '#94A3B8' }
const DAYS = { az: ['B.', 'B.e.', 'Ç.a.', 'Ç.', 'C.a.', 'C.', 'Ş.'], en: ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'] }
const dayName = (iso, lang) => DAYS[lang][new Date(iso + 'T12:00:00').getDay()]

export default function Kur() {
  const { t, lang } = useLang()
  const { user } = useAuth()
  const { data: st, error } = useApi('/kur/state')
  const { data: geo } = useApi('/kur/geo')
  const { data: mine, reload: reloadMine } = useApi(user ? '/me/kur' : null)
  const { data: obs } = useApi('/kur/obs?days=7')
  const obsMarks = (obs || []).filter((o) => o.kind === 'water' && o.salty != null).map((o) => ({ pos: [o.lat, o.lon], c: o.salty ? C.red : C.green, r: 5 }))
  const [sel, setSel] = useState(null)
  const [status, setStatus] = useState(null)
  const [modal, setModal] = useState(null)

  const options = useMemo(() => {
    const o = []
    ;(mine?.farms || []).forEach((f) => f.farm.pump_km != null && o.push({ value: `farm:${f.farm.id}`, label: `${t('my_pump')} · ${f.farm.name}`, hint: `${fmt(f.farm.pump_km, 0)} km`, km: f.farm.pump_km, group: t('my_farms') }))
    ;(geo?.villages || []).forEach((v) => o.push({ value: `v:${v.name}`, label: v.name, hint: `${fmt(v.km, 0)} km`, km: v.km, group: lang === 'az' ? 'Kəndlər' : 'Villages' }))
    return o
  }, [geo, mine, t, lang])

  useEffect(() => {
    if (!options.length || sel?.manual) return
    const def = options.find((o) => o.value.startsWith('farm:')) || options.find((o) => o.label === 'Neftçala') || options[0]
    if (sel?.value !== def.value) setSel({ value: def.value, km: def.km, label: def.label })
  }, [options, sel])
  useEffect(() => {
    if (!sel) return
    api(`/kur/km/${sel.km}`).then(setStatus).catch(() => setStatus(null))
  }, [sel, st])

  const loc = useLocation()
  useEffect(() => {
    if (!loc.hash) return
    const id = setTimeout(() => document.getElementById(loc.hash.slice(1))?.scrollIntoView({ behavior: 'smooth' }), 300)
    if (loc.hash === '#farm' && user) api('/me/alerts/read', { method: 'POST' }).catch(() => {})
    return () => clearTimeout(id)
  }, [loc.hash, mine, user])

  const pickKm = (km, label) => setSel({ value: `p:${km}`, km, label: label || `Kür · ${fmt(km, 1)} km`, manual: true })
  const now = st?.now

  return (
    <div className="k">
      {/* ------------------------------------------------ hero: NASA image of the Kür delta */}
      <section className="k-hero">
        <div className="k-hero-text">
          <h1 className="k-h1">{t('hero_1')} {t('hero_2')} {t('hero_3')}</h1>
          <p className="k-lead">{t('hero_lead')}</p>
          <div className="k-hero-cta">
            {user ? <a href="#farm" className="k-btn">{t('my_farms')} <Icon n="chev" s={14} /></a>
              : <button className="k-btn" onClick={() => setModal({ kind: 'signup' })}>{t('cta_btn')} <Icon n="chev" s={14} /></button>}
            <a href="#map" className="k-btn glass">{t('map_chip')}</a>
          </div>
        </div>
        <StatusCard st={st} error={error} status={status} sel={sel} options={options} setSel={setSel} />
        <div className="k-hero-credit">NASA Terra MODIS · {lang === 'az' ? 'Kür deltası' : 'Kür delta'} · 3.9.2025</div>
      </section>

      {/* ------------------------------------------------ map (for the municipality and the state) */}
      <section className="k-row" id="map">
        <div className="k-rowcard">
          <div className="k-rowtop"><span className="k-chipl"><Icon n="map" s={12} />{t('map_chip')}</span><span className="k-num">01</span></div>
          <h2 className="k-h2">{now?.front ? <>{t('front_now')} {fmt0(now.front.km)} km</> : t('map_title')}</h2>
          <p className="k-p">{t('map_text')}</p>
          <div className="k-legend"><i style={{ background: C.red }} />{t('map_legend_red')}<i style={{ background: C.orange }} />{t('map_legend_or')}<i style={{ background: C.green }} />{t('map_legend_fresh')}</div>
        </div>
        <div className="k-panel iris k-mapbox">
          <div className="k-map">{geo && now ? <RiverMap geo={geo} front={now.front} sel={sel} marks={obsMarks} onPick={(p) => pickKm(p.km)} onVillage={(v) => pickKm(v.km, v.name)} /> : <Spinner />}</div>
        </div>
      </section>

      {/* ------------------------------------------------ 03 your field */}
      <section className="k-sec" id="farm">
        <div className="k-sechead">
          <h2 className="k-h2 big">{user ? t('my_farms') : t('cta_title')}</h2>
          <p className="k-p">{user ? t('farm_sub') : t('cta_text')}</p>
        </div>
        {!user ? <div className="k-cta">
          <div><div className="k-cta-sms">{t('sms_example')}</div></div>
          <button className="k-btn" onClick={() => setModal({ kind: 'signup' })}>{t('cta_btn')} <Icon n="chev" s={14} /></button>
        </div> : (
          <MyFarms mine={mine} today={st?.today || ''} onIrrigated={async (f) => { await api(`/me/farms/${f.id}/irrigated`, { method: 'POST', body: {} }); reloadMine() }} onAdd={() => setModal({ kind: 'farm' })} onObs={(f) => setModal({ kind: 'obs', farm: f })}
            onPick={(f) => { setSel({ value: `farm:${f.id}`, km: f.pump_km, label: f.name, manual: true }); window.scrollTo({ top: 0, behavior: 'smooth' }) }} />
        )}
      </section>

      {modal?.kind === 'signup' && <SignupModal onClose={() => setModal(null)} onDone={() => setModal({ kind: 'farm' })} />}
      {modal?.kind === 'farm' && <FarmModal geo={geo} onClose={() => setModal(null)} onSaved={() => { setModal(null); reloadMine() }} />}
      {modal?.kind === 'obs' && <ObsModal farm={modal.farm} onClose={() => setModal(null)} onSaved={() => { setModal(null); reloadMine() }} />}
    </div>
  )
}

/* ---------------------------------------------------------------- status (glass card in the hero) */
function StatusCard({ st, error, status, sel, options, setSel }) {
  const { t, lang } = useLang()
  const lvl = status?.level || 'unknown'
  const say = lvl === 'red' ? t('say_red') : lvl === 'orange' ? t('say_orange') : lvl === 'green' ? t('say_green') : ''
  return (
    <div className={`k-status k-${lvl}`}>
      <Select label={t('pick_place')} value={sel?.value} placeholder={t('pick_place')} searchable
        onChange={(v) => { const o = options.find((x) => x.value === v); if (o) setSel({ value: o.value, km: o.km, label: o.label, manual: true }) }}
        options={options} />
      <ErrorBox error={error} />
      {!st || !status ? <Spinner /> : <>
        <div className="k-signal"><span className="k-light" />{t(`lvl_${lvl}`)}</div>
        <p className="k-say">{say}</p>
        {status.fresh_again && lvl !== 'green' && <p className="k-note">{t('fresh_again', { d: shortDate(status.fresh_again, lang) })}</p>}
        {status.first_red && lvl === 'green' && <p className="k-note">{t('salt_from', { d: shortDate(status.first_red, lang) })}</p>}
        {status.reported && <p className="k-note">{t('reported')}</p>}
        <div className="k-week">
          {status.days.filter((d) => d.date >= st.today).slice(0, 7).map((d, i) => (
            <div key={d.date} className={`k-day k-${d.level}`}><span>{i === 0 ? t('today') : dayName(d.date, lang)}</span><i /></div>))}
        </div>
      </>}
    </div>
  )
}

const shortDate = (iso, lang) => {
  const d = new Date(iso + 'T12:00:00')
  const mon = { az: ['yanvar', 'fevral', 'mart', 'aprel', 'may', 'iyun', 'iyul', 'avqust', 'sentyabr', 'oktyabr', 'noyabr', 'dekabr'], en: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'] }
  return `${d.getDate()} ${mon[lang][d.getMonth()]}`
}




/* ---------------------------------------------------------------- map */
function segments(geo, front) {
  const col = (km) => (!front ? C.unknown : km <= front.km ? C.red : km <= front.hi ? C.orange : C.green)
  const out = []
  geo.river.filter((r) => r.stem === 'kur' && r.km <= 170).forEach((r) => {
    let cur = null
    r.line.forEach((p, i) => {
      const c = col(r.kms[i])
      const ll = [p[1], p[0]]
      if (!cur || cur.c !== c) { if (cur) cur.pts.push(ll); cur = { c, pts: cur ? [cur.pts[cur.pts.length - 1], ll] : [ll] }; out.push(cur) } else cur.pts.push(ll)
    })
  })
  return out
}

function FitRiver({ geo }) {
  const map = useMap()
  useEffect(() => {
    const pts = geo.river.filter((r) => r.stem === 'kur' && r.km <= 165).flatMap((r) => r.line.map((p) => [p[1], p[0]]))
    if (pts.length) map.fitBounds(pts, { padding: [12, 12] })
  }, [geo, map])
  return null
}

function Clicks({ onClick }) {
  useMapEvents({ click: (e) => onClick(e.latlng) })
  return null
}

export function RiverMap({ geo, front, sel, onPick, onVillage, marks = [], children, onMapClick }) {
  const { data: sat } = useApi('/satellite')
  const segs = useMemo(() => segments(geo, front), [geo, front])
  const click = async ({ lat, lng }) => {
    if (onMapClick) { onMapClick({ lat, lon: lng }); return }
    if (!onPick) return
    try { onPick(await api(`/kur/point?lat=${lat.toFixed(5)}&lon=${lng.toFixed(5)}`)) } catch { /* outside the area */ }
  }
  return (
    <MapContainer center={[39.6, 49.0]} zoom={9} zoomSnap={0.25} style={{ height: '100%', background: '#0B0B0C' }} scrollWheelZoom={false} attributionControl>
      {sat?.truecolor && <TileLayer url={sat.truecolor} opacity={0.55} maxNativeZoom={9} maxZoom={14} attribution="NASA GIBS (VIIRS)" />}
      {sat?.base && <TileLayer url={sat.base.labels} maxNativeZoom={13} maxZoom={14} opacity={0.7} attribution="Labels: NASA GIBS (OSM)" />}
      <FitRiver geo={geo} />
      <Clicks onClick={click} />
      {segs.map((s, i) => <Polyline key={i} positions={s.pts} pathOptions={{ color: s.c, weight: 7, opacity: 0.95, lineCap: 'round' }} />)}
      {geo.villages.map((v) => (
        <CircleMarker key={v.name + v.km} center={[v.lat, v.lon]} radius={sel?.label === v.name ? 8 : 4}
          eventHandlers={{ click: (e) => { e.originalEvent?.stopPropagation?.(); onVillage?.(v) } }}
          pathOptions={{ color: '#fff', weight: sel?.label === v.name ? 3 : 1, fillColor: sel?.label === v.name ? '#FF6A1A' : '#E4E4E7', fillOpacity: 1 }}>
          <Tooltip direction="top" permanent={sel?.label === v.name} className="k-tip">{v.name} · {Math.round(v.km)} km</Tooltip>
        </CircleMarker>))}
      {marks.map((m, i) => <CircleMarker key={i} center={m.pos} radius={m.r || 7} pathOptions={{ color: '#fff', weight: 2, fillColor: m.c, fillOpacity: 1 }}>
        {m.label && <Tooltip permanent direction="top" className="k-tip">{m.label}</Tooltip>}</CircleMarker>)}
      {children}
    </MapContainer>
  )
}

/* ---------------------------------------------------------------- my farms */
const longDay = (iso, lang) => {
  const d = new Date(iso + 'T12:00:00')
  const az = ['Bazar', 'Bazar ertəsi', 'Çərşənbə axşamı', 'Çərşənbə', 'Cümə axşamı', 'Cümə', 'Şənbə']
  const mon = ['yan', 'fev', 'mar', 'apr', 'may', 'iyn', 'iyl', 'avq', 'sen', 'okt', 'noy', 'dek']
  return lang === 'az' ? `${az[d.getDay()]}, ${d.getDate()} ${mon[d.getMonth()]}` : d.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'short' })
}

export function MyFarms({ mine, onAdd, onObs, onPick, onIrrigated, today }) {
  const { t, lang } = useLang()
  const [done, setDone] = useState({})
  if (!mine) return <Spinner />
  return (
    <>
      <div className="k-farms">
        {mine.farms.length === 0 && <p className="k-p">{t('no_farms')}</p>}
        {mine.farms.map(({ farm, status, soil, crops, tolerant }) => {
          const lvl = status?.level || 'unknown'
          const tomorrow = status?.days.find((d) => d.date > today)
          const windy = tomorrow && tomorrow.u >= 5
          return (
            <div key={farm.id} className={`k-farm k-${lvl}`}>
              <div className="k-farm-top">
                <div><h4><Icon n="pin" s={18} /> {farm.name}</h4><div className="k-faint">{farm.pump_km != null ? `Kür · ${fmt(farm.pump_km, 0)} km` : t('no_kur')}{farm.crops?.length ? ` · ${farm.crops.map((c) => cropName(c, lang)).join(', ')}` : ''}</div></div>
              </div>

              {status && <div className="k-block">
                <div className="k-label">{t('water_today')}</div>
                <button className="k-signal sm" onClick={() => onPick(farm)}><span className="k-light" />{t(`lvl_${lvl}`)}</button>
                <p className="k-say">{lvl === 'red' ? t('say_red') : lvl === 'orange' ? t('say_orange') : t('say_green')}</p>
                {lvl !== 'green' && status.front && <p className="k-faint">{t('salt_reach', { km: fmt0(status.front.km) })}</p>}
                {windy && <p className="k-faint">{t('tomorrow_wind')}</p>}
                {status.fresh_again && lvl !== 'green' && <p className="k-faint">{t('fresh_again', { d: shortDate(status.fresh_again, lang) })}</p>}
                {status.reported && <p className="k-faint">{t('reported')}</p>}
                <div className="k-week">{status.days.filter((d) => d.date >= today).slice(0, 7).map((d, k) => (
                  <div key={d.date} className={`k-day k-${d.level}`}><span>{k === 0 ? t('today') : dayName(d.date, lang)}</span><i /></div>))}</div>
              </div>}

              <SoilAndAdvice farm={farm} lvl={lvl} soil={soil} crops={crops} tolerant={tolerant} />

              <div className="k-actions">
                <button className="k-btn sm" disabled={done[farm.id]} onClick={async () => { await onIrrigated(farm); setDone({ ...done, [farm.id]: true }) }}>
                  <Icon n="drop" s={14} />{done[farm.id] ? t('irrigated_ok') : t('irrigated_today')}</button>
                <button className="k-btn ghost sm" onClick={() => onObs(farm)}><Icon n="plus" s={14} />{t('add_obs')}</button>
              </div>
            </div>
          )
        })}
        <button className="k-add" onClick={onAdd}><Icon n="plus" s={20} />{t('add_farm')}</button>
      </div>
      <div className="k-sms">
        <div className="k-sms-head"><div className="k-label">{t('sms_title')}</div>
          <span className={`k-sms-on ${mine.sms_on && mine.phone ? 'on' : ''}`}>{mine.sms_on && mine.phone ? `${t('sms_on')} · ${mine.phone}` : t('sms_off')}</span></div>
        {mine.sms?.length ? mine.sms.map((m, k) => <div key={k} className="k-bubble">{m.body}<small>{m.created_at?.slice(0, 16)} · {m.status === 'simulated' ? t('sms_sim') : m.status}</small></div>)
          : <p className="k-faint">{t('sms_none')}</p>}
      </div>
    </>
  )
}

function SoilAndAdvice({ farm, lvl, soil, crops, tolerant }) {
  const { t, lang } = useLang()
  const ec = soil.ec
  const sat = soil.satellite
  const sLvl = ec == null ? null : ec < 2 ? 'ok' : ec < 4 ? 'mid' : 'bad'
  const salty = (ec != null && ec >= 2) || sat?.trend === 'up'
  const sensitive = crops.filter((c) => c.ece != null && c.ece < (ec != null ? Math.max(ec, 4) : 4))
  const better = tolerant.filter((id) => !farm.crops.includes(id)).slice(0, 2)
  const todo = []
  if (lvl === 'red') todo.push(t('do_stored'))
  if (lvl === 'orange') todo.push(t('do_now'))
  if (lvl === 'green' && farm.pond_m3) todo.push(t('do_pond_now'))
  if (salty && lvl === 'green') todo.push(t('do_wash'))
  if (salty && sensitive.length && better.length) todo.push(t('plant_x', { a: better.map((c) => cropName(c, lang)).join(lang === 'az' ? ' və ya ' : ' or '), b: sensitive.map((c) => cropName(c.id, lang)).join(', ') }))
  if (!todo.length) todo.push(t('do_nothing'))
  return <>
    <div className="k-block">
      <div className="k-label">{t('soil_title')}</div>
      <div className="k-soil-row">
        {sLvl ? <span className={`k-soil-lvl ${sLvl}`}><i />{t(`soil_lvl_${sLvl}`)} <small>{fmt(ec, 1)} dS/m</small></span>
          : <span className="k-faint">{t('soil_unmeasured')}</span>}
        {sat && <span className={`k-trend ${sat.trend}`}>· {t(`trend_${sat.trend}`)}</span>}
      </div>
    </div>
    <div className="k-block">
      <div className="k-label">{t('what_do')}</div>
      <ul className="k-do">{todo.map((x) => <li key={x}>{x}</li>)}</ul>
    </div>
  </>
}

const CROP_AZ = { arpa: 'Arpa', pambiq: 'Pambıq', 'seker-cugunduru': 'Şəkər çuğunduru', bugda: 'Buğda', celtik: 'Çəltik', pomidor: 'Pomidor', xiyar: 'Xiyar', kelem: 'Kələm', qargidali: 'Qarğıdalı', kartof: 'Kartof', bibar: 'Bibər', uzum: 'Üzüm', sogan: 'Soğan', lobya: 'Lobya', noxud: 'Noxud', yemis: 'Yemiş', qarpiz: 'Qarpız', badimcan: 'Badımcan', gunebaxan: 'Günəbaxan', nar: 'Nar', zeytun: 'Zeytun', alma: 'Alma', armud: 'Armud', saftali: 'Şaftalı', erik: 'Ərik', gavali: 'Gavalı', tutun: 'Tütün' }
const CROP_EN = { arpa: 'Barley', pambiq: 'Cotton', 'seker-cugunduru': 'Sugar beet', bugda: 'Wheat', celtik: 'Rice', pomidor: 'Tomato', xiyar: 'Cucumber', kelem: 'Cabbage', qargidali: 'Maize', kartof: 'Potato', bibar: 'Pepper', uzum: 'Grape', sogan: 'Onion', lobya: 'Bean', noxud: 'Chickpea', yemis: 'Melon', qarpiz: 'Watermelon', badimcan: 'Eggplant', gunebaxan: 'Sunflower', nar: 'Pomegranate', zeytun: 'Olive', alma: 'Apple', armud: 'Pear', saftali: 'Peach', erik: 'Apricot', gavali: 'Plum', tutun: 'Tobacco' }
const cropName = (id, lang) => (lang === 'az' ? CROP_AZ : CROP_EN)[id] || id

/* ---------------------------------------------------------------- sign-up */
export function SignupModal({ onClose, onDone, inline, startMode = 'new' }) {
  const { t } = useLang()
  const { login } = useAuth()
  const [mode, setMode] = useState(startMode)
  const [f, setF] = useState({ name: '', phone: '', password: '' })
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const submit = async (e) => {
    e.preventDefault(); setErr(null); setBusy(true)
    try {
      const r = mode === 'new' ? await api('/auth/register', { method: 'POST', body: { ...f, role: 'farmer' } })
        : await api('/auth/login', { method: 'POST', body: { email: f.phone, password: f.password } })
      await login(r.token)
      mode === 'new' ? onDone?.() : onClose?.()
    } catch (x) { setErr(x) } finally { setBusy(false) }
  }
  const form = (
      <form className="k-form" onSubmit={submit}>
        <h3 className="k-h3">{t('r_title')}</h3><p className="k-faint">{t('r_sub')}</p>
        <Seg label="mode" value={mode} onChange={setMode} options={[['new', t('r_new')], ['login', t('r_login')]]} />
        {mode === 'new' && <label>{t('r_name')}<input className="input" required minLength={2} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></label>}
        <label>{t('r_phone')}<input className="input" required inputMode="tel" placeholder="+994 50 123 45 67" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} /></label>
        <label>{t('r_pass')}<input className="input" required type="password" minLength={mode === 'new' ? 8 : 1} value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></label>
        <ErrorBox error={err} />
        <button className="k-btn" disabled={busy}>{t('r_go')}</button>
      </form>
  )
  return inline ? form : <Modal onClose={onClose}>{form}</Modal>
}

/* ---------------------------------------------------------------- farm: three taps, no map */
const SIMPLE_CROPS = ['pambiq', 'bugda', 'arpa', 'pomidor', 'qargidali', 'yemis', 'uzum', 'seker-cugunduru']

export function FarmModal({ geo, onClose, onSaved, inline }) {
  const { t, lang } = useLang()
  const { refresh } = useAuth()
  const az = useGeo('country/AZE')
  const [f, setF] = useState({ village: '', water_source: 'kur', crop: 'pambiq', area_ha: '', pond: false, drainage: false })
  const [more, setMore] = useState(false)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const villages = geo?.villages || []
  const save = async (e) => {
    e.preventDefault(); setErr(null)
    const v = villages.find((x) => x.name === f.village)
    if (!v) { setErr(new Error(t('f_need_village'))); return }
    setBusy(true)
    try {
      // the pump is taken as the river bank next to the village; the field as the village itself
      const p = await api(`/kur/point?lat=${v.lat}&lon=${v.lon}`)
      const hit = az?.features.find((ft) => inPoly([v.lat, v.lon], ft.geometry))
      const onKur = f.water_source === 'kur' || f.water_source === 'canal'
      await api('/me/farms', { method: 'POST', body: { name: v.name, rayon_id: hit ? hit.properties.id : 'neftcala', lat: v.lat, lon: v.lon,
        irrigated: f.water_source !== 'none', crops: [f.crop], water_source: f.water_source,
        pump_lat: onKur ? p.lat : null, pump_lon: onKur ? p.lon : null,
        area_ha: f.area_ha === '' ? null : Number(f.area_ha), pond_m3: more && f.pond ? 1 : null, drainage: more ? f.drainage : null } })
      await refresh(); onSaved()
    } catch (x) { setErr(x) } finally { setBusy(false) }
  }
  const form = (
      <form className="k-form" onSubmit={save}>
        {!inline && <h3 className="k-h3">{t('f_title')}</h3>}
        <div className="k-q"><span className="k-step">1</span>{t('f_village')}</div>
        <Select label={t('f_village')} value={f.village} placeholder={t('f_village_ph')} searchable onChange={(v) => setF({ ...f, village: v })}
          options={villages.map((v) => ({ value: v.name, label: v.name, hint: `${Math.round(v.km)} km` }))} />
        <div className="k-q"><span className="k-step">2</span>{t('f_source')}</div>
        <div className="k-choices big">{['kur', 'canal', 'none'].map((s) => (
          <button type="button" key={s} className={f.water_source === s ? 'on' : ''} onClick={() => setF({ ...f, water_source: s })}>{t(`src_${s}`)}</button>))}</div>
        <div className="k-q"><span className="k-step">3</span>{t('f_crop')}</div>
        <div className="k-choices">{SIMPLE_CROPS.map((c) => (
          <button type="button" key={c} className={f.crop === c ? 'on' : ''} onClick={() => setF({ ...f, crop: c })}>{cropName(c, lang)}</button>))}</div>
        <button type="button" className="k-more" onClick={() => setMore(!more)}>{t('f_more')} {more ? '−' : '+'}</button>
        {more && <div className="k-form">
          <label>{t('f_area')}<input className="input" type="number" min="0" step="0.1" inputMode="decimal" value={f.area_ha} onChange={(e) => setF({ ...f, area_ha: e.target.value })} /></label>
          <div className="k-choices">
            <button type="button" className={f.pond ? 'on' : ''} onClick={() => setF({ ...f, pond: !f.pond })}>{t('f_has_pond')}</button>
            <button type="button" className={f.drainage ? 'on' : ''} onClick={() => setF({ ...f, drainage: !f.drainage })}>{t('f_drain')}</button>
          </div>
        </div>}
        <ErrorBox error={err} />
        <button className="k-btn" disabled={busy}>{t('f_save')}</button>
      </form>
  )
  return inline ? form : <Modal onClose={onClose}>{form}</Modal>
}

/* ---------------------------------------------------------------- measurement: water (two big buttons) or soil (one number) */
export function ObsModal({ farm, onClose, onSaved }) {
  const { t } = useLang()
  const [kind, setKind] = useState('water')
  const [ec, setEc] = useState('')
  const [err, setErr] = useState(null)
  const [ok, setOk] = useState(false)
  const water = farm?.pump_lat ? [farm.pump_lat, farm.pump_lon] : [farm.lat, farm.lon]
  const send = async (salty) => {
    setErr(null)
    const v = ec === '' ? null : Number(ec)
    const pos = kind === 'water' ? water : [farm.lat, farm.lon]
    try {
      await api('/kur/obs', { method: 'POST', body: { kind, lat: pos[0], lon: pos[1], ec: v, salty: v == null ? salty : null } })
      setOk(true); setTimeout(onSaved, 900)
    } catch (x) { setErr(x) }
  }
  return (
    <Modal onClose={onClose}>
      <div className="k-form">
        <h3 className="k-h3">{t('obs_how')}</h3>
        <p className="k-faint">{farm.name}{farm.pump_km != null ? ` · Kür ${fmt(farm.pump_km, 0)} km` : ''}</p>
        {ok ? <div className="ok">{t('o_saved')}</div> : <>
          <Seg label="kind" value={kind} onChange={(v) => { setKind(v); setEc('') }} options={[['water', t('o_water')], ['soil', t('o_soil')]]} />
          {kind === 'water' ? <>
            <div className="k-q">{t('o_today')}</div>
            <div className="k-yesno">
              <button type="button" className="salty" onClick={() => send(true)}>{t('o_salty')}</button>
              <button type="button" className="fresh" onClick={() => send(false)}>{t('o_fresh')}</button>
            </div>
            <label>{t('o_ec_opt')}<input className="input" type="number" min="0" step="0.01" inputMode="decimal" value={ec} onChange={(e) => setEc(e.target.value)} placeholder="EC, dS/m" /></label>
          </> : <>
            <div className="k-q">{t('o_soil_q')}</div>
            <label>{t('o_soil_ec')}<input className="input" type="number" min="0" step="0.1" inputMode="decimal" value={ec} onChange={(e) => setEc(e.target.value)} placeholder="EC, dS/m" /></label>
          </>}
          {ec !== '' && <button type="button" className="k-btn" onClick={() => send(null)}>{t('f_save')}</button>}
          <ErrorBox error={err} />
        </>}
      </div>
    </Modal>
  )
}
