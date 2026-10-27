"""Head markup for the web UI: self-hosted IBM Plex faces and the app stylesheet.
The design tokens and component classes live in ui/static/app.css, served from /static.
FONTS_HEAD declares the font faces, and STYLESHEET_HEAD links the stylesheet; both are injected once per page.
"""

FONT_DIR = "/static/fonts"
FONT_FACES = (
    ("IBM Plex Sans", "ibm-plex-sans", 400),
    ("IBM Plex Sans", "ibm-plex-sans", 500),
    ("IBM Plex Sans", "ibm-plex-sans", 600),
    ("IBM Plex Mono", "ibm-plex-mono", 400),
    ("IBM Plex Mono", "ibm-plex-mono", 500),
    ("IBM Plex Mono", "ibm-plex-mono", 600),
)
PRELOAD_FACES = (("ibm-plex-sans", 400), ("ibm-plex-mono", 400))
STYLESHEET = "/static/app.css"


def _font_url(slug: str, weight: int) -> str:
    return f"{FONT_DIR}/{slug}-latin-{weight}-normal.woff2"


_PRELOADS = "".join(
    f'<link rel="preload" href="{_font_url(slug, weight)}" as="font" type="font/woff2" crossorigin>'
    for slug, weight in PRELOAD_FACES
)
_FACE_RULES = "".join(
    f'@font-face {{ font-family: "{family}"; font-style: normal; font-weight: {weight}; '
    f'font-display: swap; src: url("{_font_url(slug, weight)}") format("woff2"); }}'
    for family, slug, weight in FONT_FACES
)
FONTS_HEAD = f"{_PRELOADS}<style>{_FACE_RULES}</style>"
STYLESHEET_HEAD = f'<link rel="stylesheet" href="{STYLESHEET}">'
