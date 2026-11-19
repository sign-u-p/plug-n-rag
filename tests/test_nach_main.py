import subprocess

import pytest

from plug_n_rag import gitops
from plug_n_rag.config import find_layout
from plug_n_rag.sync import sync

from .conftest import copy_vault, make_layout

pytestmark = pytest.mark.skipif(not gitops.shutil.which("git"), reason="git fehlt")
ENV = ["-c", "user.name=Test", "-c", "user.email=t@example.invalid"]


def g(root, *args, check=True):
    return subprocess.run(["git", "-C", str(root), *ENV, *args], capture_output=True, text=True, check=check).stdout


@pytest.fixture
def setup_repos(tmp_path, fake):
    """origin (bare, main) + a 'cloud' clone on a claude/ branch + an 'obsidian' clone on main."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    root = copy_vault(tmp_path, "start")
    g(root, "init", "-q", "-b", "main")
    layout = make_layout(root)
    sync(layout, embedder=fake)
    g(root, "add", "-A")
    g(root, "commit", "-q", "-m", "Vault mit Index")
    g(root, "remote", "add", "origin", str(origin))
    g(root, "push", "-q", "-u", "origin", "main")
    cloud = tmp_path / "cloud"
    subprocess.run(["git", "clone", "-q", str(origin), str(cloud)], check=True)
    g(cloud, "checkout", "-q", "-b", "claude/notizen-xyz")
    obsidian = tmp_path / "obsidian"
    subprocess.run(["git", "clone", "-q", str(origin), str(obsidian)], check=True)
    return origin, cloud, obsidian


def test_publish_from_claude_branch_to_main(setup_repos, fake, monkeypatch):
    origin, cloud, obsidian = setup_repos
    import plug_n_rag.sync as sync_mod

    monkeypatch.setattr(sync_mod, "get_embedder", lambda cfg: fake)
    layout = find_layout(cloud)
    (cloud / "themen" / "Neu aus der Cloud.md").write_text("# Neu\n\nSitzung im Wald: Balancieren.", encoding="utf-8")
    # meanwhile someone changes another note on main (e.g. Obsidian Git)
    p = obsidian / "wissen" / "COPM.md"
    p.write_text(p.read_text(encoding="utf-8") + "\nErgänzung aus Obsidian.\n", encoding="utf-8")
    g(obsidian, "commit", "-q", "-am", "Obsidian")
    g(obsidian, "push", "-q")
    sync(layout, embedder=fake)
    out = gitops.publish_to_main(layout, "Neue Notiz", resync=lambda: sync(layout, embedder=fake))
    assert "Auf main übernommen (vom Branch claude/notizen-xyz)" in out, out
    files = g(origin, "ls-tree", "-r", "--name-only", "main").split("\n")
    assert "themen/Neu aus der Cloud.md" in files
    assert ".plug-n-rag/index/themen/Neu aus der Cloud.md.json" in files
    assert "Ergänzung aus Obsidian" in g(origin, "show", "main:wissen/COPM.md")
    assert not any(f.startswith(".plug-n-rag/cache") for f in files)
    # history kept: Obsidian's commit is an ancestor of main
    log = g(origin, "log", "--format=%s", "main")
    assert "Obsidian" in log and "Neue Notiz" in log


def test_conflict_in_note_is_not_resolved_automatically(setup_repos, fake):
    origin, cloud, obsidian = setup_repos
    for clone, text in ((obsidian, "Fassung Obsidian"), (cloud, "Fassung Cloud")):
        (clone / "wissen" / "COPM.md").write_text(text, encoding="utf-8")
    g(obsidian, "commit", "-q", "-am", "Obsidian")
    g(obsidian, "push", "-q")
    layout = find_layout(cloud)
    before = g(origin, "rev-parse", "main")
    out = gitops.publish_to_main(layout, "Cloud", resync=lambda: sync(layout, embedder=fake))
    assert "Nicht übernommen" in out and "wissen/COPM.md" in out
    assert g(origin, "rev-parse", "main") == before
    assert (cloud / "wissen" / "COPM.md").read_text(encoding="utf-8") == "Fassung Cloud"
    assert not gitops.unmerged(cloud)


def test_secret_blocks_publish(setup_repos, fake):
    origin, cloud, obsidian = setup_repos
    (cloud / "notiz.md").write_text("key: pa-" + "x" * 40, encoding="utf-8")
    layout = find_layout(cloud)
    before = g(origin, "rev-parse", "main")
    out = gitops.publish_to_main(layout, "Cloud")
    assert "API-Key" in out and "notiz.md" in out
    assert g(origin, "rev-parse", "main") == before
    assert "notiz.md" in g(cloud, "status", "--porcelain")  # nothing lost, just not committed
