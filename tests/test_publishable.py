"""Checks on what the public repository ships: manifests, skill, credits, no private details."""
import json
import os
import re
import subprocess
import unittest
from pathlib import Path

from yap_forever import gamedata

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "forever-professions"


def frontmatter(text: str) -> dict[str, str]:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    out = {}
    for line in (m.group(1) if m else "").splitlines():
        key, sep, value = line.partition(":")
        if sep and not line.startswith(" "):
            out[key.strip()] = value.strip()
    return out


def tracked_text_files() -> list[Path]:
    names = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", check=True).stdout.split()
    files = []
    for n in names:
        p = ROOT / n
        if p.is_file() and p.suffix not in {".png", ".jpg", ".gif", ".ico"}:
            files.append(p)
    return files


# Patterns are written so they never match this file's own source.
PRIVATE = [
    ("IPv4 address", re.compile(r"(?<![\d.])(?!127\.0\.0\.1)(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}(?![\d.])")),
    ("macOS home path", re.compile(r"/Use[r]s/")),
    ("Linux home path", re.compile(r"/hom[e]/\w")),
    ("Windows home path", re.compile(r"C:\\Use[r]s\\", re.I)),
    ("email address", re.compile(r"\b(?!noreply@)[\w.+-]+@(?!users\.noreply\.)[\w-]+\.[a-z]{2,}\b", re.I)),
    ("ssh key option", re.compile(r"\bss[h] -i\b")),
]


class PublishableTests(unittest.TestCase):
    def test_manifests_valid(self):
        plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        self.assertEqual(plugin["name"], "yap-forever")
        self.assertEqual(market["plugins"][0]["name"], plugin["name"])
        self.assertEqual(market["plugins"][0]["source"], "./")
        self.assertRegex(plugin["version"], r"^\d+\.\d+\.\d+$")
        self.assertEqual(plugin["license"], "GPL-3.0-or-later")

    def test_one_version_in_the_package_and_the_manifest(self):
        import yap_forever
        plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(plugin["version"], yap_forever.__version__)

    def test_the_manifest_version_is_not_behind_the_newest_tag(self):
        """The version is bumped with every tag (docs/project-setup.md, row "Tags"): a tag made
        without the bump would pin players to the version before it."""
        try:
            out = subprocess.run(["git", "tag", "-l", "v*"], cwd=ROOT, capture_output=True, text=True,
                                 timeout=30, check=True).stdout
        except (OSError, subprocess.SubprocessError):
            self.skipTest("git not available")
        tags = [tuple(map(int, m.groups())) for t in out.split()
                if (m := re.match(r"v(\d+)\.(\d+)\.(\d+)", t))]
        if not tags:
            self.skipTest("no v* tags in this checkout")
        import yap_forever
        self.assertGreaterEqual(tuple(map(int, yap_forever.__version__.split("."))), max(tags))

    def test_skill_frontmatter(self):
        fm = frontmatter((SKILL / "SKILL.md").read_text(encoding="utf-8"))
        self.assertEqual(fm.get("name"), SKILL.name)
        self.assertTrue(0 < len(fm.get("description", "")) <= 1024)

    def test_skill_reference_links_exist(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        refs = set(re.findall(r"references/[\w-]+\.md", text))
        self.assertGreaterEqual(len(refs), 3)
        for ref in refs:
            self.assertTrue((SKILL / ref).exists(), ref)

    def test_credits_cover_sources(self):
        credits = (ROOT / "CREDITS.md").read_text(encoding="utf-8")
        for url in gamedata.SOURCES.values():
            m = re.match(r"https://raw\.githubusercontent\.com/([^/]+/[^/]+)/", url)
            origin = m.group(1) if m else re.match(r"https://([^/]+)/", url).group(1)
            self.assertIn(origin, credits)
        for pin in (gamedata.SKILLUP_SHA, gamedata.QUESTIE_SHA, str(gamedata.WAGO_BUILD)):
            self.assertIn(pin, credits)

    def test_no_private_details(self):
        deny_file = ROOT / ".private-denylist"
        deny = [l.strip() for l in deny_file.read_text(encoding="utf-8").splitlines()
                if l.strip()] if deny_file.exists() else []
        hits = []
        for p in tracked_text_files():
            text = p.read_text(encoding="utf-8", errors="replace")
            for label, rx in PRIVATE:
                if rx.search(text):
                    hits.append(f"{p.relative_to(ROOT)}: {label}")
            for d in deny:  # plain text, or "re:<pattern>" for things like a bare number
                found = re.search(d[3:], text) if d.startswith("re:") else d in text
                if found:
                    hits.append(f"{p.relative_to(ROOT)}: denylisted text")
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()


# Commits up to and including this one may carry the owner's personal email (published before
# the noreply switch on 2026-11-18); every later commit by the owner must use a noreply address.
# Outside contributors' commits are theirs to sign as they like and are not checked.
IDENTITY_BASELINE = "8583233"
OWNER_LOGIN = "sableon"  # the repository owner's GitHub login (public in the repository URL)


def non_noreply(emails: list[str]) -> list[str]:
    return sorted({e for e in emails if e and "noreply" not in e})


def owner_names(authors: list[tuple[str, str]]) -> set[str]:
    """Names the owner commits under: those used with the owner's GitHub noreply address."""
    suffix = f"+{OWNER_LOGIN}@users.noreply.github.com"
    return {name for name, email in authors if email.endswith(suffix)}


def owner_leaks(rows: list[tuple[str, str, str, str]], names: set[str]) -> list[str]:
    """Non-noreply addresses on the owner's side of (author, author email, committer, committer email)."""
    return non_noreply([e for an, ae, cn, ce in rows for n, e in ((an, ae), (cn, ce)) if n in names])


class CommitIdentityTests(unittest.TestCase):
    def test_only_owner_commits_must_use_noreply(self):
        personal = "x" + "@" + "mail.example"
        owner_noreply = "1+" + OWNER_LOGIN + "@users.noreply.github.com"
        rows = [("Owner Name", owner_noreply, "GitHub", "noreply@github.com"),
                ("Some Contributor", personal, "Some Contributor", personal),
                ("Owner Name", personal, "Owner Name", personal)]
        names = owner_names([("Owner Name", owner_noreply), ("Some Contributor", personal)])
        self.assertEqual(names, {"Owner Name"})
        self.assertEqual(owner_leaks(rows, names), [personal])

    def test_non_noreply_flags_personal_addresses(self):
        personal = "x" + "@" + "mail.example"  # built up so the private-details scan ignores it
        self.assertEqual(non_noreply(["1+a@users.noreply.github.com", "noreply@github.com", personal]),
                         [personal])

    def test_commits_after_baseline_use_noreply(self):
        have = subprocess.run(["git", "cat-file", "-e", IDENTITY_BASELINE + "^{commit}"], cwd=ROOT,
                              capture_output=True)
        if have.returncode != 0:
            self.skipTest("shallow clone without the baseline commit")
        # On a pull_request run, HEAD is GitHub's throwaway test merge; check the PR's own commits
        # (its second parent). The real merge onto main is checked by the push run that follows.
        tip = "HEAD^2" if os.environ.get("GITHUB_EVENT_NAME") == "pull_request" else "HEAD"
        def log(rng, fmt):
            out = subprocess.run(["git", "log", *rng, f"--format={fmt}"], cwd=ROOT, capture_output=True,
                                 text=True, encoding="utf-8", check=True).stdout
            return [tuple(line.split("\t")) for line in out.splitlines() if line]

        names = owner_names(log([tip], "%an%x09%ae") + log([tip], "%cn%x09%ce"))
        rows = log([f"{IDENTITY_BASELINE}..{tip}"], "%an%x09%ae%x09%cn%x09%ce")
        self.assertEqual(len(owner_leaks(rows, names)), 0,
                         "a commit after the baseline uses a personal email: set the repo's user.email "
                         "to your GitHub noreply address and turn on 'Keep my email private'")
