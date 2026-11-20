// plug-n-rag Anzeige: shows quietly in the chat what plug-n-rag does.
//
// * a compact, expandable row in place of each `plug-n-rag …` Bash call (search, read, sync …)
// * a short word on the spinner while plug-n-rag works
// * a band above the prompt only while indexing runs or something waits for the person
// * a side pane (/pnr or a button) with the session's history, the vault and the savings
//
// It only reads and draws. It never changes a tool call, never sends anything on its own:
// buttons that suggest an action fill the prompt box, the person decides whether to send.
// Claude never sees what this mod draws, so it costs no tokens.

import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { Entry, Snapshot, Tab } from '../types'
import {
  ICON, RELEVANCE_MARK, estimateTokens, parseCommand, parseRead, parseSearch, summarize,
  type Call,
} from './parse'

const PANE = 'plug-n-rag'

const history = atom({ plugin: 'plug-n-rag-anzeige', key: 'history' } as const, [], { shape: 'history-1' })
const snap = atom({ plugin: 'plug-n-rag-anzeige', key: 'snap' } as const, null, { shape: 'snap-1' })
const tab = atom({ plugin: 'plug-n-rag-anzeige', key: 'tab' } as const, 'verlauf' as Tab)
const openRows = atom({ plugin: 'plug-n-rag-anzeige', key: 'open' } as const, [] as string[])
const bandHidden = atom({ plugin: 'plug-n-rag-anzeige', key: 'bandHidden' } as const, false)
const active = atom({ plugin: 'plug-n-rag-anzeige', key: 'active' } as const, null as string | null)

const fmt = (n: number) => n.toLocaleString('de-DE')

type Out = { stdout?: string; stderr?: string }

function bashCommand(input: unknown): string {
  return input && typeof input === 'object' && typeof (input as { command?: unknown }).command === 'string'
    ? (input as { command: string }).command
    : ''
}

function bashOutput(output: unknown): string | undefined {
  if (typeof output === 'string') return output
  if (output && typeof output === 'object') {
    const o = output as Out
    return [o.stdout ?? '', o.stderr ?? ''].filter(Boolean).join('\n')
  }
  return undefined
}

// Module state: starts over on a reload, which is fine (it only caches).
let cwd = ''
let launcher: string[] | null = null
let ticker: { cancel: () => void } | null = null

type Engine = any

// --- finding plug-n-rag ------------------------------------------------------------------
// Same marketplace, so plug-n-rag sits beside this plugin: in a folder marketplace (the repo)
// at <repo>/scripts, in the plugin cache at <cache>/<marketplace>/plug-n-rag/<version>/scripts.
async function findLauncher($: Engine): Promise<string[]> {
  if (launcher) return launcher
  const root = $.plugin.root.replace(/\\/g, '/')
  const up2 = root.replace(/\/[^/]+\/[^/]+\/?$/, '')
  const candidates = [`${up2}/scripts/plug-n-rag`]
  try {
    const dir = `${up2}/plug-n-rag`
    if (await $.fs.exists(dir)) {
      const versions = (await $.fs.list(dir)).map((e: { name: string }) => e.name).sort((a: string, b: string) =>
        a.localeCompare(b, undefined, { numeric: true }))
      for (const v of versions.reverse()) candidates.push(`${dir}/${v}/scripts/plug-n-rag`)
    }
  } catch {
    // the cache layout is only a convenience; other candidates follow
  }
  const home = root.split('/.claude/')[0]
  if (home && home !== root) candidates.push(`${home}/.cache/plug-n-rag/plug-n-rag`)
  for (const c of candidates) {
    try {
      if (await $.fs.exists(c)) return (launcher = ['sh', c])
    } catch {
      // try the next one
    }
  }
  return (launcher = ['plug-n-rag'])
}

// Is there a vault or an indexed folder here or above? Checked before asking plug-n-rag for data,
// so a session in an unrelated project starts nothing at all.
async function isRelevant($: Engine, start: string): Promise<boolean> {
  if (!start) return false
  const norm = (p: string) => p.replace(/\\/g, '/').replace(/\/+$/, '')
  let dir = norm(start)
  for (let i = 0; i < 40 && dir; i++) {
    for (const marker of ['.obsidian', '.plug-n-rag/plug-n-rag.yml', 'plug-n-rag.yml']) {
      try {
        if (await $.fs.exists(`${dir}/${marker}`)) return true
      } catch {
        // unreadable: treat as absent
      }
    }
    const parent = dir.replace(/\/[^/]*$/, '')
    if (parent === dir) break
    dir = parent
  }
  // centrally stored collections are listed in the user's config folder
  const home = norm($.plugin.root).split('/.claude/')[0]
  for (const reg of [`${home}/.config/plug-n-rag/collections.json`, `${home}/AppData/Roaming/plug-n-rag/collections.json`]) {
    try {
      if (!(await $.fs.exists(reg))) continue
      const roots = Object.keys(JSON.parse(String(await $.fs.read(reg))) as Record<string, string>).map(norm)
      const here = norm(start)
      if (roots.some(r => here === r || here.startsWith(r + '/'))) return true
    } catch {
      // a broken list only means: not found
    }
  }
  return false
}

async function refresh($: Engine): Promise<void> {
  try {
    const argv = await findLauncher($)
    const run = await $.process.run([...argv, 'anzeige-daten'], { cwd: cwd || undefined, timeoutMs: 120_000 })
    if (run.exitCode !== 0) return
    const data = JSON.parse(run.stdout.trim().split('\n').pop() ?? 'null') as Snapshot | null
    if (!data) return
    await update($, snap, () => data)
    const isRunning = Boolean(data.indexing?.running)
    if (isRunning && !ticker) {
      ticker = $.clock.every(10_000, () => { void refresh($) })
    } else if (!isRunning && ticker) {
      ticker.cancel()
      ticker = null
    }
  } catch {
    // No plug-n-rag (yet), an older version or no uv: the display simply stays quiet.
  }
}

async function record(
  $: Engine, id: string, call: Call, out: string, isOk: boolean,
): Promise<void> {
  let fullTokens = 0
  if (call.kind === 'suche') fullTokens = parseSearch(out).hits.reduce((sum, x) => sum + x.tokens, 0)
  const entry: Entry = {
    id, kind: call.kind, summary: summarize(call, out, false, !isOk), at: await $.clock.now(), isOk,
    tokens: call.kind === 'lesen' ? parseRead(out)?.tokens ?? estimateTokens(out) : estimateTokens(out),
    fullTokens,
  }
  await update($, history, list => [...list.filter(x => x.id !== id), entry].slice(-200))
}

function details($: any, e: any, call: Call, out: string) {
  const { Box, Text, Button } = $.ui.resolve(e)
  const openPane = async () => {
    await update($, tab, () => 'verlauf' as Tab)
    await $.ui.open({ id: PANE, title: 'plug-n-rag' })
  }
  const rows: any[] = []
  if (call.kind === 'suche') {
    const s = parseSearch(out)
    if (s.query) rows.push(<Text>{`„${s.query}“`}</Text>)
    for (const n of s.notices) rows.push(<Text dimColor>{`Hinweis: ${n}`}</Text>)
    if (s.outside) rows.push(<Text dimColor>{s.outside}</Text>)
    if (s.isNothing) rows.push(<Text>Nichts Passendes in deinen Notizen. Claude soll dann nicht so tun, als stünde es dort.</Text>)
    for (const hit of s.hits) {  // never name a variable `h`: JSX compiles to h(...)
      rows.push(<Text>{`${hit.rank}. ${hit.path}  (${fmt(hit.tokens)} Tokens)`}</Text>)
      for (const sec of hit.sections) {
        rows.push(
          <Text dimColor={sec.relevance === 'am Rande'}>
            {`    ${RELEVANCE_MARK[sec.relevance] ?? ''} ${sec.relevance} · ${sec.label}, ${sec.range}`}
          </Text>,
        )
      }
    }
    if (s.more) rows.push(<Text dimColor>{`+ ${s.more} weitere unter dem Schnitt (Claude kann sie mit --weiter holen)`}</Text>)
    const full = s.hits.reduce((sum, x) => sum + x.tokens, 0)
    if (full) {
      rows.push(<Text dimColor>{`Trefferliste: ca. ${fmt(estimateTokens(out))} Tokens statt ${fmt(full)} für alle Treffer ganz (geschätzt)`}</Text>)
    }
  } else {
    const lines = out.split('\n').filter(l => l.trim()).slice(0, 12)
    for (const l of lines) rows.push(<Text dimColor wrap="truncate-end">{l}</Text>)
    if (out.split('\n').length > 12) rows.push(<Text dimColor>…</Text>)
  }
  rows.push(<Text dimColor wrap="truncate-end">{`Befehl: plug-n-rag ${call.sub} ${call.rest}`.trim()}</Text>)
  return (
    <Box flexDirection="column" paddingLeft={2}>
      {rows}
      <Box>
        <Button key={`pane-${e.props.tool_use_id}`} plain dimColor onPress={openPane} label="Seitenleiste öffnen" />
      </Box>
    </Box>
  )
}

async function paneAsText($: any): Promise<string> {
  const s: Snapshot | null = await read($, snap)
  const list: Entry[] = await read($, history)
  const lines = ['plug-n-rag']
  if (s?.configured) lines.push(`${fmt(s.indexed ?? 0)} von ${fmt(s.files ?? 0)} Dateien semantisch durchsuchbar`)
  for (const x of list.slice(-10)) lines.push(`- ${x.summary}`)
  return lines.join('\n')
}
export const register: Register = on => {
  // --- session --------------------------------------------------------------------------------
  on('session.start', async ($, e, next) => {
    cwd = e.cwd
    await $.command.register({ name: 'pnr', description: 'plug-n-rag: Verlauf, Vault und Ersparnis anzeigen' })
    const started = await next(e)
    if (await isRelevant($, cwd)) void refresh($)
    return started
  })

  on('command.run', { command: 'pnr' }, async $ => {
    void refresh($)
    const opened = await $.ui.open({ id: PANE, title: 'plug-n-rag' })
    if (opened.isPlaced) return { text: 'plug-n-rag: Seitenleiste geöffnet.' }
    return { text: await paneAsText($) }
  })

  // --- follow plug-n-rag calls ----------------------------------------------------------------
  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    const call = parseCommand(e.command)
    if (!call) return next(e)
    await update($, active, () => call.kind)
    try {
      const ran = await next(e)
      const out = 'result' in ran && ran.result ? bashOutput(ran.result) ?? '' : ''
      const isOk = ran.deny === undefined && ran.isError !== true
      await record($, e.tool_use_id, call, out, isOk)
      return ran
    } finally {
      await update($, active, () => null)
      void refresh($)
    }
  })

  // --- the row in the transcript --------------------------------------------------------------
  on('ui.render', { component: 'ToolUse' }, async ($, e, next) => {
    if (e.props.tool !== 'Bash') return next(e)
    const call = parseCommand(bashCommand(e.props.input))
    if (!call) return next(e)
    if (e.props.isExpanded) return next(e) // ctrl+o / verbose: the full original row
    const { Box, Text, Button } = $.ui.resolve(e)
    const out = bashOutput(e.props.output)
    const line = summarize(call, out, e.props.isRunning, e.props.isErrored || e.props.isInterrupted)
    const id = e.props.tool_use_id

    if (e.surface === 'mobile') {
      // Mobile apps: the native row stays, one quiet line under it.
      return (
        <Box flexDirection="column">
          {await next(e)}
          <Text dimColor>{`plug-n-rag · ${line}`}</Text>
        </Box>
      )
    }

    const isOpen = (await read($, openRows)).includes(id)
    const canExpand = !e.props.isRunning && Boolean(out)
    const toggle = () => update($, openRows, ids => (ids.includes(id) ? ids.filter(x => x !== id) : [...ids, id].slice(-50)))

    return (
      <Box flexDirection="column">
        <Box gap={1}>
          <Text dimColor>{ICON[call.kind]}</Text>
          <Text dimColor>plug-n-rag</Text>
          <Text color={e.props.isErrored ? 'error' : undefined} wrap="truncate-end">{line}</Text>
          {canExpand && (
            <Button key={`toggle-${id}`} plain dimColor onPress={toggle}
              label={isOpen ? 'Details ausblenden' : 'Details'} />
          )}
        </Box>
        {isOpen && out ? details($, e, call, out) : null}
      </Box>
    )
  })

  // --- spinner ----------------------------------------------------------------------------
  const SPIN: Record<string, string> = {
    suche: 'Durchsucht deine Vault', lesen: 'Liest einen Abschnitt', gliederung: 'Liest die Gliederung',
    verwandt: 'Sucht Verwandtes', karte: 'Erstellt den Überblick', sync: 'Gleicht die Vault ab',
    aufnehmen: 'Nimmt PDFs auf', 'nach-main': 'Übernimmt nach main', umziehen: 'Stellt den Ordner um',
  }
  on('ui.render', { component: 'Spinner' }, async ($, e, next) => {
    const kind = await read($, active)
    const word = kind ? SPIN[kind] : undefined
    if (!word || e.props.mode !== 'tool-use') return next(e)
    return next({ ...e, props: { ...e.props, message: word } })
  })

  // --- band above the prompt: only when something runs or waits ---------------------------
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.props.hasSurvey) return next(e)
    const s = await read($, snap)
    if (!s?.configured || (await read($, bandHidden))) return next(e)
    const { Box, Text, Button, Progress } = $.ui.resolve(e)
    const hide = () => update($, bandHidden, () => true)
    const openPane = async () => {
      await update($, tab, () => 'vault' as Tab)
      await $.ui.open({ id: PANE, title: 'plug-n-rag' })
    }
    const ask = (text: string) => () => $.prompt.fill({ text })

    let message = ''
    let suggestion = ''
    let progress: { done: number; total: number } | null = null
    if (s.indexing?.running) {
      const done = s.indexing.done ?? 0
      const total = s.indexing.total ?? 0
      message = total ? `indexiert im Hintergrund: ${fmt(done)} von ${fmt(total)} Dateien · Stichwortsuche geht schon`
        : 'indexiert im Hintergrund · Stichwortsuche geht schon'
      if (total) progress = { done, total }
    } else if (s.model_mismatch) {
      message = 'Index passt nicht zum Modell: nur Stichwortsuche'
      suggestion = 'Bitte baue den plug-n-rag-Index neu auf (/plug-n-rag:reindex).'
    } else if (s.awaiting?.length) {
      const n = s.awaiting.length
      message = `${n} ${n === 1 ? 'eingescannte Datei wartet' : 'eingescannte Dateien warten'} auf Aufnahme`
      suggestion = 'Bitte nimm die eingescannten PDFs mit /plug-n-rag:aufnehmen auf.'
    } else if (s.needs_update) {
      message = 'aufgeräumter Ordneraufbau verfügbar'
      suggestion = 'Bitte stelle plug-n-rag mit `plug-n-rag umziehen` auf den neuen Ordneraufbau um.'
    } else {
      return next(e)
    }
    return (
      <Box flexDirection="column">
        <Box gap={1}>
          <Text dimColor>plug-n-rag</Text>
          <Text wrap="truncate-end">{message}</Text>
          {suggestion ? <Button key="band-do" plain onPress={ask(suggestion)} label="Vorschlag ins Eingabefeld" /> : null}
          <Button key="band-pane" plain dimColor onPress={openPane} label="Details" />
          <Button key="band-hide" plain dimColor role="dismiss" onPress={hide} label="Ausblenden" />
        </Box>
        {progress ? (
          <Progress label="Fortschritt der Indexierung" value={progress.done} max={progress.total}
            valueText={`${fmt(progress.done)} von ${fmt(progress.total)}`} />
        ) : null}
      </Box>
    )
  })

  // --- side pane ------------------------------------------------------------------------------
  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Button } = $.ui.resolve(e)
    const current = await read($, tab)
    const s = await read($, snap)
    const list = await read($, history)
    const choose = (t: Tab) => () => update($, tab, () => t)
    const tabButton = (t: Tab, label: string, key: string) => (
      <Button key={`tab-${t}`} hotkey={key} variant={current === t ? 'primary' : 'secondary'}
        onPress={choose(t)} label={current === t ? `${label} (gewählt)` : label} />
    )
    const body = current === 'verlauf' ? historyView(Text, Box, list)
      : current === 'vault' ? vaultView(Text, Box, s)
        : savingsView(Text, Box, list, s)
    return (
      <Box flexDirection="column" gap={1}>
        <Box gap={1}>
          {tabButton('verlauf', 'Verlauf', '1')}
          {tabButton('vault', 'Vault', '2')}
          {tabButton('ersparnis', 'Ersparnis', '3')}
          <Button key="refresh" plain dimColor hotkey="r" onPress={() => refresh($)} label="Aktualisieren" />
        </Box>
        {body}
      </Box>
    )
  })

  function historyView(Text: any, Box: any, list: Entry[]) {
    if (!list.length) {
      return <Text dimColor>In dieser Sitzung hat plug-n-rag noch nichts getan. Frag Claude etwas zu deinen Notizen.</Text>
    }
    return (
      <Box flexDirection="column">
        {[...list].reverse().slice(0, 60).map(x => (
          <Text color={x.isOk ? undefined : 'error'} wrap="truncate-end">
            {`${new Date(x.at).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })}  ${ICON[x.kind as keyof typeof ICON] ?? '•'} ${x.summary}`}
          </Text>
        ))}
      </Box>
    )
  }

  function vaultView(Text: any, Box: any, s: Snapshot | null) {
    if (!s) return <Text dimColor>Noch keine Daten. „Aktualisieren“ wählen.</Text>
    if (!s.configured) {
      return s.vault_detected
        ? <Text>Obsidian-Vault erkannt, aber noch nicht eingerichtet. Schreib Claude: /plug-n-rag:setup</Text>
        : <Text dimColor>Hier ist keine Vault oder Sammlung eingerichtet.</Text>
    }
    const rows: any[] = [
      <Text bold>{`${s.mode === 'collection' ? 'Sammlung' : 'Vault'} „${s.name}“`}</Text>,
      <Text>{`${fmt(s.indexed ?? 0)} von ${fmt(s.files ?? 0)} Dateien semantisch durchsuchbar`}</Text>,
    ]
    if (s.pending) rows.push(<Text>{`${fmt(s.pending)} warten noch (Stichwortsuche deckt sie ab)`}</Text>)
    if (s.indexing?.running) rows.push(<Text>Indexierung läuft im Hintergrund</Text>)
    if (s.awaiting?.length) rows.push(<Text>{`${s.awaiting.length} Scans warten auf Aufnahme: ${s.awaiting.slice(0, 3).join(', ')}${s.awaiting.length > 3 ? ' …' : ''}`}</Text>)
    if (s.errors) rows.push(<Text color="error">{`${s.errors} Dateien konnten nicht gelesen werden (Claude: plug-n-rag status)`}</Text>)
    if (s.embed_error) rows.push(<Text color="warning">{`Suche nach Bedeutung gerade nicht möglich: ${s.embed_error}`}</Text>)
    if (s.model_mismatch) rows.push(<Text color="warning">Index passt nicht zum Modell: nur Stichwortsuche</Text>)
    rows.push(<Text dimColor>{`Modell: ${s.model ?? '?'}`}</Text>)
    rows.push(<Text dimColor>{s.location === 'inside' ? 'Index im Ordner (.plug-n-rag/)' : 'Index zentral auf diesem Rechner'}</Text>)
    if (s.map?.length) {
      rows.push(<Text bold>Bereiche</Text>)
      for (const f of s.map) {
        rows.push(<Text wrap="truncate-end">{`${f.folder}/ · ${f.count}${f.desc ? ` · ${f.desc}` : ''}${f.topics.length ? ` · ${f.topics.join('; ')}` : ''}`}</Text>)
      }
    }
    if (s.version) rows.push(<Text dimColor>{`plug-n-rag ${s.version}`}</Text>)
    return <Box flexDirection="column">{rows}</Box>
  }

  function savingsView(Text: any, Box: any, list: Entry[], s: Snapshot | null) {
    const searches = list.filter(x => x.kind === 'suche')
    const reads = list.filter(x => x.kind === 'lesen')
    const got = searches.reduce((n, x) => n + x.tokens, 0) + reads.reduce((n, x) => n + x.tokens, 0)
    const full = searches.reduce((n, x) => n + x.fullTokens, 0)
    const rows: any[] = [<Text bold>Diese Sitzung</Text>]
    rows.push(<Text>{`${searches.length} Suchen, ${reads.length} gezielt gelesene Abschnitte`}</Text>)
    if (full) {
      const pct = Math.max(0, Math.round(100 * (1 - got / full)))
      rows.push(<Text>{`ca. ${fmt(got)} Tokens gelesen statt ${fmt(full)} für alle Trefferdateien ganz (−${pct} %)`}</Text>)
    }
    if (s?.savings?.searches) {
      const t = s.savings
      const pct = t.full ? Math.max(0, Math.round(100 * (1 - t.delivered / t.full))) : 0
      rows.push(<Text bold>Insgesamt</Text>)
      rows.push(<Text>{`${fmt(t.searches)} Suchen: ${fmt(t.delivered)} statt ${fmt(t.full)} Tokens (−${pct} %)`}</Text>)
    }
    if (s?.tuning?.length) {
      rows.push(<Text bold>Wie viel eine Suche liefert</Text>)
      for (const l of s.tuning) rows.push(<Text dimColor>{l}</Text>)
    }
    rows.push(<Text dimColor>Alle Zahlen sind Schätzungen (etwa 4 Zeichen pro Token).</Text>)
    return <Box flexDirection="column">{rows}</Box>
  }


}
