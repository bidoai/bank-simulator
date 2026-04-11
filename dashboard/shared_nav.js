/**
 * shared_nav.js — Apex Global Bank universal navigation bar (v2)
 *
 * 5-domain dropdown nav: Command | Markets | Risk | Treasury | Governance
 * Preserves #apex-nav-right slot for page-specific controls.
 */
(function () {
  var DOMAINS = [
    { label: 'Command', pages: [
      { label: 'Home',      href: '/' },
      { label: 'Boardroom', href: '/boardroom' },
      { label: 'Scenarios', href: '/scenarios' },
    ]},
    { label: 'Markets', pages: [
      { label: 'Trading',     href: '/trading' },
      { label: 'XVA',         href: '/xva' },
      { label: 'Sec Finance', href: '/securities-finance' },
      { label: 'Securitized', href: '/securitized' },
    ]},
    { label: 'Risk', pages: [
      { label: 'Market Risk', href: '/risk' },
      { label: 'Liquidity',   href: '/liquidity' },
    ]},
    { label: 'Treasury', pages: [
      { label: 'Treasury', href: '/treasury' },
    ]},
    { label: 'Governance', pages: [
      { label: 'Models', href: '/models' },
    ]},
  ];

  var ACCENT    = '#58a6ff';
  var MUTED     = '#8b949e';
  var TEXT      = '#c9d1d9';
  var BG        = '#0d1117';
  var CARD      = '#161b22';
  var BORDER    = '#21262d';
  var ACTIVE_BG = 'rgba(88,166,255,.1)';
  var FONT      = 'ui-monospace,"Berkeley Mono","Fira Code",monospace';
  var NAV_H     = '44px';

  var cur = window.location.pathname.replace(/\/+$/, '') || '/';

  function isActiveDomain(domain) {
    return domain.pages.some(function (p) {
      if (p.href === '/') return cur === '/';
      return cur === p.href || cur.indexOf(p.href) === 0;
    });
  }

  function isActivePage(href) {
    if (href === '/') return cur === '/';
    return cur === href || cur.indexOf(href) === 0;
  }

  /* ── Build domain buttons + dropdowns ─────────────────────────────── */
  var domainsHtml = DOMAINS.map(function (domain) {
    var domActive = isActiveDomain(domain);

    var pagesHtml = domain.pages.map(function (p) {
      var pa = isActivePage(p.href);
      return [
        '<a href="', p.href, '"',
        ' style="',
          'display:block;',
          'padding:6px 14px;',
          'font-size:11px;',
          'text-decoration:none;',
          'white-space:nowrap;',
          'color:', pa ? ACCENT : MUTED, ';',
          pa ? 'background:' + ACTIVE_BG + ';' : '',
          'transition:color .12s,background .12s;',
        '"',
        ' onmouseover="this.style.color=\'', TEXT, '\';this.style.background=\'rgba(255,255,255,0.04)\'"',
        ' onmouseout="this.style.color=\'', pa ? ACCENT : MUTED, '\';this.style.background=\'', pa ? ACTIVE_BG : 'transparent', '\'"',
        '>',
        p.label,
        '</a>',
      ].join('');
    }).join('');

    return [
      '<div class="apex-nav-domain" style="position:relative;">',
        '<button class="apex-domain-btn"',
          ' style="',
            'background:', domActive ? ACTIVE_BG : 'transparent', ';',
            'border:none;',
            'cursor:pointer;',
            'font-family:', FONT, ';',
            'font-size:11px;',
            'font-weight:', domActive ? '600' : '400', ';',
            'color:', domActive ? ACCENT : MUTED, ';',
            'padding:4px 10px;',
            'border-radius:4px;',
            'white-space:nowrap;',
            'display:flex;align-items:center;gap:4px;',
            'transition:color .12s,background .12s;',
          '"',
          ' onmouseover="this.style.color=\'', TEXT, '\'"',
          ' onmouseout="this.style.color=\'', domActive ? ACCENT : MUTED, '\'"',
        '>',
          domain.label,
          '<span style="font-size:9px;opacity:0.5;line-height:1;">&#9660;</span>',
        '</button>',
        '<div class="apex-nav-dropdown"',
          ' style="',
            'display:none;',
            'position:absolute;',
            'top:calc(100% + 4px);',
            'left:0;',
            'background:', BG, ';',
            'border:1px solid ', BORDER, ';',
            'border-radius:6px;',
            'padding:4px 0;',
            'min-width:140px;',
            'z-index:10000;',
            'box-shadow:0 8px 24px rgba(0,0,0,0.65);',
          '">',
          pagesHtml,
        '</div>',
      '</div>',
    ].join('');
  }).join('');

  /* ── Build nav element ───────────────────────────────────────────── */
  var nav = document.createElement('nav');
  nav.id = 'apex-global-nav';
  nav.setAttribute('role', 'navigation');
  nav.innerHTML =
    '<div style="display:flex;align-items:center;gap:2px;">' +
      '<a href="/"' +
        ' id="apex-brand"' +
        ' style="' +
          'color:' + ACCENT + ';' +
          'font-weight:700;' +
          'font-size:13px;' +
          'letter-spacing:0.02em;' +
          'margin-right:20px;' +
          'text-decoration:none;' +
          'white-space:nowrap;' +
          'user-select:none;' +
        '"' +
        ' onmouseover="this.style.opacity=\'0.7\'"' +
        ' onmouseout="this.style.opacity=\'1\'"' +
      '>Apex&#160;Global&#160;Bank</a>' +
      '<div style="width:1px;height:18px;background:' + BORDER + ';margin-right:12px;flex-shrink:0;"></div>' +
      '<div style="display:flex;align-items:center;gap:2px;">' + domainsHtml + '</div>' +
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

  /* ── Push page content below fixed nav ──────────────────────────── */
  var existingPad = parseInt(document.body.style.paddingTop, 10) || 0;
  if (existingPad < 44) {
    document.body.style.paddingTop = NAV_H;
  }

  /* ── Dropdown hover logic ────────────────────────────────────────── */
  var domainEls = nav.querySelectorAll('.apex-nav-domain');
  domainEls.forEach(function (domEl) {
    var dropdown = domEl.querySelector('.apex-nav-dropdown');
    var hideTimer;

    function showDropdown() {
      clearTimeout(hideTimer);
      domainEls.forEach(function (d) {
        if (d !== domEl) d.querySelector('.apex-nav-dropdown').style.display = 'none';
      });
      dropdown.style.display = 'block';
    }

    function scheduleHide() {
      hideTimer = setTimeout(function () {
        dropdown.style.display = 'none';
      }, 120);
    }

    domEl.addEventListener('mouseenter', showDropdown);
    domEl.addEventListener('mouseleave', scheduleHide);
    dropdown.addEventListener('mouseenter', function () { clearTimeout(hideTimer); });
    dropdown.addEventListener('mouseleave', scheduleHide);

    /* click on button also toggles (for touch / keyboard) */
    domEl.querySelector('.apex-domain-btn').addEventListener('click', function (e) {
      e.stopPropagation();
      var visible = dropdown.style.display === 'block';
      domainEls.forEach(function (d) {
        d.querySelector('.apex-nav-dropdown').style.display = 'none';
      });
      if (!visible) dropdown.style.display = 'block';
    });
  });

  /* close on outside click */
  document.addEventListener('click', function () {
    domainEls.forEach(function (d) {
      d.querySelector('.apex-nav-dropdown').style.display = 'none';
    });
  });
}());
