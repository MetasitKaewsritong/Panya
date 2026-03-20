import hashlib
import logging
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse

from app.config import config
from app.db import get_db_pool

router = APIRouter(prefix="/api/document-pages", tags=["documents"])
logger = logging.getLogger(__name__)

_BASENAME_SQL = "regexp_replace(document_source, '^.*/', '')"
_VIEWER_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Manual Page Viewer</title>
  <style>
    :root {
      --bg: #f4f0e8;
      --panel: rgba(255, 252, 246, 0.96);
      --panel-border: rgba(50, 44, 34, 0.08);
      --ink: #2f2922;
      --muted: #6f6658;
      --accent: #b55e2a;
      --accent-soft: rgba(181, 94, 42, 0.12);
      --shadow: 0 18px 40px rgba(54, 43, 25, 0.12);
      --content-width: min(1280px, calc(100vw - 32px));
      color-scheme: light;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      min-height: 100vh;
      background:
        radial-gradient(circle at top left, rgba(181, 94, 42, 0.12), transparent 30%),
        radial-gradient(circle at top right, rgba(33, 121, 110, 0.10), transparent 28%),
        linear-gradient(180deg, #f8f4ee 0%, #efe7dc 100%);
      color: var(--ink);
    }

    .shell {
      width: 100%;
      min-height: 100vh;
      padding: 16px;
    }

    .app {
      width: var(--content-width);
      margin: 0 auto;
      display: grid;
      gap: 16px;
    }

    .toolbar {
      position: sticky;
      top: 16px;
      z-index: 10;
      display: grid;
      gap: 14px;
      padding: 18px 20px;
      border: 1px solid var(--panel-border);
      border-radius: 24px;
      background: var(--panel);
      box-shadow: var(--shadow);
      backdrop-filter: blur(18px);
    }

    .toolbar-head {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 16px;
    }

    .title-block {
      min-width: 0;
    }

    .eyebrow {
      margin: 0 0 6px;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--accent);
    }

    .title {
      margin: 0;
      font-size: clamp(20px, 3vw, 30px);
      line-height: 1.08;
      font-weight: 700;
      word-break: break-word;
    }

    .subtitle {
      margin: 6px 0 0;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.5;
    }

    .badge {
      padding: 8px 12px;
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent);
      font-size: 12px;
      font-weight: 700;
      white-space: nowrap;
    }

    .controls {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 10px;
    }

    .btn,
    .page-chip,
    .raw-link {
      border: 1px solid transparent;
      border-radius: 999px;
      background: #fff;
      color: var(--ink);
      padding: 10px 14px;
      font: inherit;
      font-size: 14px;
      font-weight: 600;
      text-decoration: none;
      cursor: pointer;
      transition: transform 120ms ease, border-color 120ms ease, background-color 120ms ease, color 120ms ease;
    }

    .btn:hover,
    .page-chip:hover,
    .raw-link:hover {
      transform: translateY(-1px);
      border-color: rgba(181, 94, 42, 0.25);
    }

    .btn:disabled {
      cursor: not-allowed;
      opacity: 0.45;
      transform: none;
    }

    .btn-primary {
      background: var(--accent);
      color: #fff8f1;
    }

    .page-form {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 6px 8px 6px 14px;
      border-radius: 999px;
      background: #fff;
      border: 1px solid rgba(50, 44, 34, 0.10);
    }

    .page-label {
      color: var(--muted);
      font-size: 13px;
      font-weight: 600;
    }

    .page-input {
      width: 82px;
      border: 0;
      border-radius: 12px;
      background: rgba(111, 102, 88, 0.08);
      color: var(--ink);
      padding: 10px 12px;
      font: inherit;
      font-size: 14px;
      font-weight: 600;
      outline: none;
      text-align: center;
    }

    .status {
      min-height: 20px;
      font-size: 13px;
      color: var(--muted);
    }

    .pager {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .page-chip {
      padding: 8px 12px;
      font-size: 13px;
    }

    .page-chip.is-active {
      background: var(--accent-soft);
      color: var(--accent);
      border-color: rgba(181, 94, 42, 0.2);
    }

    .viewer {
      border: 1px solid var(--panel-border);
      border-radius: 28px;
      background: rgba(255, 255, 255, 0.72);
      box-shadow: var(--shadow);
      overflow: hidden;
    }

    .stage {
      position: relative;
      min-height: min(75vh, 960px);
      display: grid;
      place-items: center;
      padding: 18px;
      background:
        linear-gradient(180deg, rgba(234, 229, 222, 0.9), rgba(246, 243, 239, 0.95)),
        repeating-linear-gradient(
          135deg,
          rgba(87, 70, 42, 0.025),
          rgba(87, 70, 42, 0.025) 12px,
          rgba(255, 255, 255, 0) 12px,
          rgba(255, 255, 255, 0) 24px
        );
    }

    .page-card {
      width: min(100%, 1040px);
      background: #fff;
      border-radius: 18px;
      padding: clamp(10px, 2vw, 18px);
      box-shadow: 0 20px 44px rgba(56, 42, 17, 0.14);
    }

    .page-image {
      display: block;
      width: 100%;
      height: auto;
      border-radius: 10px;
      background: #fff;
    }

    .placeholder,
    .error-box {
      max-width: 680px;
      padding: 28px;
      border-radius: 22px;
      background: rgba(255, 251, 245, 0.95);
      border: 1px solid rgba(50, 44, 34, 0.08);
      text-align: center;
      box-shadow: 0 16px 40px rgba(56, 42, 17, 0.10);
    }

    .placeholder strong,
    .error-box strong {
      display: block;
      margin-bottom: 10px;
      font-size: 18px;
    }

    .placeholder p,
    .error-box p {
      margin: 0;
      color: var(--muted);
      line-height: 1.6;
    }

    .loading {
      position: absolute;
      inset: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      pointer-events: none;
    }

    .loading[hidden] {
      display: none;
    }

    .spinner {
      width: 52px;
      height: 52px;
      border-radius: 50%;
      border: 4px solid rgba(181, 94, 42, 0.15);
      border-top-color: var(--accent);
      animation: spin 0.85s linear infinite;
    }

    @keyframes spin {
      to { transform: rotate(360deg); }
    }

    @media (max-width: 760px) {
      .shell {
        padding: 10px;
      }

      .toolbar {
        top: 10px;
        border-radius: 20px;
        padding: 16px;
      }

      .toolbar-head {
        flex-direction: column;
      }

      .controls {
        align-items: stretch;
      }

      .page-form {
        width: 100%;
        justify-content: space-between;
      }

      .page-input {
        width: 92px;
      }

      .viewer {
        border-radius: 22px;
      }
    }
  </style>
</head>
<body>
  <div class="shell">
    <div class="app">
      <section class="toolbar">
        <div class="toolbar-head">
          <div class="title-block">
            <p class="eyebrow">Database Page Viewer</p>
            <h1 id="doc-title" class="title">Loading manual page...</h1>
            <p id="doc-subtitle" class="subtitle">Reading page images from the <code>pdf_pages</code> table.</p>
          </div>
          <div id="doc-badge" class="badge" hidden>Ready</div>
        </div>

        <div class="controls">
          <button id="prev-btn" class="btn" type="button">Previous</button>
          <form id="page-form" class="page-form">
            <span class="page-label">Page</span>
            <input id="page-input" class="page-input" type="number" min="1" step="1" value="1" inputmode="numeric" />
            <button class="btn btn-primary" type="submit">Go</button>
          </form>
          <button id="next-btn" class="btn" type="button">Next</button>
          <a id="raw-link" class="raw-link" href="#" target="_blank" rel="noopener noreferrer">Open Raw PDF</a>
        </div>

        <div id="status" class="status">Resolving document...</div>
        <div id="pager" class="pager"></div>
      </section>

      <section class="viewer">
        <div class="stage">
          <div id="placeholder" class="placeholder">
            <strong>Preparing the page viewer</strong>
            <p>The viewer is locating the requested document inside the database and loading the rendered page image.</p>
          </div>

          <div id="error-box" class="error-box" hidden>
            <strong>Could not load this document page</strong>
            <p id="error-text">The viewer could not locate the requested page image.</p>
          </div>

          <div id="page-card" class="page-card" hidden>
            <img id="page-image" class="page-image" alt="Manual page" decoding="async" />
          </div>

          <div id="loading" class="loading" hidden>
            <div class="spinner" aria-hidden="true"></div>
          </div>
        </div>
      </section>
    </div>
  </div>

  <script>
    const query = new URLSearchParams(window.location.search);
    const state = {
      manifest: null,
      currentPage: 1,
      requestedPage: parsePositiveInt(query.get("page"), 1),
      pageSet: new Set(),
    };

    const titleEl = document.getElementById("doc-title");
    const subtitleEl = document.getElementById("doc-subtitle");
    const badgeEl = document.getElementById("doc-badge");
    const statusEl = document.getElementById("status");
    const pagerEl = document.getElementById("pager");
    const pageInputEl = document.getElementById("page-input");
    const prevBtnEl = document.getElementById("prev-btn");
    const nextBtnEl = document.getElementById("next-btn");
    const rawLinkEl = document.getElementById("raw-link");
    const placeholderEl = document.getElementById("placeholder");
    const errorBoxEl = document.getElementById("error-box");
    const errorTextEl = document.getElementById("error-text");
    const pageCardEl = document.getElementById("page-card");
    const pageImageEl = document.getElementById("page-image");
    const loadingEl = document.getElementById("loading");

    function parsePositiveInt(value, fallback) {
      const parsed = Number.parseInt(value || "", 10);
      return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
    }

    function setLoading(isLoading) {
      loadingEl.hidden = !isLoading;
    }

    function setStatus(text) {
      statusEl.textContent = text || "";
    }

    function buildApiUrl(path, extraParams = {}) {
      const url = new URL(path, window.location.origin);
      for (const key of ["source_id", "source", "collection"]) {
        const value = query.get(key);
        if (value) {
          url.searchParams.set(key, value);
        }
      }
      for (const [key, value] of Object.entries(extraParams)) {
        if (value !== null && value !== undefined && value !== "") {
          url.searchParams.set(key, String(value));
        }
      }
      return url.toString();
    }

    function buildViewerUrl(page) {
      const url = new URL(window.location.href);
      url.searchParams.set("page", String(page));
      return url.toString();
    }

    function resolvePage(requestedPage, pages, minPage, maxPage) {
      if (!Array.isArray(pages) || pages.length === 0) {
        return parsePositiveInt(requestedPage, Math.max(1, minPage || 1));
      }

      if (pages.includes(requestedPage)) {
        return requestedPage;
      }

      let nearestPage = pages[0];
      let nearestDistance = Math.abs(nearestPage - requestedPage);
      for (const page of pages) {
        const distance = Math.abs(page - requestedPage);
        if (distance < nearestDistance) {
          nearestPage = page;
          nearestDistance = distance;
        }
      }

      if (requestedPage < minPage) return pages[0];
      if (requestedPage > maxPage) return pages[pages.length - 1];
      return nearestPage;
    }

    function getVisiblePages(currentPage, pages) {
      if (!Array.isArray(pages) || pages.length === 0) {
        return [];
      }

      if (pages.length <= 9) {
        return pages;
      }

      const index = pages.indexOf(currentPage);
      const start = Math.max(0, index - 2);
      const end = Math.min(pages.length, index + 3);
      const windowPages = pages.slice(start, end);

      if (start > 0) {
        windowPages.unshift(pages[0]);
      }
      if (start > 1) {
        windowPages.splice(1, 0, null);
      }
      if (end < pages.length - 1) {
        windowPages.push(null);
      }
      if (end < pages.length) {
        windowPages.push(pages[pages.length - 1]);
      }

      return windowPages;
    }

    function updatePager() {
      pagerEl.textContent = "";
      if (!state.manifest || !Array.isArray(state.manifest.pages) || state.manifest.pages.length === 0) {
        return;
      }

      for (const page of getVisiblePages(state.currentPage, state.manifest.pages)) {
        if (page === null) {
          const spacer = document.createElement("span");
          spacer.className = "page-chip";
          spacer.textContent = "...";
          spacer.style.cursor = "default";
          spacer.style.opacity = "0.6";
          pagerEl.appendChild(spacer);
          continue;
        }

        const link = document.createElement("a");
        link.className = "page-chip" + (page === state.currentPage ? " is-active" : "");
        link.href = buildViewerUrl(page);
        link.textContent = "Page " + page;
        link.addEventListener("click", (event) => {
          event.preventDefault();
          loadPage(page);
        });
        pagerEl.appendChild(link);
      }
    }

    function updateControls() {
      if (!state.manifest) {
        prevBtnEl.disabled = true;
        nextBtnEl.disabled = true;
        return;
      }

      pageInputEl.value = String(state.currentPage);
      pageInputEl.min = String(state.manifest.min_page || 1);
      pageInputEl.max = String(state.manifest.max_page || state.manifest.page_count || state.currentPage);
      prevBtnEl.disabled = !state.pageSet.has(state.currentPage - 1);
      nextBtnEl.disabled = !state.pageSet.has(state.currentPage + 1);
    }

    function updateMetadata() {
      if (!state.manifest) {
        return;
      }

      const metaParts = [];
      if (state.manifest.brand) metaParts.push(state.manifest.brand);
      if (state.manifest.model_subbrand) metaParts.push(state.manifest.model_subbrand);
      metaParts.push(state.manifest.page_count + " stored page images");

      titleEl.textContent = state.manifest.source || state.manifest.source_id;
      subtitleEl.textContent = metaParts.join(" | ");
      badgeEl.hidden = false;
      badgeEl.textContent = state.currentPage + " / " + state.manifest.max_page;
      rawLinkEl.href = state.manifest.raw_document_url || "#";
    }

    function showError(message) {
      setLoading(false);
      placeholderEl.hidden = true;
      pageCardEl.hidden = true;
      errorBoxEl.hidden = false;
      errorTextEl.textContent = message || "The requested page could not be loaded.";
      setStatus(message || "The requested page could not be loaded.");
      badgeEl.hidden = true;
    }

    function buildImageUrl(page) {
      return buildApiUrl("/api/document-pages/image", { page });
    }

    function prefetchNearbyPages(currentPage) {
      for (const page of [currentPage - 1, currentPage + 1]) {
        if (!state.pageSet.has(page)) {
          continue;
        }
        const prefetchImg = new Image();
        prefetchImg.src = buildImageUrl(page);
      }
    }

    async function loadManifest() {
      const sourceId = query.get("source_id");
      const sourceName = query.get("source");
      if (!sourceId && !sourceName) {
        throw new Error("Missing source_id or source query parameter.");
      }

      const response = await fetch(buildApiUrl("/api/document-pages/manifest"), {
        headers: { "Accept": "application/json" },
      });
      if (!response.ok) {
        let detail = "The document manifest could not be loaded.";
        try {
          const payload = await response.json();
          detail = payload.detail || detail;
        } catch (_error) {
          // Ignore invalid JSON.
        }
        throw new Error(detail);
      }

      const manifest = await response.json();
      state.manifest = manifest;
      state.pageSet = new Set(Array.isArray(manifest.pages) ? manifest.pages : []);
      const initialPage = resolvePage(state.requestedPage, manifest.pages, manifest.min_page, manifest.max_page);
      state.currentPage = initialPage;
      updateMetadata();
      updateControls();
      updatePager();
      if (state.requestedPage !== initialPage) {
        setStatus("Page " + state.requestedPage + " was not stored, so the closest available page was loaded instead.");
      } else {
        setStatus("Loaded page " + initialPage + " from the database.");
      }
    }

    async function loadPage(page) {
      if (!state.manifest) {
        return;
      }

      if (!state.pageSet.has(page)) {
        showError("Page " + page + " is not available in the database for this document.");
        return;
      }

      setLoading(true);
      errorBoxEl.hidden = true;
      placeholderEl.hidden = true;
      pageCardEl.hidden = false;
      setStatus("Loading page " + page + " from the database...");

      try {
        const imageUrl = buildImageUrl(page);
        await new Promise((resolve, reject) => {
          pageImageEl.onload = () => resolve();
          pageImageEl.onerror = () => reject(new Error("The page image could not be decoded."));
          pageImageEl.src = imageUrl;
        });

        state.currentPage = page;
        updateMetadata();
        updateControls();
        updatePager();
        window.history.replaceState({}, "", buildViewerUrl(page));
        pageImageEl.alt = (state.manifest.source || "Manual page") + " - Page " + page;
        setStatus("Showing page " + page + " from " + state.manifest.source + ".");
        prefetchNearbyPages(page);
      } catch (error) {
        showError(error.message || "The page image could not be loaded.");
      } finally {
        setLoading(false);
      }
    }

    prevBtnEl.addEventListener("click", () => {
      if (!prevBtnEl.disabled) {
        loadPage(state.currentPage - 1);
      }
    });

    nextBtnEl.addEventListener("click", () => {
      if (!nextBtnEl.disabled) {
        loadPage(state.currentPage + 1);
      }
    });

    document.getElementById("page-form").addEventListener("submit", (event) => {
      event.preventDefault();
      const nextPage = parsePositiveInt(pageInputEl.value, state.currentPage);
      loadPage(nextPage);
    });

    window.addEventListener("keydown", (event) => {
      if (event.target && ["INPUT", "TEXTAREA"].includes(event.target.tagName)) {
        return;
      }
      if (event.key === "ArrowLeft" && !prevBtnEl.disabled) {
        loadPage(state.currentPage - 1);
      }
      if (event.key === "ArrowRight" && !nextBtnEl.disabled) {
        loadPage(state.currentPage + 1);
      }
    });

    (async () => {
      try {
        await loadManifest();
        await loadPage(state.currentPage);
      } catch (error) {
        showError(error.message || "The requested document could not be resolved.");
      }
    })();
  </script>
</body>
</html>
"""


def _display_source_name(source_value: str) -> str:
    cleaned = str(source_value or "").replace("\\", "/").rstrip("/")
    if not cleaned:
        return ""
    return cleaned.rsplit("/", 1)[-1]


def _normalize_source_value(value: str | None) -> str:
    return str(value or "").strip()


def _normalize_collection(value: str | None) -> str:
    collection = _normalize_source_value(value) or str(config.DEFAULT_COLLECTION or "plcnext")
    return collection


def _execute_manifest_query(cursor, where_clause: str, params: list[Any], collection: str | None) -> dict[str, Any] | None:
    collection_filter = ""
    query_params = list(params)
    order_clause = "page_count DESC, source ASC"

    if collection:
        collection_filter = "collection_name = %s AND "
        query_params.insert(0, collection)

    query = f"""
        SELECT
            collection_name,
            document_source,
            COALESCE(NULLIF(MAX(metadata->>'source'), ''), {_BASENAME_SQL}) AS source,
            MAX(NULLIF(brand, '')) AS brand,
            MAX(NULLIF(model_subbrand, '')) AS model_subbrand,
            COUNT(*)::int AS page_count,
            MIN(page_number)::int AS min_page,
            MAX(page_number)::int AS max_page,
            ARRAY_AGG(page_number ORDER BY page_number) AS pages
        FROM pdf_pages
        WHERE {collection_filter}{where_clause}
        GROUP BY collection_name, document_source
        ORDER BY {order_clause}
        LIMIT 1
    """
    cursor.execute(query, query_params)
    row = cursor.fetchone()
    if not row:
        return None

    page_numbers = [int(page) for page in (row[8] or [])]
    display_source = row[2] or _display_source_name(row[1])
    return {
        "collection": row[0],
        "source_id": row[1],
        "source": display_source,
        "brand": row[3] or "",
        "model_subbrand": row[4] or "",
        "page_count": int(row[5] or 0),
        "min_page": int(row[6] or 0),
        "max_page": int(row[7] or 0),
        "pages": page_numbers,
        "raw_document_url": f"/api/documents/{quote(display_source)}",
    }


def _resolve_document_manifest(*, source_id: str | None, source: str | None, collection: str | None) -> dict[str, Any]:
    normalized_source_id = _normalize_source_value(source_id)
    normalized_source = _normalize_source_value(source)
    normalized_collection = _normalize_collection(collection) if collection else None

    if not normalized_source_id and not normalized_source:
        raise HTTPException(status_code=400, detail="Either source_id or source must be provided.")

    pool = get_db_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cursor:
            attempts: list[tuple[str, list[Any], str | None]] = []

            if normalized_source_id:
                attempts.append(("document_source = %s", [normalized_source_id], normalized_collection))

            if normalized_source:
                attempts.append((f"{_BASENAME_SQL} = %s", [normalized_source], normalized_collection))
                attempts.append(("COALESCE(NULLIF(metadata->>'source', ''), '') = %s", [normalized_source], normalized_collection))

            if normalized_source_id:
                attempts.append(("document_source = %s", [normalized_source_id], None))

            if normalized_source:
                attempts.append((f"{_BASENAME_SQL} = %s", [normalized_source], None))
                attempts.append(("COALESCE(NULLIF(metadata->>'source', ''), '') = %s", [normalized_source], None))

            for where_clause, params, attempt_collection in attempts:
                manifest = _execute_manifest_query(cursor, where_clause, params, attempt_collection)
                if manifest:
                    return manifest
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to resolve document manifest: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to resolve the requested document.") from exc
    finally:
        pool.putconn(conn)

    raise HTTPException(status_code=404, detail="Document pages were not found in the database.")


def _compute_page_etag(source_id: str, page: int, byte_length: int) -> str:
    digest = hashlib.sha1(f"{source_id}:{page}:{byte_length}".encode("utf-8")).hexdigest()
    return f'W/"{digest}"'


@router.get("/manifest")
def document_manifest(
    source_id: str | None = Query(default=None),
    source: str | None = Query(default=None),
    collection: str | None = Query(default=None),
):
    return _resolve_document_manifest(source_id=source_id, source=source, collection=collection)


@router.get("/image")
def document_page_image(
    request: Request,
    page: int = Query(..., ge=1),
    source_id: str | None = Query(default=None),
    source: str | None = Query(default=None),
    collection: str | None = Query(default=None),
):
    manifest = _resolve_document_manifest(source_id=source_id, source=source, collection=collection)
    pool = get_db_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT image_data, COALESCE(NULLIF(metadata->>'mime_type', ''), 'image/png') AS mime_type
                FROM pdf_pages
                WHERE collection_name = %s
                  AND document_source = %s
                  AND page_number = %s
                LIMIT 1
                """,
                (manifest["collection"], manifest["source_id"], page),
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"Page {page} was not found in the database.")

        image_bytes = bytes(row[0])
        mime_type = row[1] or "image/png"
        etag = _compute_page_etag(manifest["source_id"], page, len(image_bytes))
        if request.headers.get("if-none-match") == etag:
            return Response(
                status_code=304,
                headers={
                    "Cache-Control": "public, max-age=86400",
                    "ETag": etag,
                    "X-Document-Source": manifest["source"],
                    "X-Document-Collection": manifest["collection"],
                },
            )
        return Response(
            content=image_bytes,
            media_type=mime_type,
            headers={
                "Cache-Control": "public, max-age=86400",
                "ETag": etag,
                "X-Document-Source": manifest["source"],
                "X-Document-Collection": manifest["collection"],
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to load page image %s page %s: %s", manifest["source_id"], page, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load the requested page image.") from exc
    finally:
        pool.putconn(conn)


@router.get("/view", response_class=HTMLResponse)
def document_page_viewer():
    return HTMLResponse(_VIEWER_HTML)
