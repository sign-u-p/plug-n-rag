// Pure helpers: recognise plug-n-rag calls in a Bash command and read their text output.
// plug-n-rag writes German or English (the vault's language); both formats are recognised,
// and the display speaks the same language. Nothing here touches the engine.

export type Lang = 'de' | 'en'

let current: Lang = 'de'

/** Set the display language (from plug-n-rag's snapshot or from an output it just wrote). */
export function setLang(lang: unknown): void {
  if (lang === 'de' || lang === 'en') current = lang
}

export const lang = (): Lang => current

/** The text in the display language. */
export const T = (de: string, en: string): string => (current === 'en' ? en : de)

/** Which language an output of plug-n-rag is written in, if it shows. */
export function detectLang(out: string): Lang | null {
  if (/^\d+ notes? for “|^Nothing relevant found for “|\(\d[\d,]* tokens\)$|^Sync: |^Published to /m.test(out)) return 'en'
  if (/^\d+ Notiz(?:en)? zu „|^Nichts Passendes gefunden zu „|\(\d[\d.]* Tokens\)$|^Abgleich: |^Auf \S+ übernommen/m.test(out)) return 'de'
  return null
}

export type Kind =
  | 'suche' | 'lesen' | 'gliederung' | 'verwandt' | 'karte' | 'sync' | 'aufnehmen'
  | 'nach-main' | 'status' | 'cloud' | 'umziehen' | 'andere'

const ALIAS: Record<string, Kind> = {
  suche: 'suche', search: 'suche', lesen: 'lesen', read: 'lesen', gliederung: 'gliederung',
  outline: 'gliederung', verwandt: 'verwandt', related: 'verwandt', karte: 'karte', map: 'karte',
  sync: 'sync', reindex: 'sync', hydrate: 'sync', aufnehmen: 'aufnehmen', ingest: 'aufnehmen',
  'nach-main': 'nach-main', 'to-main': 'nach-main', status: 'status', cloud: 'cloud',
  umziehen: 'umziehen', migrate: 'umziehen',
}

const HIDDEN = new Set(['session-start', 'stop', 'anzeige-daten', 'display-data', 'mcp'])

export type Call = { kind: Kind; sub: string; rest: string }

/** The plug-n-rag call in a Bash command (a bare command, a full launcher path or `uv run`). */
export function parseCommand(command: string): Call | null {
  const re = /(?:^|[\s"'/&;|(])plug-n-rag["']?((?:\s+--(?:ordner|folder)(?:\s+|=)(?:"[^"]*"|'[^']*'|\S+))?)\s+([a-z][a-z-]*)([^\n]*)/g
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
  /** plug-n-rag ≥ 0.9.3: the search was incomplete (model loading, index partly built) */
  isProvisional: boolean
  outside: string | null
  hits: Hit[]
  more: number
  notices: string[]
}

// whole numbers only: "2.400" (German) and "2,400" (English) are both 2400
const num = (s: string) => Number(s.replace(/[.,]/g, '')) || 0

const RELEVANCE = '(sehr passend|passend|am Rande|very relevant|relevant|marginal)'
const RANGE = '((?:Z|S|Abs|l|p|para)\\. [\\d–]+(?: \\((?:gedruckt S|printed p)\\. [^)]+\\))?)'
const SECTION_RE = new RegExp(`^\\s+› (.+), ${RANGE} \\(${RELEVANCE}\\)$`)

export function parseSearch(out: string): Search {
  const res: Search = { query: '', isNothing: false, isKeywordOnly: false, isProvisional: false, outside: null, hits: [], more: 0, notices: [] }
  for (const raw of out.split('\n')) {
    const line = raw.replace(/\s+$/, '')
    let m: RegExpMatchArray | null
    if ((m = line.match(/^(?:Suchmodus|Search mode): (.*)$/))) {
      const mode = m[1] ?? ''
      res.isKeywordOnly = /^(?:nur Stichwort|keyword only)/.test(mode)
      res.isProvisional = !/(?:Index vollständig|index complete)/.test(mode)
      continue
    }
    if (/^⚠ (?:Vorläufiges Ergebnis|Provisional result)/.test(line)) { res.isProvisional = true; continue }
    if ((m = line.match(/^(?:Hinweis|Note): (.*)$/))) { res.notices.push((m[1] ?? '')); continue }
    if ((m = line.match(/^(?:Nichts Passendes gefunden zu „(.*)“|Nothing relevant found for “(.*)”)/))) {
      res.isNothing = true
      res.query = m[1] ?? m[2] ?? ''
      continue
    }
    if ((m = line.match(/^\d+ (?:Notiz(?:en)? zu „(.*)“|notes? for “(.*)”)(.*)$/))) {
      res.query = m[1] ?? m[2] ?? ''
      const tail = m[3] ?? ''
      if (tail.includes('nur Stichwortsuche') || tail.includes('keyword search only')) res.isKeywordOnly = true
      const o = tail.match(/(Außerhalb von [^ ]+ gefunden|Ohne Filter \([^)]*\) gefunden|Found outside \S+|Found without filter \([^)]*\))/)
      res.outside = o ? (o[1] ?? null) : null
      continue
    }
    if ((m = line.match(/^(\d+)\. (.+?) \(([\d.,]+) [Tt]okens\)$/))) {
      res.hits.push({ rank: Number((m[1] ?? '')), path: (m[2] ?? ''), tokens: num((m[3] ?? '')), sections: [] })
      continue
    }
    if ((m = line.match(SECTION_RE))) {
      const hit = res.hits[res.hits.length - 1]
      if (hit) hit.sections.push({ label: (m[1] ?? ''), range: (m[2] ?? ''), relevance: (m[3] ?? '') })
      continue
    }
    if ((m = line.match(/^\[--(?:weiter|more): (\d+)/))) res.more = Number((m[1] ?? ''))
  }
  return res
}

export type Read = { path: string; label: string; tokens: number }

const READ_HEAD = /^(.+?) › (.+) \(([\d.,]+) [Tt]okens\)$/

/** Every section header in the output of `lesen`/`read`: `path › label (N Tokens)`.
 *  Claude sometimes reads several sections in one command, separated by lines like `====`. */
export function parseReads(out: string): Read[] {
  const found: Read[] = []
  for (const line of out.split('\n')) {
    const m = line.trim().match(READ_HEAD)
    if (m) found.push({ path: m[1] ?? '', label: m[2] ?? '', tokens: num(m[3] ?? '') })
  }
  return found
}

/** The first section read (kept for callers that need one). */
export function parseRead(out: string): Read | null {
  return parseReads(out)[0] ?? null
}

export const estimateTokens = (text: string) => Math.max(0, Math.round(text.length / 3.8))

export const RELEVANCE_MARK: Record<string, string> = {
  'sehr passend': '●●●', passend: '●●○', 'am Rande': '●○○',
  'very relevant': '●●●', relevant: '●●○', marginal: '●○○',
}

export const isMarginal = (relevance: string) => relevance === 'am Rande' || relevance === 'marginal'

// the first line that says something (not a separator such as "====" or "----")
const firstLine = (s: string) => (s.split('\n').find(l => /[\p{L}\p{N}]/u.test(l)) ?? '').trim()
const shortPath = (p: string) => (p.length > 48 ? '…' + p.slice(-47) : p)
const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`

const RUNNING: Record<Kind, [string, string]> = {
  suche: ['durchsucht deine Vault …', 'searching your vault …'],
  lesen: ['liest einen Abschnitt …', 'reading a section …'],
  gliederung: ['liest die Gliederung …', 'reading the outline …'],
  verwandt: ['sucht Verwandtes …', 'looking for related notes …'],
  karte: ['erstellt den Überblick …', 'building the overview …'],
  sync: ['gleicht ab …', 'syncing …'],
  aufnehmen: ['nimmt PDFs auf …', 'ingesting PDFs …'],
  'nach-main': ['übernimmt nach main …', 'publishing to main …'],
  status: ['prüft den Zustand …', 'checking the state …'],
  cloud: ['prüft die Cloud-Einrichtung …', 'checking the cloud setup …'],
  umziehen: ['stellt den Ordneraufbau um …', 'switching the folder layout …'],
  andere: ['arbeitet …', 'working …'],
}

/** One calm line for a call: what plug-n-rag did, in plain words. */
export function summarize(call: Call, out: string | undefined, isRunning: boolean, isErrored: boolean): string {
  if (isRunning) {
    const [de, en] = RUNNING[call.kind]
    return T(de, en)
  }
  const text = out ?? ''
  if (isErrored) return T('Fehler: ', 'Error: ') + (firstLine(text) || T('unbekannt', 'unknown'))
  switch (call.kind) {
    case 'suche': {
      const s = parseSearch(text)
      if (s.isNothing) return T(`Gesucht: nichts Passendes zu „${s.query}“`, `Searched: nothing relevant for “${s.query}”`) + (s.isProvisional ? T(' (vorläufig)', ' (provisional)') : '')
      if (!s.hits.length) return firstLine(text) || T('Gesucht', 'Searched')
      const best = s.hits[0]?.sections[0]?.relevance
      return T('Gesucht: ', 'Searched: ') + T(plural(s.hits.length, 'Notiz', 'Notizen'), plural(s.hits.length, 'note', 'notes')) +
        (best ? T(` · beste ${best}`, ` · best ${best}`) : '') +
        (s.more ? T(` · ${s.more} weitere`, ` · ${s.more} more`) : '') +
        (s.isKeywordOnly ? T(' · nur Stichwort', ' · keyword only') : s.isProvisional ? T(' · vorläufig', ' · provisional') : '')
    }
    case 'lesen': {
      const reads = parseReads(text)
      if (reads.length === 1) return T('Gelesen: ', 'Read: ') + `${shortPath(reads[0]!.path)} › ${reads[0]!.label}`
      if (reads.length > 1) {
        const notes = new Set(reads.map(x => x.path)).size
        return T(`Gelesen: ${plural(reads.length, 'Abschnitt', 'Abschnitte')} aus ${plural(notes, 'Notiz', 'Notizen')}`,
          `Read: ${plural(reads.length, 'section', 'sections')} from ${plural(notes, 'note', 'notes')}`)
      }
      return firstLine(text)
    }
    case 'gliederung': {
      const l = firstLine(text)
      return T('Gliederung: ', 'Outline: ') + shortPath(l.split(' – ')[0] ?? l)
    }
    case 'verwandt':
      return T('Verwandtes zu ', 'Related to ') +
        shortPath(firstLine(text).replace(/^(?:Verwandt mit|Related to) /, '').replace(/:$/, ''))
    case 'karte':
      return T('Überblick über die Vault', 'Overview of the vault')
    case 'sync': {
      const l = firstLine(text)
      if (/^(?:Abgleich: nichts zu tun|Sync: nothing to do)/.test(l)) return T('Abgeglichen: alles aktuell', 'Synced: all up to date')
      return l.replace(/^Abgleich: /, 'Abgeglichen: ').replace(/^Sync: /, 'Synced: ')
    }
    case 'nach-main': {
      const starts = ['Auf ', 'Nicht übernommen', 'Abgebrochen', 'Push', 'Published to', 'Not published', 'Stopped']
      return text.split('\n').find(x => starts.some(p => x.startsWith(p))) ?? firstLine(text)
    }
    default:
      return firstLine(text) || `plug-n-rag ${call.sub}`
  }
}

export const ICON: Record<Kind, string> = {
  suche: '🔍', lesen: '📖', gliederung: '🗂', verwandt: '🔗', karte: '🗺', sync: '🔄', aufnehmen: '📄',
  'nach-main': '⤴', status: 'ℹ', cloud: '☁', umziehen: '📦', andere: '•',
}
