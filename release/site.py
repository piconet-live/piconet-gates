#!/usr/bin/env python3
"""site.py PATCH-NOTES VERSION SETUP REPO_URL SITE: the site's notes page and download link for one release.

Writes SITE/src/content/notes/X-Y-Z.md (the version's section of PATCH-NOTES.md, with the frontmatter the site's
notes collection takes) and SITE/src/data/release.json (the GitHub link to SETUP, its size and SHA-256). The summary
and highlights are the first sentences of the notes' first bullets, one section after another: a draft to read.
"""
import datetime, hashlib, json, os, re, sys

path, version, setup, repo, site = sys.argv[1:]
lines = open(path, encoding="utf-8").read().split("\n")
head = re.compile(r"^## Version " + re.escape(version) + r" .*\((\d+ \w+ \d{4})\)\s*$")
start = next((i for i, l in enumerate(lines) if head.match(l)), None)
if start is None:
    sys.exit(f'release: {path} has no heading "## Version {version} · build ... (D Month YYYY)"')
date = datetime.datetime.strptime(head.match(lines[start]).group(1), "%d %B %Y").date().isoformat()
end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
body = "\n".join(lines[start + 1:end]).strip()

# the bullets of each "### " section, "### Details" and its "#### " parts left out
sections, cur = [], None
for l in body.split("\n"):
    if l.startswith("### Details") or l.startswith("#### "):
        cur = None
    elif l.startswith("### "):
        cur = []
        sections.append(cur)
    elif cur is not None and l.startswith("- "):
        cur.append(l[2:])
    elif cur is not None and cur and l.startswith("  "):
        cur[-1] += " " + l.strip()

def sentence(text):   # the bullet's first sentence, bold marks left out
    text = " ".join(text.replace("**", "").split())
    return re.split(r"(?<=\.)\s", text, maxsplit=1)[0].rstrip(".") + "."

picks = []
for row in range(4):
    picks += [sentence(s[row]) for s in sections if row < len(s)]
picks = picks[:4]
if not picks:
    sys.exit(f"release: the section of {version} in {path} has no bullets to take highlights from")

x, y = (int(n) for n in version.split(".")[1:3])
q = lambda t: json.dumps(t, ensure_ascii=False)
page = os.path.join(site, "src/content/notes", version.replace(".", "-") + ".md")
if os.path.exists(page):   # a page written already may have been edited by hand: a run again keeps it
    said = "kept, as it is there already (remove it to write it again)"
else:
    said = "written"
    with open(page, "w", encoding="utf-8") as f:
        f.write(f"---\nversion: {q(version)}\ndate: {q(date)}\norder: {x * 100 + y}\nsummary: {q(' '.join(picks[:2]))}\nhighlights:\n")
        f.writelines(f"  - {q(h)}\n" for h in picks)
        f.write("---\n" + body + "\n")

release = {"version": version, "date": date,
           "url": f"{repo}/releases/download/v{version}/{os.path.basename(setup)}",
           "size": f"{round(os.path.getsize(setup) / 2**20)} MB",
           "sha256": hashlib.sha256(open(setup, "rb").read()).hexdigest()}
with open(os.path.join(site, "src/data/release.json"), "w", encoding="utf-8") as f:
    f.write(json.dumps(release, indent=2) + "\n")
print(f"site: notes page {said}: {page}")
print(f"site: download: {release['url']} ({release['size']}, {release['sha256']})")
