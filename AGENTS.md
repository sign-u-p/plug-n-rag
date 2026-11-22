# plug-n-rag: instructions for AI agents

> **Deutsch:** Diese Datei richtet sich an KI-Agenten. Sagt jemand z. B. „Richte dieses Repo für
> plug-n-rag ein: github.com/sign-u-p/plug-n-rag“, steht hier alles, was der Agent dafür tun muss.
> Menschen lesen besser die [README](README.de.md).

You are probably here because a user said something like:

> "Set up this repo for plug-n-rag: github.com/sign-u-p/plug-n-rag"
> „Richte dieses Repo für plug-n-rag ein: sign-u-p/plug-n-rag“

That is the whole request. This file tells you everything else. Follow it from top to bottom.

*How to read this file if you only have the repo name:* fetch
`https://raw.githubusercontent.com/sign-u-p/plug-n-rag/main/AGENTS.md`, or run step 1 below; a
copy then lies at `~/.claude/plugins/marketplaces/plug-n-rag/AGENTS.md`.

**Which case are you in?**

- **The working directory is the user's own repo or folder** (an Obsidian vault, a folder of notes
  or documents) → this file is for you. Go on with step 1.
- **The working directory is the plug-n-rag repo itself** (it contains `plugins/plug-n-rag/` and
  this `AGENTS.md`) → you are developing plug-n-rag. Ignore the steps below and read
  [CONTRIBUTING.md](CONTRIBUTING.md), [SPEC.md](SPEC.md) and [DECISIONS.md](DECISIONS.md).

## What plug-n-rag is (30 seconds)

A Claude Code plugin. It builds a local search index (keywords + meaning) for the user's notes, so
that Claude reads only the matching sections and cites their source. It never changes a note.
The user is usually **not a developer**: no jargon, short paragraphs, one question per message,
in the user's language (German: gender-fair with a colon, e.g. "Nutzer:in").

## Step 1: Install the plugin (you do this)

Requires the `claude` CLI (Claude Code). If it is missing, tell the user that plug-n-rag is a
Claude Code plugin and stop.

First check whether it is already there:

```bash
ls -d ~/.claude/plugins/cache/plug-n-rag/plug-n-rag/*/ 2>/dev/null
```

If nothing is listed, install it (both commands, in this order):

```bash
claude plugin marketplace add sign-u-p/plug-n-rag
claude plugin install plug-n-rag@plug-n-rag
```

If `marketplace add` says it already exists, run `claude plugin marketplace update plug-n-rag`
instead. If GitHub is not reachable, tell the user the network of the session must allow
`github.com`.

## Step 2: Find the command

A plugin installed during a session does **not** show its `/plug-n-rag:…` commands until the user
types `/reload-plugins`, and `plug-n-rag` is not on the PATH yet. Don't wait for that. Use the full
path. Shell variables don't survive between tool calls, so put this in front of **every** call:

```bash
PNR="$(ls -d ~/.claude/plugins/cache/plug-n-rag/plug-n-rag/*/ | sort -V | tail -1)scripts/plug-n-rag"
"$PNR" --version
```

Always run it with the **Bash** tool (never PowerShell). The first call may take a minute: `uv`
fetches Python and the dependencies. If `uv` is missing, offer to install it
(`curl -LsSf https://astral.sh/uv/install.sh | sh`) and ask first.

## Step 3: Read the setup guide and follow it

```bash
"$PNR" guide setup        # German alias: "$PNR" anleitung setup
```

This prints the full setup guide (the same text as `/plug-n-rag:setup`). **It is the authoritative
source. Follow it step by step.** Where it says `plug-n-rag …`, use `"$PNR" …`. It contains the
invariants (never change a note, no destructive git, API keys never in files or chat), the order of
the questions, the privacy note, the first indexing and the wrap-up.

Other guides, when the setup guide refers to them: `"$PNR" guide` lists them all, e.g.
`guide cloud`, `guide to-main`.

## Step 4: In a cloud session, also do this

You are in a cloud session if `CLAUDE_CODE_REMOTE=true` or `"$PNR" cloud --check` says so. The
setup guide has a section "Cloud-Weg" for this. In short:

1. **Skip** installing uv, Git and GitHub steps: the repo is already on GitHub. If the repo is
   **public**, say so clearly and offer help to make it private.
2. **Network for the search model** (local model only): `"$PNR" cloud --check`. If Hugging Face is
   blocked and you have tools to change the cloud environment, propose the exact hosts from
   `"$PNR" cloud --hosts` (the user confirms). Otherwise explain where to enter them. Until then
   setup continues with keyword search; `"$PNR" sync` adds the semantic index later.
3. **Self-setup, so future sessions have the plugin by themselves:** explain in one sentence what it
   does, ask, then run `"$PNR" cloud --bootstrap`. It adds `.plug-n-rag/cloud-start.sh` and a start
   hook in `.claude/settings.json`; locally it does nothing.
4. **Commit and bring it to `main`.** Cloud sessions start from the main branch, so the index files
   and the self-setup must get there. Follow `"$PNR" guide to-main`; ask before you push, never
   `--force`.

## Step 5: Finish

Tell the user, in plain words:

- what was set up and where the index lives,
- that they can now simply ask questions about their notes,
- that the `/plug-n-rag:…` commands appear after typing **`/reload-plugins`** once (or in the next
  session),
- in the cloud: that future sessions with this repo install plug-n-rag by themselves.

## If something goes wrong

| Symptom | What to do |
| --- | --- |
| `claude plugin …` fails, GitHub unreachable | The session's network must allow `github.com`. |
| `$PNR` is empty | Install failed: repeat step 1 and read its output. |
| "search model could not be loaded" | Hugging Face hosts missing from the network allowlist (`"$PNR" cloud --hosts`). Keyword search works meanwhile. |
| User types `/plug-n-rag:setup` and it is unknown | Not an error: read `"$PNR" guide setup` and follow it. Ask for `/reload-plugins` once. |
| Anything else | `"$PNR" status` and `"$PNR" cloud --check` tell you what is missing. |

More background for humans: [README.md](README.md) (English), [README.de.md](README.de.md)
(Deutsch).
