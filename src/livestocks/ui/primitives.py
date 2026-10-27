"""Shared HTML fragments for the web UI: cards, breadcrumbs, empty states, page titles and table headers.
Every builder escapes the text it is given, so callers pass plain strings for titles, labels and messages.
Only the body argument of card and empty_card is trusted markup, and it must come from a builder in ui/.
"""

from html import escape


def card(
    title: str,
    body: str,
    sub: str | None = None,
    label: str | None = None,
    padded: bool = True,
) -> str:
    """Return a titled card around trusted body markup, with an optional subtitle and accessible name.
    The title, subtitle and label are escaped; padded wraps the body in the standard card padding.
    Use padded=False for a full-bleed table that should sit flush with the card edges.
    """
    aria = f' aria-label="{escape(label)}"' if label else ""
    sub_html = f'<span class="sub">{escape(sub)}</span>' if sub else ""
    content = f'<div class="card-body">{body}</div>' if padded else body
    return (
        f'<section class="card"{aria}><div class="card-head"><h2>{escape(title)}</h2>{sub_html}</div>'
        f"{content}</section>"
    )


def crumb(*parts: tuple[str, str | None]) -> str:
    """Return a breadcrumb trail where each part is a (label, href) pair.
    A part with no href is the current page and gets aria-current; the trail sits in a labelled nav.
    Labels are escaped, and the separators are hidden from assistive technology.
    """
    items: list[str] = []
    for index, (label, href) in enumerate(parts):
        if index:
            items.append('<span aria-hidden="true">/</span>')
        if href is None:
            items.append(f'<span aria-current="page">{escape(label)}</span>')
        else:
            items.append(f'<a href="{escape(href)}">{escape(label)}</a>')
    return f'<nav class="crumb" aria-label="Breadcrumb">{"".join(items)}</nav>'


def page_title(title: str, sub: str | None = None) -> str:
    """Return the page heading with its optional muted subtitle.
    The heading is the page's only h1, so each page should render exactly one.
    Both strings are escaped.
    """
    sub_html = f'<span class="sub">{escape(sub)}</span>' if sub else ""
    return f'<div class="page-title"><h1>{escape(title)}</h1>{sub_html}</div>'


def empty_card(title: str, text: str, action: str | None = None) -> str:
    """Return the centred message card shown when there is nothing to display.
    The title and text are escaped; action is optional trusted markup such as a link button.
    Empty states always explain why the area is empty.
    """
    action_html = action or ""
    return (
        f'<section class="card empty"><h3>{escape(title)}</h3>'
        f"<p>{escape(text)}</p>{action_html}</section>"
    )


def th(label: str, scope: str = "col", classes: str = "") -> str:
    """Return a table header cell with its scope set for assistive technology.
    Row headers use scope="row" and column headers scope="col", the default.
    The label is escaped and classes is a space-separated list of extra classes.
    """
    cls = f' class="{escape(classes)}"' if classes else ""
    return f'<th scope="{escape(scope)}"{cls}>{escape(label)}</th>'


def trunc(text: str) -> str:
    """Return a single-line span that is cut with an ellipsis, with the full text in a tooltip.
    Long company names use it so a table column stays narrow without hiding the full name.
    The text is escaped in both the content and the title attribute.
    """
    safe = escape(text)
    return f'<span class="trunc" title="{safe}">{safe}</span>'
