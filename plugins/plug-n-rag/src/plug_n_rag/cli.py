"""Command line entry point: ``plug-n-rag <befehl>``.

Hooks, skill, slash commands and the MCP wrapper all call into this core.
Subcommands and options are German (as in SPEC) with English aliases; help and messages
follow the folder's language (see i18n.py).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from . import __version__
from . import i18n
from .config import Layout, find_layout, init_layout, load_config, save_config
from .i18n import tr
from .util import LockBusy, fmt_int, plural, user_cache_dir

PURPOSES = ["frage", "recherche", "erstellen", "question", "research", "create"]
PURPOSE_FROM_EN = {"question": "frage", "research": "recherche", "create": "erstellen"}
TRANSCRIPTION_FROM_EN = {"ask": "fragen", "local": "lokal", "allowed": "erlaubt"}
LOCATION_FROM_EN = {"folder": "ordner", "central": "zentral"}
PLACE_CHOICES = ["neben_original", "ordner", "intern", "beside", "folder", "internal"]


def not_set_up() -> str:
    return tr("Hier ist noch nichts für plug-n-rag eingerichtet. "
              "Mit /plug-n-rag:setup startet die geführte Einrichtung.",
              "Nothing is set up for plug-n-rag here yet. "
              "/plug-n-rag:setup starts the guided setup.")


def _layout(args, require: bool = True) -> Layout | None:
    start = Path(args.ordner).expanduser() if getattr(args, "ordner", None) else None
    layout = find_layout(start)
    i18n.use_layout(layout if layout is not None and layout.configured else None)
    if require and (layout is None or not layout.configured):
        print(not_set_up())
        sys.exit(2)
    return layout


def _purpose(value: str | None) -> str:
    return PURPOSE_FROM_EN.get(value or "frage", value or "frage")


def _place(value: str | None) -> str | None:
    from .ingest import PLACE_FROM_EN

    return PLACE_FROM_EN.get(value, value) if value else value


def _print(text: str) -> None:
    sys.stdout.write(text.rstrip() + "\n")


# --- commands ---------------------------------------------------------------------------

def cmd_karte(args):
    from .mapview import karte

    _print(karte(_layout(args), short=args.kurz))


def cmd_suche(args):
    from .search import search

    query = " ".join(args.frage) if args.frage else None
    _print(search(_layout(args), query, purpose=_purpose(args.zweck), folder=args.in_, tag=args.tag,
                  since=args.seit, more=args.weiter))


def cmd_gliederung(args):
    from .navigate import outline

    _print(outline(_layout(args), " ".join(args.notiz)))


def cmd_lesen(args):
    from .navigate import read

    _print(read(_layout(args), " ".join(args.ziel)))


def cmd_verwandt(args):
    from .navigate import related

    _print(related(_layout(args), " ".join(args.notiz)))


def cmd_status(args):
    from .status import status

    _print(status(_layout(args), check_remote=not args.schnell))


def _report_text(r) -> str:
    parts = []
    if r.added:
        parts.append(tr(f"{len(r.added)} neu", f"{len(r.added)} new"))
    if r.updated:
        parts.append(tr(f"{len(r.updated)} geändert", f"{len(r.updated)} changed"))
    if r.removed:
        parts.append(tr(f"{len(r.removed)} entfernt", f"{len(r.removed)} removed"))
    if r.private_removed:
        parts.append(tr(f"{len(r.private_removed)} privat (Index gelöscht)",
                        f"{len(r.private_removed)} private (index deleted)"))
    head = tr("Abgleich: ", "Sync: ") + (", ".join(parts) if parts else tr("nichts zu tun", "nothing to do"))
    head += tr(f" · {fmt_int(r.unchanged)} unverändert", f" · {fmt_int(r.unchanged)} unchanged")
    if r.embedded_chunks or r.reused_chunks:
        head += tr(f" · {fmt_int(r.embedded_chunks)} Abschnitte neu eingebettet, {fmt_int(r.reused_chunks)} wiederverwendet",
                   f" · {fmt_int(r.embedded_chunks)} sections newly embedded, {fmt_int(r.reused_chunks)} reused")
    lines = [head]
    note = tr("Hinweis: ", "Note: ")
    if r.pending:
        lines.append(tr(f"Noch ausstehend: {plural(len(r.pending), 'Datei', 'Dateien')}",
                        f"Still pending: {plural(len(r.pending), 'file', 'files')}"))
    if r.embed_error:
        lines.append(note + r.embed_error)
    if r.model_mismatch:
        lines.append(note + tr("Index passt nicht zum Modell, nur Stichwortsuche. /plug-n-rag:reindex bietet die Neuindexierung an.",
                               "The index does not match the model, keyword search only. /plug-n-rag:reindex offers a full reindex."))
    if r.awaiting:
        lines.append(note + _awaiting(len(r.awaiting)))
    for path, msg in list(r.errors.items())[:5]:
        lines.append(tr("Fehler: ", "Error: ") + f"{path}: {msg}")
    return "\n".join(lines)


def _awaiting(n: int) -> str:
    return tr(f"{plural(n, 'eingescannte Datei wartet', 'eingescannte Dateien warten')} auf Aufnahme (/plug-n-rag:aufnehmen)",
              f"{plural(n, 'scanned file is', 'scanned files are')} waiting for ingestion (/plug-n-rag:aufnehmen)")


def cmd_sync(args):
    from .sync import sync

    layout = _layout(args, require=not args.quiet)
    if layout is None or not layout.configured:
        return
    progress = (lambda msg: print("  " + msg, file=sys.stderr)) if args.fortschritt else None
    try:
        r = sync(layout, time_budget=args.budget, progress=progress, lock_wait=0 if args.quiet else 60)
    except LockBusy:
        if not args.quiet:
            _print(tr("Ein anderer Abgleich läuft gerade. Bitte kurz warten.",
                      "Another sync is running right now. Please wait a moment."))
        return
    _write_pending_spawn(layout, r, args)
    if not args.quiet:
        _print(_report_text(r))


def _write_pending_spawn(layout, r, args):
    if r.pending and not r.embed_error and not r.model_mismatch and getattr(args, "budget", None):
        spawn_background_sync(layout)


def cmd_hydrate(args):
    from .db import hydrate

    st = hydrate(_layout(args), rebuild=args.neu)
    _print(tr(f"Suchdatenbank: {st['notes']} Dateien ({st['added']} neu, {st['updated']} aktualisiert, "
              f"{st['removed']} entfernt) in {st['elapsed']:.1f} s",
              f"Search database: {st['notes']} files ({st['added']} new, {st['updated']} updated, "
              f"{st['removed']} removed) in {st['elapsed']:.1f} s"))


def cmd_reindex(args):
    from .sync import pending_count, reindex

    layout = _layout(args)
    if not args.ja:
        todo, total = pending_count(layout)
        emb = layout.config["embedding"]
        _print(tr(f"Neuindexierung von {plural(total, 'Datei', 'Dateien')} mit Modell "
                  f"{emb['model']} ({emb['provider']}). "
                  "Bitte mit Nutzer:in bestätigen und dann `plug-n-rag reindex --ja` ausführen.",
                  f"Full reindex of {plural(total, 'file', 'files')} with model {emb['model']} ({emb['provider']}). "
                  "Please confirm with the user, then run `plug-n-rag reindex --yes`."))
        return
    r = reindex(layout, progress=(lambda m: print("  " + m, file=sys.stderr)) if args.fortschritt else None)
    _print(_report_text(r))


def cmd_init(args):
    root = Path(args.pfad).expanduser().resolve() if args.pfad else Path.cwd()
    lang = i18n._norm(args.sprache) if args.sprache else i18n.language()
    i18n.set_language(lang)
    if not root.is_dir():
        _print(tr(f"Ordner nicht gefunden: {root}", f"Folder not found: {root}"))
        sys.exit(2)
    mode = "collection" if args.modus in ("sammlung", "collection") else "vault"
    from . import gitops

    if args.extern:
        args.ort = "zentral"
    args.ort = LOCATION_FROM_EN.get(args.ort, args.ort)
    if args.ort:
        location = "external" if args.ort == "zentral" else "inside"
    else:  # vaults always inside; collections inside only if they already are a git repo
        location = "inside" if mode == "vault" or gitops.is_repo(root) else "external"
    extra: dict = {"language": lang}
    if args.privat:
        extra["private_folders"] = args.privat
    from .config import COLLECTION_FORMATS, VAULT_DEFAULT_EXCLUDE
    from .scan import detect_template_folders

    excl = list(VAULT_DEFAULT_EXCLUDE) if mode == "vault" else [".git/**", ".plug-n-rag/**", ".obsidian/**", ".trash/**"]
    if mode == "vault":
        excl += [f"{t}/**" for t in detect_template_folders(root)]
    excl += args.ausschliessen or []
    extra["exclude"] = list(dict.fromkeys(excl))
    if mode == "vault" and args.formate:
        extra["formats"] = args.formate
    elif mode == "collection":
        extra["formats"] = args.formate or list(COLLECTION_FORMATS)
    if args.abschriften:
        extra["abschriften"] = {"ort": _place(args.abschriften)}
        if args.abschriften_ordner:
            extra["abschriften"]["ordner"] = args.abschriften_ordner
    from .config import CONFIG_NAME, STATE_DIR_NAME, external_state_dir

    existed = ((root / STATE_DIR_NAME / CONFIG_NAME).exists() or (root / CONFIG_NAME).exists()
               or (location == "external" and (external_state_dir(root) / CONFIG_NAME).exists()))
    layout = init_layout(root, mode=mode, location=location, provider=args.provider, model=args.modell, extra=extra)
    if location == "inside" and layout.mode == "vault":
        _ensure_gitignore(root)
    if existed:
        i18n.use_layout(layout)
    _print((tr("Konfiguration war schon vorhanden, nichts überschrieben: ",
               "A configuration already existed, nothing overwritten: ") if existed
            else tr("Eingerichtet: ", "Set up: ")) + str(layout.config_path))
    _print(f"Index: {layout.index_dir}" + (tr(" (im Ordner)", " (inside the folder)") if layout.location == "inside" else
                                           tr(" (zentral auf diesem Rechner, im Ordner wird nichts angelegt)",
                                              " (central on this computer, nothing is created in the folder)")))
    _print(tr("Ausgeschlossen: ", "Excluded: ") + ", ".join(layout.config.get("exclude", [])))
    _print(tr("Sprache der Ausgaben: Deutsch (ändern: plug-n-rag konfig --setzen language=en)",
              "Language of messages: English (change: plug-n-rag config --set language=de)"))


def _ensure_gitignore(root: Path) -> None:
    """Add Obsidian's per-device files to .gitignore (append only, never rewrite)."""
    gi = root / ".gitignore"
    wanted = [".obsidian/workspace*.json", ".trash/"]
    try:
        current = gi.read_text(encoding="utf-8") if gi.exists() else ""
    except OSError:
        return
    missing = [w for w in wanted if w not in current.splitlines()]
    if missing:
        sep = "" if not current or current.endswith("\n") else "\n"
        gi.write_text(current + sep + "# plug-n-rag\n" + "\n".join(missing) + "\n", encoding="utf-8")


def cmd_inventur(args):
    from .inventory import as_json, inventory, render

    root = Path(args.pfad).expanduser() if args.pfad else Path.cwd()
    if args.sprache:
        i18n.set_language(args.sprache)
    else:
        found = find_layout(root)
        i18n.use_layout(found if found is not None and found.configured else None)
    inv = inventory(root)
    _print(as_json(inv) if args.json else render(inv))


def cmd_config(args):
    layout = _layout(args)
    cfg = load_config(layout.config_path)
    if args.setzen:
        import yaml

        for item in args.setzen:
            key, _, raw = item.partition("=")
            value = yaml.safe_load(raw) if raw else None
            node = cfg
            parts = key.split(".")
            for p in parts[:-1]:
                node = node.setdefault(p, {})
            node[parts[-1]] = value
        if any(k.lower().find("key") >= 0 and "api" in k.lower() for k in (s.partition("=")[0] for s in args.setzen)):
            _print(tr("API-Keys gehören nicht in die Konfiguration. Bitte VOYAGE_API_KEY als Umgebungsvariable setzen.",
                      "API keys do not belong in the configuration. Please set VOYAGE_API_KEY as an environment variable."))
            sys.exit(2)
        save_config(layout.config_path, cfg)
        layout.config = load_config(layout.config_path)
        i18n.use_layout(layout)
        _print(tr("Konfiguration gespeichert.", "Configuration saved."))
    import yaml

    _print(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False))


def cmd_lernen(args):
    from . import tuning

    layout = _layout(args)
    if args.zuruecksetzen:
        tuning.reset(layout, keep_overrides=args.vorgaben_behalten)
        _print(tr("Lern-Datei auf Startwerte gesetzt.", "Learning file reset to starting values."))
    elif args.tiefer or args.knapper:
        purpose = _purpose(args.zweck)
        ov = tuning.set_override(layout, purpose, deeper=bool(args.tiefer))
        _print(tr(f"Vorgabe für „{purpose}“ gespeichert: ", f"Preference for “{tuning.PURPOSE_EN[purpose]}” saved: ")
               + ", ".join(f"{k}={v}" for k, v in ov.items()))
    else:
        tuning.learn(layout)
    _print("\n".join(tuning.describe(layout)))


def cmd_aufnehmen(args):
    from .ingest import complete, ingest

    layout = _layout(args)
    files = [Path(p) for p in args.dateien]
    args.ablage = _place(args.ablage)
    if args.ablage:
        from .ingest import PLACE_EN, PLACES

        valid = PLACES["collection" if layout.mode == "collection" else "vault"]
        if args.ablage not in valid:
            shown = [tr(v, PLACE_EN[v]) for v in valid]
            _print(tr(f"„{args.ablage}“ passt nicht zu diesem Modus. Möglich: {', '.join(shown)}",
                      f"“{PLACE_EN.get(args.ablage, args.ablage)}” does not fit this mode. Possible: {', '.join(shown)}"))
            return
        cfg = load_config(layout.config_path)
        cfg.setdefault("abschriften", {})["ort"] = args.ablage
        save_config(layout.config_path, cfg)
        layout.config = load_config(layout.config_path)
    if args.abschliessen:
        _print(complete(layout, files, args.abschliessen))
    else:
        mode = TRANSCRIPTION_FROM_EN.get(args.transkription, args.transkription)
        if mode == "fragen":  # a permanent choice in the config counts as consent / refusal
            mode = {"allow": "erlaubt", "local_only": "lokal"}.get(str(layout.config.get("transcription")), "fragen")
        _print(ingest(layout, files, transcribe=mode))


def cmd_githook(args):
    from .gitops import install_precommit

    layout = _layout(args)
    _print(install_precommit(layout.root, str(write_launcher())))


def write_launcher() -> Path:
    """A stable launcher in the user cache that points at the currently installed plugin."""
    root = os.environ.get("PLUG_N_RAG_PLUGIN_ROOT") or str(Path(__file__).resolve().parents[2])
    path = user_cache_dir() / "plug-n-rag"
    script = f'#!/bin/sh\nexec "{root}/scripts/plug-n-rag" "$@"\n'
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.read_text(encoding="utf-8") != script:
            path.write_text(script, encoding="utf-8")
            path.chmod(0o755)
    except OSError:
        pass
    return path


def spawn_background_sync(layout: Layout) -> None:
    """Continue indexing detached from the hook so the session can start right away."""
    log = layout.cache_dir / "background.log"
    cmd = [sys.executable, "-m", "plug_n_rag.cli", "--ordner", str(layout.root), "sync", "--quiet"]
    try:
        with open(log, "ab") as fh:
            kwargs = {"stdout": fh, "stderr": fh, "stdin": subprocess.DEVNULL, "cwd": str(layout.root)}
            if os.name == "nt":
                kwargs["creationflags"] = 0x00000008  # DETACHED_PROCESS
            else:
                kwargs["start_new_session"] = True
            subprocess.Popen(cmd, **kwargs)  # noqa: S603
    except OSError:
        pass


def cmd_session_start(args):
    """SessionStart hook: setup check, git pull, sync (time-boxed), hydrate, short map."""
    layout = _layout(args, require=False)
    if layout is None:
        return
    if not layout.configured:
        _print(tr("plug-n-rag: Obsidian-Vault erkannt, aber noch nicht eingerichtet. "
                  "/plug-n-rag:setup startet die Einrichtung.",
                  "plug-n-rag: Obsidian vault detected, but not set up yet. "
                  "/plug-n-rag:setup starts the setup."))
        return
    from . import gitops, tuning
    from .mapview import karte
    from .sync import sync

    write_launcher()
    notes: list[str] = []
    git_cfg = layout.config.get("git", {}) or {}
    in_git = layout.location == "inside" and gitops.inside_repo(layout.root)
    if in_git:
        msg = gitops.pull(layout.root)
        if msg:
            notes.append(msg)
    budget = args.budget
    emb_cfg = layout.config.get("embedding", {})
    if emb_cfg.get("provider", "local") == "local":
        from .embed.local import is_model_cached

        if not is_model_cached(emb_cfg.get("model", ""), emb_cfg.get("revision")):
            budget = 0  # never download ~470 MB inside the hook: the background sync does it
            notes.append(tr("Das Suchmodell wird einmalig im Hintergrund geladen (etwa 470 MB). "
                            "Bis dahin funktioniert die Stichwortsuche.",
                            "The search model is loaded once in the background (about 470 MB). "
                            "Until then keyword search works."))
    try:
        r = sync(layout, time_budget=budget, lock_wait=5)
    except LockBusy:
        r = None
        notes.append(tr("Ein Abgleich läuft bereits im Hintergrund.", "A sync is already running in the background."))
    if r is not None:
        if r.pending and not r.embed_error and not r.model_mismatch:
            spawn_background_sync(layout)
            notes.append(tr(f"{plural(len(r.pending), 'Datei wird', 'Dateien werden')} im Hintergrund indexiert; "
                            "Stichwortsuche funktioniert schon.",
                            f"{plural(len(r.pending), 'file is', 'files are')} being indexed in the background; "
                            "keyword search already works."))
        if r.embed_error:
            notes.append(tr(f"Semantischer Index nicht aktualisierbar: {r.embed_error}",
                            f"Semantic index cannot be updated: {r.embed_error}"))
            from .cloud import in_cloud

            if in_cloud():
                notes.append(tr("Cloud-Sitzung: `plug-n-rag cloud` zeigt, was die Cloud-Umgebung braucht "
                                "(Netzwerkfreigabe, Setup-Skript).",
                                "Cloud session: `plug-n-rag cloud` shows what the cloud environment needs "
                                "(network access, setup script)."))
        if r.model_mismatch:
            notes.append(tr("Index passt nicht zum Modell: nur Stichwortsuche. /plug-n-rag:reindex anbieten.",
                            "The index does not match the model: keyword search only. Offer /plug-n-rag:reindex."))
        if r.errors:
            notes.append(tr(f"{len(r.errors)} Dateien konnten nicht gelesen werden (Details: plug-n-rag status).",
                            f"{len(r.errors)} files could not be read (details: plug-n-rag status)."))
        if r.awaiting:
            notes.append(_awaiting(len(r.awaiting)) + ".")
        if in_git and r.changed:
            mode = git_cfg.get("auto_commit", "off")
            done = False
            if mode == "all":
                done = gitops.commit_all(layout.root, tr("plug-n-rag: Änderungen übernommen und Index aktualisiert",
                                                         "plug-n-rag: changes taken over and index updated"))
            elif mode == "index":
                done = gitops.commit_paths(layout.root, gitops.index_paths(layout),
                                           tr("plug-n-rag: Index aktualisiert", "plug-n-rag: index updated"))
            if done and git_cfg.get("auto_push"):
                gitops.push(layout.root)
    from .migrate import needs_update

    if needs_update(layout):
        notes.append(tr("plug-n-rag nutzt jetzt einen aufgeräumten Ordneraufbau. `plug-n-rag umziehen` stellt "
                        "um, ohne etwas neu zu berechnen (vorher kurz bei der Nutzer:in nachfragen).",
                        "plug-n-rag now uses a tidier folder layout. `plug-n-rag migrate` switches over "
                        "without recomputing anything (briefly ask the user first)."))
    try:
        tuning.learn(layout)
    except Exception:  # noqa: BLE001 - learning must never break the session start
        pass
    _print(karte(layout, short=True))
    for n in notes:
        _print(tr("Hinweis: ", "Note: ") + n)
    from .cloud import in_cloud

    if in_cloud() and str(layout.config.get("anzeige", "kompakt")) not in ("aus", "off"):
        # Nothing is drawn in cloud sessions, so the person cannot see what plug-n-rag did.
        _print(tr("Anzeige: In dieser Cloud-Sitzung sieht die Nutzer:in nicht, was plug-n-rag tut. Beende "
                  "Antworten, die sich auf die Vault stützen, mit einer Zeile wie „— aus deiner Vault: "
                  "3 Abschnitte aus 2 Notizen“.",
                  "Display: in this cloud session the user cannot see what plug-n-rag does. End answers "
                  "that rely on the vault with a line like “— from your vault: 3 sections from 2 notes”."))


def cmd_stop(args):
    """Stop hook: quick sync. Silent and never blocking."""
    layout = _layout(args, require=False)
    if layout is None or not layout.configured:
        return
    from .sync import sync

    try:
        r = sync(layout, lock_wait=0)
    except LockBusy:
        return
    except Exception as exc:  # noqa: BLE001 - a hook must not break the session
        print(tr(f"plug-n-rag: Abgleich fehlgeschlagen: {exc}", f"plug-n-rag: sync failed: {exc}"), file=sys.stderr)
        return
    git_cfg = layout.config.get("git", {}) or {}
    if r.changed and git_cfg.get("auto_commit") == "index" and layout.location == "inside":
        from . import gitops

        if gitops.inside_repo(layout.root):
            gitops.commit_paths(layout.root, gitops.index_paths(layout),
                                tr("plug-n-rag: Index aktualisiert", "plug-n-rag: index updated"))


def cmd_cloud(args):
    from .cloud import check, guide, setup_script

    layout = _layout(args, require=False)
    cfg = layout.config if layout and layout.configured else load_config(Path("/nonexistent"))
    if args.hosts:
        from .cloud import resolve_hosts

        _print("\n".join(resolve_hosts(cfg)))
    elif args.skript:
        sys.stdout.write(setup_script(cfg))
    elif args.pruefen:
        _print(check(layout, network=not args.offline))
    else:
        _print(guide(layout if layout and layout.configured else None, cfg))


def cmd_modell_laden(args):
    from .cloud import preload_model

    layout = _layout(args, require=False)
    model = args.modell
    if not model:
        emb = (layout.config if layout and layout.configured else {}).get("embedding", {})
        if emb.get("provider", "local") != "local":
            _print(tr("Diese Vault nutzt Voyage AI, es gibt kein lokales Modell zu laden.",
                      "This vault uses Voyage AI, there is no local model to load."))
            return
        model = emb.get("model", "intfloat/multilingual-e5-small")
    _print(preload_model(model))


def cmd_nach_main(args):
    from . import gitops
    from .sync import sync

    layout = _layout(args)
    if layout.location != "inside" or not gitops.inside_repo(layout.root):
        _print(tr("Diese Vault ist kein Git-Repo, es gibt nichts nach main zu übernehmen.",
                  "This vault is not a git repository, there is nothing to publish to main."))
        return
    sync(layout)
    msg = args.nachricht or tr("Notizen und Suchindex übernommen (plug-n-rag)",
                               "Notes and search index published (plug-n-rag)")
    _print(gitops.publish_to_main(layout, msg, resync=lambda: sync(layout)))


def plugin_root() -> Path:
    return Path(os.environ.get("PLUG_N_RAG_PLUGIN_ROOT") or Path(__file__).resolve().parents[2])


def cmd_anleitung(args):
    """Print a skill's instructions, for sessions where the freshly installed plugin is not loaded yet."""
    root = plugin_root()
    skills = root / "skills"
    names = sorted(p.name for p in skills.iterdir() if (p / "SKILL.md").is_file()) if skills.is_dir() else []
    args.name = SKILL_ALIASES.get(args.name or "", args.name)
    if not args.name or args.name not in names:
        _print(tr("Verfügbare Anleitungen: ", "Available guides: ") + ", ".join(names))
        return
    text = (skills / args.name / "SKILL.md").read_text(encoding="utf-8")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        text = text[end + 4:].lstrip("\n") if end > 0 else text
    launcher = root / "scripts" / "plug-n-rag"
    text = text.replace("${CLAUDE_PLUGIN_ROOT}", str(root)).replace("$ARGUMENTS", " ".join(args.argumente))
    _print(tr(f"(Anleitung „{args.name}“ aus plug-n-rag. Ist `plug-n-rag` nicht auf dem PATH, "
              f"den vollen Pfad verwenden: {launcher})",
              f"(Guide “{args.name}” from plug-n-rag. If `plug-n-rag` is not on the PATH, "
              f"use the full path: {launcher})") + "\n\n" + text)


SKILL_ALIASES = {"search": "suche", "ingest": "aufnehmen", "to-main": "nach-main",
                 "switch-model": "modell-wechseln", "reset-learning": "lernen-zuruecksetzen"}


def cmd_umziehen(args):
    from .migrate import move

    layout = _layout(args)
    args.nach = LOCATION_FROM_EN.get(args.nach, args.nach)
    if args.nach == "zentral" and layout.mode == "vault" and not args.trotzdem:
        _print(tr("Bei einer Vault gehört der Index in den Ordner .plug-n-rag/: nur dann funktionieren "
                  "Cloud-Sitzungen und mehrere Geräte. Wenn trotzdem zentral gewünscht: --trotzdem.",
                  "For a vault the index belongs in the folder .plug-n-rag/: only then do cloud sessions "
                  "and several devices work. If central is wanted anyway: --anyway."))
        return
    for step in move(layout, args.nach):
        _print(step)
    from .sync import sync

    new = find_layout(layout.root)
    if new and new.configured:
        r = sync(new)
        _print(_report_text(r))


def cmd_anzeige_daten(args):
    from .anzeige import render_json

    _print(render_json(_layout(args, require=False)))


def cmd_mcp(args):
    from .mcp_server import main as mcp_main

    mcp_main()


# --- parser -------------------------------------------------------------------------------

def _language_from_argv(argv: list[str]) -> None:
    """Pick the language before parsing, so that --help already speaks it."""
    start = None
    for i, a in enumerate(argv):
        if a in ("--ordner", "--folder") and i + 1 < len(argv):
            start = Path(argv[i + 1]).expanduser()
        elif a.startswith(("--ordner=", "--folder=")):
            start = Path(a.split("=", 1)[1]).expanduser()
    try:
        layout = find_layout(start)
    except OSError:
        layout = None
    i18n.use_layout(layout if layout is not None and layout.configured else None)


def _cmd(sub, de: str, en: str, help_de: str | None, help_en: str | None, extra_aliases=()):
    """A subcommand under its German and English name; the current language's name comes first."""
    name, alias = (en, de) if i18n.is_en() else (de, en)
    aliases = [a for a in (alias, *extra_aliases) if a != name]
    if help_de is None:
        return sub.add_parser(name, aliases=aliases)
    return sub.add_parser(name, aliases=aliases, help=tr(help_de, help_en))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="plug-n-rag", description=tr(
        "Semantische Suche in Vaults und Sammlungen.", "Semantic search in vaults and collections."))
    p.add_argument("--version", action="version", version=f"plug-n-rag {__version__}")
    p.add_argument(*(("--folder", "--ordner") if i18n.is_en() else ("--ordner", "--folder")), dest="ordner", metavar=tr("ORDNER", "FOLDER"),
                   help=tr("Vault oder Sammlung (Standard: aktueller Ordner)",
                           "vault or collection (default: current folder)"))
    sub = p.add_subparsers(dest="cmd", required=True)

    s = _cmd(sub, "karte", "map", "Überblick über Ordner und Schwerpunkte", "overview of folders and topics")
    s.add_argument("--kurz", "--short", dest="kurz", action="store_true")
    s.set_defaults(func=cmd_karte)

    s = _cmd(sub, "suche", "search", "Relevante Notizen finden", "find relevant notes")
    s.add_argument("frage", nargs="*")
    s.add_argument("--zweck", "--purpose", dest="zweck", choices=PURPOSES, default="frage")
    s.add_argument("--in", dest="in_", metavar=tr("ORDNER", "FOLDER"))
    s.add_argument("--tag")
    s.add_argument("--seit", "--since", dest="seit", metavar=tr("JJJJ-MM-TT", "YYYY-MM-DD"))
    s.add_argument("--weiter", "--more", dest="weiter", action="store_true",
                   help=tr("nächste Seite der letzten Suche", "next page of the last search"))
    s.set_defaults(func=cmd_suche)

    s = _cmd(sub, "gliederung", "outline", "Überschriften mit Positionen und Größe",
             "headings with positions and size")
    s.add_argument("notiz", nargs="+")
    s.set_defaults(func=cmd_gliederung)

    s = _cmd(sub, "lesen", "read", "Abschnitt lesen: notiz#Überschrift oder notiz:45-80",
             "read a section: note#Heading or note:45-80")
    s.add_argument("ziel", nargs="+")
    s.set_defaults(func=cmd_lesen)

    s = _cmd(sub, "verwandt", "related", "Links, Backlinks, ähnliche Notizen", "links, backlinks, similar notes")
    s.add_argument("notiz", nargs="+")
    s.set_defaults(func=cmd_verwandt)

    s = sub.add_parser("status", help=tr("Zustand, Modell, Fehler, gelernte Werte, Ersparnis",
                                         "state, model, errors, learned values, savings"))
    s.add_argument("--schnell", "--quick", dest="schnell", action="store_true",
                   help=tr("ohne GitHub-Abfrage", "without asking GitHub"))
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("sync", help=tr("Abgleich Dateien ↔ Index", "sync files ↔ index"))
    s.add_argument("--quiet", action="store_true")
    s.add_argument("--budget", type=float, default=None,
                   help=tr("Zeitbudget in Sekunden, Rest im Hintergrund", "time budget in seconds, rest in the background"))
    s.add_argument("--fortschritt", "--progress", dest="fortschritt", action="store_true")
    s.set_defaults(func=cmd_sync)

    s = sub.add_parser("hydrate", help=tr("Suchdatenbank aus Index-Dateien bauen", "build the search database from index files"))
    s.add_argument("--neu", "--rebuild", dest="neu", action="store_true",
                   help=tr("komplett neu bauen", "rebuild completely"))
    s.set_defaults(func=cmd_hydrate)

    s = sub.add_parser("reindex", help=tr("Vollständige Neuindexierung", "full reindex"))
    s.add_argument("--ja", "--yes", dest="ja", action="store_true", help=tr("bestätigt", "confirmed"))
    s.add_argument("--fortschritt", "--progress", dest="fortschritt", action="store_true")
    s.set_defaults(func=cmd_reindex)

    s = sub.add_parser("init", help=tr("Konfiguration anlegen (vom Setup genutzt)", "create the configuration (used by setup)"))
    s.add_argument("pfad", nargs="?")
    s.add_argument("--modus", "--mode", dest="modus", choices=["vault", "sammlung", "collection"], default="vault")
    s.add_argument("--ort", "--location", dest="ort", choices=["ordner", "zentral", "folder", "central"],
                   help=tr("Dateien von plug-n-rag im Ordner (.plug-n-rag/) oder zentral auf diesem Rechner",
                           "plug-n-rag's files inside the folder (.plug-n-rag/) or central on this computer"))
    s.add_argument("--extern", action="store_true", help=argparse.SUPPRESS)  # old name for --ort zentral
    s.add_argument("--abschriften", "--transcripts", dest="abschriften", choices=PLACE_CHOICES,
                   help=tr("Ablage von Abschriften aus /plug-n-rag:aufnehmen",
                           "where transcripts from /plug-n-rag:aufnehmen go"))
    s.add_argument("--abschriften-ordner", "--transcripts-folder", dest="abschriften_ordner",
                   help=tr("Ordner für Abschriften in einer Vault (Standard: Abschriften)",
                           "folder for transcripts in a vault (default: Abschriften)"))
    s.add_argument("--provider", choices=["local", "voyage", "fake"], default="local")
    s.add_argument("--modell", "--model", dest="modell")
    s.add_argument("--sprache", "--language", dest="sprache", choices=["de", "en"],
                   help=tr("Sprache der Ausgaben (Standard: Systemsprache)",
                           "language of messages (default: system language)"))
    s.add_argument("--privat", "--private", dest="privat", nargs="*",
                   help=tr("private Ordner, z. B. 'Tagebuch/**'", "private folders, e.g. 'Journal/**'"))
    s.add_argument("--ausschliessen", "--exclude", dest="ausschliessen", nargs="*")
    s.add_argument("--formate", "--formats", dest="formate", nargs="*", choices=["markdown", "text", "pdf"])
    s.set_defaults(func=cmd_init)

    s = _cmd(sub, "inventur", "inventory", "Bestandsaufnahme für das Setup", "inventory for the setup")
    s.add_argument("pfad", nargs="?")
    s.add_argument("--json", action="store_true")
    s.add_argument("--sprache", "--language", dest="sprache", choices=["de", "en"])
    s.set_defaults(func=cmd_inventur)

    s = _cmd(sub, "konfig", "config", "Konfiguration anzeigen oder setzen (schluessel=wert)",
             "show or set the configuration (key=value)")
    s.add_argument("--setzen", "--set", dest="setzen", nargs="*")
    s.set_defaults(func=cmd_config)

    s = _cmd(sub, "lernen", "learn", "Token-Steuerung auswerten, Vorgaben setzen, zurücksetzen",
             "evaluate token steering, set preferences, reset")
    s.add_argument("--zuruecksetzen", "--reset", dest="zuruecksetzen", action="store_true")
    s.add_argument("--vorgaben-behalten", "--keep-preferences", dest="vorgaben_behalten", action="store_true")
    s.add_argument("--tiefer", "--deeper", dest="tiefer", action="store_true",
                   help=tr("Feedback: zu oberflächlich", "feedback: too shallow"))
    s.add_argument("--knapper", "--shorter", dest="knapper", action="store_true",
                   help=tr("Feedback: zu ausführlich", "feedback: too long"))
    s.add_argument("--zweck", "--purpose", dest="zweck", choices=PURPOSES, default="frage")
    s.set_defaults(func=cmd_lernen)

    s = _cmd(sub, "aufnehmen", "ingest", "PDFs in Text umwandeln (Kaskade)", "turn PDFs into text (cascade)")
    s.add_argument("dateien", nargs="+")
    s.add_argument("--transkription", "--transcription", dest="transkription",
                   choices=["fragen", "lokal", "erlaubt", "ask", "local", "allowed"], default="fragen")
    s.add_argument("--abschliessen", "--finish", dest="abschliessen", choices=["haiku", "sonnet"],
                   help=tr("Transkription übernehmen und ablegen", "take over the transcription and save it"))
    s.add_argument("--ablage", "--place", dest="ablage", choices=PLACE_CHOICES,
                   help=tr("Ablage der Abschriften festlegen (wird in der Konfiguration gemerkt)",
                           "set where transcripts go (remembered in the configuration)"))
    s.set_defaults(func=cmd_aufnehmen)

    s = sub.add_parser("git-hook", help=tr("Git-pre-commit-Hook installieren", "install the git pre-commit hook"))
    s.set_defaults(func=cmd_githook)

    s = sub.add_parser("session-start")  # hooks only, no help text
    s.add_argument("--budget", type=float, default=6.0)
    s.set_defaults(func=cmd_session_start)

    s = sub.add_parser("stop")
    s.set_defaults(func=cmd_stop)

    s = sub.add_parser("cloud", help=tr("Einrichtung für Cloud-Sitzungen: Anleitung, Setup-Skript, Prüfung",
                                        "setup for cloud sessions: guide, setup script, check"))
    s.add_argument("--skript", "--script", dest="skript", action="store_true",
                   help=tr("nur das Setup-Skript ausgeben", "print only the setup script"))
    s.add_argument("--pruefen", "--check", dest="pruefen", action="store_true",
                   help=tr("prüfen, ob alles für Cloud-Sitzungen bereit ist", "check whether everything is ready for cloud sessions"))
    s.add_argument("--hosts", action="store_true",
                   help=tr("tatsächlich nötige Download-Hosts ermitteln", "find the download hosts actually needed"))
    s.add_argument("--offline", action="store_true", help=argparse.SUPPRESS)
    s.set_defaults(func=cmd_cloud)

    s = _cmd(sub, "modell-laden", "load-model", "Lokales Suchmodell herunterladen und prüfen",
             "download and check the local search model")
    s.add_argument("--modell", "--model", dest="modell")
    s.set_defaults(func=cmd_modell_laden)

    s = _cmd(sub, "nach-main", "to-main", "Alle Änderungen (Notizen und Index) sicher nach main übernehmen",
             "safely publish all changes (notes and index) to main")
    s.add_argument("--nachricht", "--message", "-m", dest="nachricht", help=tr("Commit-Nachricht", "commit message"))
    s.set_defaults(func=cmd_nach_main)

    s = _cmd(sub, "anleitung", "guide", "Leitfaden eines Skills ausgeben (z. B. setup, cloud, nach-main)",
             "print a skill's guide (e.g. setup, cloud, to-main)")
    s.add_argument("name", nargs="?")
    s.add_argument("argumente", nargs="*")
    s.set_defaults(func=cmd_anleitung)

    s = _cmd(sub, "umziehen", "migrate", "Auf den aktuellen Ordneraufbau umstellen oder Ablageort wechseln",
             "switch to the current folder layout or change where the index lives")
    s.add_argument("--nach", "--to", dest="nach", choices=["ordner", "zentral", "folder", "central"],
                   help=tr("Ziel: im Ordner (.plug-n-rag/) oder zentral", "target: inside the folder (.plug-n-rag/) or central"))
    s.add_argument("--trotzdem", "--anyway", dest="trotzdem", action="store_true", help=argparse.SUPPRESS)
    s.set_defaults(func=cmd_umziehen)

    s = sub.add_parser("anzeige-daten", aliases=["display-data"])  # JSON for the mod
    s.set_defaults(func=cmd_anzeige_daten)

    s = sub.add_parser("mcp", help=tr("MCP-Server starten (stdio)", "start the MCP server (stdio)"))
    s.set_defaults(func=cmd_mcp)
    return p


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252 ("St�rung")
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass
    _language_from_argv(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
