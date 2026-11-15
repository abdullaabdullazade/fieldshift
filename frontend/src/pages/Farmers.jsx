import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { ago, api, initials, useApi, useAuth, useCatalog } from '../lib.jsx'
import { DemoTag, ErrorBox, Icon, Select, Spinner, StarInput, Stars, Swap, Title } from '../ui.jsx'

const digits = (p) => (p || '').replace(/[^0-9+]/g, '')

export function Contacts({ u }) {
  if (u.is_demo) {
    return (
      <div className="row" style={{ gap: 8 }}>
        {u.phone && <span className="contact off" title="Demo contact"><Icon n="phone" s={16} />{u.phone}</span>}
        {u.whatsapp && <span className="contact off" title="Demo contact"><Icon n="msg" s={16} />WhatsApp</span>}
        {u.telegram && <span className="contact off" title="Demo contact"><Icon n="msg" s={16} />Telegram</span>}
      </div>)
  }
  return (
    <div className="row" style={{ gap: 8 }}>
      {u.phone && <a className="contact ph" href={`tel:${digits(u.phone)}`}><Icon n="phone" s={16} />{u.phone}</a>}
      {u.whatsapp && <a className="contact wa" href={`https://wa.me/${digits(u.whatsapp).replace('+', '')}`} target="_blank" rel="noreferrer"><Icon n="msg" s={16} />WhatsApp</a>}
      {u.telegram && <a className="contact tg" href={`https://t.me/${u.telegram}`} target="_blank" rel="noreferrer"><Icon n="msg" s={16} />Telegram</a>}
      {!u.phone && !u.whatsapp && !u.telegram && <span className="small faint">No public contacts</span>}
    </div>
  )
}

export function FarmerCard({ u }) {
  const { crops } = useCatalog()
  const cname = (id) => crops.find((c) => c.id === id)?.name || id
  const allCrops = [...new Set(u.farms.flatMap((f) => f.crops))]
  return (
    <div className="card stack">
      <div className="row" style={{ flexWrap: 'nowrap' }}>
        <div className="avatar">{initials(u.name)}</div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <Link to={`/farmers/${u.id}`}><h3>{u.name} {u.is_demo ? <DemoTag /> : null}</h3></Link>
          <div className="small muted">{[...new Set(u.farms.map((f) => (f.iso3 && f.iso3 !== 'AZE' ? `${f.rayon}, ${f.country}` : f.rayon)))].join(' · ') || 'No farm listed yet'}</div>
        </div>
        <Stars value={u.rating.avg} count={u.rating.count} />
      </div>
      {u.bio && <p className="small muted">{u.bio.length > 180 ? `${u.bio.slice(0, 180)}…` : u.bio}</p>}
      {allCrops.length > 0 && <div className="chips">{allCrops.slice(0, 8).map((c) => <span key={c} className="tag grey">{cname(c)}</span>)}</div>}
      <div className="between"><Contacts u={u} /><Link to={`/farmers/${u.id}`} className="btn sm ghost">Profile & reviews</Link></div>
    </div>
  )
}

export default function Farmers() {
  const [sp, setSp] = useSearchParams()
  const { crops, rayons } = useCatalog()
  const country = sp.get('country') || 'AZE'
  const rayon = sp.get('rayon') || '', crop = sp.get('crop') || '', sort = sp.get('sort') || 'rating'
  const { data: countries } = useApi('/countries')
  const { data: units } = useApi(`/rayons?scope=${country}`)
  const [q, setQ] = useState(sp.get('q') || '')
  const set = (k, v) => { const n = new URLSearchParams(sp); v ? n.set(k, v) : n.delete(k); setSp(n, { replace: true }) }
  const qs = new URLSearchParams({ country, ...(rayon && { rayon }), ...(crop && { crop }), ...(sp.get('q') && { q: sp.get('q') }), sort })
  const { data, error, stamp, loading } = useApi(`/farmers?${qs}`)
  return (
    <>
      <div className="section-head" style={{ marginTop: 0 }}>
        <Title dark="Farmers." orange="By district and crop." />
        <p className="muted" style={{ maxWidth: 460 }}>Every farmer has their own account and lists their districts and crops. Contact
          them directly, and rate them after you buy.</p>
      </div>
      {data?.some((u) => u.is_demo) && <p className="note" style={{ marginBottom: 16 }}>Profiles marked <DemoTag /> are sample data for the
        presentation: their crops and districts come from real AzStat statistics, but the people, contacts and reviews are not real.</p>}
      <div className="card row" style={{ marginBottom: 20 }}>
        <Select label="Country" style={{ flex: '1 1 170px' }} value={country} onChange={(v) => { const n = new URLSearchParams(sp); n.set('country', v); n.delete('rayon'); setSp(n, { replace: true }) }}
          options={(countries || []).map((c) => ({ value: c.iso3, label: c.name, group: c.grp === 'world' ? c.continent : 'Azerbaijan & neighbours' }))} />
        <Select label={country === 'AZE' ? 'District' : 'Province'} style={{ flex: '1 1 180px' }} value={rayon} onChange={(v) => set('rayon', v)}
          options={[{ value: '', label: country === 'AZE' ? 'All districts' : 'All provinces' }, ...(units || []).map((r) => ({ value: r.id, label: r.name, group: country === 'AZE' ? r.econ : undefined }))]} />
        <Select label="Crop" style={{ flex: '1 1 180px' }} value={crop} onChange={(v) => set('crop', v)}
          options={[{ value: '', label: 'All crops' }, ...crops.map((c) => ({ value: c.id, label: c.name, group: c.grp }))]} />
        <form style={{ flex: '2 1 240px', display: 'flex', gap: 8 }} onSubmit={(e) => { e.preventDefault(); set('q', q) }}>
          <input className="input" placeholder="Search by name or description" value={q} onChange={(e) => setQ(e.target.value)} />
          <button className="btn">Search</button></form>
        <Select label="Sort" style={{ flex: '0 1 170px' }} value={sort} onChange={(v) => set('sort', v)}
          options={[{ value: 'rating', label: 'Best rated' }, { value: 'reviews', label: 'Most reviewed' }, { value: 'new', label: 'Newest' }]} />
      </div>
      <ErrorBox error={error} />
      {!data ? <Spinner /> : data.length ? (
        <Swap k={stamp} loading={loading}><div className="grid g2">{data.map((u) => <FarmerCard key={u.id} u={u} />)}</div></Swap>
      ) : (
        <div className="card empty"><Icon n="users" s={40} />
          <p style={{ marginTop: 10 }}>No farmers match these filters yet.</p>
          <Link to="/account" className="btn" style={{ marginTop: 14 }}>Register as a farmer</Link></div>
      )}
    </>
  )
}

export function Farmer() {
  const { id } = useParams()
  const { user } = useAuth()
  const { crops } = useCatalog()
  const { data: u, error, reload } = useApi(`/farmers/${id}`)
  const [form, setForm] = useState({ rating: 0, crop_id: '', comment: '' })
  const [msg, setMsg] = useState(null)
  if (error) return <ErrorBox error={error} />
  if (!u) return <Spinner />
  const cname = (c) => crops.find((x) => x.id === c)?.name || c
  const submit = async (e) => {
    e.preventDefault()
    if (!form.rating) { setMsg({ err: 'Choose 1–5 stars' }); return }
    try { await api(`/farmers/${id}/reviews`, { method: 'POST', body: form }); setMsg({ ok: 'Thanks, your review is published.' }); setForm({ rating: 0, crop_id: '', comment: '' }); reload() } catch (err) { setMsg({ err: err.message }) }
  }
  const del = async (rid) => { await api(`/reviews/${rid}`, { method: 'DELETE' }); reload() }
  const total = u.reviews.length
  return (
    <div className="split wide">
      <div className="stack">
        <div className="card">
          <div className="row" style={{ flexWrap: 'nowrap', gap: 18 }}>
            <div className="avatar lg">{initials(u.name)}</div>
            <div><h2 style={{ fontFamily: 'var(--display)', fontSize: 28, fontWeight: 500, letterSpacing: '-.03em', color: 'var(--ink)' }}>{u.name} {u.is_demo ? <DemoTag /> : null}</h2>
              <Stars value={u.rating.avg} count={u.rating.count} />
              <div className="xs faint">Member since {new Date(u.created_at + 'Z').toLocaleDateString('en-GB')}</div></div>
          </div>
          {u.bio && <p style={{ marginTop: 16 }}>{u.bio}</p>}
          <div style={{ marginTop: 16 }}><Contacts u={u} /></div>
        </div>
        <div className="card">
          <h3>Farms</h3>
          {u.farms.length ? u.farms.map((f) => (
            <div key={f.id} className="between" style={{ padding: '12px 0', borderBottom: '1px solid var(--line)' }}>
              <div><b>{f.name}</b> · <Link to={`/r/${f.rayon_id}`} className="or b">{f.rayon}</Link>
                <div className="xs muted">{f.area_ha ? `${f.area_ha} ha · ` : ''}{f.irrigated ? 'irrigated' : 'rain-fed'}</div></div>
              <div className="chips">{f.crops.map((c) => <span key={c} className="tag grey">{cname(c)}</span>)}</div>
            </div>)) : <p className="muted small">No farms listed.</p>}
        </div>
      </div>
      <div className="stack">
        <div className="card">
          <h3>Buyer reviews</h3>
          <div className="row" style={{ marginTop: 10, alignItems: 'center', gap: 24 }}>
            <div style={{ fontFamily: 'var(--display)', fontSize: 44, fontWeight: 500, letterSpacing: '-.04em', color: 'var(--ink)' }}>{u.rating.avg ? u.rating.avg.toFixed(1) : '—'}</div>
            <div style={{ flex: 1 }}>{[5, 4, 3, 2, 1].map((s) => (
              <div key={s} className="row" style={{ gap: 8, flexWrap: 'nowrap' }}><span className="xs b" style={{ width: 22 }}>{s}★</span>
                <div className="bar" style={{ flex: 1 }}><i style={{ width: `${total ? (u.histogram[s] / total) * 100 : 0}%` }} /></div>
                <span className="xs muted" style={{ width: 22 }}>{u.histogram[s]}</span></div>))}</div>
          </div>
        </div>
        {user && user.id !== u.id ? (
          <form className="card stack" onSubmit={submit}>
            <h3>Rate this farmer</h3>
            <StarInput value={form.rating} onChange={(rating) => setForm({ ...form, rating })} />
            <Select label="Product bought" value={form.crop_id} placeholder="Product bought (optional)" onChange={(v) => setForm({ ...form, crop_id: v })}
              options={[{ value: '', label: 'Not specified' }, ...[...new Set(u.farms.flatMap((f) => f.crops))].map((c) => ({ value: c, label: cname(c) }))]} />
            <textarea className="input" placeholder="How was the quality, price, delivery?" maxLength={1500} value={form.comment} onChange={(e) => setForm({ ...form, comment: e.target.value })} />
            {msg?.err && <div className="err">{msg.err}</div>}{msg?.ok && <div className="ok">{msg.ok}</div>}
            <button className="btn">Publish review</button>
          </form>
        ) : !user ? <div className="card"><Link to="/account" className="or b">Sign in</Link> to leave a review.</div> : null}
        {u.reviews.map((r) => (
          <div key={r.id} className="card tight">
            <div className="between"><div><b>{r.author}</b> {r.author_demo ? <DemoTag /> : null} <span className="xs muted">{r.author_role === 'buyer' ? 'buyer' : 'farmer'}{r.crop ? ` · bought ${r.crop}` : ''}</span></div>
              <Stars value={r.rating} /></div>
            {r.comment && <p className="small" style={{ marginTop: 8 }}>{r.comment}</p>}
            <div className="between xs faint" style={{ marginTop: 6 }}><span>{ago(r.created_at)}</span>
              {user?.id === r.author_id && <button className="chip" onClick={() => del(r.id)}>Delete</button>}</div>
          </div>))}
      </div>
    </div>
  )
}
