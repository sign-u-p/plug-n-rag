---
name: reset-learning
disable-model-invocation: true
description: Resets or shows the learned values of plug-n-rag's token steering (English name of /plug-n-rag:lernen-zuruecksetzen).
allowed-tools: Bash(plug-n-rag lernen*) Bash(plug-n-rag learn*) Bash(plug-n-rag guide*)
---

This is the English name of `/plug-n-rag:lernen-zuruecksetzen`. Load its instructions and follow them exactly:

```
plug-n-rag guide reset-learning $ARGUMENTS
```

(If `plug-n-rag` is not on the PATH: `"${CLAUDE_PLUGIN_ROOT}/scripts/plug-n-rag" guide reset-learning $ARGUMENTS`.)
Answer in the language the user writes in. The instructions are written in German; every command in
them also has an English alias (e.g. `aufnehmen` = `ingest`, `--transkription erlaubt` =
`--transcription allowed`, `nach-main` = `to-main`, `konfig --setzen` = `config --set`).
