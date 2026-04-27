"""PubMed-backed literature review tools.

Mirrors the DISCOVERY_OPS pattern in services/discovery.py — a small registry of
named ops the literature_agent calls, each returning a JSON-serializable dict with
`{ok, ...}` or `{ok: false, error}` so the agent can self-correct.

PubMed E-utilities (esearch + efetch) are free and key-less. The base URL and
defaults are conservative; if NCBI rate-limits the host, set a NCBI API key in
config later — for now the no-auth path is enough.
"""

from __future__ import annotations

import functools
import xml.etree.ElementTree as ET
from typing import Any

import requests


PUBMED_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
DEFAULT_TIMEOUT = 30
DEFAULT_SEARCH_LIMIT = 10
MAX_SEARCH_LIMIT = 30
MAX_FETCH_BATCH = 25


# ---------- esearch / efetch ----------


@functools.lru_cache(maxsize=128)
def _cached_esearch(query: str, retmax: int) -> list[str]:
    r = requests.get(
        f"{PUBMED_BASE}/esearch.fcgi",
        params={
            "db": "pubmed",
            "term": query,
            "retmax": retmax,
            "retmode": "json",
            "sort": "relevance",
        },
        timeout=DEFAULT_TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    return list(data.get("esearchresult", {}).get("idlist", []))


@functools.lru_cache(maxsize=128)
def _cached_efetch(pmids_csv: str) -> str:
    r = requests.get(
        f"{PUBMED_BASE}/efetch.fcgi",
        params={"db": "pubmed", "id": pmids_csv, "retmode": "xml"},
        timeout=DEFAULT_TIMEOUT,
    )
    r.raise_for_status()
    return r.text


def _parse_articles(xml_text: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    articles: list[dict[str, Any]] = []
    for art in root.findall(".//PubmedArticle"):
        pmid = (art.findtext(".//PMID") or "").strip()

        title = (art.findtext(".//ArticleTitle") or "").strip()

        # Abstract is often split into AbstractText elements with @Label
        abstract_parts: list[str] = []
        for at in art.findall(".//Abstract/AbstractText"):
            label = at.attrib.get("Label")
            text = "".join(at.itertext()).strip()
            if not text:
                continue
            abstract_parts.append(f"{label}: {text}" if label else text)
        abstract = "\n".join(abstract_parts)

        authors: list[str] = []
        for au in art.findall(".//AuthorList/Author"):
            last = (au.findtext("LastName") or "").strip()
            init = (au.findtext("Initials") or "").strip()
            full = f"{last} {init}".strip()
            if full:
                authors.append(full)

        journal = (art.findtext(".//Journal/Title") or "").strip()
        year = (art.findtext(".//JournalIssue/PubDate/Year")
                or art.findtext(".//JournalIssue/PubDate/MedlineDate")
                or "").strip()[:4]

        doi = ""
        for aid in art.findall(".//ArticleIdList/ArticleId"):
            if aid.attrib.get("IdType") == "doi":
                doi = (aid.text or "").strip()
                break

        articles.append({
            "pmid": pmid,
            "title": title,
            "abstract": abstract,
            "authors": authors[:8],
            "journal": journal,
            "year": year,
            "doi": doi,
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
        })
    return articles


# ---------- Public ops (called by the agent via apply_literature_op) ----------


def search_pubmed(query: str, limit: int = DEFAULT_SEARCH_LIMIT) -> dict:
    """Full-text search PubMed; returns a list of pmids ranked by relevance."""
    capped = max(1, min(int(limit), MAX_SEARCH_LIMIT))
    pmids = _cached_esearch(query, capped)
    return {"ok": True, "query": query, "n_results": len(pmids), "pmids": pmids}


def fetch_pubmed(pmids: list[str]) -> dict:
    """Fetch full article metadata + abstracts for up to 25 pmids in one batch."""
    if not isinstance(pmids, list) or not pmids:
        return {"ok": False, "error": "fetch_pubmed requires a non-empty pmids list"}
    capped = pmids[:MAX_FETCH_BATCH]
    csv = ",".join(str(p) for p in capped)
    try:
        xml = _cached_efetch(csv)
        articles = _parse_articles(xml)
    except ET.ParseError as e:
        return {"ok": False, "error": f"Could not parse PubMed XML: {e}"}
    return {"ok": True, "n_articles": len(articles), "articles": articles}


LITERATURE_OPS = {
    "search_pubmed": search_pubmed,
    "fetch_pubmed": fetch_pubmed,
}

LITERATURE_OPS_DOC = """Literature review ops (PubMed E-utilities):
- search_pubmed(query, limit=10)
    # PubMed full-text search. Returns ranked pmids. limit cap = 30.
    # Use specific MeSH-style queries: "covid-19 vaccine effectiveness elderly"
    # rather than vague "covid". Quote multi-word phrases sparingly — PubMed's
    # default OR-boolean usually finds more relevant results.
- fetch_pubmed(pmids)
    # Fetch full metadata + abstracts for a list of pmids (cap 25 per call).
    # Returns {articles: [{pmid, title, abstract, authors, journal, year, doi, url}]}
"""


def apply_literature_op(op_spec: dict) -> dict:
    """op_spec = {'op': name, 'args': {...}}"""
    name = op_spec["op"]
    fn = LITERATURE_OPS.get(name)
    if not fn:
        return {"ok": False, "error": f"Unknown op '{name}'"}
    try:
        return fn(**op_spec.get("args", {}))
    except requests.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
