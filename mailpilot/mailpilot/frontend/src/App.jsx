import { useCallback, useEffect, useMemo, useState } from 'react'
import Sidebar from './components/Sidebar.jsx'
import ListPane from './components/ListPane.jsx'
import DetailPane from './components/DetailPane.jsx'
import { api } from './api.js'

export default function App() {
  const [folders, setFolders] = useState(null)
  const [health, setHealth] = useState(null)
  const [view, setView] = useState({ type: 'folder', value: 'inbox', label: 'Входящие' })

  const [emails, setEmails] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [filter, setFilter] = useState('all')

  const [draft, setDraft] = useState('')
  const [query, setQuery] = useState('')
  const [isSearch, setIsSearch] = useState(false)
  const [searching, setSearching] = useState(false)

  const [summary, setSummary] = useState(null)
  const [summarizing, setSummarizing] = useState(false)
  const [scope, setScope] = useState('email')

  const [toast, setToast] = useState(null)

  const tagMeta = useMemo(() => {
    const m = {}
    for (const t of folders?.tags || []) m[t.id] = { label: t.label, color: t.color }
    return m
  }, [folders])

  const showToast = (text, undo) => {
    setToast({ text, undo })
    setTimeout(() => setToast((t) => (t && t.text === text ? null : t)), 4000)
  }

  const loadFolders = useCallback(async () => {
    try {
      setFolders(await api.folders())
    } catch (e) { /* ignore */ }
  }, [])

  useEffect(() => {
    loadFolders()
    api.health().then(setHealth).catch(() => {})
  }, [loadFolders])

  // ---- загрузка списка по текущему виду/фильтру ----
  const loadList = useCallback(async (autoSelect) => {
    const params = {}
    if (view.type === 'folder') params.folder = view.value
    else { params.folder = 'inbox'; params[view.type] = view.value }
    if (filter === 'unread') params.unread = true
    if (filter === 'starred') params.starred = true
    try {
      const data = await api.emails(params)
      setEmails(data.items)
      if (autoSelect) {
        setSelectedId(data.items.length ? data.items[0].id : null)
      } else if (!data.items.find((e) => e.id === selectedId)) {
        // selection ушло из списка — оставляем detail как есть только если ещё открыт
      }
    } catch (e) { showToast('Не удалось загрузить письма') }
  }, [view, filter, selectedId])

  useEffect(() => {
    if (!isSearch) loadList(true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, filter])

  // ---- загрузка письма ----
  useEffect(() => {
    if (!selectedId) { setDetail(null); return }
    setSummary(null); setScope('email'); setSummarizing(false)
    api.email(selectedId).then((d) => {
      setDetail(d)
      setEmails((list) => list.map((e) => (e.id === d.id ? { ...e, unread: false } : e)))
      loadFolders()
    }).catch(() => showToast('Не удалось открыть письмо'))
  }, [selectedId, loadFolders])

  // ---- поиск ----
  const submitSearch = async () => {
    const q = draft.trim()
    if (!q) return
    setSearching(true); setIsSearch(true); setQuery(q); setSelectedId(null)
    try {
      const data = await api.search(q)
      setEmails(data.results)
      if (data.results.length) setSelectedId(data.results[0].id)
    } catch (e) { showToast('Ошибка поиска') }
    finally { setSearching(false) }
  }
  const clearSearch = () => {
    setDraft(''); setQuery(''); setIsSearch(false); setSelectedId(null)
    loadList(true)
  }

  const onSelectView = (v) => {
    setView(v); setFilter('all'); setIsSearch(false); setDraft(''); setQuery('')
  }

  // ---- действия над письмом ----
  const onAction = async (action) => {
    if (!detail) return
    const id = detail.id
    if (action === 'reply' || action === 'forward') {
      showToast(action === 'reply' ? 'Черновик ответа создан (демо)' : 'Письмо переслано (демо)')
      return
    }
    try {
      const updated = await api.action(id, action)
      if (action === 'star') {
        setDetail((d) => ({ ...d, starred: updated.starred }))
        setEmails((list) => list.map((e) => (e.id === id ? { ...e, starred: updated.starred } : e)))
        loadFolders()
        return
      }
      // archive / delete -> убрать из списка, закрыть detail
      setEmails((list) => list.filter((e) => e.id !== id))
      setDetail(null); setSelectedId(null)
      loadFolders()
      const undoAction = action === 'archive' ? 'unarchive' : 'restore'
      showToast(action === 'archive' ? 'Письмо в архиве' : 'Письмо удалено', async () => {
        await api.action(id, undoAction)
        setToast(null); loadFolders(); if (!isSearch) loadList(false)
      })
    } catch (e) { showToast('Не удалось выполнить действие') }
  }

  // ---- AI-сводка ----
  const doSummarize = async (sc) => {
    if (!selectedId) return
    setSummarizing(true)
    try {
      const s = await api.summarize(selectedId, sc)
      setSummary(s)
    } catch (e) { showToast('Не удалось получить AI-сводку') }
    finally { setSummarizing(false) }
  }
  const onScope = (sc) => { setScope(sc); if (summary) doSummarize(sc) }

  // ---- подзаголовок списка ----
  const subtitle = useMemo(() => {
    if (isSearch) return `Найдено: ${emails.length} · BM25 + семантика`
    const n = emails.length
    const word = n % 10 === 1 && n % 100 !== 11 ? 'письмо' : 'писем'
    if (view.type === 'folder' && view.value === 'inbox') {
      const unread = folders?.folders?.inbox_unread ?? 0
      return `${n} ${word}, ${unread} непрочитанных`
    }
    return `${n} ${word}`
  }, [emails, isSearch, view, folders])

  const title = isSearch ? `Поиск: «${query}»` : view.label

  return (
    <div className="app">
      <Sidebar folders={folders} view={view} onSelect={onSelectView} health={health} />
      <ListPane
        title={title}
        subtitle={subtitle}
        emails={emails}
        selectedId={selectedId}
        onSelect={setSelectedId}
        query={query}
        draft={draft}
        onDraftChange={setDraft}
        onSubmitSearch={submitSearch}
        onClearSearch={clearSearch}
        isSearch={isSearch}
        searching={searching}
        filter={filter}
        onFilter={setFilter}
        tagMeta={tagMeta}
        onRefresh={() => (isSearch ? submitSearch() : loadList(false))}
      />
      <DetailPane
        email={detail}
        onAction={onAction}
        summary={summary}
        summarizing={summarizing}
        scope={scope}
        onScope={onScope}
        onSummarize={doSummarize}
        tagMeta={tagMeta}
      />

      {toast && (
        <div className="toast">
          <span>{toast.text}</span>
          {toast.undo && <button onClick={toast.undo}>Отменить</button>}
        </div>
      )}
    </div>
  )
}
