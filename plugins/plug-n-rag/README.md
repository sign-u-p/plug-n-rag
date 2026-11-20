# plug-n-rag

Macht Obsidian-Vaults und auf Wunsch andere Ordner für Claude Code semantisch durchsuchbar, damit
Claude gezielt statt vollständig liest und Tokens spart.

Installation, erste Schritte, Datenschutz, Cloud-Sitzungen und bekannte Grenzen stehen in der
[Anleitung im Repository](https://github.com/sign-u-p/plug-n-rag#readme).

Kurz:

```
/plugin marketplace add sign-u-p/plug-n-rag
/plugin install plug-n-rag@plug-n-rag
```

Danach im Ordner deiner Vault `/plug-n-rag:setup` eingeben.

Dieser Ordner enthält das Plugin: `scripts/` (Starter), `skills/`, `hooks/`, `agents/`, den
Python-Kern unter `src/plug_n_rag/` und die Tests unter `tests/`. Lizenz: MIT, siehe `LICENSE`
und `THIRD_PARTY_NOTICES.md`.
