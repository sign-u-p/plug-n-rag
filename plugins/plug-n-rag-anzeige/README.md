# plug-n-rag Display

> **English:** an optional display for [plug-n-rag](../../README.md). It shows a calm, expandable
> line in the chat for each step plug-n-rag takes (e.g. "🔍 Searched: 3 notes · best very
> relevant"), a narrow band above the prompt only while indexing runs or something waits for you,
> and on request (`/pnr`) a side pane with history, vault state and estimated savings. Claude sees
> none of it, so it costs no tokens. It reads plug-n-rag's output in English and German and speaks
> the vault's language. Install: `/plugin install plug-n-rag-anzeige@plug-n-rag`.

**Sieh im Chat, was plug-n-rag gerade für dich tut.**

[plug-n-rag](../../README.de.md) arbeitet still im Hintergrund: Es durchsucht deine Notizen, Claude
liest die passenden Abschnitte, und alles bleibt aktuell. Dieser optionale Zusatz macht das
sichtbar, ohne zu stören. So siehst du, welche Notizen gefunden wurden, was Claude davon gelesen
hat und wie viel das gezielte Lesen ungefähr gespart hat.

Die Anzeige spricht die Sprache deiner Vault (Deutsch oder Englisch).

Claude sieht nichts von der Anzeige. Sie verbraucht also nichts von deinem Kontingent.

## Was du siehst

**Eine ruhige Zeile pro Schritt.** Wo sonst ein technischer Befehl stünde, steht zum Beispiel:

```
🔍 plug-n-rag   Gesucht: 3 Notizen · beste sehr passend · 2 weitere   Details
📖 plug-n-rag   Gelesen: projekte/Website-Relaunch.md › Entscheidungen, Z. 40–47
```

Ein Klick auf **Details** zeigt, was gefunden wurde: welche Notizen, welche Abschnitte mit Zeilen,
wie gut sie passen (als Wort und als ●●● / ●●○ / ●○○) und was unterhalb der Schwelle lag. Mit
Strg+O siehst du wie gewohnt den ursprünglichen Befehl.

**Ein Wort am Arbeits-Hinweis**, solange plug-n-rag läuft, zum Beispiel „Durchsucht deine Vault“.

**Ein schmales Band über dem Eingabefeld, nur wenn es etwas zu sagen gibt:**
- wenn im Hintergrund Notizen durchsuchbar gemacht werden (mit Fortschrittsbalken),
- wenn etwas auf dich wartet, etwa eingescannte PDFs.

Das Band lässt sich ausblenden. Der Knopf „Vorschlag ins Eingabefeld“ schreibt nur einen Vorschlag
hinein; ob du ihn abschickst, entscheidest du.

**Eine Seitenleiste, wenn du sie willst.** Über „Seitenleiste öffnen“ oder den Befehl `/pnr`
öffnest du drei Ansichten:
- **Verlauf:** alles, was plug-n-rag in dieser Sitzung getan hat,
- **Vault:** wie viele Notizen durchsuchbar sind, was noch wartet, Bereiche und Schwerpunkte,
- **Ersparnis:** wie viel Claude gelesen hat im Vergleich zum vollständigen Lesen (geschätzt).

Mit der Tastatur: 1, 2, 3 wechseln die Ansicht, R aktualisiert.

## Installieren

Voraussetzung ist plug-n-rag; der Zusatz bringt es automatisch mit, falls es fehlt.

- **Über die Plugin-Seite:** Einstellungen → Plugins, Marketplace `sign-u-p/plug-n-rag` (falls noch
  nicht hinzugefügt), dann bei **plug-n-rag Display** auf „Hinzufügen“.
- **In Claude Code:**

  ```
  /plugin install plug-n-rag-anzeige@plug-n-rag
  ```

Danach eine neue Sitzung starten oder `/reload-plugins` eingeben.

## Wo es funktioniert

| Wo du arbeitest | Was du siehst |
| --- | --- |
| Desktop-App, Code-Tab (lokale Sitzung) | alles |
| Terminal, VS Code | alles (in VS Code ohne Band) |
| Handy-App | eine ruhige Zeile unter dem jeweiligen Schritt |
| Browser (claude.ai/code, Cloud-Sitzung) | nichts; dort schreibt Claude stattdessen eine kurze Quellenzeile unter Antworten aus deiner Vault |

In Projekten ohne Vault oder eingerichteten Ordner tut der Zusatz nichts.

Du brauchst Claude Code ab Version 2.1.287 (Desktop-App ab 2.1.286). Organisationen können solche
Zusätze zentral abschalten; plug-n-rag funktioniert dann weiter, nur ohne Anzeige.

<details>
<summary>Wie die Anzeige funktioniert und was sie darf</summary>

Technisch ist die Anzeige ein **Mod**: ein kleines Programm, das sich in die Oberfläche von Claude
Code einklinkt. Mods dürfen viel; deshalb ist dieser bewusst eng gehalten:

- Er **liest und zeichnet nur.** Er verändert keine Befehle von Claude und schickt nie selbst
  etwas ab.
- **Woher die Zeilen kommen:** Wenn Claude einen plug-n-rag-Befehl ausführt, liest der Mod dessen
  Ausgabe (die Trefferliste, die Claude ohnehin bekommt) und fasst sie in eine Zeile.
- **Woher Band und Seitenleiste ihre Zahlen haben:** Der Mod fragt plug-n-rag auf deinem Rechner
  (`plug-n-rag anzeige-daten`) nach dem Stand: Anzahl der Notizen, was wartet, Ersparnis. Darin
  stehen keine Notizinhalte und keine Suchanfragen. Gefragt wird nur in der Nähe einer Vault, nach
  einem plug-n-rag-Schritt und wenn du die Seitenleiste öffnest.
- **Kein Netz:** Der Mod selbst stellt keine Verbindung ins Internet her.

Nachprüfen lässt sich das: `claude plugin validate` listet für jeden Mod auf, welche Fähigkeiten
er nutzt.

</details>

Abschalten: in `/plugin` (oder auf der Plugin-Seite) deaktivieren oder deinstallieren.
