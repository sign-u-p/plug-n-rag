/** One plug-n-rag call Claude made in this session, as the side pane lists it. */
export type Entry = {
  id: string
  kind: string
  summary: string
  at: number
  isOk: boolean
  /** estimated tokens Claude received from this call */
  tokens: number
  /** for searches: tokens of the hit notes, had they been read completely */
  fullTokens: number
}

/** What `plug-n-rag anzeige-daten` reports (subset the display reads). */
export type Snapshot = {
  version: string
  configured: boolean
  vault_detected: boolean
  /** language of plug-n-rag's texts for this folder (from 0.9) */
  language?: 'de' | 'en'
  name?: string
  mode?: string
  location?: string
  files?: number
  indexed?: number
  pending?: number
  awaiting?: string[]
  errors?: number
  embed_error?: string | null
  model?: string
  model_mismatch?: boolean
  indexing?: { running: boolean; done?: number; total?: number }
  needs_update?: boolean
  savings?: { searches: number; delivered: number; full: number }
  tuning?: string[]
  map?: { folder: string; count: number; topics: string[]; desc: string }[]
}

export type Tab = 'verlauf' | 'vault' | 'ersparnis'

declare module 'claude-code' {
  interface PluginState {
    'plug-n-rag-anzeige': {
      history: Shaped<Entry[]>
      snap: Shaped<Snapshot | null>
      tab: Tab
      open: string[]
      bandHidden: boolean
      active: string | null
    }
  }
}
