/**
 * glossary.js — Apex Global Bank financial term tooltips
 *
 * Auto-detects known financial terms in table headers, KPI labels, and
 * card titles across all dashboards. Shows a floating definition on hover.
 * Works on both static and dynamically injected content via MutationObserver.
 */
(function () {
  /* ── Glossary dictionary ─────────────────────────────────────────────── */
  var GLOSSARY = {
    'Delta':     'Rate of change of option/portfolio value with respect to a $1 move in the underlying price.',
    'Gamma':     'Rate of change of Delta; measures convexity of P&L with respect to the underlying.',
    'Vega':      'Sensitivity of option value to a 1% change in implied volatility.',
    'Theta':     'Time decay — option value lost per calendar day, all else equal.',
    'Rho':       'Sensitivity of option value to a 1 basis-point change in the risk-free rate.',
    'DV01':      'Dollar value of a 1-basis-point (0.01%) move in yield; the primary fixed-income risk measure.',
    'PV01':      'Present value change for a 1 bp parallel shift in the yield curve. Synonymous with DV01.',
    'CVA':       'Credit Valuation Adjustment — cost of counterparty default risk, subtracted from the clean MTM of a derivative.',
    'DVA':       'Debit Valuation Adjustment — benefit arising from one\'s own credit risk; the symmetric counterpart of CVA.',
    'FVA':       'Funding Valuation Adjustment — cost or benefit of funding uncollateralised derivative positions.',
    'BCVA':      'Bilateral CVA — combines CVA and DVA into one symmetric counterparty risk valuation adjustment.',
    'XVA':       'Collective umbrella term for valuation adjustments: CVA, DVA, FVA, ColVA, KVA, MVA.',
    'PFE':       'Potential Future Exposure — high-percentile (e.g. 95%) simulated future MTM, used in CCR limit monitoring.',
    'EE':        'Expected Exposure — probability-weighted average positive MTM at a future time horizon.',
    'EPE':       'Expected Positive Exposure — time-average of EE over the remaining life of a trade.',
    'EEPE':      'Effective Expected Positive Exposure — non-decreasing EPE profile used in the Basel SA-CCR capital formula.',
    'CCR':       'Counterparty Credit Risk — the risk that a counterparty defaults before final settlement of a contract.',
    'VaR':       'Value at Risk — the loss not expected to be exceeded with a given confidence level (e.g. 99%) over a set horizon (e.g. 1 day).',
    'ES':        'Expected Shortfall (a.k.a. CVaR) — average loss in the worst tail scenarios beyond the VaR threshold. FRTB capital uses 97.5% ES.',
    'FRTB':      'Fundamental Review of the Trading Book — Basel III/IV market-risk capital framework replacing the old 1996 IMA/SA regime.',
    'IMA':       'Internal Models Approach — regulator-approved VaR/ES model used for market-risk capital under FRTB.',
    'SA':        'Standardised Approach — the rule-based fallback capital calculation method under FRTB.',
    'RWA':       'Risk-Weighted Assets — on- and off-balance-sheet assets scaled by regulatory risk weights; the denominator of capital ratios.',
    'CET1':      'Common Equity Tier 1 — highest-quality regulatory capital: retained earnings and common shares net of deductions.',
    'LCR':       'Liquidity Coverage Ratio — HQLA stock must cover ≥ 100% of net cash outflows over a 30-day stress scenario.',
    'NSFR':      'Net Stable Funding Ratio — available stable funding must exceed required stable funding ≥ 100% over a 1-year horizon.',
    'DFAST':     'Dodd-Frank Act Stress Test — annual Fed scenario exercise projecting bank CET1 over 9 quarters under Severely Adverse conditions.',
    'CCAR':      'Comprehensive Capital Analysis and Review — annual Fed capital adequacy assessment for US systemically important banks.',
    'OAS':       'Option-Adjusted Spread — yield spread over the benchmark curve after removing the value of embedded options (e.g. MBS prepayment).',
    'Duration':  'Sensitivity of a bond\'s price to a parallel shift in yields, measured in years. Also called modified or effective duration.',
    'Convexity': 'Second-order price sensitivity to yield changes; positive convexity means the price rises faster than it falls for equal-sized moves.',
    'SOFR':      'Secured Overnight Financing Rate — the ARRC-selected USD risk-free rate based on overnight Treasury repo, replacing USD LIBOR.',
    'LIBOR':     'London Interbank Offered Rate — the legacy unsecured benchmark rate for major currencies; fully ceased end-2023.',
    'MTD':       'Month-to-date — cumulative P&L or flow from the first calendar day of the current month.',
    'YTD':       'Year-to-date — cumulative figure from January 1 of the current calendar year.',
    'MTM':       'Mark-to-Market — current fair value of a position based on observable market prices or models.',
    'P&L':       'Profit & Loss — net financial result; in trading, decomposed into Greek attribution buckets (Delta, Gamma, Vega, Theta, etc.).',
    'IM':        'Initial Margin — collateral posted upfront to cover potential future exposure in bilateral or cleared derivative trades.',
    'VM':        'Variation Margin — daily (or intraday) cash collateral exchanged to settle MTM moves under a Credit Support Annex.',
    'SIMM':      'ISDA Standard Initial Margin Model — industry-standard IM calculation for uncleared OTC derivatives (version 2.x).',
    'MPoR':      'Margin Period of Risk — the time from the last successful VM exchange to trade close-out; key driver of IM size.',
    'CSA':       'Credit Support Annex — ISDA schedule specifying collateral terms: thresholds, minimum transfer amounts, eligible currency.',
    'CCP':       'Central Counterparty — clearing house that interposes itself as buyer to every seller and seller to every buyer, mutualising default risk.',
    'ALM':       'Asset-Liability Management — managing the mismatch between asset and liability duration, repricing, and cash-flows to control rate and liquidity risk.',
    'FTP':       'Funds Transfer Pricing — internal rate at which treasury charges or credits business lines for their use of or provision of funding.',
    'RAROC':     'Risk-Adjusted Return on Capital — business-line return divided by economic capital; used for performance measurement and pricing.',
    'NMD':       'Non-Maturing Deposits — deposits with no contractual maturity (e.g. current/savings accounts); modelled behaviourally for ALM and LCR.',
    'MBS':       'Mortgage-Backed Security — ABS collateralised by a pool of residential mortgage loans, often with agency (FNMA/FHLMC) guarantee.',
    'ABS':       'Asset-Backed Security — bond backed by a pool of consumer or corporate loans or receivables (auto, credit card, student loans).',
    'CMBS':      'Commercial Mortgage-Backed Security — structured bond backed by a pool of commercial real estate loans.',
    'CLO':       'Collateralised Loan Obligation — structured vehicle backed by a diversified pool of leveraged corporate loans, tranched by seniority.',
    'WAC':       'Weighted Average Coupon — weighted average interest rate of the loans in an MBS or ABS pool.',
    'WAM':       'Weighted Average Maturity — weighted average remaining term of the loans in an MBS or ABS pool.',
    'CPR':       'Conditional Prepayment Rate — annualised fraction of the pool principal expected to prepay each year.',
    'PSA':       'Public Securities Association prepayment model — benchmark ramp (100% PSA = 6% CPR by month 30 of a new mortgage pool).',
    'IFRS 9':    'International accounting standard governing classification/measurement of financial instruments and Expected Credit Loss provisioning.',
    'ECL':       'Expected Credit Loss — IFRS 9 impairment estimate: PD × LGD × EAD, discounted at the effective interest rate.',
    'PD':        'Probability of Default — estimated likelihood a borrower defaults within a 12-month or lifetime horizon.',
    'LGD':       'Loss Given Default — fraction of the exposure not recovered after default; equals 1 minus the recovery rate.',
    'EAD':       'Exposure at Default — estimated outstanding drawn balance at the time of a default event.',
    'SR 11-7':   'Federal Reserve supervisory guidance (2011) on model risk management: independent validation, documentation, and governance of all models.',
    'Repo':      'Repurchase Agreement — short-term secured borrowing where securities are sold and simultaneously agreed to be repurchased at a higher price.',
    'Haircut':   'Discount applied to collateral market value to buffer price volatility; e.g. a 5% haircut means $100 of bonds counts as $95 of collateral.',
    'HQLA':      'High-Quality Liquid Assets — assets eligible for the LCR numerator: Level 1 (cash, central bank reserves, sovereigns) and Level 2 (IG corporates, covered bonds).',
    'Notional':  'Face or reference amount of a derivative used to compute cash-flows; not typically exchanged (except in cross-currency swaps).',
    'Spread':    'Difference in yield or rate between two instruments; e.g. credit spread = bond yield minus the risk-free benchmark.',
    'Utilisation': 'Proportion of a risk or credit limit that has been consumed; utilisation = current exposure ÷ limit.',
  };

  /* ── Build sorted key list (longest first, for greedy matching) ────── */
  var TERMS = Object.keys(GLOSSARY).sort(function (a, b) {
    return b.length - a.length;
  });

  /* ── Escape a string for use in a RegExp ────────────────────────────── */
  function escapeRe(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  /* ── Build a combined regex that matches any glossary term ────────────
   *  Word boundaries (\b) are used so "ES" doesn't match inside "FRTB".
   *  We build one alternation for efficiency.                           */
  var pattern = new RegExp(
    '\\b(' + TERMS.map(escapeRe).join('|') + ')\\b',
    'g'
  );

  /* ── Tooltip element ─────────────────────────────────────────────────── */
  var tip = document.createElement('div');
  tip.id = 'gloss-tip';
  document.body.appendChild(tip);

  function showTip(el, def) {
    tip.textContent = def;
    tip.classList.add('visible');

    var rect = el.getBoundingClientRect();
    var tipW = tip.offsetWidth;
    var tipH = tip.offsetHeight;
    var vw   = window.innerWidth;
    var vh   = window.innerHeight;
    var GAP  = 6;

    // Prefer above; flip below if insufficient space
    var top = rect.top - tipH - GAP;
    if (top < GAP) top = rect.bottom + GAP;

    // Centre horizontally over element, clamped to viewport
    var left = rect.left + rect.width / 2 - tipW / 2;
    left = Math.max(GAP, Math.min(left, vw - tipW - GAP));

    tip.style.top  = top  + 'px';
    tip.style.left = left + 'px';
  }

  function hideTip() {
    tip.classList.remove('visible');
  }

  /* ── Target selectors — elements where we scan for terms ────────────── */
  var TARGETS = [
    'th', 'td',
    '.kpi-label', '.kpi-title', '.kpi-box',
    '.card-title', '.section-header',
    '.metric-label', '.gauge-label',
    '.badge',
    'label',
    '[data-glossary]',
  ].join(',');

  /* ── Wrap glossary terms in a single text node ───────────────────────── */
  function wrapTextNode(node) {
    var text = node.nodeValue;
    if (!text || !text.trim()) return;

    // Reset regex state
    pattern.lastIndex = 0;
    if (!pattern.test(text)) return;
    pattern.lastIndex = 0;

    var frag   = document.createDocumentFragment();
    var last   = 0;
    var match;

    while ((match = pattern.exec(text)) !== null) {
      var term = match[1];
      var def  = GLOSSARY[term];
      if (!def) continue;

      // Text before the match
      if (match.index > last) {
        frag.appendChild(document.createTextNode(text.slice(last, match.index)));
      }

      var span = document.createElement('span');
      span.className     = 'gloss';
      span.dataset.g     = term;
      span.textContent   = term;
      frag.appendChild(span);

      last = match.index + term.length;
    }

    if (last === 0) return; // no matches — leave node untouched

    // Remaining text after last match
    if (last < text.length) {
      frag.appendChild(document.createTextNode(text.slice(last)));
    }

    node.parentNode.replaceChild(frag, node);
  }

  /* ── Walk an element's text nodes and wrap known terms ───────────────── */
  function processElement(el) {
    // Skip if already processed or contains .gloss children
    if (el.querySelector && el.querySelector('.gloss')) return;
    if (el.closest && el.closest('.gloss')) return;

    // Walk only direct text nodes (don't recurse into child elements here —
    // the caller's querySelectorAll already targets the right leaf elements)
    var childNodes = Array.prototype.slice.call(el.childNodes);
    for (var i = 0; i < childNodes.length; i++) {
      var node = childNodes[i];
      if (node.nodeType === Node.TEXT_NODE) {
        wrapTextNode(node);
      }
    }
  }

  /* ── Scan a subtree for target elements and process each ─────────────── */
  function scan(root) {
    // Also check if root itself is a target
    var els;
    try {
      els = (root.querySelectorAll ? root.querySelectorAll(TARGETS) : []);
    } catch (e) {
      return;
    }
    var list = Array.prototype.slice.call(els);
    // Include root itself if it matches
    if (root.matches && root.matches(TARGETS)) list.unshift(root);
    for (var i = 0; i < list.length; i++) {
      processElement(list[i]);
    }
  }

  /* ── Tooltip event delegation ─────────────────────────────────────────── */
  document.addEventListener('mouseover', function (e) {
    var el = e.target;
    if (el && el.classList && el.classList.contains('gloss')) {
      var def = GLOSSARY[el.dataset.g];
      if (def) showTip(el, def);
    }
  });

  document.addEventListener('mouseout', function (e) {
    var el = e.target;
    if (el && el.classList && el.classList.contains('gloss')) {
      hideTip();
    }
  });

  /* ── Initial scan on DOMContentLoaded ────────────────────────────────── */
  function init() {
    scan(document.body);

    /* Watch for dynamically injected content (fetch → innerHTML) */
    var observer = new MutationObserver(function (mutations) {
      for (var i = 0; i < mutations.length; i++) {
        var added = mutations[i].addedNodes;
        for (var j = 0; j < added.length; j++) {
          var node = added[j];
          if (node.nodeType === Node.ELEMENT_NODE) {
            scan(node);
          }
        }
      }
    });

    observer.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
}());
