import { Search, Compose, Refresh, Paperclip, Dot } from '../icons.jsx'
import { avatarColor, initials, formatTime, highlight } from '../util.js'

function Snippet({ email, query }) {
  const text = email.match_snippet || email.snippet || ''
  if (!query) return <>{text}</>
  return (
    <>
      {highlight(text, query).map((p, i) =>
        typeof p === 'string' ? <span key={i}>{p}</span> : <mark key={i}>{p.mark}</mark>
      )}
    </>
  )
}

function EmailCard({ email, selected, onClick, tagMeta, query, isSearch }) {
  return (
    <button
      className={`email-card ${selected ? 'selected' : ''} ${email.unread ? 'unread' : ''}`}
      onClick={onClick}
    >
      <div className="ec-top">
        <div className="avatar" style={{ background: avatarColor(email.from_email) }}>
          {initials(email.from_name)}
        </div>
        <div className="ec-headtext">
          <div className="ec-name">{email.from_name}</div>
        </div>
        <div className="ec-time">{formatTime(email.received_at)}</div>
      </div>

      <div className="ec-sub">{email.subject}</div>
      <div className="ec-snippet"><Snippet email={email} query={query} /></div>

      <div className="ec-chips">
        {email.tags.map((t) => {
          const meta = tagMeta[t]
          if (!meta) return null
          return (
            <span key={t} className="chip" style={{ background: `${meta.color}18`, color: meta.color }}>
              <span className="cdot" style={{ background: meta.color }} />
              {meta.label}
            </span>
          )
        })}
        {email.has_attachments && (
          <span className="attach-chip">
            <Paperclip size={12} /> {email.attachments[0]}
            {email.attachments.length > 1 ? ` +${email.attachments.length - 1}` : ''}
          </span>
        )}
        {isSearch && email.channels && (
          <>
            {email.channels.map((ch) => (
              <span key={ch} className={`channel-badge ${ch}`}>
                {ch === 'bm25' ? 'BM25' : 'семантика'}
              </span>
            ))}
          </>
        )}
      </div>

      {email.unread && !isSearch && (
        <span className="unread-dot"><Dot size={9} color="#0a7cff" /></span>
      )}
    </button>
  )
}

export default function ListPane({
  title, subtitle, emails, selectedId, onSelect, query, draft,
  onDraftChange, onSubmitSearch, onClearSearch, isSearch, searching,
  filter, onFilter, tagMeta, onRefresh,
}) {
  return (
    <section className="list-pane">
      <div className="list-head">
        <div className="list-title">{title}</div>
        <div className="list-sub">{subtitle}</div>
      </div>

      <div className="searchbar">
        <form
          className="search-input-wrap"
          onSubmit={(e) => { e.preventDefault(); onSubmitSearch() }}
        >
          <Search size={16} />
          <input
            placeholder="Умный поиск по ящику…"
            value={draft}
            onChange={(e) => onDraftChange(e.target.value)}
          />
          {draft && (
            <span className="search-clear" onClick={onClearSearch} role="button">×</span>
          )}
        </form>
        <button className="icon-btn" title="Обновить" onClick={onRefresh}>
          <Refresh size={16} />
        </button>
        <button className="icon-btn" title="Написать"><Compose size={16} /></button>
      </div>

      {!isSearch && (
        <div className="filter-row">
          {[
            { id: 'all', label: 'Все' },
            { id: 'unread', label: 'Непрочитанные' },
            { id: 'starred', label: 'Избранное' },
          ].map((f) => (
            <button
              key={f.id}
              className={`filter-pill ${filter === f.id ? 'active' : ''}`}
              onClick={() => onFilter(f.id)}
            >
              {f.label}
            </button>
          ))}
        </div>
      )}

      <div className="email-list">
        {searching && (
          <div className="list-empty">Ищу по лексике (BM25) и смыслу…</div>
        )}
        {!searching && emails.length === 0 && (
          <div className="list-empty">
            {isSearch ? 'Ничего не найдено. Попробуйте другой запрос.' : 'Папка пуста.'}
          </div>
        )}
        {!searching && emails.map((e) => (
          <EmailCard
            key={e.id}
            email={e}
            selected={e.id === selectedId}
            onClick={() => onSelect(e.id)}
            tagMeta={tagMeta}
            query={isSearch ? query : ''}
            isSearch={isSearch}
          />
        ))}
      </div>
    </section>
  )
}
