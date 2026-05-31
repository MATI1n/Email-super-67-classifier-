// Вспомогательные функции отображения.

const AVATAR_COLORS = [
  '#0a7cff', '#0ca678', '#f08c00', '#e5484d', '#ae3ec9',
  '#d6336c', '#1098ad', '#5b5bff', '#f76707', '#37b24d',
]

export function avatarColor(seed = '') {
  let h = 0
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) >>> 0
  return AVATAR_COLORS[h % AVATAR_COLORS.length]
}

export function initials(name = '') {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (!parts.length) return '?'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[1][0]).toUpperCase()
}

const MONTHS = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']

export function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const sameDay = d.toDateString() === now.toDateString()
  if (sameDay) {
    return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
  }
  const yesterday = new Date(now); yesterday.setDate(now.getDate() - 1)
  if (d.toDateString() === yesterday.toDateString()) return 'вчера'
  if (d.getFullYear() === now.getFullYear()) return `${d.getDate()} ${MONTHS[d.getMonth()]}`
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit' })
}

// Цвета «умных» папок (категорий классификатора).
export const CATEGORY_COLOR = {
  urgent: '#e5484d',
  alerts: '#f08c00',
  spam: '#868e96',
  hr_documents: '#ae3ec9',
  newsletters: '#1098ad',
  support: '#0a7cff',
  errors: '#d6336c',
}

// Подсветка термов запроса в сниппете поиска.
export function highlight(text, query) {
  if (!query) return [text]
  const terms = query.toLowerCase().split(/\s+/).filter((t) => t.length > 1)
  if (!terms.length) return [text]
  const re = new RegExp(`(${terms.map(escapeRe).join('|')})`, 'gi')
  return String(text).split(re).map((part, i) =>
    re.test(part) ? { mark: part, key: i } : part
  )
}
function escapeRe(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') }
