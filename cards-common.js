/**
 * Shared utilities for In-Between recipe cards.
 */
(function (global) {
  'use strict';

  function normalizeConnection(conn) {
    if (Array.isArray(conn)) {
      return { from: conn[0], to: conn[1], color: conn[2], dash: !!conn[3] };
    }
    return conn;
  }

  function drawBezierNoodle(svg, rect, fromId, toId, color, options) {
    const dash = options.dash || false;
    const enhanced = options.enhanced || false;

    const e1 = document.getElementById(fromId);
    const e2 = document.getElementById(toId);
    if (!e1 || !e2) return;

    const r1 = e1.getBoundingClientRect();
    const r2 = e2.getBoundingClientRect();
    const x1 = r1.left + r1.width / 2 - rect.left;
    const y1 = r1.top + r1.height / 2 - rect.top;
    const x2 = r2.left + r2.width / 2 - rect.left;
    const y2 = r2.top + r2.height / 2 - rect.top;

    let d;
    if (enhanced) {
      const dx = Math.abs(x2 - x1);
      const cx1 = x1 + dx * 0.45;
      const cx2 = x2 - dx * 0.45;
      const c1y = y1 + (y2 - y1) * 0.2;
      const c2y = y2 - (y2 - y1) * 0.2;
      d = 'M ' + x1 + ' ' + y1 + ' C ' + cx1 + ' ' + c1y + ', ' + cx2 + ' ' + c2y + ', ' + x2 + ' ' + y2;
    } else {
      const dx = Math.abs(x2 - x1) * 0.5;
      d = 'M ' + x1 + ' ' + y1 + ' C ' + (x1 + dx) + ' ' + y1 + ', ' + (x2 - dx) + ' ' + y2 + ', ' + x2 + ' ' + y2;
    }

    if (enhanced) {
      const glow = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      glow.setAttribute('d', d);
      glow.setAttribute('stroke', color);
      glow.setAttribute('stroke-width', '6');
      glow.setAttribute('fill', 'none');
      glow.setAttribute('opacity', '0.12');
      glow.setAttribute('class', 'm-noodle-glow');
      svg.appendChild(glow);
    }

    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', d);
    path.setAttribute('stroke', color);
    path.setAttribute('stroke-width', enhanced ? '2.5' : '2');
    path.setAttribute('fill', 'none');
    path.setAttribute('opacity', '0.7');
    if (dash) path.setAttribute('stroke-dasharray', '4 3');
    if (enhanced) path.setAttribute('class', 'm-noodle');
    svg.appendChild(path);

    if (enhanced) {
      [[x1, y1], [x2, y2]].forEach(function (pt) {
        const dot = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        dot.setAttribute('cx', pt[0]);
        dot.setAttribute('cy', pt[1]);
        dot.setAttribute('r', '3');
        dot.setAttribute('fill', color);
        dot.setAttribute('opacity', '0.8');
        svg.appendChild(dot);
      });
    }
  }

  function setupCopyButton(copyBtn, textEl) {
    if (!copyBtn || !textEl) return;

    copyBtn.addEventListener('click', async function () {
      const text = textEl.textContent;
      try {
        await navigator.clipboard.writeText(text);
      } catch (err) {
        const textarea = document.createElement('textarea');
        textarea.value = text;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
      }
      this.textContent = '\u2713 Copied!';
      this.classList.add('copied');
      setTimeout(function () {
        copyBtn.textContent = 'Copy';
        copyBtn.classList.remove('copied');
      }, 2000);
    });
  }

  function setupNodeGraph(options) {
    const detailsEl = options.detailsEl;
    const containerEl = options.containerEl;
    const canvasEl = options.canvasEl;
    const svgEl = options.svgEl;
    const connections = options.connections || [];
    const enhanced = !!options.enhanced;
    const openDelay = options.openDelay != null ? options.openDelay : 50;

    if (!detailsEl || !containerEl || !canvasEl || !svgEl) {
      return { redraw: function () {}, disconnect: function () {} };
    }

    let noodlesDrawn = false;
    let resizeObserver = null;
    let resizeTimeout;

    function drawNoodles() {
      svgEl.innerHTML = '';
      const rect = canvasEl.getBoundingClientRect();
      connections.forEach(function (conn) {
        const c = normalizeConnection(conn);
        drawBezierNoodle(svgEl, rect, c.from, c.to, c.color, { dash: c.dash, enhanced: enhanced });
      });
      noodlesDrawn = true;
    }

    detailsEl.addEventListener('toggle', function () {
      if (this.open && !noodlesDrawn) {
        setTimeout(drawNoodles, openDelay);
      }
    });

    if (window.ResizeObserver) {
      resizeObserver = new ResizeObserver(function () {
        if (detailsEl.open && noodlesDrawn) drawNoodles();
      });
      resizeObserver.observe(containerEl);
    }

    window.addEventListener('resize', function () {
      clearTimeout(resizeTimeout);
      resizeTimeout = setTimeout(function () {
        if (detailsEl.open && noodlesDrawn) drawNoodles();
      }, 200);
    }, { passive: true });

    return {
      redraw: drawNoodles,
      disconnect: function () {
        if (resizeObserver) resizeObserver.disconnect();
      }
    };
  }

  global.CardCommon = {
    setupCopyButton: setupCopyButton,
    setupNodeGraph: setupNodeGraph
  };
})(window);
