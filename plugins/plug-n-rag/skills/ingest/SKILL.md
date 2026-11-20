---
name: ingest
disable-model-invocation: true
description: Turns PDFs, including scans, into searchable text with plug-n-rag (English name of /plug-n-rag:aufnehmen).
argument-hint: "<pdf file> [more]"
allowed-tools: Bash(plug-n-rag aufnehmen*) Bash(plug-n-rag sync*) Bash(plug-n-rag ingest*) Bash(plug-n-rag guide*)
---

> **Werkzeug / tool:** `plug-n-rag` immer mit dem **Bash**-Werkzeug ausführen, nie mit PowerShell
> (unter Windows kennt PowerShell den Befehl nicht). Always run `plug-n-rag` with the Bash tool.

This is the English name of `/plug-n-rag:aufnehmen`. Load its instructions and follow them exactly:

```
plug-n-rag guide ingest $ARGUMENTS
```

(If `plug-n-rag` is not on the PATH: `"${CLAUDE_PLUGIN_ROOT}/scripts/plug-n-rag" guide ingest $ARGUMENTS`.)
Answer in the language the user writes in. The instructions are written in German; every command in
them also has an English alias (e.g. `aufnehmen` = `ingest`, `--transkription erlaubt` =
`--transcription allowed`, `nach-main` = `to-main`, `konfig --setzen` = `config --set`).
