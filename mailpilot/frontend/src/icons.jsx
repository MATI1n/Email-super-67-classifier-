// Набор инлайн-SVG иконок (без внешних зависимостей).
const S = ({ children, size = 18, stroke = 2, ...p }) => (
  <svg
    width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={stroke} strokeLinecap="round"
    strokeLinejoin="round" {...p}
  >
    {children}
  </svg>
)

export const Inbox = (p) => (<S {...p}><path d="M22 12h-6l-2 3h-4l-2-3H2" /><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" /></S>)
export const Send = (p) => (<S {...p}><path d="m22 2-7 20-4-9-9-4Z" /><path d="M22 2 11 13" /></S>)
export const Star = ({ filled, ...p }) => (<S {...p} fill={filled ? 'currentColor' : 'none'}><path d="M11.5 2.6 14 7.7l5.6.8-4 3.9.9 5.6-5-2.6-5 2.6 1-5.6-4-3.9 5.5-.8z" /></S>)
export const Archive = (p) => (<S {...p}><rect width="20" height="5" x="2" y="3" rx="1" /><path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8" /><path d="M10 12h4" /></S>)
export const Trash = (p) => (<S {...p}><path d="M3 6h18" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" /></S>)
export const Draft = (p) => (<S {...p}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6" /></S>)
export const Search = (p) => (<S {...p}><circle cx="11" cy="11" r="8" /><path d="m21 21-4.3-4.3" /></S>)
export const Compose = (p) => (<S {...p}><path d="M12 20h9" /><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" /></S>)
export const Reply = (p) => (<S {...p}><path d="M9 17l-5-5 5-5" /><path d="M4 12h11a4 4 0 0 1 4 4v2" /></S>)
export const Forward = (p) => (<S {...p}><path d="M15 17l5-5-5-5" /><path d="M20 12H9a4 4 0 0 0-4 4v2" /></S>)
export const Sparkles = (p) => (<S {...p}><path d="M12 3l1.9 4.6L18.5 9l-4.6 1.9L12 15l-1.9-4.1L5.5 9l4.6-1.4z" /><path d="M5 19l.8-2 2-.8-2-.8L5 13.4l-.8 2-2 .8 2 .8z" /><path d="M19 17l.6-1.5L21 15l-1.4-.6L19 13l-.6 1.4L17 15l1.4.5z" /></S>)
export const Paperclip = (p) => (<S {...p}><path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48" /></S>)
export const Folder = ({ color = 'currentColor', ...p }) => (<S {...p} stroke={color} fill={color} fillOpacity="0.18"><path d="M4 20a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2z" /></S>)
export const Chevron = (p) => (<S {...p}><path d="m6 9 6 6 6-6" /></S>)
export const Refresh = (p) => (<S {...p}><path d="M3 12a9 9 0 0 1 15-6.7L21 8" /><path d="M21 3v5h-5" /><path d="M21 12a9 9 0 0 1-15 6.7L3 16" /><path d="M3 21v-5h5" /></S>)
export const More = (p) => (<S {...p}><circle cx="12" cy="12" r="1" /><circle cx="19" cy="12" r="1" /><circle cx="5" cy="12" r="1" /></S>)
export const Tag = (p) => (<S {...p}><path d="M12.6 2.6A2 2 0 0 0 11.2 2H4a2 2 0 0 0-2 2v7.2a2 2 0 0 0 .6 1.4l8.2 8.2a2 2 0 0 0 2.8 0l6.4-6.4a2 2 0 0 0 0-2.8z" /><circle cx="7.5" cy="7.5" r="1.2" fill="currentColor" /></S>)
export const Mail = (p) => (<S {...p}><rect width="20" height="16" x="2" y="4" rx="2" /><path d="m22 7-10 5L2 7" /></S>)
export const Dot = ({ size = 8, color = 'currentColor' }) => (
  <svg width={size} height={size} viewBox="0 0 8 8"><circle cx="4" cy="4" r="4" fill={color} /></svg>
)
export const Clock = (p) => (<S {...p}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></S>)
export const AlertTriangle = (p) => (<S {...p}><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" /><path d="M12 9v4" /><path d="M12 17h.01" /></S>)
