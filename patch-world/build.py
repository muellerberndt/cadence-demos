"""Build index.html from page.html with core.js inlined at the CORE marker.

python3 build.py
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent
MARKER = "<!-- CORE -->"


def main():
    page = (ROOT / "page.html").read_text()
    core = (ROOT / "core.js").read_text()
    if MARKER not in page:
        raise SystemExit("page.html has no CORE marker")
    out = page.replace(MARKER, "<script>\n" + core + "</script>")
    (ROOT / "index.html").write_text(out)
    print(f"wrote {ROOT / 'index.html'} ({len(out)} bytes)")


if __name__ == "__main__":
    main()
