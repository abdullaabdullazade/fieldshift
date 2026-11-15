import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ago, api, useApi, useAuth } from '../lib.jsx'
import { DemoTag, ErrorBox, Icon, Modal, Seg, Spinner, StarInput, Stars, Stat, Swap, Title } from '../ui.jsx'

const KINDS = { idea: 'Idea', bug: 'Bug', data: 'Data issue', praise: 'Praise' }
const STATUS = { new: 'New', planned: 'Planned', in_progress: 'In progress', done: 'Done' }

export default function Feedback() {
  const { user } = useAuth()
  const [kind, setKind] = useState('')
  const [sort, setSort] = useState('top')
  const { data, error, reload, stamp, loading } = useApi(`/feedback?sort=${sort}${kind ? `&kind=${kind}` : ''}`)
  const [form, setForm] = useState({ kind: 'idea', title: '', body: '', rating: 0 })
  const [msg, setMsg] = useState(null)
  const [open, setOpen] = useState(null)
  const submit = async (e) => {
    e.preventDefault(); setMsg(null)
    try {
      await api('/feedback', { method: 'POST', body: { ...form, rating: form.rating || null, page: document.referrer.slice(0, 200) } })
      setForm({ kind: 'idea', title: '', body: '', rating: 0 }); setMsg({ ok: 'Thanks! Your feedback is on the board.' }); reload()
    } catch (x) { setMsg({ err: x.message }) }
  }
  const vote = async (id) => { if (!user) return; await api(`/feedback/${id}/vote`, { method: 'POST' }); reload() }
  const s = data?.summary
  return (
    <>
      <div className="section-head" style={{ marginTop: 0 }}>
        <Title dark="Feedback+" orange="Shape what we build next." />
        <p className="muted" style={{ maxWidth: 480 }}>Tell us what to build next, report a bug or wrong data, and vote on others' ideas.
          The most-voted items go to the top.</p>
      </div>
      {s && <div className="grid g4" style={{ marginBottom: 22 }}>
        <Stat v={s.avg ? `${s.avg.toFixed(1)} ★` : '—'} l={`average app rating (${s.count} ratings)`} />
        <Stat cls="blue" v={s.by_kind.idea || 0} l="ideas" />
        <Stat cls="green" v={s.by_kind.praise || 0} l="praise" />
        <Stat v={(s.by_kind.bug || 0) + (s.by_kind.data || 0)} l="bugs & data issues" />
      </div>}
      <div className="split wide">
        <div className="stack">
          <div className="between">
            <div className="chips">
              <button className={`chip ${!kind ? 'on' : ''}`} onClick={() => setKind('')}>All</button>
              {Object.entries(KINDS).map(([k, l]) => <button key={k} className={`chip ${kind === k ? 'on' : ''}`} onClick={() => setKind(k)}>{l}</button>)}
            </div>
            <Seg label="Sort" value={sort} onChange={setSort} options={[['top', 'Most voted'], ['new', 'Newest']]} />
          </div>
          <ErrorBox error={error} />
          {!data ? <Spinner /> : data.items.length ? <Swap k={`${kind}${sort}`} loading={loading}><div className="stack">{data.items.map((f) => (
            <div key={f.id} className="card tight row" style={{ flexWrap: 'nowrap', alignItems: 'flex-start' }}>
              <button className={`vote ${f.voted ? 'on' : ''}`} onClick={() => vote(f.id)} disabled={!user} title={user ? 'Vote' : 'Sign in to vote'}>
                <Icon n="up" s={16} /><span>{f.votes}</span></button>
              <div style={{ flex: 1, minWidth: 0, cursor: 'pointer' }} onClick={() => setOpen(f.id)}>
                <div className="row" style={{ gap: 8 }}><span className="tag grey">{KINDS[f.kind]}</span><span className="tag navy">{STATUS[f.status] || f.status}</span>
                  {f.rating && <Stars value={f.rating} />}</div>
                <h3 style={{ marginTop: 8 }}>{f.title}</h3>
                {f.body && <p className="small muted" style={{ marginTop: 4 }}>{f.body.length > 220 ? `${f.body.slice(0, 220)}…` : f.body}</p>}
                <div className="xs faint" style={{ marginTop: 6 }}>{f.author || 'anonymous'} {f.author_demo ? <DemoTag /> : null} · {ago(f.created_at)} · {f.comments} comments</div>
              </div>
            </div>))}</div></Swap> : <div className="card empty">Nothing here yet. Be the first to share feedback.</div>}
        </div>
        {user ? (
          <form className="card stack" onSubmit={submit}>
            <h3>Share feedback</h3>
            <div className="chips">{Object.entries(KINDS).map(([k, l]) => (
              <button type="button" key={k} className={`chip ${form.kind === k ? 'on' : ''}`} onClick={() => setForm({ ...form, kind: k })}>{l}</button>))}</div>
            <input className="input" placeholder="Short title" required minLength={3} maxLength={140} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
            <textarea className="input" placeholder="Details: what happened, what you expected, which district or crop…" maxLength={4000} value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} />
            <div><label className="f">Rate the app (optional)</label><StarInput value={form.rating} onChange={(rating) => setForm({ ...form, rating })} /></div>
            {msg?.ok && <div className="ok">{msg.ok}</div>}{msg?.err && <div className="err">{msg.err}</div>}
            <button className="btn">Submit</button>
          </form>
        ) : <div className="card"><Link to="/account" className="or b">Sign in</Link> to post feedback and vote.</div>}
      </div>
      {open && <FeedbackModal id={open} onClose={() => { setOpen(null); reload() }} />}
    </>
  )
}

function FeedbackModal({ id, onClose }) {
  const { user } = useAuth()
  const { data: f, reload } = useApi(`/feedback/${id}`)
  const [body, setBody] = useState('')
  const send = async (e) => { e.preventDefault(); if (!body.trim()) return; await api(`/feedback/${id}/comments`, { method: 'POST', body: { body } }); setBody(''); reload() }
  return (
    <Modal onClose={onClose}>
      {!f ? <Spinner /> : (
        <div className="stack">
          <div className="row" style={{ gap: 8 }}><span className="tag grey">{KINDS[f.kind]}</span><span className="tag navy">{STATUS[f.status] || f.status}</span><span className="small muted">{f.votes} votes</span></div>
          <h3 style={{ fontSize: 22 }}>{f.title}</h3>
          {f.body && <p style={{ whiteSpace: 'pre-wrap' }}>{f.body}</p>}
          <div className="xs faint">{f.author} · {ago(f.created_at)}</div>
          <h3 style={{ marginTop: 10 }}>Comments</h3>
          {f.comments.map((c) => <div key={c.id} className="card tight"><b className="small">{c.author}</b> <span className="xs faint">{ago(c.created_at)}</span><p className="small" style={{ marginTop: 4 }}>{c.body}</p></div>)}
          {!f.comments.length && <p className="small muted">No comments yet.</p>}
          {user && <form className="row" onSubmit={send}><input className="input" style={{ flex: 1 }} value={body} onChange={(e) => setBody(e.target.value)} placeholder="Add a comment" maxLength={2000} /><button className="btn">Post</button></form>}
          <button className="btn light" onClick={onClose}>Close</button>
        </div>)}
    </Modal>
  )
}
