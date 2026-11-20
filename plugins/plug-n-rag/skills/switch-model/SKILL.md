---
name: switch-model
disable-model-invocation: true
description: Switches plug-n-rag's embedding provider or model, with a cost estimate and a full reindex (English name of /plug-n-rag:modell-wechseln). Only on the user's explicit request.
allowed-tools: Bash(plug-n-rag konfig*) Bash(plug-n-rag inventur*) Bash(plug-n-rag status*) Bash(plug-n-rag config*) Bash(plug-n-rag inventory*) Bash(plug-n-rag guide*)
---

This is the English name of `/plug-n-rag:modell-wechseln`. Load its instructions and follow them exactly:

```
plug-n-rag guide switch-model $ARGUMENTS
```

(If `plug-n-rag` is not on the PATH: `"${CLAUDE_PLUGIN_ROOT}/scripts/plug-n-rag" guide switch-model $ARGUMENTS`.)
Answer in the language the user writes in. The instructions are written in German; every command in
them also has an English alias (e.g. `aufnehmen` = `ingest`, `--transkription erlaubt` =
`--transcription allowed`, `nach-main` = `to-main`, `konfig --setzen` = `config --set`).
