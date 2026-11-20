import { expect, test } from 'claude-code/testing'

import { parseCommand, parseSearch, summarize } from '../hooks/parse'

// Real output of `plug-n-rag suche` (0.6.0).
const SEARCH = `3 Notizen zu „Wie unterstütze ich ein Kind, das morgens beim Anziehen eskaliert?“

1. gespraeche/2026-10-supervision.md (118 Tokens)
   › Fall K., Z. 7–11 (sehr passend)
   „…iner Reizverarbeitungsstörung: morgens beim Anziehen eskaliert es fast täglich…“

2. themen/Handlungsplanung.md (1.018 Tokens)
   › Intervention, Z. 24–34 (passend)
   › Praxie, Z. 6–12 (am Rande)

3. wissen/Sensorische Integration.md (330 Tokens)
   › Alltagsstrategien, Z. 24–32 (passend)

[--weiter: 2 weitere Notizen]
Lesen: plug-n-rag lesen "gespraeche/2026-10-supervision.md#Fall K." (nur passende Abschnitte, nicht ganze Dateien)`

const NOTHING = `Nichts Passendes gefunden zu „Rezept für Apfelkuchen“.
Bitte nicht aus Allgemeinwissen antworten, als stünde es in den Notizen.`

const CMD = 'plug-n-rag suche "Wie unterstütze ich ein Kind?" --zweck recherche'

test('recognises plug-n-rag in many spellings, but not its hooks', async () => {
  expect(parseCommand(CMD)?.kind).toBe('suche')
  expect(parseCommand('/root/.claude/plugins/cache/plug-n-rag/plug-n-rag/0.6.0/scripts/plug-n-rag lesen "a.md#B"')?.kind).toBe('lesen')
  expect(parseCommand('cd x && plug-n-rag --ordner "/a b" sync --fortschritt')?.kind).toBe('sync')
  expect(parseCommand('plug-n-rag search foo')?.kind).toBe('suche')
  expect(parseCommand('plug-n-rag session-start')).toBeNull()
  expect(parseCommand('plug-n-rag anzeige-daten')).toBeNull()
  expect(parseCommand('git status')).toBeNull()
  expect(parseCommand('ls plug-n-rag-anzeige')).toBeNull()
})

test('reads a search result and says it in one calm line', async () => {
  const s = parseSearch(SEARCH)
  expect(s.query).toBe('Wie unterstütze ich ein Kind, das morgens beim Anziehen eskaliert?')
  expect(s.hits.map(h => h.path)).toEqual([
    'gespraeche/2026-10-supervision.md', 'themen/Handlungsplanung.md', 'wissen/Sensorische Integration.md'])
  expect(s.hits[1]?.tokens).toBe(1018)
  expect(s.hits[1]?.sections.map(x => x.relevance)).toEqual(['passend', 'am Rande'])
  expect(s.more).toBe(2)
  const call = parseCommand(CMD)!
  expect(summarize(call, SEARCH, false, false)).toBe('Gesucht: 3 Notizen · beste sehr passend · 2 weitere')
  expect(summarize(call, NOTHING, false, false)).toBe('Gesucht: nichts Passendes zu „Rezept für Apfelkuchen“')
  expect(summarize(call, undefined, true, false)).toBe('durchsucht deine Vault …')
})

const row = (props: Record<string, unknown>) => ({
  plugin: 'plug-n-rag-anzeige',
  component: 'ToolUse',
  requestId: 't1',
  props: {
    tool_use_id: 't1', tool: 'Bash', input: { command: CMD }, isRunning: false, isErrored: false,
    isInterrupted: false, isExpanded: false, output: { stdout: SEARCH, stderr: '' }, ...props,
  },
}) as const

test('a plug-n-rag call becomes one compact row that opens on demand', async ($, on) => {
  on('ui.render', ($, e) => {
    const { Text } = $.ui.resolve(e)
    return <Text>Bash(engine row)</Text>
  })
  for (const surface of ['desktop', 'terminal'] as const) {
    const ui = await $.ui.mount({ ...row({}), surface } as any)
    expect((await ui.find({ type: 'Text', text: /Gesucht: 3 Notizen/ }))?.text).toBe('Gesucht: 3 Notizen · beste sehr passend · 2 weitere')
    expect(await ui.find({ type: 'Text', text: /engine row/ })).toBeUndefined()
    expect(await ui.find({ type: 'Text', text: /Handlungsplanung/ })).toBeUndefined()
    await ui.press({ key: 't1'.replace(/^/, 'toggle-') })
    expect((await ui.find({ type: 'Text', text: /2\. themen\/Handlungsplanung\.md/ }))?.text)
      .toBe('2. themen/Handlungsplanung.md  (1.018 Tokens)')
    expect((await ui.find({ type: 'Text', text: /am Rande · Praxie/ }))?.text).toContain('●○○ am Rande · Praxie, Z. 6–12')
    expect(await ui.find({ type: 'Text', text: /2 weitere unter dem Schnitt/ })).toBeDefined()
    await ui.press({ key: 'toggle-t1' })
    await ui.unmount()
  }
})

test('ctrl+o (expanded view) and other commands keep the engine row', async ($, on) => {
  on('ui.render', ($, e) => {
    const { Text } = $.ui.resolve(e)
    return <Text>Bash(engine row)</Text>
  })
  let ui = await $.ui.mount({ ...row({ isExpanded: true }), surface: 'desktop' } as any)
  expect(await ui.find({ type: 'Text', text: /engine row/ })).toBeDefined()
  await ui.unmount()
  ui = await $.ui.mount({ ...row({ input: { command: 'git status' } }), surface: 'desktop' } as any)
  expect(await ui.find({ type: 'Text', text: /engine row/ })).toBeDefined()
  await ui.unmount()
})

test('on mobile the native row stays, with one quiet line under it', async ($, on) => {
  on('ui.render', ($, e) => {
    const { Text } = $.ui.resolve(e)
    return <Text>Bash(engine row)</Text>
  })
  const ui = await $.ui.mount({ ...row({}), surface: 'mobile' } as any)
  expect(await ui.find({ type: 'Text', text: /engine row/ })).toBeDefined()
  expect((await ui.find({ type: 'Text', text: /^plug-n-rag · / }))?.text).toBe('plug-n-rag · Gesucht: 3 Notizen · beste sehr passend · 2 weitere')
  await ui.unmount()
})

const SNAPSHOT = {
  version: '0.7.0', configured: true, vault_detected: false, name: 'Fachliteratur', mode: 'collection',
  location: 'inside', files: 12, indexed: 10, pending: 0, awaiting: ['scan.pdf', 'alt.pdf'], errors: 0,
  embed_error: null, model: 'lokal', model_mismatch: false, indexing: { running: false }, needs_update: false,
  savings: { searches: 4, delivered: 900, full: 6000 }, tuning: ['Frage: bis zu 3 Notizen (Startwert)'],
  map: [{ folder: 'buecher', count: 10, topics: ['gruppe'], desc: 'Fachbücher' }],
}

test('band only when something waits; its button only fills the prompt box', async ($, on) => {
  const filled: string[] = []
  on('fs.exists', () => ({ value: false }))
  on('command.register', () => ({ value: { command: 'pnr' } }))
  on('process.run', () => ({ value: { exitCode: 0, stdout: JSON.stringify(SNAPSHOT), stderr: '' } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('prompt.fill', (_, e) => {
    filled.push(e.text)
    return { isFilled: true, text: e.text, cursor: e.text.length }
  })
  await $.session.start({ cwd: '/vault', surface: 'desktop', isInteractive: true })
  const band = {
    plugin: 'plug-n-rag-anzeige', component: 'AbovePrompt', surface: 'desktop',
    props: { hasSurvey: false, isCollapsed: false, isWorking: false, maxRows: 4, bodyColumns: 80,
      scroll: { offset: 0, bodyRows: 4 }, view: {} },
  } as const
  const ui = await $.ui.mount(band as any)
  expect((await ui.find({ type: 'Text', text: /warten auf Aufnahme/ }))?.text).toBe('2 eingescannte Dateien warten auf Aufnahme')
  await ui.press({ key: 'band-do' })
  expect(filled).toEqual(['Bitte nimm die eingescannten PDFs mit /plug-n-rag:aufnehmen auf.'])
  await ui.press({ key: 'band-hide' })
  expect(await ui.find({ type: 'Text', text: /warten auf Aufnahme/ })).toBeUndefined()
  await ui.unmount()
})

test('the side pane lists this session and the savings', async ($, on) => {
  on('fs.exists', () => ({ value: false }))
  on('command.register', () => ({ value: { command: 'pnr' } }))
  on('process.run', () => ({ value: { exitCode: 0, stdout: JSON.stringify(SNAPSHOT), stderr: '' } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('tool.call', () => ({ result: { stdout: SEARCH, stderr: '' } }))
  on('clock.now', () => ({ value: Date.parse('2026-11-20T10:15:00Z') }))
  await $.session.start({ cwd: '/vault', surface: 'desktop', isInteractive: true })
  await $.tool.call({ tool: 'Bash', command: CMD })
  const pane = {
    plugin: 'plug-n-rag-anzeige', component: 'Pane', requestId: 'plug-n-rag', surface: 'desktop',
    props: { title: 'plug-n-rag', isFocused: false, bodyColumns: 60, placement: 'dock',
      scroll: { offset: 0, bodyRows: 30 }, view: {} },
  } as const
  const ui = await $.ui.mount(pane as any)
  expect((await ui.find({ type: 'Text', text: /Gesucht: 3 Notizen/ }))?.text).toContain('🔍 Gesucht: 3 Notizen')
  await ui.press({ key: 'tab-vault' })
  expect((await ui.find({ type: 'Text', text: /semantisch durchsuchbar/ }))?.text).toBe('10 von 12 Dateien semantisch durchsuchbar')
  expect(await ui.find({ type: 'Text', text: /2 Scans warten/ })).toBeDefined()
  await ui.press({ key: 'tab-ersparnis' })
  expect((await ui.find({ type: 'Text', text: /Tokens gelesen statt/ }))?.text).toContain('statt 1.466 für alle Trefferdateien ganz')
  expect((await ui.find({ type: 'Text', text: /^4 Suchen/ }))?.text).toBe('4 Suchen: 900 statt 6.000 Tokens (−85 %)')
  await ui.unmount()
})
