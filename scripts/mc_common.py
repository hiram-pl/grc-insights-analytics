"""
mc_common.py
Helpers shared by aggregate_mailchimp.py (account export) and pull_mailchimp.py (API),
so both paths clean URLs and check for emails the same way.
"""

import re
from pathlib import Path
from urllib.parse import urlsplit

EMAIL = re.compile(r"[^@\s,;:<>\"']+@[^@\s,;:<>\"']+\.[a-z]{2,}", re.I)


def redact(value):
    """Replace any email address in a text value with [email]; leave non-text unchanged."""
    return EMAIL.sub("[email]", value) if isinstance(value, str) else value


def slugify(title):
    """Mailchimp's export file-name rule: lowercase, runs of non-alphanumerics -> '-'.
    Mirrors regexp_replace(lower(Title), '[^a-z0-9]+', '-', 'g') in build_db.py."""
    return re.sub(r"[^a-z0-9]+", "-", str(title).lower())


def clean_url(url):
    """URL -> (domain, path) with query strings dropped.
    Links that carry an email address (mailto:, or malformed http://name@domain where the
    address lands in the host) become ('email link', '')."""
    p = urlsplit(url or "")
    if p.scheme == "mailto" or "@" in p.netloc or EMAIL.search(p.path):
        return "email link", ""
    return p.netloc.lower().removeprefix("www.") or p.scheme, p.path


def assert_no_emails(folder):
    """Stop if any CSV in folder contains an email address. Never weaken or skip this."""
    for f in Path(folder).glob("*.csv"):
        text = f.read_text(errors="ignore")
        assert not EMAIL.search(text), f"Email address found in {f.name}; do not share it."
