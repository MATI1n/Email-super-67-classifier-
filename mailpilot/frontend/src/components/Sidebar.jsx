import {
  Inbox, Send, Star, Archive, Trash, Draft, Folder, Mail,
} from '../icons.jsx'
import { CATEGORY_COLOR, avatarColor, initials } from '../util.js'

const SYSTEM = [
  { id: 'inbox', label: 'Входящие', icon: Inbox, key: 'inbox' },
  { id: 'sent', label: 'Отправленные', icon: Send, key: 'sent' },
  { id: 'starred', label: 'Избранное', icon: Star, key: 'starred' },
  { id: 'archive', label: 'Архив', icon: Archive, key: 'archive' },
  { id: 'trash', label: 'Корзина', icon: Trash, key: 'trash' },
  { id: 'drafts', label: 'Черновики', icon: Draft, key: 'drafts' },
]

function fmtCount(n) {
  if (!n) return ''
  return n > 999 ? '999+' : String(n)
}

export default function Sidebar({ folders, view, onSelect, health }) {
  const fc = folders?.folders || {}
  const cats = folders?.categories || []
  const tags = folders?.tags || []
  const agent = 'Саня 67'
  const agentMail = 'support@company.ru'

  const isActive = (type, value) => view.type === type && view.value === value

  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-logo"><Mail size={17} /></div>
        <div>
          <div className="brand-name">MailPilot</div>
          <div className="brand-sub">Почта поддержки</div>
        </div>
      </div>

      <div className="sidebar-scroll">
        {SYSTEM.map((s) => {
          const Icon = s.icon
          const count = s.key === 'inbox' ? fc.inbox : fc[s.key]
          return (
            <button
              key={s.id}
              className={`nav-item ${isActive('folder', s.id) ? 'active' : ''}`}
              onClick={() => onSelect({ type: 'folder', value: s.id, label: s.label })}
            >
              <span className="ni-icon"><Icon size={17} /></span>
              <span className="ni-label">{s.label}</span>
              <span className="ni-count">{fmtCount(count)}</span>
            </button>
          )
        })}

        <div className="section-head">Категории</div>
        {cats.map((c) => (
          <button
            key={c.id}
            className={`nav-item ${isActive('category', c.id) ? 'active' : ''}`}
            onClick={() => onSelect({ type: 'category', value: c.id, label: c.label })}
          >
            <span className="folder-dot">
              <Folder size={16} color={CATEGORY_COLOR[c.id] || '#868e96'} />
            </span>
            <span className="ni-label">{c.label}</span>
            <span className="ni-count">{fmtCount(c.count)}</span>
          </button>
        ))}

        <div className="section-head">Теги · тип проблемы</div>
        {tags.map((t) => (
          <button
            key={t.id}
            className={`tag-row ${isActive('tag', t.id) ? 'active' : ''}`}
            onClick={() => onSelect({ type: 'tag', value: t.id, label: t.label })}
          >
            <span className="tag-bullet" style={{ background: t.color }} />
            <span className="ni-label">{t.label}</span>
            <span className="ni-count">{fmtCount(t.count)}</span>
          </button>
        ))}
      </div>

      <div className="profile">
        <div className="avatar" style={{ background: avatarColor(agent), width: 34, height: 34 }}>
          {initials(agent)}
        </div>
        <div className="meta">
          <div className="pname">{agent}</div>
          <div className="pmail">{agentMail}</div>
        </div>
        {health && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, alignItems: 'flex-end' }}>
            <span className={`mode-badge ${health.ai_mode === 'mock' ? 'mock' : ''}`}>
              AI: {health.ai_mode === 'deepseek' ? 'DeepSeek' : 'mock'}
            </span>
          </div>
        )}
      </div>
    </aside>
  )
}
