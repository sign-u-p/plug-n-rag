"""Cloud sessions (claude.ai/code): what the environment needs and whether it is in place.

Cloud sessions do not install plugins that a repository enables in ``.claude/settings.json``.
What works instead: a *setup script* on the cloud environment installs plug-n-rag at user
scope inside the container and preloads the model. The environment snapshot then keeps
plugin, Python packages and model, so later sessions start ready to search.
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request

from . import gitops
from .config import Layout
from .embed.local import LOCAL_MODELS, is_model_cached
from .i18n import tr

MARKETPLACE_REPO = "sign-u-p/plug-n-rag"
HF_HOSTS = ["huggingface.co", "*.hf.co"]  # *.hf.co covers the download CDNs (e.g. us.aws.cdn.hf.co)
VOYAGE_HOST = "api.voyageai.com"


def in_cloud() -> bool:
    return os.environ.get("CLAUDE_CODE_REMOTE") == "true"


def _provider(config: dict) -> tuple[str, str]:
    emb = config.get("embedding", {}) or {}
    return emb.get("provider", "local"), emb.get("model", "intfloat/multilingual-e5-small")


def allowed_domains(config: dict) -> list[str]:
    provider, _ = _provider(config)
    return list(HF_HOSTS) if provider == "local" else []


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # noqa: D401 - keep the 30x response
        return None


def resolve_hosts(config: dict) -> list[str]:
    """Exact hosts the model download needs (for tools that do not accept ``*.`` patterns).

    Asks Hugging Face where the files redirect to. If huggingface.co itself is blocked, only
    ``huggingface.co`` is returned; call again after allowing it to learn the CDN host.
    """
    provider, model = _provider(config)
    if provider == "voyage":
        return [VOYAGE_HOST]
    if provider != "local" or model not in LOCAL_MODELS:
        return []
    spec = LOCAL_MODELS[model]
    hosts = ["huggingface.co"]
    opener = urllib.request.build_opener(_NoRedirect)
    for key in ("tokenizer", "onnx"):
        url = f"https://huggingface.co/{model}/resolve/{spec['revision']}/{spec[key]}"
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "plug-n-rag"})
        try:
            opener.open(req, timeout=10)
        except urllib.error.HTTPError as exc:
            loc = exc.headers.get("Location", "") if exc.headers else ""
            host = urllib.parse.urlparse(loc).hostname
            if host and host not in hosts:
                hosts.append(host)
        except (urllib.error.URLError, OSError, TimeoutError):
            break
    return hosts


def setup_script(config: dict) -> str:
    provider, model = _provider(config)
    lines = [
        "#!/bin/bash",
        tr("# plug-n-rag für Cloud-Sitzungen: Plugin installieren und Suchmodell vorab laden.",
           "# plug-n-rag for cloud sessions: install the plugin and preload the search model."),
        tr("# Läuft beim Bau der Umgebung; das Ergebnis wird als Abbild für spätere Sitzungen gespeichert.",
           "# Runs when the environment is built; the result is kept as a snapshot for later sessions."),
        "command -v claude >/dev/null 2>&1 || exit 0",
        f"claude plugin marketplace add {MARKETPLACE_REPO} >/dev/null 2>&1 \\",
        "  || claude plugin marketplace update plug-n-rag >/dev/null 2>&1 || true",
        "claude plugin install plug-n-rag@plug-n-rag >/dev/null 2>&1 || true",
        'P=$(ls -d "$HOME"/.claude/plugins/cache/plug-n-rag/plug-n-rag/*/ 2>/dev/null | sort -V | tail -1)',
    ]
    if provider == "local":
        lines.append(f'if [ -n "$P" ]; then "${{P}}scripts/plug-n-rag" modell-laden --modell {model} || true; fi')
    else:
        lines.append('if [ -n "$P" ]; then "${P}scripts/plug-n-rag" --version || true; fi')
    lines.append("exit 0")
    return "\n".join(lines) + "\n"


def guide(layout: Layout | None, config: dict) -> str:
    provider, model = _provider(config)
    out = [tr("plug-n-rag in Cloud-Sitzungen (claude.ai/code, Desktop- und Handy-App)",
              "plug-n-rag in cloud sessions (claude.ai/code, desktop and mobile app)"), ""]
    out.append(tr("Wichtig: Ein Eintrag in .claude/settings.json des Vault-Repos reicht in der Cloud nicht. "
                  "Cloud-Sitzungen installieren keine Plugins aus dem Repo. Stattdessen bekommt die "
                  "Cloud-Umgebung ein Setup-Skript.",
                  "Important: an entry in the vault repository's .claude/settings.json is not enough in the "
                  "cloud. Cloud sessions do not install plugins from the repository. Instead the cloud "
                  "environment gets a setup script."))
    out.append("")
    out.append(tr("1. Cloud-Umgebung öffnen: in der Sitzungsleiste auf den Namen der Umgebung, dann "
                  "„Bearbeiten“ (oder eine neue Umgebung „Hinzufügen“, z. B. „Vault“).",
                  "1. Open the cloud environment: click the environment's name in the session bar, then "
                  "“Edit” (or “Add” a new environment, e.g. “Vault”)."))
    domains = allowed_domains(config)
    if domains:
        out.append(tr("2. Netzwerkzugriff: „Limited“, Häkchen bei „Allow package managers“ lassen, unter "
                      "„Allowed domains“ eintragen (für das Suchmodell von Hugging Face):",
                      "2. Network access: “Limited”, keep “Allow package managers” ticked, and add under "
                      "“Allowed domains” (for the search model from Hugging Face):"))
        out += [f"     {d}" for d in domains]
    elif provider == "voyage":
        out.append(tr(f"2. Netzwerkzugriff: „Limited“ reicht. Den Voyage-Key als Netzwerk-Secret für den Host "
                      f"{VOYAGE_HOST} hinterlegen (nie ins Repo, nie als Umgebungsvariable). Damit ist der Host "
                      "automatisch erreichbar.",
                      f"2. Network access: “Limited” is enough. Store the Voyage key as a network secret for the "
                      f"host {VOYAGE_HOST} (never in the repository, never as an environment variable). That "
                      "makes the host reachable automatically."))
    else:
        out.append(tr("2. Netzwerkzugriff: „Limited“ reicht, keine zusätzlichen Freigaben nötig.",
                      "2. Network access: “Limited” is enough, nothing else needs to be allowed."))
    out.append(tr("3. Setup-Skript einfügen:", "3. Paste the setup script:"))
    out.append("")
    out += ["     " + ln if ln else "" for ln in setup_script(config).splitlines()]
    out.append("")
    out.append(tr("4. Speichern und eine neue Sitzung mit dem Vault-Repo in dieser Umgebung starten. Der erste "
                  "Start dauert einige Minuten (Modell etwa 470 MB), danach startet die Umgebung aus dem Abbild.",
                  "4. Save and start a new session with the vault repository in this environment. The first "
                  "start takes a few minutes (model about 470 MB); after that the environment starts from "
                  "its snapshot.")
               if provider == "local" else
               tr("4. Speichern und eine neue Sitzung mit dem Vault-Repo in dieser Umgebung starten.",
                  "4. Save and start a new session with the vault repository in this environment."))
    out.append(tr("5. In der Cloud-Sitzung prüfen: `plug-n-rag cloud --pruefen`.",
                  "5. Check inside the cloud session: `plug-n-rag cloud --check`."))
    out.append("")
    out.append(tr("Hinweise:", "Notes:"))
    out.append(tr("- Die Index-Dateien (.plug-n-rag/index/) müssen committet und gepusht sein, sonst rechnet jede "
                  "Cloud-Sitzung neu.",
                  "- The index files (.plug-n-rag/index/) must be committed and pushed, otherwise every "
                  "cloud session recomputes them."))
    out.append(tr("- Cloud-Sitzungen arbeiten auf einem eigenen Branch (claude/…). Änderungen an Notizen erscheinen "
                  "in Obsidian erst nach dem Zusammenführen auf GitHub.",
                  "- Cloud sessions work on a branch of their own (claude/…). Changes to notes only show up "
                  "in Obsidian after they are merged on GitHub."))
    out.append(tr(f"- Ist das Repo {MARKETPLACE_REPO} privat, braucht die Umgebung Zugriff darauf.",
                  f"- If the repository {MARKETPLACE_REPO} is private, the environment needs access to it."))
    if layout is not None:
        out.append(tr(f"- Konfiguration dieser Vault: Provider {provider}, Modell {model}.",
                      f"- Configuration of this vault: provider {provider}, model {model}."))
    return "\n".join(out)


def _probe(url: str, timeout: float = 8.0) -> tuple[bool, str]:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "plug-n-rag"})
    try:
        with urllib.request.urlopen(req, timeout=timeout):
            return True, tr("erreichbar", "reachable")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 404, 405):  # the host answered: reachable
            return True, tr("erreichbar", "reachable")
        return False, tr(f"blockiert (HTTP {exc.code})", f"blocked (HTTP {exc.code})")
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return False, tr(f"nicht erreichbar ({getattr(exc, 'reason', exc)})",
                         f"not reachable ({getattr(exc, 'reason', exc)})")


def check(layout: Layout | None, *, network: bool = True) -> str:
    cfg = layout.config if layout else {}
    provider, model = _provider(cfg or {"embedding": {}})
    ok, warn, info = "✓", "⚠", "–"
    lines = [tr("Prüfung für Cloud-Sitzungen", "Check for cloud sessions")]
    if in_cloud():
        lines.append(f"{ok} " + tr("Läuft in einer Cloud-Sitzung", "Running in a cloud session"))
    else:
        lines.append(f"{info} " + tr("Keine Cloud-Sitzung (lokal). Die Prüfung zeigt, was eine Cloud-Sitzung bräuchte.",
                                     "Not a cloud session (local). The check shows what a cloud session would need."))
    root = os.environ.get("PLUG_N_RAG_PLUGIN_ROOT", "")
    if "/.claude/plugins/" in root.replace("\\", "/"):
        lines.append(f"{ok} " + tr(f"Plugin ist installiert ({root})", f"Plugin is installed ({root})"))
    elif root:
        lines.append(f"{info} " + tr(f"Plugin läuft aus einem Ordner ({root}), nicht aus dem Marketplace",
                                     f"Plugin runs from a folder ({root}), not from the marketplace"))
    if layout is None or not layout.configured:
        lines.append(f"{warn} " + tr("Hier ist keine Vault eingerichtet (/plug-n-rag:setup)",
                                     "No vault is set up here (/plug-n-rag:setup)"))
        return "\n".join(lines)
    if layout.location == "inside" and gitops.inside_repo(layout.root):
        try:
            tracked = gitops.git(layout.root, "ls-files", "--", ".plug-n-rag/index").stdout.split("\n")
            tracked = [t for t in tracked if t.endswith(".json")]
            dirty = [ln for ln in gitops.status_porcelain(layout.root) if ".plug-n-rag/index" in ln]
        except (OSError, subprocess.SubprocessError):
            tracked, dirty = [], []
        if not tracked:
            lines.append(f"{warn} " + tr("Index-Dateien sind nicht im Repo. Committen und pushen, sonst rechnet jede "
                                         "Cloud-Sitzung alles neu.",
                                         "Index files are not in the repository. Commit and push them, otherwise "
                                         "every cloud session recomputes everything."))
        elif dirty:
            lines.append(f"{warn} " + tr(f"{len(dirty)} Index-Dateien sind geändert, aber nicht committet",
                                         f"{len(dirty)} index files are changed but not committed"))
        else:
            lines.append(f"{ok} " + tr(f"{len(tracked)} Index-Dateien sind im Repo",
                                       f"{len(tracked)} index files are in the repository"))
        url = gitops.remote_url(layout.root)
        vis = gitops.repo_visibility(layout.root) if (url and network) else None
        if not url:
            lines.append(f"{warn} " + tr("Kein GitHub-Repo verbunden. Cloud-Sitzungen brauchen die Vault auf GitHub.",
                                         "No GitHub repository connected. Cloud sessions need the vault on GitHub."))
        elif vis == "public":
            lines.append(f"{warn} " + tr("Das Vault-Repo ist ÖFFENTLICH. Dringend auf privat stellen.",
                                         "The vault repository is PUBLIC. Please make it private right away."))
        elif vis:
            lines.append(f"{ok} " + tr("Vault-Repo auf GitHub, privat", "Vault repository on GitHub, private"))
        settings = layout.root / ".claude" / "settings.json"
        try:
            data = json.loads(settings.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        if any("plug-n-rag" in str(k) for k in (data.get("enabledPlugins") or {})):
            lines.append(f"{info} " + tr(".claude/settings.json aktiviert plug-n-rag. Das hilft lokal, in der Cloud "
                                         "lädt erst das Setup-Skript das Plugin.",
                                         ".claude/settings.json enables plug-n-rag. That helps locally; in the "
                                         "cloud only the setup script loads the plugin."))
    elif layout.location == "external":
        lines.append(f"{warn} " + tr("Index liegt außerhalb des Ordners (Sammlungs-Modus ohne Git): in Cloud-Sitzungen "
                                     "nicht verfügbar.",
                                     "The index lies outside the folder (collection mode without git): not "
                                     "available in cloud sessions."))
    if provider == "local":
        if is_model_cached(model, (cfg.get("embedding") or {}).get("revision")):
            lines.append(f"{ok} " + tr("Suchmodell liegt bereit", "Search model is ready"))
        elif network:
            reach, why = _probe(f"https://huggingface.co/api/models/{model}")
            if reach:
                lines.append(f"{warn} " + tr(f"Suchmodell fehlt noch, Hugging Face ist {why}: `plug-n-rag modell-laden`",
                                             f"Search model still missing, Hugging Face is {why}: "
                                             "`plug-n-rag load-model`"))
            else:
                lines.append(f"{warn} " + tr(f"Suchmodell fehlt, Hugging Face {why}. In der Cloud-Umgebung unter "
                                             f"„Allowed domains“ eintragen: {', '.join(HF_HOSTS)}",
                                             f"Search model missing, Hugging Face {why}. Add under “Allowed "
                                             f"domains” in the cloud environment: {', '.join(HF_HOSTS)}"))
    elif provider == "voyage":
        from .embed.voyage import api_key

        has_key = bool(os.environ.get("VOYAGE_API_KEY")) or (api_key() not in (None, "proxy-injected"))
        if in_cloud() and not has_key:
            lines.append(f"{info} " + tr(f"Voyage-Key wird in der Cloud als Netzwerk-Secret für {VOYAGE_HOST} erwartet",
                                         f"In the cloud the Voyage key is expected as a network secret for {VOYAGE_HOST}"))
        elif not has_key:
            lines.append(f"{warn} " + tr("Kein Voyage-Key gefunden (VOYAGE_API_KEY)", "No Voyage key found (VOYAGE_API_KEY)"))
        if network:
            reach, why = _probe(f"https://{VOYAGE_HOST}/v1/embeddings")
            lines.append(f"{ok if reach else warn} " + tr(f"{VOYAGE_HOST} ist {why}", f"{VOYAGE_HOST} is {why}"))
    return "\n".join(lines)


def preload_model(model: str, revision: str | None = None) -> str:
    """Download and load the local model once (for setup scripts and first runs)."""
    from .embed import EmbeddingUnavailable
    from .embed.local import LocalEmbedder

    if model not in LOCAL_MODELS:
        return tr(f"Unbekanntes lokales Modell: {model}", f"Unknown local model: {model}")
    cached = is_model_cached(model, revision)
    try:
        LocalEmbedder(model, revision, quiet=False).embed(["Probe"], "query")
    except EmbeddingUnavailable as exc:
        return tr(f"Suchmodell konnte nicht geladen werden: {exc}", f"Search model could not be loaded: {exc}")
    if cached:
        return tr(f"Suchmodell {model} war schon geladen und ist einsatzbereit.",
                  f"Search model {model} was already loaded and is ready.")
    return tr(f"Suchmodell {model} wurde heruntergeladen und ist einsatzbereit.",
              f"Search model {model} was downloaded and is ready.")
