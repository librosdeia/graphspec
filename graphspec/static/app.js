/* graphspec serve — core editor loop. No framework, no build step, no network
   beyond this server. Extension modules (lens.js, traceoverlay.js, a11y.js)
   plug in through the documented `window.gs` API at the bottom. */
(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const editor = $('editor'), gutter = $('gutter'), highlights = $('highlights');
  const canvas = $('canvas'), pill = $('pill'), problemList = $('problemlist');
  const dotPreview = $('dotpreview'), dotText = $('dottext'), gvHint = $('gvhint');
  const tooltip = $('tooltip');

  const state = {
    fileName: 'graphspec.yaml',
    mtime: 0,
    dirty: false,
    problems: [],
    sourceMap: [],
    stateFields: [],
    lastRender: null,      // last successful render payload
    valid: false,
    graphviz: false,
    currentProblem: -1,
    pan: { x: 20, y: 20, scale: 1 },
    overlayActive: false,  // set by traceoverlay.js
  };

  // ------------------------------------------------------------------ fetch
  async function api(path, body) {
    const res = await fetch(path, {
      method: body === undefined ? 'GET' : 'POST',
      headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    return res.json();
  }

  // ------------------------------------------------------------------ editor
  function lineCount() { return editor.value.split('\n').length; }

  function esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function renderGutter() {
    const n = lineCount();
    const marks = {};
    for (const p of state.problems) {
      if (p.line > 0) marks[p.line] = marks[p.line] === 'err' ? 'err' : (p.severity === 'error' ? 'err' : (marks[p.line] || 'warn'));
    }
    let html = '';
    for (let i = 1; i <= n; i++) {
      const cls = marks[i] ? ' ' + marks[i] : '';
      const tip = marks[i] ? state.problems.filter(p => p.line === i).map(p => '[' + p.rule_id + ']').join(' ') : '';
      html += '<span class="ln' + cls + '" title="' + esc(tip) + '">' + i + '</span>';
    }
    gutter.innerHTML = html;
  }

  function renderHighlights(focusLine) {
    const lines = editor.value.split('\n');
    const byLine = {};
    for (const p of state.problems) {
      if (p.line > 0) byLine[p.line] = p.severity === 'error' ? 'hl-err' : (byLine[p.line] || 'hl-warn');
    }
    let html = '';
    for (let i = 0; i < lines.length; i++) {
      const cls = (i + 1 === focusLine) ? 'hl-focus' : (byLine[i + 1] || '');
      const text = esc(lines[i]) || ' ';
      html += cls ? '<span class="' + cls + '">' + text + '</span>\n' : text + '\n';
    }
    highlights.innerHTML = html;
  }

  editor.addEventListener('scroll', () => {
    gutter.scrollTop = editor.scrollTop;
    highlights.scrollTop = editor.scrollTop;
    highlights.scrollLeft = editor.scrollLeft;
  });

  function cursorLine() {
    return editor.value.slice(0, editor.selectionStart).split('\n').length;
  }

  function jumpToLine(line) {
    const lines = editor.value.split('\n');
    let pos = 0;
    for (let i = 0; i < line - 1 && i < lines.length; i++) pos += lines[i].length + 1;
    editor.focus();
    editor.setSelectionRange(pos, pos + (lines[line - 1] || '').length);
    const lh = editor.scrollHeight / Math.max(1, lines.length);
    editor.scrollTop = Math.max(0, (line - 4) * lh);
    renderHighlights(line);
  }

  // ------------------------------------------------------------- validation
  let debounceTimer = null;
  editor.addEventListener('input', () => {
    state.dirty = true;
    $('graphname').classList.add('dirty');
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(refresh, 300);
  });

  async function refresh() {
    const yaml = editor.value;
    const [v, r] = await Promise.all([
      api('/validate', { yaml }),
      api('/render', { yaml }),
    ]);
    state.problems = v.problems || [];
    state.sourceMap = v.source_map || [];
    state.stateFields = v.state_fields || [];
    state.valid = !!v.valid;
    renderPill(v);
    renderProblems();
    renderGutter();
    renderHighlights();
    if (!r.error) {
      state.lastRender = r;
      drawRender(r);
      canvas.classList.toggle('dimmed', !state.valid);
    } else {
      // keep the last valid graph visible, dimmed — never a blank canvas
      canvas.classList.add('dimmed');
    }
    gs.emit('refresh', { validate: v, render: r.error ? null : r });
  }

  function renderPill(v) {
    const errs = state.problems.filter(p => p.severity === 'error').length;
    const warns = state.problems.length - errs;
    if (errs) { pill.textContent = '● ' + errs + ' error' + (errs > 1 ? 's' : '') + (warns ? ' · ' + warns + ' warning' + (warns > 1 ? 's' : '') : ''); pill.className = 'pill err'; }
    else if (warns) { pill.textContent = '● ' + warns + ' warning' + (warns > 1 ? 's' : ''); pill.className = 'pill warn'; }
    else { pill.textContent = 'valid'; pill.className = 'pill ok'; }
    if (v.name) $('graphname').textContent = v.name;
    $('graphname').classList.toggle('dirty', state.dirty);
  }

  function renderProblems() {
    $('problemcount').textContent = state.problems.length;
    problemList.innerHTML = '';
    state.problems.forEach((p, i) => {
      const li = document.createElement('li');
      li.className = p.severity === 'error' ? 'err' : 'warn';
      const sev = document.createElement('span');
      sev.className = 'sev';
      sev.textContent = p.severity === 'error' ? '✕' : '⚠';
      li.appendChild(sev);
      li.appendChild(document.createTextNode(p.formatted));
      li.addEventListener('click', () => gotoProblem(i));
      problemList.appendChild(li);
    });
  }

  function gotoProblem(i) {
    if (!state.problems.length) return;
    state.currentProblem = ((i % state.problems.length) + state.problems.length) % state.problems.length;
    const p = state.problems[state.currentProblem];
    [...problemList.children].forEach((li, j) => li.classList.toggle('current', j === state.currentProblem));
    if (p.line > 0) jumpToLine(p.line);
    // flash the offending element in the canvas
    const entry = state.sourceMap.filter(e => e.line === p.line)[0];
    if (entry) {
      const el = findSvgElement(entry);
      if (el) {
        el.classList.add('flash');
        setTimeout(() => el.classList.remove('flash'), 1200);
      }
    }
  }

  // ---------------------------------------------------------------- canvas
  let fittedOnce = false;
  function drawRender(r) {
    if (r.format === 'svg') {
      dotPreview.hidden = true;
      // The SVG is produced by this local server's Graphviz from the user's own
      // file (localhost-only, no third-party content); dot emits escaped XML and
      // innerHTML never executes <script> nodes.
      canvas.innerHTML = r.svg;
      const svg = canvas.querySelector('svg');
      if (svg) {
        svg.removeAttribute('width'); svg.removeAttribute('height');
        const vb = svg.viewBox && svg.viewBox.baseVal;
        if (vb && vb.width) {
          svg.style.width = vb.width + 'px';
          svg.style.height = vb.height + 'px';
        }
        svg.style.transformOrigin = '0 0';
        annotateSvg(svg);
        if (!fittedOnce) { fittedOnce = true; fit(); } else { applyPan(); }
      }
      canvas.hidden = false;
    } else {
      canvas.innerHTML = '';
      dotText.textContent = r.dot;
      gvHint.textContent = r.hint || '';
      dotPreview.hidden = false;
    }
    gs.emit('render', canvas.querySelector('svg'), r);
  }

  function annotateSvg(svg) {
    svg.querySelectorAll('g.node').forEach(g => {
      g.setAttribute('tabindex', '0');
      g.setAttribute('role', 'img');
      const name = titleOf(g);
      g.setAttribute('aria-label', 'node ' + name);
      g.addEventListener('click', () => {
        const entry = state.sourceMap.find(e => e.kind === 'node' && e.name === name);
        if (entry) jumpToLine(entry.line);
      });
      g.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') g.dispatchEvent(new Event('click')); });
    });
    svg.querySelectorAll('g.edge').forEach(g => {
      const t = titleOf(g);
      const entry = state.sourceMap.find(e => e.kind === 'edge' && e.title === t);
      g.addEventListener('mousemove', (ev) => {
        if (!entry || (!entry.when && !entry.max)) return;
        tooltip.textContent = (entry.when ? 'when: ' + entry.when : '') +
          (entry.max ? '  max=' + entry.max + ' counter=' + entry.counter : '');
        tooltip.style.left = (ev.clientX - canvas.getBoundingClientRect().left + 12) + 'px';
        tooltip.style.top = (ev.clientY - canvas.getBoundingClientRect().top + 12) + 'px';
        tooltip.hidden = false;
      });
      g.addEventListener('mouseleave', () => { tooltip.hidden = true; });
      g.addEventListener('click', () => { if (entry) jumpToLine(entry.line); });
    });
  }

  function titleOf(g) {
    const t = g.querySelector('title');
    return t ? t.textContent : '';
  }

  function findSvgElement(entry) {
    const svg = canvas.querySelector('svg');
    if (!svg) return null;
    const want = entry.kind === 'edge' ? entry.title : entry.name;
    const sel = entry.kind === 'edge' ? 'g.edge' : 'g.node';
    return [...svg.querySelectorAll(sel)].find(g => titleOf(g) === want) || null;
  }

  // cursor position -> halo in canvas
  let lastHalo = null;
  editor.addEventListener('keyup', syncHalo);
  editor.addEventListener('click', syncHalo);
  function syncHalo() {
    const line = cursorLine();
    let best = null;
    for (const e of state.sourceMap) if (e.line <= line && (!best || e.line >= best.line)) best = e;
    if (lastHalo) lastHalo.classList.remove('halo');
    if (best) {
      const el = findSvgElement(best);
      if (el) { el.classList.add('halo'); lastHalo = el; }
    }
  }

  // pan / zoom
  function applyPan() {
    const svg = canvas.querySelector('svg');
    if (svg) svg.style.transform = 'translate(' + state.pan.x + 'px,' + state.pan.y + 'px) scale(' + state.pan.scale + ')';
  }
  let dragging = null;
  canvas.addEventListener('mousedown', (e) => { if (e.target.closest('g.node')) return; dragging = { x: e.clientX, y: e.clientY }; });
  window.addEventListener('mouseup', () => { dragging = null; });
  window.addEventListener('mousemove', (e) => {
    if (!dragging) return;
    state.pan.x += e.clientX - dragging.x; state.pan.y += e.clientY - dragging.y;
    dragging = { x: e.clientX, y: e.clientY };
    applyPan();
  });
  canvas.addEventListener('wheel', (e) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.1 : 0.9;
    state.pan.scale = Math.min(6, Math.max(0.15, state.pan.scale * factor));
    applyPan();
  }, { passive: false });
  function zoom(delta) { state.pan.scale = Math.min(6, Math.max(0.15, state.pan.scale * (delta > 0 ? 1.2 : 0.8))); applyPan(); }
  function fit() {
    // center the sheet on the drafting grid with a generous margin
    const svg = canvas.querySelector('svg');
    if (!svg) { state.pan = { x: 20, y: 20, scale: 1 }; applyPan(); return; }
    const vb = svg.viewBox && svg.viewBox.baseVal;
    const w = (vb && vb.width) || svg.getBoundingClientRect().width / state.pan.scale || 300;
    const h = (vb && vb.height) || svg.getBoundingClientRect().height / state.pan.scale || 150;
    const margin = 48;
    const scale = Math.min(1.25,
      (canvas.clientWidth - 2 * margin) / w,
      (canvas.clientHeight - 2 * margin) / h);
    state.pan = {
      x: Math.max(margin, (canvas.clientWidth - w * scale) / 2),
      y: Math.max(margin, (canvas.clientHeight - h * scale) / 2),
      scale: Math.max(0.15, scale),
    };
    applyPan();
  }

  // ------------------------------------------------------------------ split
  const split = $('split'), divider = $('divider');
  const saved = localStorage.getItem('graphspec.split');
  if (saved) document.documentElement.style.setProperty('--split', saved);
  divider.addEventListener('mousedown', (e) => {
    e.preventDefault();
    const move = (ev) => {
      const pct = Math.min(80, Math.max(15, (ev.clientX / split.clientWidth) * 100));
      document.documentElement.style.setProperty('--split', pct + '%');
      localStorage.setItem('graphspec.split', pct + '%');
    };
    const up = () => { window.removeEventListener('mousemove', move); window.removeEventListener('mouseup', up); };
    window.addEventListener('mousemove', move);
    window.addEventListener('mouseup', up);
  });

  // ------------------------------------------------------------------ theme
  $('themebtn').addEventListener('click', () => {
    const cur = document.documentElement.dataset.theme ||
      (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    document.documentElement.dataset.theme = cur === 'dark' ? 'light' : 'dark';
    localStorage.setItem('graphspec.theme', document.documentElement.dataset.theme);
  });
  const savedTheme = localStorage.getItem('graphspec.theme');
  if (savedTheme) document.documentElement.dataset.theme = savedTheme;

  // ----------------------------------------------------------------- export
  const exportBtn = $('exportbtn'), exportMenu = $('exportmenu');
  function toggleExport(show) {
    exportMenu.hidden = show === undefined ? !exportMenu.hidden : !show;
    exportBtn.setAttribute('aria-expanded', String(!exportMenu.hidden));
    if (!exportMenu.hidden) exportMenu.querySelector('button').focus();
  }
  exportBtn.addEventListener('click', () => toggleExport());
  document.addEventListener('click', (e) => { if (!e.target.closest('#exportwrap')) toggleExport(false); });
  exportMenu.addEventListener('click', (e) => {
    const fmt = e.target.dataset && e.target.dataset.fmt;
    if (!fmt || !state.lastRender) return;
    if (fmt === 'dot') download('graph.dot', new Blob([state.lastRender.dot], { type: 'text/vnd.graphviz' }));
    if (fmt === 'svg' && state.lastRender.svg) download('graph.svg', new Blob([state.lastRender.svg], { type: 'image/svg+xml' }));
    if (fmt === 'png' && state.lastRender.svg) exportPng();
    toggleExport(false);
  });
  function download(name, blob) {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = name;
    a.click();
    URL.revokeObjectURL(a.href);
  }
  function exportPng() {
    const img = new Image();
    const blobUrl = URL.createObjectURL(new Blob([state.lastRender.svg], { type: 'image/svg+xml' }));
    img.onload = () => {
      const c = document.createElement('canvas');
      c.width = img.width * 2; c.height = img.height * 2;
      c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
      c.toBlob((b) => { download('graph.png', b); URL.revokeObjectURL(blobUrl); }, 'image/png');
    };
    img.src = blobUrl;
  }
  function refreshExportAvailability() {
    exportMenu.querySelector('[data-fmt="svg"]').disabled = !state.graphviz;
    exportMenu.querySelector('[data-fmt="png"]').disabled = !state.graphviz;
  }

  // ------------------------------------------------------------------- save
  async function save() {
    const res = await api('/save', { yaml: editor.value });
    if (res.ok) {
      state.dirty = false;
      state.mtime = res.mtime;
      $('graphname').classList.remove('dirty');
    }
  }
  document.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 's') { e.preventDefault(); save(); }
  });

  // external change detection
  setInterval(async () => {
    const res = await api('/mtime');
    if (res.mtime && state.mtime && res.mtime > state.mtime + 0.001) {
      $('banner').hidden = false;
    }
  }, 2000);
  $('reloadbtn').addEventListener('click', async () => {
    const doc = await api('/file');
    editor.value = doc.yaml;
    state.mtime = doc.mtime;
    state.dirty = false;
    $('banner').hidden = true;
    refresh();
  });
  $('dismissbanner').addEventListener('click', () => {
    $('banner').hidden = true;
    state.mtime = Date.now() / 1000;  // stop re-prompting until the next change
  });

  // --------------------------------------------------------------- problems
  $('problemstoggle').addEventListener('click', () => {
    const collapsed = $('problems').classList.toggle('collapsed');
    $('problemstoggle').setAttribute('aria-expanded', String(!collapsed));
    $('problemstoggle').textContent = (collapsed ? '▸' : '▾') + ' PROBLEMS (' + state.problems.length + ')';
  });

  // ------------------------------------------------------------------- init
  async function init() {
    const doc = await api('/file');
    state.mtime = doc.mtime;
    state.graphviz = doc.graphviz;
    $('graphname').textContent = doc.name;
    refreshExportAvailability();
    if (!doc.yaml.trim()) {
      // never a blank canvas: template picker
      const picker = $('picker'), list = $('pickerlist');
      (doc.examples || []).forEach(ex => {
        const b = document.createElement('button');
        b.textContent = ex.name;
        b.addEventListener('click', () => { editor.value = ex.yaml; picker.hidden = true; state.dirty = true; refresh(); });
        list.appendChild(b);
      });
      const blank = document.createElement('button');
      blank.textContent = 'blank';
      blank.addEventListener('click', () => {
        editor.value = 'graphspec: 1\nname: my-graph\nentry: start\nterminals: [done]\n\nnodes:\n  start: {kind: llm}\n  done: {kind: terminal}\n\nedges:\n  - {from: start, to: done}\n';
        picker.hidden = true; state.dirty = true; refresh();
      });
      list.appendChild(blank);
      picker.hidden = false;
    } else {
      editor.value = doc.yaml;
    }
    refresh();
  }

  // -------------------------------------------------- extension API (window.gs)
  const listeners = {};
  const gs = {
    api, state, editor, canvas, jumpToLine, gotoProblem, zoom, fit, save,
    findSvgElement, titleOf,
    panBy: (dx, dy) => { state.pan.x += dx; state.pan.y += dy; applyPan(); },
    refresh,
    yaml: () => editor.value,
    svg: () => canvas.querySelector('svg'),
    on: (ev, cb) => { (listeners[ev] = listeners[ev] || []).push(cb); },
    emit: (ev, ...args) => { (listeners[ev] || []).forEach(cb => { try { cb(...args); } catch (e) { console.error('[gs]', ev, e); } }); },
    costPanel: (text) => {
      const el = $('costpanel');
      if (text == null) { el.hidden = true; el.textContent = ''; problemList.hidden = false; }
      else { el.textContent = text; el.hidden = false; problemList.hidden = true; $('problems').classList.remove('collapsed'); }
    },
    toggleProblems: () => $('problemstoggle').click(),
    toggleExport,
  };
  window.gs = gs;

  init();
})();
