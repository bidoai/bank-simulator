/**
 * shared_nav.js — Apex Global Bank universal navigation bar
 *
 * Injected into every dashboard page.  Provides:
 *  - Brand link (always navigates to / via window.location)
 *  - Tab links with auto-detected active state
 *  - Optional right-side slot for page-specific controls
 *    (populate via: document.getElementById('apex-nav-right'))
 */
(function () {
  var PAGES = [
    { path: '/boardroom', label: 'Boardroom'       },
    { path: '/trading',   label: 'Trading'         },
    { path: '/risk',      label: 'Risk'            },
    { path: '/securities-finance', label: 'Sec Finance' },
    { path: '/securitized', label: 'Securitized'   },
    { path: '/xva',       label: 'XVA Analytics'   },
    { path: '/models',    label: 'Model Governance' },
    { path: '/scenarios', label: 'Scenarios'       },
  ];

  var ACCENT  = '#58a6ff';
  var MUTED   = '#8b949e';
  var BG      = '#0d1117';
  var BORDER  = '#21262d';
  var ACTIVE_BG = 'rgba(88,166,255,.1)';
  var FONT    = 'ui-monospace,"Berkeley Mono","Fira Code",monospace';
  var NAV_H   = '44px';

  var cur = window.location.pathname.replace(/\/+$/, '') || '/';

  /* ── Build tab links ─────────────────────────────────────────────── */
  var linksHtml = PAGES.map(function (p) {
    var active = (cur === p.path);
    return [
      '<a href="', p.path, '"',
      ' style="',
        'padding:4px 10px;',
        'border-radius:4px;',
        'font-size:11px;',
        'font-weight:', active ? '600' : '400', ';',
        'text-decoration:none;',
        'white-space:nowrap;',
        'color:', active ? ACCENT : MUTED, ';',
        active ? 'background:' + ACTIVE_BG + ';' : '',
        'transition:color .15s,background .15s;',
      '"',
      ' onmouseover="if(!this.dataset.active){this.style.color=\'#c9d1d9\';this.style.background=\'#161b22\';}"',
      ' onmouseout="if(!this.dataset.active){this.style.color=\'', MUTED, '\';this.style.background=\'transparent\';}"',
      active ? ' data-active="1"' : '',
      '>',
      p.label,
      '</a>',
    ].join('');
  }).join('');

  /* ── Build nav HTML ──────────────────────────────────────────────── */
  var nav = document.createElement('nav');
  nav.id = 'apex-global-nav';
  nav.setAttribute('role', 'navigation');
  nav.innerHTML =
    '<div style="display:flex;align-items:center;gap:2px;">' +
      '<a' +
        ' id="apex-brand"' +
        ' onclick="window.location.href=\'\/\'"' +
        ' title="Home"' +
        ' style="' +
          'cursor:pointer;' +
          'color:' + ACCENT + ';' +
          'font-weight:700;' +
          'font-size:13px;' +
          'letter-spacing:0.02em;' +
          'margin-right:20px;' +
          'text-decoration:none;' +
          'white-space:nowrap;' +
          'user-select:none;' +
        '"' +
        ' onmouseover="this.style.opacity=\'0.75\'"' +
        ' onmouseout="this.style.opacity=\'1\'"' +
      '>Apex Global Bank</a>' +
      '<div style="width:1px;height:18px;background:' + BORDER + ';margin-right:16px;"></div>' +
      linksHtml +
    '</div>' +
    '<div id="apex-nav-right" style="display:flex;align-items:center;gap:10px;"></div>';

  nav.style.cssText = [
    'position:fixed', 'top:0', 'left:0', 'right:0',
    'z-index:9999',
    'height:' + NAV_H,
    'background:' + BG,
    'border-bottom:1px solid ' + BORDER,
    'display:flex', 'align-items:center', 'justify-content:space-between',
    'padding:0 20px',
    'font-family:' + FONT,
    'box-sizing:border-box',
  ].join(';');

  /* ── Insert at top of body ───────────────────────────────────────── */
  var firstChild = document.body.firstChild;
  if (firstChild) {
    document.body.insertBefore(nav, firstChild);
  } else {
    document.body.appendChild(nav);
  }

  /* ── Push page content below fixed nav ───────────────────────────── */
  // Prefer a data attribute on body; otherwise just pad the body.
  var existingPad = parseInt(document.body.style.paddingTop, 10) || 0;
  if (existingPad < 44) {
    document.body.style.paddingTop = NAV_H;
  }
}());
