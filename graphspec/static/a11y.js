/* graphspec serve — accessibility & keyboard extension (M5 fan-out).
   Loaded after app.js; talks to the editor only through window.gs. Adds the
   global keymap, focus-order guarantees on the problems list, an Escape
   handler for the export menu, aria-keyshortcuts + a visually-hidden keyboard
   map, and role/aria-label wiring on the rendered SVG. No network, no build
   step, no animation beyond what the core CSS already allows. */
(function () {
  'use strict';

  if (!window.gs) return; // a11y.js always loads after app.js defines gs
  var gs = window.gs;

  var $ = function (id) { return document.getElementById(id); };

  // ------------------------------------------------------------------- CSS
  // Only new rule needed is the standard visually-hidden ("sr-only") pattern
  // for the keyboard-help note; everything else reuses core focus styling
  // (button:focus-visible, [tabindex]:focus-visible already cover the
  // elements we touch below) and honors prefers-reduced-motion by adding no
  // transitions/animations at all.
  var style = document.createElement('style');
  style.textContent =
    '.visually-hidden {' +
    '  position: absolute !important;' +
    '  width: 1px; height: 1px;' +
    '  margin: -1px; padding: 0; border: 0;' +
    '  clip: rect(0, 0, 0, 0);' +
    '  clip-path: inset(50%);' +
    '  overflow: hidden;' +
    '  white-space: nowrap;' +
    '}';
  document.head.appendChild(style);

  // ------------------------------------------------------- keyboard-help note
  var KEYMAP = [
    ['⌘S / Ctrl+S', 'Save the file'],
    ['F8', 'Go to next problem'],
    ['Shift+F8', 'Go to previous problem'],
    ['⌘E / Ctrl+E', 'Toggle the export menu'],
    ['⌘\\ / Ctrl+\\', 'Toggle the problems panel'],
    ['Arrow keys', 'Pan the canvas (when the canvas or a node has focus)'],
    ['+ / =', 'Zoom in (when the canvas or a node has focus)'],
    ['-', 'Zoom out (when the canvas or a node has focus)'],
    ['0', 'Fit the graph to the canvas (when the canvas or a node has focus)'],
    ['Enter', 'Activate the focused node or problem entry'],
    ['Escape', 'Close the export menu']
  ];

  function buildKeyboardHelp() {
    var region = document.createElement('div');
    region.id = 'a11y-keyboard-help';
    region.className = 'visually-hidden';
    region.setAttribute('role', 'note');
    var heading = document.createElement('h2');
    heading.textContent = 'Keyboard shortcuts';
    region.appendChild(heading);
    var list = document.createElement('ul');
    KEYMAP.forEach(function (pair) {
      var li = document.createElement('li');
      li.textContent = pair[0] + ': ' + pair[1];
      list.appendChild(li);
    });
    region.appendChild(list);
    document.body.insertBefore(region, document.body.firstChild);
  }
  buildKeyboardHelp();

  // ------------------------------------------------------------ shortcuts UI
  var exportBtn = $('exportbtn');
  var problemsToggle = $('problemstoggle');
  var problemList = $('problemlist');
  if (exportBtn) exportBtn.setAttribute('aria-keyshortcuts', 'Meta+E');
  if (problemsToggle) {
    problemsToggle.setAttribute('aria-keyshortcuts', 'Meta+Backslash');
    problemsToggle.setAttribute('aria-controls', 'problemlist');
  }

  // ------------------------------------------------------- problems: focus
  // Focus order in the document is already top bar -> editor -> divider ->
  // canvas -> problems (verified against index.html's DOM order and the
  // core's tabindex usage); nothing to reorder here. We only need each
  // <li> to be a keyboard-operable "button".
  function enhanceProblemList() {
    if (!problemList) return;
    var items = problemList.children;
    for (var i = 0; i < items.length; i++) {
      var li = items[i];
      li.setAttribute('tabindex', '0');
      li.setAttribute('role', 'button');
      li.addEventListener('keydown', function (ev) {
        if (ev.key === 'Enter' || ev.key === ' ') {
          ev.preventDefault();
          this.click();
        }
      });
    }
  }
  enhanceProblemList();
  gs.on('refresh', enhanceProblemList);

  // -------------------------------------------------------------- keymap
  document.addEventListener('keydown', function (e) {
    var mod = e.metaKey || e.ctrlKey;
    var key = e.key;

    // These three work everywhere, including while typing in the editor.
    if (key === 'F8') {
      e.preventDefault();
      var cur = gs.state.currentProblem;
      gs.gotoProblem(e.shiftKey ? cur - 1 : cur + 1);
      return;
    }
    if (mod && (key === 'e' || key === 'E')) {
      e.preventDefault();
      gs.toggleExport();
      return;
    }
    if (mod && key === '\\') {
      e.preventDefault();
      gs.toggleProblems();
      return;
    }

    // Escape: close the export menu if it's open, but never swallow the
    // key otherwise — the lens and trace-overlay modules also listen for it.
    if (key === 'Escape') {
      var exportMenu = $('exportmenu');
      if (exportMenu && !exportMenu.hidden) gs.toggleExport(false);
      return;
    }

    // Everything past this point must not interfere with typing.
    if (e.target === gs.editor) return;

    // Canvas pan/zoom/fit — only when the canvas or a node inside it has focus.
    var active = document.activeElement;
    var canvasFocused = gs.canvas && (active === gs.canvas || gs.canvas.contains(active));
    if (!canvasFocused) return;

    var STEP = 40;
    switch (key) {
      case 'ArrowUp': e.preventDefault(); gs.panBy(0, -STEP); break;
      case 'ArrowDown': e.preventDefault(); gs.panBy(0, STEP); break;
      case 'ArrowLeft': e.preventDefault(); gs.panBy(-STEP, 0); break;
      case 'ArrowRight': e.preventDefault(); gs.panBy(STEP, 0); break;
      case '+': case '=': e.preventDefault(); gs.zoom(1); break;
      case '-': e.preventDefault(); gs.zoom(-1); break;
      case '0': e.preventDefault(); gs.fit(); break;
      default: break;
    }
  });

  // ------------------------------------------------------- SVG a11y wiring
  // Per-node labels are already set by app.js (annotateSvg); we only need to
  // label the graph as a whole, deriving the name from the SVG's own
  // top-level <title> (Graphviz emits the graph name there, ahead of any
  // g.node/g.edge titles) rather than reaching past the gs API for it.
  function graphTitleOf(svg) {
    var titles = svg.querySelectorAll('title');
    for (var i = 0; i < titles.length; i++) {
      var t = titles[i];
      var parent = t.parentElement;
      var inNodeOrEdge = parent && parent.classList &&
        (parent.classList.contains('node') || parent.classList.contains('edge'));
      if (!inNodeOrEdge) return t.textContent || '';
    }
    return '';
  }

  gs.on('render', function (svgEl) {
    if (!svgEl) return; // DOT-preview mode (no Graphviz): nothing to label
    svgEl.setAttribute('role', 'img');
    var name = graphTitleOf(svgEl);
    svgEl.setAttribute('aria-label', 'graph ' + name);
  });
})();
