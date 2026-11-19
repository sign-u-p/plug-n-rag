---
name: suche
description: Durchsucht die Obsidian-Vault oder eingerichtete Sammlung der Nutzer:in mit plug-n-rag (semantisch und per Stichwort) und liest nur die passenden Abschnitte. Immer verwenden, wenn eine Frage, Recherche oder ein Text sich auf Inhalte der eigenen Notizen, Dokumente oder der Vault stützen soll, statt grep oder ganze Dateien zu lesen.
allowed-tools: Bash(plug-n-rag *)
---

# Suchen und Lesen in der Vault

Die Vault ist mit plug-n-rag indexiert. Der Befehl `plug-n-rag` liegt auf dem PATH
(Ersatz, falls nicht gefunden: `"${CLAUDE_PLUGIN_ROOT}/bin/plug-n-rag"`). Er arbeitet im
aktuellen Ordner; für einen anderen Ordner `--ordner <pfad>` vor den Befehl setzen.

## Ablauf: Karte → Suche → Gliederung → Abschnitt

1. **Orientieren** (nur wenn die Kurz-Karte vom Sitzungsstart nicht reicht): `plug-n-rag karte`
2. **Suchen**, immer mit Zweck:
   `plug-n-rag suche "<frage in eigenen Worten>" --zweck frage|recherche|erstellen`
   - `frage`: konkrete Frage, wenige präzise Treffer
   - `recherche`: Überblick über ein Thema, mehr Notizen
   - `erstellen`: Grundlage für einen neuen Text, wenige Notizen, dafür vollständiger lesen
   - Filter nur, wenn die Frage einen Bereich nahelegt: `--in <ordner>`, `--tag <tag>`, `--seit JJJJ-MM-TT`
   - Mehr Treffer derselben Suche: `plug-n-rag suche --weiter` (rechnet nicht neu)
3. **Gliederung** bei Notizen über etwa 1.000 Tokens: `plug-n-rag gliederung <pfad>`
4. **Lesen**, nur was gebraucht wird:
   - Abschnitt: `plug-n-rag lesen "<pfad>#<Überschrift>"`
   - Zeilen oder Seiten: `plug-n-rag lesen "<pfad>:45-80"` (bei Markdown geht auch das Read-Werkzeug mit offset/limit)
   - Ganze Notiz nur bei `--zweck erstellen` oder wenn der Zusammenhang wirklich nötig ist
5. **Verwandtes**: `plug-n-rag verwandt <pfad>` (Links und Backlinks zuerst, dann inhaltlich ähnlich)

## Regeln

- Für Inhalte der Vault zuerst `plug-n-rag suche`, nicht grep. grep nur für exakte Zeichenketten
  (Dateinamen, Datumsangaben, wörtliche Zitate).
- Jede Aussage aus der Vault mit Pfad und Zeilen (bzw. Seiten) belegen, z. B.
  „(wissen/si-grundlagen.md, Z. 45–80)“.
- Meldet die Suche „Nichts Passendes gefunden“, das offen sagen. Nicht aus Allgemeinwissen
  antworten, als käme es aus den Notizen. Allgemeinwissen nur klar gekennzeichnet ergänzen.
- Relevanz steht in Worten (sehr passend, passend, am Rande). „Am Rande“ nur lesen, wenn nötig.
- Neue PDFs nicht direkt lesen, sondern `/plug-n-rag:aufnehmen` anbieten.
- Rückmeldungen zur Gründlichkeit speichern:
  „zu oberflächlich“ → `plug-n-rag lernen --tiefer --zweck <zweck>`,
  „zu ausführlich“ → `plug-n-rag lernen --knapper --zweck <zweck>`. Kurz bestätigen.
- Meldet die Suche einen Modellkonflikt oder veralteten Index: Nutzer:in informieren und
  `/plug-n-rag:reindex` anbieten.
- Notizen nie ohne ausdrückliche Zustimmung ändern. Wenn du mit Zustimmung Notizen änderst und
  committest, `.plug-n-rag/index/` im selben Commit mitnehmen (vorher `plug-n-rag sync`).
- Ausgaben an Nutzer:innen auf Deutsch, gendergerecht mit Doppelpunkt.
