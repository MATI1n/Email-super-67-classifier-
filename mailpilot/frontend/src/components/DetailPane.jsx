import {
  Archive, Trash, Star, Reply, Forward, Sparkles, Paperclip,
  More, Folder, Mail, Clock, AlertTriangle,
} from '../icons.jsx'
import { avatarColor, initials, formatTime } from '../util.js'

function AiPanel({ email, summary, summarizing, scope, onScope, onSummarize }) {
  return (
    <div className="ai-panel">
      <div className="ai-head">
        <div className="ai-spark"><Sparkles size={17} /></div>
        <div className="ai-title">AI-сводка обращения</div>
        {summary && <div className="ai-model">{summary.model} · {summary.mode}</div>}
        {!summarizing && (
          <button className="ai-gen-btn" onClick={() => onSummarize(scope)}>
            <Sparkles size={15} />
            {summary ? 'Обновить' : 'Суммаризировать'}
          </button>
        )}
      </div>

      <div className="scope-tabs">
        <button
          className={`scope-tab ${scope === 'email' ? 'active' : ''}`}
          onClick={() => onScope('email')}
        >Это письмо</button>
        <button
          className={`scope-tab ${scope === 'ticket' ? 'active' : ''}`}
          onClick={() => onScope('ticket')}
        >Вся заявка · {email.ticket_id}</button>
      </div>

      <div className="ai-body">
        {summarizing && (
          <>
            <div className="shimmer" style={{ height: 14, width: '92%', marginBottom: 8 }} />
            <div className="shimmer" style={{ height: 14, width: '78%', marginBottom: 8 }} />
            <div className="shimmer" style={{ height: 14, width: '60%' }} />
          </>
        )}

        {!summarizing && summary && (
          <>
            <div className="ai-summary-text">{summary.summary}</div>

            {summary.highlights?.length > 0 && (
              <>
                <div className="ai-block-title">Ключевые моменты</div>
                {summary.highlights.map((h, i) => (
                  <div className="ai-hl" key={i}>
                    <span className="hl-dot">●</span>
                    <span>{h}</span>
                  </div>
                ))}
              </>
            )}

            {summary.suggested_action && (
              <div className="ai-action">
                <b>→</b>
                <div><b>Рекомендация:</b> {summary.suggested_action}</div>
              </div>
            )}
          </>
        )}

        {!summarizing && !summary && (
          <div className="ai-summary-text" style={{ color: '#7a7a82' }}>
            Нажмите «Суммаризировать» — AI выделит суть обращения, ключевые факты,
            сроки и предложит следующее действие. Работает на DeepSeek (или локальном
            режиме без ключа).
          </div>
        )}
      </div>
    </div>
  )
}

export default function DetailPane({
  email, onAction, summary, summarizing, scope, onScope, onSummarize, tagMeta,
}) {
  if (!email) {
    return (
      <section className="detail-pane">
        <div className="empty-state">
          <div className="es-ico"><Mail size={30} /></div>
          <h3>Выберите письмо</h3>
          <p>Слева — входящие обращения, разложенные классификатором. Откройте любое,
             чтобы прочитать, получить AI-сводку и обработать.</p>
        </div>
      </section>
    )
  }

  const isError = email.category === 'errors'

  return (
    <section className="detail-pane">
      <div className="detail-toolbar">
        <button className="tool-btn" title="В архив" onClick={() => onAction('archive')}><Archive size={18} /></button>
        <button className="tool-btn" title="Удалить" onClick={() => onAction('delete')}><Trash size={18} /></button>
        <button
          className={`tool-btn ${email.starred ? 'active' : ''}`}
          title="В избранное" onClick={() => onAction('star')}
        ><Star size={18} filled={email.starred} /></button>
        <span className="tool-sep" />
        <button className="tool-btn" title="Ответить" onClick={() => onAction('reply')}><Reply size={18} /></button>
        <button className="tool-btn" title="Переслать" onClick={() => onAction('forward')}><Forward size={18} /></button>
        <span className="tool-spacer" />
        <button className="tool-move"><Folder size={16} /> Переместить</button>
        <button className="tool-btn" title="Ещё"><More size={18} /></button>
      </div>

      <div className="detail-scroll">
        <div className="msg-head">
          <div className="avatar" style={{ background: avatarColor(email.from_email) }}>
            {isError ? <AlertTriangle size={20} /> : initials(email.from_name)}
          </div>
          <div className="mh-text">
            <div className="mh-name">{email.from_name}</div>
            <div className="mh-to">
              <b>кому:</b> {email.to || 'it-support@company.ru'}
              {email.from_email && <> · <b>от:</b> {email.from_email}</>}
            </div>
            <div className="mh-ticket">Заявка {email.ticket_id} · {email.category_label}</div>
          </div>
          <div className="mh-date"><Clock size={12} /> {formatTime(email.received_at)}</div>
        </div>

        <div className="msg-subject">{email.subject}</div>

        <div className="msg-chips">
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
        </div>

        {!isError && (
          <AiPanel
            email={email}
            summary={summary}
            summarizing={summarizing}
            scope={scope}
            onScope={onScope}
            onSummarize={onSummarize}
          />
        )}

        <div className="msg-body">{email.body}</div>

        {email.attachments?.length > 0 && (
          <div className="msg-attachments">
            {email.attachments.map((a) => (
              <div className="attach-card" key={a}>
                <span className="ac-ico"><Paperclip size={15} /></span>
                {a}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="detail-footer">
        <button className="btn-primary" onClick={() => onAction('reply')}>
          <Reply size={16} /> Ответить
        </button>
        <button className="btn-ghost" onClick={() => onAction('forward')}>
          <Forward size={16} /> Переслать
        </button>
      </div>
    </section>
  )
}
