/* graphspec serve — trace overlay by drag-and-drop (M5, UI-SPEC "Trace overlay by
   drag-and-drop"). Loaded after app.js; talks to window.gs only, no framework, no
   network beyond this server's own /trace endpoint. */
(function () {
  'use strict';

  const gs = window.gs;
  if (!gs) return; // app.js failed to init; nothing to attach to

  // ------------------------------------------------------------------- style
  // Drag-hover affordance only. No fills here — fills are the overlay's job once a
  // trace lands (server already colors nodes); this is just "you can drop here".
  // Any transition below is neutralized globally by app.css's
  // `@media (prefers-reduced-motion: reduce) { * { transition: none !important } }`,
  // so we don't need a second reduced-motion guard in this file.
  const style = document.createElement('style');
  style.textContent = [
    '.gs-trace-dragover { outline: 3px dashed var(--accent); outline-offset: -3px; }',
    '#costpanel .gs-drift { color: var(--warn); }',
  ].join('\n');
  document.head.appendChild(style);

  // -------------------------------------------------------------- drop targets
  // Per the spec: dragover/drop must work over the canvas itself and over the whole
  // main split area (so dropping near the editor pane still works, not just the exact
  // canvas pixels). #split is the ancestor of both panes.
  const mainArea = document.getElementById('split') || document.body;
  const canvas = gs.canvas;

  function markDragOver(e) {
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
    canvas.classList.add('gs-trace-dragover');
  }
  function unmarkIfLeft(el) {
    return function (e) {
      if (!el.contains(e.relatedTarget)) canvas.classList.remove('gs-trace-dragover');
    };
  }
  function handleDrop(e) {
    e.preventDefault();
    e.stopPropagation(); // avoid double-handling: canvas is nested inside mainArea
    canvas.classList.remove('gs-trace-dragover');
    const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
    if (!file) return;
    readDroppedFile(file);
  }

  [canvas, mainArea].forEach((el) => {
    el.addEventListener('dragover', markDragOver);
    el.addEventListener('dragleave', unmarkIfLeft(el));
    el.addEventListener('drop', handleDrop);
  });

  // -------------------------------------------------------------------- pipeline
  function readDroppedFile(file) {
    const reader = new FileReader();
    reader.onload = () => {
      let otlp;
      try {
        otlp = JSON.parse(String(reader.result));
      } catch (err) {
        gs.costPanel('trace: dropped file is not valid JSON');
        return;
      }
      sendTrace(otlp);
    };
    reader.onerror = () => { gs.costPanel('trace: could not read dropped file'); };
    reader.readAsText(file);
  }

  async function sendTrace(otlp) {
    let payload;
    try {
      payload = await gs.api('/trace', { yaml: gs.yaml(), otlp });
    } catch (err) {
      gs.costPanel('trace: request to /trace failed');
      return;
    }
    if (!payload || payload.error) {
      gs.costPanel('trace: ' + (payload && payload.error ? payload.error : 'request failed'));
      return;
    }
    applyOverlay(payload);
  }

  function applyOverlay(payload) {
    gs.state.overlayActive = true;

    if (payload.format === 'svg' && payload.svg) {
      const dotPreview = document.getElementById('dotpreview');
      // Same-origin server output (this machine's own graphspec render pipeline),
      // mirrors how app.js trusts /render's svg: dot emits escaped XML, innerHTML
      // never executes <script> nodes.
      canvas.innerHTML = payload.svg;
      const svg = canvas.querySelector('svg');
      if (svg) {
        svg.removeAttribute('width');
        svg.removeAttribute('height');
        svg.style.transformOrigin = '0 0';
      }
      if (dotPreview) dotPreview.hidden = true;
      canvas.hidden = false;
    } else {
      const dotText = document.getElementById('dottext');
      const dotPreview = document.getElementById('dotpreview');
      canvas.innerHTML = '';
      if (dotText) dotText.textContent = payload.dot || '';
      if (dotPreview) dotPreview.hidden = false;
    }

    // The transform lives on the svg element; our innerHTML swap replaced it, so
    // reapply the current pan/zoom rather than resetting it.
    gs.panBy(0, 0);

    gs.costPanel(buildCostText(payload));
  }

  function buildCostText(payload) {
    const table = payload.cost_table || '';
    const lines = [table];
    (payload.drift || []).forEach((d) => {
      if (!table.includes(d)) lines.push('drift: ' + d);
    });
    return lines.join('\n');
  }

  // ---------------------------------------------------------------------- clear
  // Esc always clears the overlay and restores the live, editable view.
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape' || !gs.state.overlayActive) return;
    gs.state.overlayActive = false;
    gs.costPanel(null);
    gs.refresh();
  });

  // Behavior choice for "suspend the editor's normal re-render overwrite" (spec
  // point 3): we do NOT fight the core's re-render loop by re-swapping the overlay
  // svg back in on every 'render' event. Instead, the overlay is dropped the next
  // time the core actually completes a live re-render while it's active — i.e. the
  // user edited the buffer and validation+render ran again. This is simpler and
  // predictable: editing the graph always means "I'm looking at the live graph
  // again," and Esc remains the explicit, always-available way to clear early.
  gs.on('render', () => {
    if (!gs.state.overlayActive) return;
    gs.state.overlayActive = false;
    gs.costPanel(null);
  });
})();
