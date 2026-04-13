/**
 * shared_nav.js — Apex Global Bank universal navigation bar (v3)
 *
 * Improves first-load legibility, active-path visibility, and keyboard access.
 */
(function () {
  var DOMAINS = [
    { label: 'Command', pages: [
      { label: 'Home', href: '/' },
      { label: 'Boardroom', href: '/boardroom' },
      { label: 'Scenarios', href: '/scenarios' },
    ]},
    { label: 'Markets', pages: [
      { label: 'Trading', href: '/trading' },
      { label: 'XVA', href: '/xva' },
      { label: 'Sec Finance', href: '/securities-finance' },
      { label: 'Securitized', href: '/securitized' },
    ]},
    { label: 'Risk', pages: [
      { label: 'Market Risk', href: '/risk' },
      { label: 'Liquidity', href: '/liquidity' },
    ]},
    { label: 'Treasury', pages: [
      { label: 'Treasury', href: '/treasury' },
    ]},
    { label: 'Governance', pages: [
      { label: 'Models', href: '/models' },
    ]},
  ];

  var COLORS = {
    accent: '#58a6ff',
    muted: '#d0d7de',
    text: '#f0f6fc',
    bg: '#0d1117',
    panel: '#111827',
    border: '#30363d',
    btnBg: '#1b2230',
    btnHover: '#263246',
    activeBg: '#1f4f86',
    activeBorder: 'rgba(88,166,255,0.65)',
    locationBg: 'rgba(88,166,255,0.12)',
  };
  var FONT = 'ui-monospace,"Berkeley Mono","Fira Code",monospace';
  var NAV_H = '52px';
  var cur = window.location.pathname.replace(/\/+$/, '') || '/';

  function isActivePage(href) {
    if (href === '/') return cur === '/';
    return cur === href || cur.indexOf(href) === 0;
  }

  function isActiveDomain(domain) {
    return domain.pages.some(function (page) {
      return isActivePage(page.href);
    });
  }

  function getActivePage(domain) {
    for (var i = 0; i < domain.pages.length; i += 1) {
      if (isActivePage(domain.pages[i].href)) return domain.pages[i];
    }
    return null;
  }

  function injectStyles() {
    var style = document.createElement('style');
    style.textContent = [
      '#apex-global-nav .apex-nav-domain{position:relative}',
      '#apex-global-nav .apex-domain-btn{outline:none;color:' + COLORS.text + ' !important;background:' + COLORS.btnBg + ' !important;border:1px solid ' + COLORS.border + ' !important;opacity:1 !important}',
      '#apex-global-nav .apex-domain-btn:hover{color:' + COLORS.text + ' !important;background:' + COLORS.btnHover + ' !important;border-color:rgba(240,246,252,.32) !important}',
      '#apex-global-nav .apex-domain-btn[data-active="true"]{background:' + COLORS.activeBg + ' !important;border-color:' + COLORS.activeBorder + ' !important;color:' + COLORS.text + ' !important}',
      '#apex-global-nav .apex-domain-btn:focus-visible{box-shadow:0 0 0 2px rgba(88,166,255,.55)}',
      '#apex-global-nav .apex-nav-link{outline:none;color:' + COLORS.muted + ' !important}',
      '#apex-global-nav .apex-nav-link:hover{color:' + COLORS.text + ' !important;background:rgba(240,246,252,.08) !important}',
      '#apex-global-nav .apex-nav-link[data-active="true"]{color:' + COLORS.text + ' !important;background:' + COLORS.activeBg + ' !important;border-left:3px solid ' + COLORS.accent + ' !important;padding-left:11px !important;font-weight:600 !important}',
      '#apex-global-nav .apex-nav-link:focus-visible{background:rgba(240,246,252,.08)!important;color:' + COLORS.text + '!important}',
      '#apex-global-nav, #apex-global-nav *{color-scheme:dark}',
    ].join('');
    document.head.appendChild(style);
  }

  function buildPageLink(page) {
    var active = isActivePage(page.href);
    return [
      '<a class="apex-nav-link" data-active="', active ? 'true' : 'false', '" href="', page.href, '" style="',
      'display:block;',
      'padding:10px 14px;',
      'font-size:12px;',
      'text-decoration:none;',
      'white-space:nowrap;',
      'color:', active ? COLORS.text : COLORS.muted, ';',
      active ? 'background:' + COLORS.activeBg + ';border-left:3px solid ' + COLORS.accent + ';padding-left:11px;font-weight:600;' : '',
      'transition:color .12s,background .12s,border-color .12s;',
      '"',
      ' onmouseover="this.style.color=\'', COLORS.text, '\';this.style.background=\'rgba(240,246,252,0.08)\'"',
      ' onmouseout="this.style.color=\'', active ? COLORS.text : COLORS.muted, '\';this.style.background=\'', active ? COLORS.activeBg : 'transparent', '\'"',
      '>',
      page.label,
      '</a>',
    ].join('');
  }

  function buildDomain(domain) {
    var active = isActiveDomain(domain);
    var activePage = getActivePage(domain);
    var buttonColor = COLORS.text;
    var buttonBg = active ? COLORS.activeBg : COLORS.btnBg;
    var buttonBorder = active ? COLORS.activeBorder : COLORS.border;

    return [
      '<div class="apex-nav-domain">',
        '<button class="apex-domain-btn" data-active="', active ? 'true' : 'false', '" type="button" aria-haspopup="true" aria-expanded="false" style="',
          'background:', buttonBg, ';',
          'border:1px solid ', buttonBorder, ';',
          'cursor:pointer;',
          'font-family:', FONT, ';',
          'font-size:13px;',
          'font-weight:', active ? '700' : '700', ';',
          'color:', buttonColor, ';',
          'padding:8px 14px;',
          'border-radius:8px;',
          'white-space:nowrap;',
          'display:flex;align-items:center;gap:4px;',
          'min-height:38px;',
          'appearance:none;',
          '-webkit-appearance:none;',
          'box-shadow:', active ? '0 0 0 1px rgba(88,166,255,.14), inset 0 1px 0 rgba(255,255,255,.04)' : 'inset 0 1px 0 rgba(255,255,255,.03)', ';',
          'transition:color .12s,background .12s,border-color .12s,box-shadow .12s,transform .12s;',
        '"',
        ' onmouseover="this.style.color=\'', COLORS.text, '\';this.style.background=\'', active ? COLORS.activeBg : COLORS.btnHover, '\';this.style.borderColor=\'', active ? COLORS.activeBorder : 'rgba(240,246,252,.32)', '\';this.style.transform=\'translateY(-1px)\';this.style.boxShadow=\'0 6px 18px rgba(0,0,0,.25)\'"',
        ' onmouseout="this.style.color=\'', buttonColor, '\';this.style.background=\'', buttonBg, '\';this.style.borderColor=\'', buttonBorder, '\';this.style.transform=\'translateY(0)\';this.style.boxShadow=\'', active ? '0 0 0 1px rgba(88,166,255,.14), inset 0 1px 0 rgba(255,255,255,.04)' : 'inset 0 1px 0 rgba(255,255,255,.03)', '\'"',
        '>',
          domain.label,
          active && activePage ? '<span style="font-size:10px;color:' + COLORS.text + ';margin-left:6px;padding:2px 7px;border-radius:999px;background:' + COLORS.locationBg + ';border:1px solid rgba(88,166,255,.28)"> ' + activePage.label + '</span>' : '',
          '<span style="font-size:11px;opacity:1;line-height:1;margin-left:4px;color:' + COLORS.accent + '">&#9660;</span>',
        '</button>',
        '<div class="apex-nav-dropdown" style="',
          'display:none;',
          'position:absolute;',
          'top:calc(100% + 6px);',
          'left:0;',
          'background:', COLORS.panel, ';',
          'border:1px solid ', COLORS.border, ';',
          'border-radius:8px;',
          'padding:6px 0;',
          'min-width:190px;',
          'z-index:10000;',
          'box-shadow:0 18px 40px rgba(0,0,0,.58);',
        '">',
          domain.pages.map(buildPageLink).join(''),
        '</div>',
      '</div>',
    ].join('');
  }

  injectStyles();

  var nav = document.createElement('nav');
  nav.id = 'apex-global-nav';
  nav.setAttribute('role', 'navigation');
  var locationHtml = '';
  for (var i = 0; i < DOMAINS.length; i += 1) {
    if (isActiveDomain(DOMAINS[i])) {
      var page = getActivePage(DOMAINS[i]);
      locationHtml = '<div style="padding:7px 10px;border-radius:8px;background:' + COLORS.locationBg + ';border:1px solid rgba(88,166,255,.24);color:' + COLORS.text + ';font-size:11px;font-weight:600;white-space:nowrap">' + DOMAINS[i].label + (page ? ' / ' + page.label : '') + '</div>';
      break;
    }
  }

  nav.innerHTML =
    '<div style="display:flex;align-items:center;gap:2px;min-width:0">' +
      '<a href="/" id="apex-brand" style="' +
        'color:' + COLORS.accent + ';' +
        'font-weight:800;' +
        'font-size:14px;' +
        'letter-spacing:0.03em;' +
        'margin-right:16px;' +
        'text-decoration:none;' +
        'white-space:nowrap;' +
        'user-select:none;' +
      '" onmouseover="this.style.opacity=\'0.7\'" onmouseout="this.style.opacity=\'1\'">Apex&#160;Global&#160;Bank</a>' +
      '<div style="width:1px;height:24px;background:' + COLORS.border + ';margin-right:12px;flex-shrink:0;"></div>' +
      '<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;min-width:0">' + DOMAINS.map(buildDomain).join('') + '</div>' +
    '</div>' +
    '<div style="display:flex;align-items:center;gap:10px;min-width:0">' + locationHtml + '<div id="apex-nav-right" style="display:flex;align-items:center;gap:10px;"></div></div>';

  nav.style.cssText = [
    'position:fixed', 'top:0', 'left:0', 'right:0',
    'z-index:9999',
    'height:' + NAV_H,
    'background:linear-gradient(180deg, rgba(13,17,23,.98), rgba(13,17,23,.94))',
    'border-bottom:1px solid ' + COLORS.border,
    'color:' + COLORS.text,
    'display:flex', 'align-items:center', 'justify-content:space-between',
    'padding:0 20px',
    'font-family:' + FONT,
    'box-sizing:border-box',
    'backdrop-filter:blur(10px)',
    'box-shadow:0 10px 28px rgba(0,0,0,.22)',
  ].join(';');

  if (document.body.firstChild) {
    document.body.insertBefore(nav, document.body.firstChild);
  } else {
    document.body.appendChild(nav);
  }

  var existingPad = parseInt(document.body.style.paddingTop, 10) || 0;
  if (existingPad < parseInt(NAV_H, 10)) {
    document.body.style.paddingTop = NAV_H;
  }

  var domainEls = nav.querySelectorAll('.apex-nav-domain');

  function closeAll() {
    domainEls.forEach(function (el) {
      el.querySelector('.apex-nav-dropdown').style.display = 'none';
      el.querySelector('.apex-domain-btn').setAttribute('aria-expanded', 'false');
    });
  }

  domainEls.forEach(function (domEl) {
    var dropdown = domEl.querySelector('.apex-nav-dropdown');
    var button = domEl.querySelector('.apex-domain-btn');
    var hideTimer;

    function showDropdown() {
      clearTimeout(hideTimer);
      closeAll();
      dropdown.style.display = 'block';
      button.setAttribute('aria-expanded', 'true');
    }

    function scheduleHide() {
      hideTimer = setTimeout(function () {
        dropdown.style.display = 'none';
        button.setAttribute('aria-expanded', 'false');
      }, 120);
    }

    domEl.addEventListener('mouseenter', showDropdown);
    domEl.addEventListener('mouseleave', scheduleHide);
    dropdown.addEventListener('mouseenter', function () { clearTimeout(hideTimer); });
    dropdown.addEventListener('mouseleave', scheduleHide);

    button.addEventListener('click', function (e) {
      e.stopPropagation();
      var visible = dropdown.style.display === 'block';
      closeAll();
      if (!visible) {
        dropdown.style.display = 'block';
        button.setAttribute('aria-expanded', 'true');
      }
    });

    button.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        showDropdown();
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        showDropdown();
        var firstLink = dropdown.querySelector('a');
        if (firstLink) firstLink.focus();
      } else if (e.key === 'Escape') {
        closeAll();
        button.focus();
      }
    });
  });

  document.addEventListener('click', closeAll);
}());
