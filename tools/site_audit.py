#!/usr/bin/env python3
"""Monthly quality-control audit and publisher for joseantoniocharles.com.

Usage (from anywhere):
    python3 tools/site_audit.py              audit only
    python3 tools/site_audit.py --publish    audit, then commit and push to GitHub
                                             if nothing blocking was found
    python3 tools/site_audit.py --offline    skip network checks (links, DNS, live site)

Result levels:
    FAIL   blocks publishing; fix in the local folder first
    ALERT  live-site or publishing problem that needs attention (does not block)
    WARN   worth reviewing
    PASS   check succeeded

Reports go to .audit/<date>.md and .audit/latest.md (not published).
Python 3.9 standard library only.
"""

import argparse
import datetime as dt
import hashlib
import html.parser
import re
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOMAIN = "joseantoniocharles.com"
GITHUB_HOST = "charlesantoniojose-byte.github.io"
GITHUB_PAGES_IPS = {"185.199.108.153", "185.199.109.153", "185.199.110.153", "185.199.111.153"}
RESUME_PDF = ROOT / "assets/docs/Jose_Antonio_Charles_Resume.pdf"
MASTER_RESUME = Path.home() / ("Library/CloudStorage/OneDrive-Personal/Personal Projects/"
                               "Engineering_Mass_Apply/Resume_Cover Letter_CV/Jose Charles Resume.docx")
REQUIRED_FILES = ["index.html", "css/style.css", "js/script.js", "CNAME",
                  "assets/docs/Jose_Antonio_Charles_Resume.pdf"]
SKIP_DIRS = {".git", ".audit", "tools"}
TEXT_EXT = {".html", ".css", ".js", ".md", ".txt", ".yml", ".json", ""}
MAX_FILE_BYTES = 25 * 1024 * 1024
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
             "source", "track", "wbr", "path", "circle", "rect", "line", "polyline", "stop", "use"}
SENSITIVE_NAME = re.compile(r"transcript|student.?id|ssn|passport|\.env$|id_rsa|\.pem$|\.key$", re.I)
SECRET_PATTERNS = [
    (re.compile(r"ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}"), "GitHub token"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key"),
]
EM_DASH = re.compile(r"—|&mdash;|&#8212;|&#x2014;", re.I)
UA = "Mozilla/5.0 (Macintosh) joseantoniocharles-site-audit/1.0"

results = []
pushed = False


def record(level, check, message):
    results.append((level, check, message))


def site_files():
    for p in sorted(ROOT.rglob("*")):
        if p.is_file() and not (set(p.relative_to(ROOT).parts) & SKIP_DIRS):
            yield p


def rel(p):
    return p.relative_to(ROOT).as_posix()


def run(cmd, timeout=60):
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


# ---------------------------------------------------------------- local checks

class PageParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.errors, self.ids, self.refs = [], [], set(), []
        self.imgs_without_alt, self.blank_without_noopener = 0, 0
        self.title, self.description, self.canonical = False, False, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            self.ids.add(a["id"])
        for key in ("href", "src"):
            if a.get(key):
                self.refs.append((tag, a[key]))
        if tag == "img" and "alt" not in a:
            self.imgs_without_alt += 1
        if tag == "a" and a.get("target") == "_blank" and "noopener" not in (a.get("rel") or ""):
            self.blank_without_noopener += 1
        if tag == "title":
            self.title = True
        if tag == "meta" and a.get("name") == "description" and a.get("content"):
            self.description = True
        if tag == "link" and a.get("rel") == "canonical":
            self.canonical = a.get("href")
        if tag not in VOID_TAGS:
            self.stack.append((tag, self.getpos()[0]))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS and self.stack and self.stack[-1][0] == tag:
            self.stack.pop()

    def handle_endtag(self, tag):
        if tag in VOID_TAGS:
            return
        if self.stack and self.stack[-1][0] == tag:
            self.stack.pop()
        elif any(t == tag for t, _ in self.stack):
            while self.stack and self.stack[-1][0] != tag:
                t, line = self.stack.pop()
                self.errors.append(f"<{t}> opened on line {line} is never closed")
            self.stack.pop()
        else:
            self.errors.append(f"stray </{tag}> on line {self.getpos()[0]}")


def parse_pages():
    pages = {}
    for p in site_files():
        if p.suffix == ".html":
            parser = PageParser()
            parser.feed(p.read_text(encoding="utf-8"))
            parser.close()
            for t, line in parser.stack:
                if t not in ("html", "body", "head"):
                    parser.errors.append(f"<{t}> opened on line {line} is never closed")
            pages[p] = parser
    return pages


def check_required_files():
    missing = [f for f in REQUIRED_FILES if not (ROOT / f).is_file()]
    if missing:
        record("FAIL", "Required files", "missing: " + ", ".join(missing))
    else:
        record("PASS", "Required files", f"all {len(REQUIRED_FILES)} present")
    cname = ROOT / "CNAME"
    if cname.is_file() and cname.read_text().strip() != DOMAIN:
        record("FAIL", "CNAME", f"contains '{cname.read_text().strip()}', expected '{DOMAIN}'")


def check_html(pages):
    bad = {rel(p): parser.errors for p, parser in pages.items() if parser.errors}
    if bad:
        for page, errs in bad.items():
            record("FAIL", "HTML structure", f"{page}: " + "; ".join(errs[:5]))
    else:
        record("PASS", "HTML structure", f"{len(pages)} pages well formed")

    for p, parser in pages.items():
        if parser.imgs_without_alt:
            record("WARN", "Accessibility", f"{rel(p)}: {parser.imgs_without_alt} image(s) missing alt text")
        if parser.blank_without_noopener:
            record("WARN", "Link safety", f"{rel(p)}: {parser.blank_without_noopener} new-tab link(s) without rel=noopener")
    home = pages.get(ROOT / "index.html")
    if home:
        missing = [n for n, ok in (("<title>", home.title), ("meta description", home.description)) if not ok]
        if missing:
            record("WARN", "SEO", "index.html missing " + ", ".join(missing))
        if home.canonical != f"https://{DOMAIN}/":
            record("WARN", "SEO", f"canonical is {home.canonical!r}, expected https://{DOMAIN}/")


def check_local_links(pages):
    broken = []
    for p, parser in pages.items():
        for tag, ref in parser.refs:
            if re.match(r"^(https?:|mailto:|tel:|data:|javascript:|//)", ref):
                continue
            path, _, frag = ref.partition("#")
            target = (p.parent / urllib.parse.unquote(path)).resolve() if path else p
            if target.is_dir():
                target = target / "index.html"
            if not target.is_file():
                broken.append(f"{rel(p)} -> {ref}")
            elif frag and target in pages and frag not in pages[target].ids and frag != "top":
                broken.append(f"{rel(p)} -> {ref} (no element with id '{frag}')")
    if broken:
        for b in broken:
            record("FAIL", "Internal links", b)
    else:
        total = sum(len(pr.refs) for pr in pages.values())
        record("PASS", "Internal links", f"{total} links and asset references resolve")


def check_text_rules():
    dashes, secrets = [], []
    for p in site_files():
        if p.suffix.lower() not in TEXT_EXT:
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(text.splitlines(), 1):
            if EM_DASH.search(line):
                dashes.append(f"{rel(p)}:{i}")
        for pattern, label in SECRET_PATTERNS:
            if pattern.search(text):
                secrets.append(f"{rel(p)} ({label})")
    if dashes:
        record("FAIL", "Style: no em dashes", "found at " + ", ".join(dashes[:10]))
    else:
        record("PASS", "Style: no em dashes", "none found")
    for s in secrets:
        record("FAIL", "Secrets", f"possible credential in {s}")


def check_files():
    big = [f"{rel(p)} ({p.stat().st_size / 1e6:.1f} MB)" for p in site_files() if p.stat().st_size > MAX_FILE_BYTES]
    for b in big:
        record("FAIL", "File size", f"{b} exceeds 25 MB")
    sensitive = [rel(p) for p in site_files() if SENSITIVE_NAME.search(p.name)]
    for s in sensitive:
        record("FAIL", "Sensitive files", f"{s} looks private (transcript, ID, key); remove before publishing")
    empty = [rel(p) for p in site_files() if p.stat().st_size == 0 and p.name != ".nojekyll"]
    for e in empty:
        record("WARN", "Empty files", f"{e} is 0 bytes (possibly a cloud-only placeholder)")
    if not (big or sensitive):
        record("PASS", "Files", f"{sum(1 for _ in site_files())} files, none oversized or sensitive")


def check_resume_freshness():
    if not RESUME_PDF.is_file():
        return
    if not MASTER_RESUME.is_file():
        record("WARN", "Resume freshness", f"master resume not found at {MASTER_RESUME}")
        return
    pdf_t = dt.datetime.fromtimestamp(RESUME_PDF.stat().st_mtime)
    doc_t = dt.datetime.fromtimestamp(MASTER_RESUME.stat().st_mtime)
    if doc_t > pdf_t:
        record("WARN", "Resume freshness",
               f"master resume edited {doc_t:%Y-%m-%d}, site PDF exported {pdf_t:%Y-%m-%d}; re-export the PDF")
    else:
        record("PASS", "Resume freshness", f"site PDF ({pdf_t:%Y-%m-%d}) is newer than the master resume")


# -------------------------------------------------------------- network checks

def fetch(url, timeout=20, follow=True):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    opener = urllib.request.build_opener() if follow else urllib.request.build_opener(NoRedirect)
    with opener.open(req, timeout=timeout) as resp:
        return resp.status, resp.headers, resp.read()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def check_external_links(pages):
    urls = sorted({ref for pr in pages.values() for tag, ref in pr.refs
                   if ref.startswith("http") and tag == "a" and DOMAIN not in ref})
    bad = []
    for url in urls:
        try:
            fetch(url, timeout=15)
        except urllib.error.HTTPError as e:
            if e.code not in (403, 429, 999):  # LinkedIn and others block automated requests
                bad.append(f"{url} (HTTP {e.code})")
        except Exception as e:
            bad.append(f"{url} ({type(e).__name__})")
    for b in bad:
        record("WARN", "External links", b)
    if not bad:
        record("PASS", "External links", f"{len(urls)} reachable")


def dig(rtype, name):
    code, out = run(["/usr/bin/dig", "+short", rtype, name, "@1.1.1.1"], timeout=20)
    return [line.rstrip(".") for line in out.splitlines() if line] if code == 0 else []


def cert_days_left(host):
    ctx = ssl.create_default_context()
    with socket.create_connection((host, 443), timeout=15) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as s:
            expires = dt.datetime.strptime(s.getpeercert()["notAfter"], "%b %d %H:%M:%S %Y %Z")
    return (expires - dt.datetime.utcnow()).days


def check_live_site():
    apex = set(dig("A", DOMAIN))
    if apex == GITHUB_PAGES_IPS:
        record("PASS", "DNS", f"{DOMAIN} points to GitHub Pages")
    else:
        record("ALERT", "DNS", f"{DOMAIN} A records are {sorted(apex) or 'missing'}; expected the 4 GitHub IPs")
    www = dig("CNAME", "www." + DOMAIN)
    if www[:1] != [GITHUB_HOST]:
        record("ALERT", "DNS", f"www.{DOMAIN} CNAME is {www or 'missing'}; expected {GITHUB_HOST}")

    for host, level in ((DOMAIN, "ALERT"), ("www." + DOMAIN, "WARN")):
        try:
            days = cert_days_left(host)
            if days < 14:
                record("ALERT", "HTTPS", f"{host} certificate expires in {days} days")
            elif days < 30:
                record("WARN", "HTTPS", f"{host} certificate expires in {days} days (GitHub normally renews)")
            else:
                record("PASS", "HTTPS", f"{host} certificate valid for {days} more days")
        except Exception as e:
            record(level, "HTTPS", f"{host}: no valid certificate ({type(e).__name__})")

    try:
        fetch(f"http://{DOMAIN}/", follow=False)
        record("WARN", "HTTPS", "http:// is not redirected to https://; tick Enforce HTTPS in GitHub Pages settings")
    except urllib.error.HTTPError as e:
        location = e.headers.get("Location", "")
        if e.code in (301, 302, 308) and location.startswith("https://"):
            record("PASS", "HTTPS", "http:// redirects to https://")
        else:
            record("WARN", "HTTPS", f"http:// returned {e.code} -> {location or 'no redirect'}")
    except Exception as e:
        record("ALERT", "Live site", f"http://{DOMAIN}/ unreachable ({type(e).__name__})")


def check_deploy_matches_github(wait_seconds=0):
    """The live index.html should match index.html on GitHub's main branch.

    After a push, GitHub Pages takes about a minute to redeploy, so retry until wait_seconds."""
    code, _ = run(["/usr/bin/git", "fetch", "-q", "origin"])
    if code != 0:
        record("WARN", "Deployment", "could not fetch from GitHub to compare")
        return
    proc = subprocess.run(["/usr/bin/git", "show", "origin/main:index.html"], cwd=ROOT, capture_output=True)
    if proc.returncode != 0:
        record("WARN", "Deployment", "index.html not found on GitHub main branch")
        return
    target = hashlib.sha256(proc.stdout).digest()  # raw bytes: run() would strip the trailing newline
    deadline = time.time() + wait_seconds
    while True:
        body = None
        for scheme in ("https", "http"):
            try:
                _, _, body = fetch(f"{scheme}://{DOMAIN}/?audit={int(time.time())}")
                break
            except Exception:
                pass
        if body is not None and hashlib.sha256(body).digest() == target or time.time() >= deadline:
            break
        time.sleep(20)
    if body is None:
        record("ALERT", "Deployment", "live site could not be downloaded")
    elif hashlib.sha256(body).digest() == target:
        record("PASS", "Deployment", "live site matches the GitHub main branch")
    else:
        record("ALERT", "Deployment", "live site differs from GitHub main; check the Actions tab for a failed Pages build")


# ------------------------------------------------------------------ publishing

def publish():
    git = "/usr/bin/git"
    code, status = run([git, "status", "--porcelain"])
    if status:
        changed = len(status.splitlines())
        run([git, "add", "-A"])
        code, out = run([git, "commit", "-q", "-m", f"Site update {dt.date.today()} (monthly audit passed)"])
        if code != 0:
            record("ALERT", "Publish", f"commit failed: {out[-300:]}")
            return
        record("PASS", "Publish", f"committed {changed} changed file(s)")
    code, out = run([git, "fetch", "-q", "origin"])
    if code != 0:
        record("ALERT", "Publish", f"fetch failed: {out[-300:]}")
        return
    code, _ = run([git, "merge-base", "--is-ancestor", "origin/main", "HEAD"])
    if code != 0:
        code, out = run([git, "merge", "--no-edit", "-q", "origin/main"])
        if code != 0:
            run([git, "merge", "--abort"])
            record("ALERT", "Publish", "GitHub has edits that conflict with local changes; resolve manually")
            return
    code, ahead = run([git, "rev-list", "--count", "origin/main..HEAD"])
    if ahead.strip() == "0":
        record("PASS", "Publish", "GitHub already up to date; nothing to push")
        return
    global pushed
    code, out = run([git, "push", "-q", "origin", "HEAD:main"], timeout=180)
    if code == 0:
        pushed = True
        record("PASS", "Publish", f"pushed {ahead.strip()} commit(s) to GitHub; site redeploys in about a minute")
    else:
        hint = " (sign in with: ~/.local/bin/gh auth login, then gh auth setup-git)" if "Authentication" in out or "could not read Username" in out else ""
        record("ALERT", "Publish", f"push failed{hint}: {out[-300:]}")


# ---------------------------------------------------------------------- report

def write_report(published):
    order = {"FAIL": 0, "ALERT": 1, "WARN": 2, "PASS": 3}
    counts = {k: sum(1 for r in results if r[0] == k) for k in order}
    now = dt.datetime.now()
    lines = [f"# Site audit {now:%Y-%m-%d %H:%M}", "",
             f"Folder: `{ROOT}`  ",
             f"Site: https://{DOMAIN}/  ",
             f"Mode: {'audit + publish' if published else 'audit only'}", "",
             "| FAIL | ALERT | WARN | PASS |", "|---|---|---|---|",
             f"| {counts['FAIL']} | {counts['ALERT']} | {counts['WARN']} | {counts['PASS']} |", ""]
    if counts["FAIL"]:
        lines += ["**Publishing was blocked.** Fix the FAIL items in the local folder; the next run publishes.", ""]
    lines += ["| Level | Check | Detail |", "|---|---|---|"]
    for level, check, msg in sorted(results, key=lambda r: order[r[0]]):
        lines.append(f"| {level} | {check} | {msg.replace('|', '/')} |")
    report = "\n".join(lines) + "\n"
    out_dir = ROOT / ".audit"
    out_dir.mkdir(exist_ok=True)
    (out_dir / f"{now:%Y-%m-%d}.md").write_text(report)
    (out_dir / "latest.md").write_text(report)
    return counts, out_dir / "latest.md"


def notify(counts):
    if counts["FAIL"] or counts["ALERT"]:
        msg = f"{counts['FAIL']} fail, {counts['ALERT']} alert. See Portfolio/.audit/latest.md"
        title = "Portfolio audit needs attention"
    else:
        msg = f"All clear ({counts['PASS']} passed, {counts['WARN']} warnings)"
        title = "Portfolio audit passed"
    subprocess.run(["/usr/bin/osascript", "-e", f'display notification "{msg}" with title "{title}"'],
                   capture_output=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--publish", action="store_true", help="commit and push if nothing blocking was found")
    ap.add_argument("--offline", action="store_true", help="skip network checks")
    ap.add_argument("--no-notify", action="store_true", help="skip the macOS notification")
    args = ap.parse_args()

    pages = parse_pages()
    check_required_files()
    check_html(pages)
    check_local_links(pages)
    check_text_rules()
    check_files()
    check_resume_freshness()
    if not args.offline:
        check_external_links(pages)
        check_live_site()

    blocked = any(r[0] == "FAIL" for r in results)
    if args.publish and not blocked:
        publish()
    if not args.offline:
        check_deploy_matches_github(wait_seconds=300 if pushed else 0)

    counts, path = write_report(args.publish and not blocked)
    print(path.read_text())
    if not args.no_notify:
        notify(counts)
    return 1 if counts["FAIL"] or counts["ALERT"] else 0


if __name__ == "__main__":
    sys.exit(main())
