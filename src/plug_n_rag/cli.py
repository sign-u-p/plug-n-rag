"""Command line entry point: ``plug-n-rag <befehl>``.

Hooks, skill, slash commands and the MCP wrapper all call into this core.
Subcommands are German (as in SPEC) with English aliases.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from . import __version__
from .config import Layout, find_layout, init_layout, load_config, save_config
from .util import LockBusy, fmt_int, plural, user_cache_dir

NOT_SET_UP = ("Hier ist noch nichts für plug-n-rag eingerichtet. "
              "Mit /plug-n-rag:setup startet die geführte Einrichtung.")


def _layout(args, require: bool = True) -> Layout | None:
    start = Path(args.ordner).expanduser() if getattr(args, "ordner", None) else None
    layout = find_layout(start)
    if require and (layout is None or not layout.configured):
        print(NOT_SET_UP)
        sys.exit(2)
    return layout


def _print(text: str) -> None:
    sys.stdout.write(text.rstrip() + "\n")


# --- commands ---------------------------------------------------------------------------

def cmd_karte(args):
    from .mapview import karte

    _print(karte(_layout(args), short=args.kurz))


def cmd_suche(args):
    from .search import search

    query = " ".join(args.frage) if args.frage else None
    _print(search(_layout(args), query, purpose=args.zweck, folder=args.in_, tag=args.tag,
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
        parts.append(f"{len(r.added)} neu")
    if r.updated:
        parts.append(f"{len(r.updated)} geändert")
    if r.removed:
        parts.append(f"{len(r.removed)} entfernt")
    if r.private_removed:
        parts.append(f"{len(r.private_removed)} privat (Index gelöscht)")
    head = "Abgleich: " + (", ".join(parts) if parts else "nichts zu tun")
    head += f" · {fmt_int(r.unchanged)} unverändert"
    if r.embedded_chunks or r.reused_chunks:
        head += f" · {fmt_int(r.embedded_chunks)} Abschnitte neu eingebettet, {fmt_int(r.reused_chunks)} wiederverwendet"
    lines = [head]
    if r.pending:
        lines.append(f"Noch ausstehend: {plural(len(r.pending), 'Datei', 'Dateien')}")
    if r.embed_error:
        lines.append(f"Hinweis: {r.embed_error}")
    if r.model_mismatch:
        lines.append("Hinweis: Index passt nicht zum Modell, nur Stichwortsuche. /plug-n-rag:reindex bietet die Neuindexierung an.")
    if r.awaiting:
        lines.append(f"Hinweis: {plural(len(r.awaiting), 'eingescannte Datei wartet', 'eingescannte Dateien warten')} "
                     "auf Aufnahme (/plug-n-rag:aufnehmen)")
    for path, msg in list(r.errors.items())[:5]:
        lines.append(f"Fehler: {path}: {msg}")
    return "\n".join(lines)


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
            _print("Ein anderer Abgleich läuft gerade. Bitte kurz warten.")
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
    _print(f"Suchdatenbank: {st['notes']} Dateien ({st['added']} neu, {st['updated']} aktualisiert, "
           f"{st['removed']} entfernt) in {st['elapsed']:.1f} s")


def cmd_reindex(args):
    from .sync import pending_count, reindex

    layout = _layout(args)
    if not args.ja:
        todo, total = pending_count(layout)
        _print(f"Neuindexierung von {plural(total, 'Datei', 'Dateien')} mit Modell "
               f"{layout.config['embedding']['model']} ({layout.config['embedding']['provider']}). "
               "Bitte mit Nutzer:in bestätigen und dann `plug-n-rag reindex --ja` ausführen.")
        return
    r = reindex(layout, progress=(lambda m: print("  " + m, file=sys.stderr)) if args.fortschritt else None)
    _print(_report_text(r))


def cmd_init(args):
    root = Path(args.pfad).expanduser().resolve() if args.pfad else Path.cwd()
    if not root.is_dir():
        _print(f"Ordner nicht gefunden: {root}")
        sys.exit(2)
    mode = "collection" if args.modus in ("sammlung", "collection") else "vault"
    from . import gitops

    if args.extern:
        args.ort = "zentral"
    if args.ort:
        location = "external" if args.ort == "zentral" else "inside"
    else:  # vaults always inside; collections inside only if they already are a git repo
        location = "inside" if mode == "vault" or gitops.is_repo(root) else "external"
    extra: dict = {}
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
        extra["abschriften"] = {"ort": args.abschriften}
        if args.abschriften_ordner:
            extra["abschriften"]["ordner"] = args.abschriften_ordner
    from .config import CONFIG_NAME, STATE_DIR_NAME, external_state_dir

    existed = ((root / STATE_DIR_NAME / CONFIG_NAME).exists() or (root / CONFIG_NAME).exists()
               or (location == "external" and (external_state_dir(root) / CONFIG_NAME).exists()))
    layout = init_layout(root, mode=mode, location=location, provider=args.provider, model=args.modell, extra=extra)
    if location == "inside" and layout.mode == "vault":
        _ensure_gitignore(root)
    _print(("Konfiguration war schon vorhanden, nichts überschrieben: " if existed else "Eingerichtet: ")
           + str(layout.config_path))
    _print(f"Index: {layout.index_dir}" + (" (im Ordner)" if layout.location == "inside" else
                                           " (zentral auf diesem Rechner, im Ordner wird nichts angelegt)"))
    _print(f"Ausgeschlossen: {', '.join(layout.config.get('exclude', []))}")


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
            _print("API-Keys gehören nicht in die Konfiguration. Bitte VOYAGE_API_KEY als Umgebungsvariable setzen.")
            sys.exit(2)
        save_config(layout.config_path, cfg)
        _print("Konfiguration gespeichert.")
    import yaml

    _print(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False))


def cmd_lernen(args):
    from . import tuning

    layout = _layout(args)
    if args.zuruecksetzen:
        tuning.reset(layout, keep_overrides=args.vorgaben_behalten)
        _print("Lern-Datei auf Startwerte gesetzt.")
    elif args.tiefer or args.knapper:
        ov = tuning.set_override(layout, args.zweck, deeper=bool(args.tiefer))
        _print(f"Vorgabe für „{args.zweck}“ gespeichert: " + ", ".join(f"{k}={v}" for k, v in ov.items()))
    else:
        tuning.learn(layout)
    _print("\n".join(tuning.describe(layout)))


def cmd_aufnehmen(args):
    from .ingest import complete, ingest

    layout = _layout(args)
    files = [Path(p) for p in args.dateien]
    if args.ablage:
        from .ingest import PLACES

        valid = PLACES["collection" if layout.mode == "collection" else "vault"]
        if args.ablage not in valid:
            _print(f"„{args.ablage}“ passt nicht zu diesem Modus. Möglich: {', '.join(valid)}")
            return
        cfg = load_config(layout.config_path)
        cfg.setdefault("abschriften", {})["ort"] = args.ablage
        save_config(layout.config_path, cfg)
        layout.config = load_config(layout.config_path)
    if args.abschliessen:
        _print(complete(layout, files, args.abschliessen))
    else:
        mode = args.transkription
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
        _print("plug-n-rag: Obsidian-Vault erkannt, aber noch nicht eingerichtet. "
               "/plug-n-rag:setup startet die Einrichtung.")
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
            notes.append("Das Suchmodell wird einmalig im Hintergrund geladen (etwa 470 MB). "
                         "Bis dahin funktioniert die Stichwortsuche.")
    try:
        r = sync(layout, time_budget=budget, lock_wait=5)
    except LockBusy:
        r = None
        notes.append("Ein Abgleich läuft bereits im Hintergrund.")
    if r is not None:
        if r.pending and not r.embed_error and not r.model_mismatch:
            spawn_background_sync(layout)
            notes.append(f"{plural(len(r.pending), 'Datei wird', 'Dateien werden')} im Hintergrund indexiert; "
                         "Stichwortsuche funktioniert schon.")
        if r.embed_error:
            notes.append(f"Semantischer Index nicht aktualisierbar: {r.embed_error}")
            from .cloud import in_cloud

            if in_cloud():
                notes.append("Cloud-Sitzung: `plug-n-rag cloud` zeigt, was die Cloud-Umgebung braucht "
                             "(Netzwerkfreigabe, Setup-Skript).")
        if r.model_mismatch:
            notes.append("Index passt nicht zum Modell: nur Stichwortsuche. /plug-n-rag:reindex anbieten.")
        if r.errors:
            notes.append(f"{len(r.errors)} Dateien konnten nicht gelesen werden (Details: plug-n-rag status).")
        if r.awaiting:
            notes.append(f"{plural(len(r.awaiting), 'eingescannte Datei wartet', 'eingescannte Dateien warten')} "
                         "auf Aufnahme (/plug-n-rag:aufnehmen).")
        if in_git and r.changed:
            mode = git_cfg.get("auto_commit", "off")
            done = False
            if mode == "all":
                done = gitops.commit_all(layout.root, "plug-n-rag: Änderungen übernommen und Index aktualisiert")
            elif mode == "index":
                done = gitops.commit_paths(layout.root, gitops.index_paths(layout), "plug-n-rag: Index aktualisiert")
            if done and git_cfg.get("auto_push"):
                gitops.push(layout.root)
    from .migrate import needs_update

    if needs_update(layout):
        notes.append("plug-n-rag nutzt jetzt einen aufgeräumten Ordneraufbau. `plug-n-rag umziehen` stellt "
                     "um, ohne etwas neu zu berechnen (vorher kurz bei der Nutzer:in nachfragen).")
    try:
        tuning.learn(layout)
    except Exception:  # noqa: BLE001 - learning must never break the session start
        pass
    _print(karte(layout, short=True))
    for n in notes:
        _print("Hinweis: " + n)
    from .cloud import in_cloud

    if in_cloud() and str(layout.config.get("anzeige", "kompakt")) != "aus":
        # Nothing is drawn in cloud sessions, so the person cannot see what plug-n-rag did.
        _print("Anzeige: In dieser Cloud-Sitzung sieht die Nutzer:in nicht, was plug-n-rag tut. Beende "
               "Antworten, die sich auf die Vault stützen, mit einer Zeile wie „— aus deiner Vault: "
               "3 Abschnitte aus 2 Notizen“.")


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
        print(f"plug-n-rag: Abgleich fehlgeschlagen: {exc}", file=sys.stderr)
        return
    git_cfg = layout.config.get("git", {}) or {}
    if r.changed and git_cfg.get("auto_commit") == "index" and layout.location == "inside":
        from . import gitops

        if gitops.inside_repo(layout.root):
            gitops.commit_paths(layout.root, gitops.index_paths(layout), "plug-n-rag: Index aktualisiert")


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
            _print("Diese Vault nutzt Voyage AI, es gibt kein lokales Modell zu laden.")
            return
        model = emb.get("model", "intfloat/multilingual-e5-small")
    _print(preload_model(model))


def cmd_nach_main(args):
    from . import gitops
    from .sync import sync

    layout = _layout(args)
    if layout.location != "inside" or not gitops.inside_repo(layout.root):
        _print("Diese Vault ist kein Git-Repo, es gibt nichts nach main zu übernehmen.")
        return
    sync(layout)
    msg = args.nachricht or "Notizen und Suchindex übernommen (plug-n-rag)"
    _print(gitops.publish_to_main(layout, msg, resync=lambda: sync(layout)))


def plugin_root() -> Path:
    return Path(os.environ.get("PLUG_N_RAG_PLUGIN_ROOT") or Path(__file__).resolve().parents[2])


def cmd_anleitung(args):
    """Print a skill's instructions, for sessions where the freshly installed plugin is not loaded yet."""
    root = plugin_root()
    skills = root / "skills"
    names = sorted(p.name for p in skills.iterdir() if (p / "SKILL.md").is_file()) if skills.is_dir() else []
    if not args.name or args.name not in names:
        _print("Verfügbare Anleitungen: " + ", ".join(names))
        return
    text = (skills / args.name / "SKILL.md").read_text(encoding="utf-8")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        text = text[end + 4:].lstrip("\n") if end > 0 else text
    launcher = root / "scripts" / "plug-n-rag"
    text = text.replace("${CLAUDE_PLUGIN_ROOT}", str(root)).replace("$ARGUMENTS", " ".join(args.argumente))
    _print(f"(Anleitung „{args.name}“ aus plug-n-rag. Ist `plug-n-rag` nicht auf dem PATH, "
           f"den vollen Pfad verwenden: {launcher})\n\n" + text)


def cmd_umziehen(args):
    from .migrate import move

    layout = _layout(args)
    if args.nach == "zentral" and layout.mode == "vault" and not args.trotzdem:
        _print("Bei einer Vault gehört der Index in den Ordner .plug-n-rag/: nur dann funktionieren "
               "Cloud-Sitzungen und mehrere Geräte. Wenn trotzdem zentral gewünscht: --trotzdem.")
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

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="plug-n-rag", description="Semantische Suche in Vaults und Sammlungen.")
    p.add_argument("--version", action="version", version=f"plug-n-rag {__version__}")
    p.add_argument("--ordner", help="Vault oder Sammlung (Standard: aktueller Ordner)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("karte", aliases=["map"], help="Überblick über Ordner und Schwerpunkte")
    s.add_argument("--kurz", action="store_true")
    s.set_defaults(func=cmd_karte)

    s = sub.add_parser("suche", aliases=["search"], help="Relevante Notizen finden")
    s.add_argument("frage", nargs="*")
    s.add_argument("--zweck", choices=["frage", "recherche", "erstellen"], default="frage")
    s.add_argument("--in", dest="in_", metavar="ORDNER")
    s.add_argument("--tag")
    s.add_argument("--seit", metavar="JJJJ-MM-TT")
    s.add_argument("--weiter", action="store_true", help="nächste Seite der letzten Suche")
    s.set_defaults(func=cmd_suche)

    s = sub.add_parser("gliederung", aliases=["outline"], help="Überschriften mit Positionen und Größe")
    s.add_argument("notiz", nargs="+")
    s.set_defaults(func=cmd_gliederung)

    s = sub.add_parser("lesen", aliases=["read"], help="Abschnitt lesen: notiz#Überschrift oder notiz:45-80")
    s.add_argument("ziel", nargs="+")
    s.set_defaults(func=cmd_lesen)

    s = sub.add_parser("verwandt", aliases=["related"], help="Links, Backlinks, ähnliche Notizen")
    s.add_argument("notiz", nargs="+")
    s.set_defaults(func=cmd_verwandt)

    s = sub.add_parser("status", help="Zustand, Modell, Fehler, gelernte Werte, Ersparnis")
    s.add_argument("--schnell", action="store_true", help="ohne GitHub-Abfrage")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("sync", help="Abgleich Dateien ↔ Index")
    s.add_argument("--quiet", action="store_true")
    s.add_argument("--budget", type=float, default=None, help="Zeitbudget in Sekunden, Rest im Hintergrund")
    s.add_argument("--fortschritt", action="store_true")
    s.set_defaults(func=cmd_sync)

    s = sub.add_parser("hydrate", help="Suchdatenbank aus Index-Dateien bauen")
    s.add_argument("--neu", action="store_true", help="komplett neu bauen")
    s.set_defaults(func=cmd_hydrate)

    s = sub.add_parser("reindex", help="Vollständige Neuindexierung")
    s.add_argument("--ja", action="store_true", help="bestätigt")
    s.add_argument("--fortschritt", action="store_true")
    s.set_defaults(func=cmd_reindex)

    s = sub.add_parser("init", help="Konfiguration anlegen (vom Setup genutzt)")
    s.add_argument("pfad", nargs="?")
    s.add_argument("--modus", choices=["vault", "sammlung", "collection"], default="vault")
    s.add_argument("--ort", choices=["ordner", "zentral"],
                   help="Dateien von plug-n-rag im Ordner (.plug-n-rag/) oder zentral auf diesem Rechner")
    s.add_argument("--extern", action="store_true", help=argparse.SUPPRESS)  # old name for --ort zentral
    s.add_argument("--abschriften", choices=["neben_original", "ordner", "intern"],
                   help="Ablage von Abschriften aus /plug-n-rag:aufnehmen")
    s.add_argument("--abschriften-ordner", help="Ordner für Abschriften in einer Vault (Standard: Abschriften)")
    s.add_argument("--provider", choices=["local", "voyage", "fake"], default="local")
    s.add_argument("--modell")
    s.add_argument("--privat", nargs="*", help="private Ordner, z. B. 'Tagebuch/**'")
    s.add_argument("--ausschliessen", nargs="*")
    s.add_argument("--formate", nargs="*", choices=["markdown", "text", "pdf"])
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("inventur", help="Bestandsaufnahme für das Setup")
    s.add_argument("pfad", nargs="?")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_inventur)

    s = sub.add_parser("konfig", help="Konfiguration anzeigen oder setzen (schluessel=wert)")
    s.add_argument("--setzen", nargs="*")
    s.set_defaults(func=cmd_config)

    s = sub.add_parser("lernen", help="Token-Steuerung auswerten, Vorgaben setzen, zurücksetzen")
    s.add_argument("--zuruecksetzen", action="store_true")
    s.add_argument("--vorgaben-behalten", action="store_true")
    s.add_argument("--tiefer", action="store_true", help="Feedback: zu oberflächlich")
    s.add_argument("--knapper", action="store_true", help="Feedback: zu ausführlich")
    s.add_argument("--zweck", choices=["frage", "recherche", "erstellen"], default="frage")
    s.set_defaults(func=cmd_lernen)

    s = sub.add_parser("aufnehmen", aliases=["ingest"], help="PDFs in Text umwandeln (Kaskade)")
    s.add_argument("dateien", nargs="+")
    s.add_argument("--transkription", choices=["fragen", "lokal", "erlaubt"], default="fragen")
    s.add_argument("--abschliessen", choices=["haiku", "sonnet"], help="Transkription übernehmen und ablegen")
    s.add_argument("--ablage", choices=["neben_original", "ordner", "intern"],
                   help="Ablage der Abschriften festlegen (wird in der Konfiguration gemerkt)")
    s.set_defaults(func=cmd_aufnehmen)

    s = sub.add_parser("git-hook", help="Git-pre-commit-Hook installieren")
    s.set_defaults(func=cmd_githook)

    s = sub.add_parser("session-start", help=argparse.SUPPRESS)
    s.add_argument("--budget", type=float, default=6.0)
    s.set_defaults(func=cmd_session_start)

    s = sub.add_parser("stop", help=argparse.SUPPRESS)
    s.set_defaults(func=cmd_stop)

    s = sub.add_parser("cloud", help="Einrichtung für Cloud-Sitzungen: Anleitung, Setup-Skript, Prüfung")
    s.add_argument("--skript", action="store_true", help="nur das Setup-Skript ausgeben")
    s.add_argument("--pruefen", action="store_true", help="prüfen, ob alles für Cloud-Sitzungen bereit ist")
    s.add_argument("--hosts", action="store_true", help="tatsächlich nötige Download-Hosts ermitteln")
    s.add_argument("--offline", action="store_true", help=argparse.SUPPRESS)
    s.set_defaults(func=cmd_cloud)

    s = sub.add_parser("modell-laden", help="Lokales Suchmodell herunterladen und prüfen")
    s.add_argument("--modell")
    s.set_defaults(func=cmd_modell_laden)

    s = sub.add_parser("nach-main", help="Alle Änderungen (Notizen und Index) sicher nach main übernehmen")
    s.add_argument("--nachricht", "-m", help="Commit-Nachricht")
    s.set_defaults(func=cmd_nach_main)

    s = sub.add_parser("anleitung", help="Leitfaden eines Skills ausgeben (z. B. setup, cloud, nach-main)")
    s.add_argument("name", nargs="?")
    s.add_argument("argumente", nargs="*")
    s.set_defaults(func=cmd_anleitung)

    s = sub.add_parser("umziehen", help="Auf den aktuellen Ordneraufbau umstellen oder Ablageort wechseln")
    s.add_argument("--nach", choices=["ordner", "zentral"], help="Ziel: im Ordner (.plug-n-rag/) oder zentral")
    s.add_argument("--trotzdem", action="store_true", help=argparse.SUPPRESS)
    s.set_defaults(func=cmd_umziehen)

    s = sub.add_parser("anzeige-daten", help=argparse.SUPPRESS)  # JSON for the display mod
    s.set_defaults(func=cmd_anzeige_daten)

    s = sub.add_parser("mcp", help="MCP-Server starten (stdio)")
    s.set_defaults(func=cmd_mcp)
    return p


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252 ("St�rung")
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
