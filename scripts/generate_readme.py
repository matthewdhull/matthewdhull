#!/usr/bin/env python3
"""
Generate README.md from a simple YAML list of projects.

Usage:
  python scripts/generate_readme.py > README.md

Env vars:
  GITHUB_TOKEN (optional) - to fetch fresh star counts.
"""

from __future__ import annotations

import os
import sys
import textwrap
import typing as t

try:
    import yaml  # type: ignore
except Exception as e:  # pragma: no cover
    print("Missing dependency: pyyaml. Install with `pip install pyyaml requests`.", file=sys.stderr)
    raise

import json
import requests


OWNER_DEFAULT = os.environ.get("GITHUB_OWNER", "matthewdhull")
TOKEN = os.environ.get("GITHUB_TOKEN")
HEADERS = {"Accept": "application/vnd.github+json"}
if TOKEN:
    HEADERS["Authorization"] = f"Bearer {TOKEN}"


def read_projects(path: str) -> list[dict[str, t.Any]]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, list):
        raise ValueError("projects.yml must be a list")
    return data


def parse_repo(repo: str) -> tuple[str, str]:
    if "/" in repo:
        owner, name = repo.split("/", 1)
    else:
        owner, name = OWNER_DEFAULT, repo
    return owner, name


def get_star_count(repo: str) -> int | None:
    owner, name = parse_repo(repo)
    url = f"https://api.github.com/repos/{owner}/{name}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            return int(r.json().get("stargazers_count", 0))
        else:
            # On error (rate limit, 404, etc.), skip stars gracefully
            return None
    except Exception:
        return None


def html_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def render_cell(p: dict[str, t.Any], width_px: int = 220, desc_height: int | None = None) -> str:
    name = html_escape(p.get("name", ""))
    repo = p.get("repo", "")
    owner, repo_name = parse_repo(repo)
    repo_url = f"https://github.com/{owner}/{repo_name}" if repo else "#"
    teaser = p.get("teaser")
    description = html_escape(p.get("description", ""))
    homepage = p.get("homepage")
    paper = p.get("paper")
    video = p.get("video")

    # Fetch stars once per cell (optional)
    stars = get_star_count(repo) if repo else None
    stars_badge = (
        f'<a href="{repo_url}/stargazers" title="GitHub Stars">{stars}</a>'
        if stars is not None
        else (f'<a href="{repo_url}/stargazers" title="GitHub Stars"></a>' if repo else "")
    )

    # Helpers to render theme-aware icons from local assets
    def icon_picture(name: str, size: int) -> str:
        # Prefer files in ./assets/ (user repo layout). Fallback gracefully.
        light = f'./assets/icon-{name}-light.svg'
        dark = f'./assets/icon-{name}-dark.svg'
        # If the light variant does not exist, use dark for both to avoid broken icons
        light_fs = light[2:]
        dark_fs = dark[2:]
        if not os.path.exists(light_fs) and os.path.exists(dark_fs):
            light = dark
        # Fallback src uses light version
        return (
            f"<picture>\n"
            f"  <source media=\"(prefers-color-scheme: light)\" srcset=\"{light}\" />\n"
            f"  <source media=\"(prefers-color-scheme: dark)\" srcset=\"{dark}\" />\n"
            f"  <img src=\"{light}\" width=\"{size}px\" height=\"{size}px\" />\n"
            f"</picture>"
        )

    demo_icon = icon_picture("demo", 18)
    pdf_icon = icon_picture("pdf", 18)
    yt_icon = icon_picture("youtube", 18)
    star_icon = icon_picture("star", 18)

    # Build icon row: only present icons left-to-right plus a final star cell.
    def small_cell(html: str) -> str:
        return f'<td align="center" valign="middle" width="40">{html}</td>'

    icon_cells: list[str] = []
    if homepage:
        icon_cells.append(small_cell(f'<a href="{homepage}" title="Project">{demo_icon}</a>'))
    if paper:
        icon_cells.append(small_cell(f'<a href="{paper}" title="Paper">{pdf_icon}</a>'))
    if video:
        icon_cells.append(small_cell(f'<a href="{video}" title="Video">{yt_icon}</a>'))

    # Star icon + number; include when repo exists
    star_html = (
        f'<a href="{repo_url}/stargazers" title="GitHub Stars">{star_icon}</a>' + (f'&nbsp;{stars}' if stars is not None else '')
        if repo
        else ''
    )
    icon_cells.append(f'<td align="left" valign="middle">{star_html}</td>')

    icons_html = "\n                ".join(icon_cells)

    # Inner structure
    teaser_html = (
        f'<a href="{repo_url}"><img src="{teaser}" width="{width_px}px"/></a>'
        if teaser
        else ""
    )

    title_line = f'<a href="{repo_url}"><strong>{name}</strong></a>: {description}'
    height_attr = f' height=\"{desc_height}\"' if desc_height else ''

    cell = f"""
    <td>
      <table>
        <tr>
          <td>
            {teaser_html}
          </td>
        </tr>
        <tr>
          <td width=\"{width_px}px\"{height_attr} valign=\"top\">{title_line}</td>
        </tr>
        <tr>
          <td>
            <table width=\"{width_px - 2}px\" cellpadding=\"0\" cellspacing=\"0\">
              <tr>
                {icons_html}
              </tr>
            </table>
          </td>
        </tr>
      </table>
    </td>
    """.strip()
    return textwrap.dedent(cell)


def chunk(seq: list[t.Any], n: int) -> list[list[t.Any]]:
    return [seq[i : i + n] for i in range(0, len(seq), n)]


def render_grid(projects: list[dict[str, t.Any]], columns: int = 3) -> str:
    parts = []
    for group in chunk(projects, columns):
        # Estimate rows of text for each description to normalize card heights per row
        def est_lines(p: dict[str, t.Any]) -> int:
            name = str(p.get("name", ""))
            desc = str(p.get("description", ""))
            text = f"{name}: {desc}"
            # Roughly 42 chars fit per line at this width/font size
            per_line = 42
            lines = (len(text) + per_line - 1) // per_line
            return max(1, min(lines, 6))  # clamp to a reasonable range

        max_lines = max(est_lines(p) for p in group) if group else 1
        # Approx line height ~ 26px + small padding
        desc_height = 26 * max_lines + 10

        cells = "\n      ".join(render_cell(p, desc_height=desc_height) for p in group)
        parts.append(
            f"""
<table width=\"100%\" cellpadding=\"0\" cellspacing=\"0\">
  <tr>
      {cells}
  </tr>
</table>
            """.strip()
        )
    return "\n\n".join(parts)


def render_header() -> str:
    # Minimal, editable intro header. You can modify templates/README_intro.md if you want.
    return textwrap.dedent(
        """
        ## Hi There!

        I'm <a href="https://sites.gatech.edu/matthewhull">Matthew Hull</a>, an ML PhD student at Georgia Tech. This is a curated list of my open-source projects, research, and demos. 

        My research focuses on adversarial machine learning and simulation using differentiable rendering.
        
        Please reach out if you have any questions or want to chat!
        """
    ).strip()


def build_readme(projects: list[dict[str, t.Any]]) -> str:
    header = render_header()
    grid = render_grid(projects)
    return f"""{header}

{grid}
""".rstrip() + "\n"


def main() -> None:
    projects = read_projects(os.path.join("data", "projects.yml"))
    content = build_readme(projects)
    sys.stdout.write(content)


if __name__ == "__main__":
    main()
