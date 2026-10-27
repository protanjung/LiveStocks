"""Head markup for the web UI: self-hosted Bricolage Grotesque and Instrument Sans faces and the app stylesheet.
The design tokens and component classes live in ui/static/app.css, served from /static.
FONTS_HEAD declares the font faces, and STYLESHEET_HEAD links the stylesheet; both are injected once per page.
"""

FONT_DIR = "/static/fonts"
FONT_FACES = (
    ("Bricolage Grotesque", "bricolage-grotesque", 600),
    ("Bricolage Grotesque", "bricolage-grotesque", 700),
    ("Instrument Sans", "instrument-sans", 400),
    ("Instrument Sans", "instrument-sans", 500),
    ("Instrument Sans", "instrument-sans", 600),
)
PRELOAD_FACES = (("instrument-sans", 400), ("bricolage-grotesque", 700))
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
