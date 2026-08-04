/* graphspec serve — the data-flow lens (M5 fan-out).
   Paints writers/readers/unset-paths for a selected state field on top of the
   current SVG. Chips live in the #chips element already present in the top bar.
   No framework, no build step, no network beyond this server (POST /flow only). */
(function () {
  'use strict';

  const gs = window.gs;
  if (!gs) return; // app.js failed to load; nothing to hook into

  // ------------------------------------------------------------------- style
  const style = document.createElement('style');
  style.textContent = [
    '.lens-writer ellipse, .lens-writer polygon, .lens-writer path, .lens-writer rect {',
    '  stroke: var(--accent) !important; stroke-width: 3px !important; stroke-dasharray: none !important;',
    '}',
    '.lens-reader-required ellipse, .lens-reader-required polygon, .lens-reader-required path, .lens-reader-required rect {',
    '  stroke: var(--accent) !important; stroke-width: 2.5px !important; stroke-dasharray: 7 3 !important;',
    '}',
    '.lens-reader-optional ellipse, .lens-reader-optional polygon, .lens-reader-optional path, .lens-reader-optional rect {',
    '  stroke: var(--accent) !important; stroke-width: 2.5px !important; stroke-dasharray: 2 3 !important;',
    '}',
    '.lens-edge-writer path, .lens-edge-writer polygon {',
    '  stroke: var(--accent) !important; stroke-width: 2.5px !important; stroke-dasharray: 7 3 !important;',
    '}',
    '.lens-unset-edge path, .lens-unset-edge polygon {',
    '  stroke: var(--err) !important; stroke-width: 2.5px !important;',
    '}',
    '.lens-unset-node ellipse, .lens-unset-node polygon, .lens-unset-node path, .lens-unset-node rect {',
    '  stroke: var(--err) !important; stroke-width: 3px !important;',
    '}',
    '#chips .chip[aria-pressed="true"] { box-shadow: 0 0 0 1px var(--accent-soft) inset; }',
  ].join('\n');
  document.head.appendChild(style);

  const LENS_CLASSES = [
    'lens-writer', 'lens-reader-required', 'lens-reader-optional',
    'lens-edge-writer', 'lens-unset-edge', 'lens-unset-node',
  ];

  // ------------------------------------------------------------------- state
  let activeField = null;   // currently selected field, or null
  let activeData = null;    // last /flow payload for activeField
  let fetchToken = 0;       // guards against out-of-order /flow responses

  function chipsEl() { return document.getElementById('chips'); }

  // --------------------------------------------------------------- painting
  function clearPaint() {
    const svg = gs.svg();
    if (!svg) return;
    LENS_CLASSES.forEach((cls) => {
      svg.querySelectorAll('.' + cls).forEach((g) => g.classList.remove(cls));
    });
  }

  function markNode(name, cls) {
    const el = gs.findSvgElement({ kind: 'node', name: name });
    if (el) el.classList.add(cls);
  }

  function markEdge(title, cls) {
    let el = gs.findSvgElement({ kind: 'edge', title: title });
    if (!el) {
      // fallback: match g.edge <title> text directly against the SVG
      const svg = gs.svg();
      if (svg) {
        el = [...svg.querySelectorAll('g.edge')].find((g) => gs.titleOf(g) === title) || null;
      }
    }
    if (el) el.classList.add(cls);
  }

  function paint() {
    clearPaint();
    if (!activeField || !activeData) return;
    if (gs.state.overlayActive) return; // never paint over the trace overlay
    const svg = gs.svg();
    if (!svg) return;

    (activeData.writers || []).forEach((name) => markNode(name, 'lens-writer'));
    (activeData.readers || []).forEach((name) => markNode(name, 'lens-reader-required'));
    (activeData.optional_readers || []).forEach((name) => markNode(name, 'lens-reader-optional'));
    (activeData.edge_writers || []).forEach((title) => markEdge(title, 'lens-edge-writer'));
    (activeData.unset_paths || []).forEach((path) => {
      for (let i = 0; i < path.length - 1; i++) {
        markEdge(path[i] + '->' + path[i + 1], 'lens-unset-edge');
      }
      if (path.length) markNode(path[path.length - 1], 'lens-unset-node');
    });
  }

  // -------------------------------------------------------------- lifecycle
  function updateChipPressedStates() {
    const wrap = chipsEl();
    if (!wrap) return;
    [...wrap.children].forEach((b) => {
      b.setAttribute('aria-pressed', String(b.dataset.field === activeField));
    });
  }

  function deactivateLens() {
    if (!activeField) return;
    activeField = null;
    activeData = null;
    clearPaint();
    updateChipPressedStates();
  }

  async function fetchAndPaint(field) {
    if (gs.state.overlayActive) { deactivateLens(); return; }
    const token = ++fetchToken;
    const data = await gs.api('/flow', { yaml: gs.yaml(), field: field });
    if (token !== fetchToken) return;       // superseded by a newer request
    if (field !== activeField) return;      // field changed/cleared meanwhile
    if (data.error) { deactivateLens(); return; }
    activeData = data;
    paint();
  }

  function activateLens(field) {
    if (gs.state.overlayActive) return; // do not fight the trace overlay
    activeField = field;
    activeData = null;
    updateChipPressedStates();
    fetchAndPaint(field);
  }

  function toggleField(field) {
    if (activeField === field) { deactivateLens(); return; }
    activateLens(field);
  }

  // ---------------------------------------------------------------- chips UI
  function rebuildChips() {
    const wrap = chipsEl();
    if (!wrap) return;
    const fields = gs.state.stateFields || [];
    if (activeField && fields.indexOf(activeField) === -1) deactivateLens();
    wrap.innerHTML = '';
    fields.forEach((field) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'chip';
      b.textContent = field;
      b.dataset.field = field;
      b.setAttribute('aria-pressed', String(field === activeField));
      b.addEventListener('click', () => toggleField(field));
      wrap.appendChild(b);
    });
  }

  gs.on('refresh', () => {
    rebuildChips();
    if (activeField) fetchAndPaint(activeField); // buffer changed -> re-derive
  });

  gs.on('render', () => {
    // the SVG element is replaced on every render; repaint on top of the new one
    if (activeField && activeData) paint();
  });

  // --------------------------------------------------------------- Escape
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && activeField) deactivateLens();
  });

  // -------------------------------------------------- bonus: cursor linkage
  // When the caret sits on a `state:` field's YAML line, activate that field's
  // lens automatically (mirrors the halo linkage app.js already does for nodes/edges).
  function fieldAtCursor() {
    const line = gs.editor.value.slice(0, gs.editor.selectionStart).split('\n').length;
    const entries = (gs.state.sourceMap || []).filter((e) => e.kind === 'state');
    // exact-line match: state field entries are single-line declarations
    const hit = entries.find((e) => e.line === line);
    return hit ? hit.name : null;
  }

  function syncLensToCursor() {
    const field = fieldAtCursor();
    if (!field) return; // don't clear an existing lens just because the caret moved off
    if (field === activeField) return;
    activateLens(field);
  }

  gs.editor.addEventListener('click', syncLensToCursor);
  gs.editor.addEventListener('keyup', syncLensToCursor);
})();
