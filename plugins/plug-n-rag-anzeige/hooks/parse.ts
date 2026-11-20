// Pure helpers: recognise plug-n-rag calls in a Bash command and read their text output.
// The output format is plug-n-rag's own (German, stable); nothing here touches the engine.

export type Kind =
  | 'suche' | 'lesen' | 'gliederung' | 'verwandt' | 'karte' | 'sync' | 'aufnehmen'
  | 'nach-main' | 'status' | 'cloud' | 'umziehen' | 'andere'

const ALIAS: Record<string, Kind> = {
  suche: 'suche', search: 'suche', lesen: 'lesen', read: 'lesen', gliederung: 'gliederung',
  outline: 'gliederung', verwandt: 'verwandt', related: 'verwandt', karte: 'karte', map: 'karte',
  sync: 'sync', reindex: 'sync', hydrate: 'sync', aufnehmen: 'aufnehmen', ingest: 'aufnehmen',
  'nach-main': 'nach-main', status: 'status', cloud: 'cloud', umziehen: 'umziehen',
}

const HIDDEN = new Set(['session-start', 'stop', 'anzeige-daten', 'mcp'])

export type Call = { kind: Kind; sub: string; rest: string }

/** The plug-n-rag call in a Bash command (a bare command, a full launcher path or `uv run`). */
export function parseCommand(command: string): Call | null {
  const re = /(?:^|[\s"'/&;|(])plug-n-rag["']?((?:\s+--ordner(?:\s+|=)(?:"[^"]*"|'[^']*'|\S+))?)\s+([a-z][a-z-]*)([^\n]*)/g
  let m: RegExpExecArray | null
  while ((m = re.exec(command)) !== null) {
    const sub = m[2] ?? ''
    if (HIDDEN.has(sub)) return null
    return { kind: ALIAS[sub] ?? 'andere', sub, rest: (m[3] ?? '').trim() }
  }
  return null
}

export type Section = { label: string; range: string; relevance: string }
export type Hit = { rank: number; path: string; tokens: number; sections: Section[] }
export type Search = {
  query: string
  isNothing: boolean
  isKeywordOnly: boolean
  outside: string | null
  hits: Hit[]
  more: number
  notices: string[]
}

const num = (s: string) => Number(s.replace(/\./g, '')) || 0

export function parseSearch(out: string): Search {
  const res: Search = { query: '', isNothing: false, isKeywordOnly: false, outside: null, hits: [], more: 0, notices: [] }
  for (const raw of out.split('\n')) {
    const line = raw.replace(/\s+$/, '')
    let m: RegExpMatchArray | null
    if ((m = line.match(/^Hinweis: (.*)$/))) { res.notices.push((m[1] ?? '')); continue }
    if ((m = line.match(/^Nichts Passendes gefunden zu „(.*)“/))) { res.isNothing = true; res.query = (m[1] ?? ''); continue }
    if ((m = line.match(/^\d+ Notiz(?:en)? zu „(.*)“(.*)$/))) {
      res.query = (m[1] ?? '')
      res.isKeywordOnly = (m[2] ?? '').includes('nur Stichwortsuche')
      const o = (m[2] ?? '').match(/(Außerhalb von [^ ]+ gefunden|Ohne Filter \([^)]*\) gefunden)/)
      res.outside = o ? (o[1] ?? null) : null
      continue
    }
    if ((m = line.match(/^(\d+)\. (.+?) \(([\d.]+) Tokens\)$/))) {
      res.hits.push({ rank: Number((m[1] ?? '')), path: (m[2] ?? ''), tokens: num((m[3] ?? '')), sections: [] })
      continue
    }
    if ((m = line.match(/^\s+› (.+), ((?:Z|S|Abs)\. [\d–]+(?: \(gedruckt S\. [^)]+\))?) \((sehr passend|passend|am Rande)\)$/))) {
      const hit = res.hits[res.hits.length - 1]
      if (hit) hit.sections.push({ label: (m[1] ?? ''), range: (m[2] ?? ''), relevance: (m[3] ?? '') })
      continue
    }
    if ((m = line.match(/^\[--weiter: (\d+)/))) res.more = Number((m[1] ?? ''))
  }
  return res
}

/** First line of `lesen`: `path › label (N Tokens)`. */
export function parseRead(out: string): { path: string; label: string; tokens: number } | null {
  const m = (out.split('\n')[0] ?? '').match(/^(.+?) › (.+) \(([\d.]+) Tokens\)$/)
  return m ? { path: (m[1] ?? ''), label: (m[2] ?? ''), tokens: num((m[3] ?? '')) } : null
}

export const estimateTokens = (text: string) => Math.max(0, Math.round(text.length / 3.8))

export const RELEVANCE_MARK: Record<string, string> = {
  'sehr passend': '●●●',
  passend: '●●○',
  'am Rande': '●○○',
}

const firstLine = (s: string) => (s.split('\n').find(l => l.trim()) ?? '').trim()
const shortPath = (p: string) => (p.length > 48 ? '…' + p.slice(-47) : p)
const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`

/** One calm line for a call: what plug-n-rag did, in plain German. */
export function summarize(call: Call, out: string | undefined, isRunning: boolean, isErrored: boolean): string {
  if (isRunning) {
    return {
      suche: 'durchsucht deine Vault …', lesen: 'liest einen Abschnitt …', gliederung: 'liest die Gliederung …',
      verwandt: 'sucht Verwandtes …', karte: 'erstellt den Überblick …', sync: 'gleicht ab …',
      aufnehmen: 'nimmt PDFs auf …', 'nach-main': 'übernimmt nach main …', status: 'prüft den Zustand …',
      cloud: 'prüft die Cloud-Einrichtung …', umziehen: 'stellt den Ordneraufbau um …', andere: 'arbeitet …',
    }[call.kind]
  }
  const text = out ?? ''
  if (isErrored) return `Fehler: ${firstLine(text) || 'unbekannt'}`
  switch (call.kind) {
    case 'suche': {
      const s = parseSearch(text)
      if (s.isNothing) return `Gesucht: nichts Passendes zu „${s.query}“`
      if (!s.hits.length) return firstLine(text) || 'Gesucht'
      const best = s.hits[0]?.sections[0]?.relevance
      return `Gesucht: ${plural(s.hits.length, 'Notiz', 'Notizen')}${best ? ` · beste ${best}` : ''}` +
        (s.more ? ` · ${s.more} weitere` : '') + (s.isKeywordOnly ? ' · nur Stichwort' : '')
    }
    case 'lesen': {
      const r = parseRead(text)
      return r ? `Gelesen: ${shortPath(r.path)} › ${r.label}` : firstLine(text)
    }
    case 'gliederung': {
      const l = firstLine(text)
      return `Gliederung: ${shortPath(l.split(' – ')[0] ?? l)}`
    }
    case 'verwandt':
      return `Verwandtes zu ${shortPath(firstLine(text).replace(/^Verwandt mit /, '').replace(/:$/, ''))}`
    case 'karte':
      return 'Überblick über die Vault'
    case 'sync': {
      const l = firstLine(text)
      return l.startsWith('Abgleich: nichts zu tun') ? 'Abgeglichen: alles aktuell' : l.replace(/^Abgleich: /, 'Abgeglichen: ')
    }
    case 'nach-main': {
      const l = text.split('\n').find(x => x.startsWith('Auf ') || x.startsWith('Nicht übernommen') || x.startsWith('Abgebrochen') || x.startsWith('Push')) ?? firstLine(text)
      return l
    }
    default:
      return firstLine(text) || `plug-n-rag ${call.sub}`
  }
}

export const ICON: Record<Kind, string> = {
  suche: '🔍', lesen: '📖', gliederung: '🗂', verwandt: '🔗', karte: '🗺', sync: '🔄', aufnehmen: '📄',
  'nach-main': '⤴', status: 'ℹ', cloud: '☁', umziehen: '📦', andere: '•',
}
