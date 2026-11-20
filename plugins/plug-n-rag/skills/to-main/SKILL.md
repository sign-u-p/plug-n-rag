---
name: to-main
disable-model-invocation: true
description: Publishes all changes of the session (notes and plug-n-rag's search index) safely to main (English name of /plug-n-rag:nach-main).
argument-hint: "[commit message]"
allowed-tools: Bash(plug-n-rag nach-main*) Bash(plug-n-rag status*) Bash(git status*) Bash(git diff*) Bash(plug-n-rag to-main*) Bash(plug-n-rag guide*)
---

This is the English name of `/plug-n-rag:nach-main`. Load its instructions and follow them exactly:

```
plug-n-rag guide to-main $ARGUMENTS
```

(If `plug-n-rag` is not on the PATH: `"${CLAUDE_PLUGIN_ROOT}/scripts/plug-n-rag" guide to-main $ARGUMENTS`.)
Answer in the language the user writes in. The instructions are written in German; every command in
them also has an English alias (e.g. `aufnehmen` = `ingest`, `--transkription erlaubt` =
`--transcription allowed`, `nach-main` = `to-main`, `konfig --setzen` = `config --set`).
