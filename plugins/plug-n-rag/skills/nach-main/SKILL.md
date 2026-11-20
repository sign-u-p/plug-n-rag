---
name: nach-main
description: Übernimmt alle Änderungen der Sitzung (Notizen und Suchindex von plug-n-rag) sicher in den Hauptstand (main) des Vault-Repos auf GitHub, auch aus einer Cloud-Sitzung heraus. Verwenden, wenn die Nutzer:in sagt „leg das nach main“, „übernimm das“, „veröffentlichen“, „damit ich es in Obsidian sehe“ oder Ähnliches. English: publishes all changes of the session (notes and search index) to main, e.g. when the user says “put it on main”, “publish this” or “so I can see it in Obsidian” (/plug-n-rag:to-main).
argument-hint: "[commit-nachricht]"
allowed-tools: Bash(plug-n-rag nach-main*) Bash(plug-n-rag status*) Bash(git status*) Bash(git diff*) Bash(plug-n-rag to-main*)
---

> **Sprache / language:** Antworte in der Sprache, in der die Nutzer:in schreibt; auf Deutsch
> gendergerecht mit Doppelpunkt. If the user writes in English, answer in English. Alle Befehle
> gibt es auch englisch (`search`, `read`, `outline`, `--purpose question`, …); die festen Texte
> von plug-n-rag folgen der Sprache der Vault (`language` in der Konfiguration).

# Änderungen nach main übernehmen

Nur auf ausdrücklichen Wunsch der Nutzer:in in diesem Chat. Die Aufforderung im Chat ist die
Erlaubnis, für diesen einen Vorgang nach `main` zu pushen, auch wenn die Sitzung sonst auf einem
eigenen Branch (`claude/…`) arbeitet.

1. Kurz zeigen, was übernommen wird: `git status --short` (bei Bedarf `git diff --stat`). In
   einfachen Worten zusammenfassen: neue, geänderte, gelöschte Notizen. Der Index
   (`.plug-n-rag/index/`) gehört immer dazu.
2. Ausführen: `plug-n-rag nach-main -m "<kurze Beschreibung in der Sprache der Nutzer:in>"`
   (`$ARGUMENTS` als Nachricht verwenden, falls angegeben). Der Befehl:
   - gleicht den Index ab und committet alles (nie den lokalen Cache),
   - bricht ab, wenn etwas wie ein API-Key aussieht,
   - holt den neuesten Stand von `main` und führt ihn zusammen (kein Rebase, kein `--force`),
   - berechnet Index-Dateien mit Konflikt neu,
   - bricht bei Konflikten **in Notizen** ab, ohne etwas zu verändern,
   - pusht nach `main` und zusätzlich auf den Sitzungs-Branch.
3. Ergebnis erklären:
   - „Auf main übernommen“: In Obsidian erscheint es nach dem nächsten Abholen (Obsidian Git:
     beim Start oder im eingestellten Intervall).
   - „Nicht übernommen … unterschiedlich geändert“: die betroffenen Notizen nennen, beide Fassungen
     zeigen (`git show origin/main:<pfad>` und die Datei hier) und fragen, welche gelten soll oder ob
     zusammengeführt werden soll. Nichts automatisch entscheiden. Danach erneut `nach-main`.
   - „Push … abgelehnt“ / geschützter Branch: anbieten, stattdessen einen Pull Request anzulegen.
   - „API-Key“: Datei nennen, den Key nicht wiederholen, gemeinsam entfernen.
4. Nie `git push --force`, nie `git reset --hard`, nie Notiz-Konflikte selbst auflösen.
