/**
 * guide-toc.js
 * Auto-builds a sticky table of contents for guide pages from the H2/H3
 * headings inside .entry-content / .guide-body, wires smooth-scroll, and
 * highlights the active section while scrolling.
 *
 * Enqueued ONLY on template-guide.php (see cbi_enqueue_styles() in functions.php).
 *
 * Markup it expects (rendered by template-guide.php):
 *   - #guide-toc            desktop left-rail <nav>, starts hidden
 *   - #guide-toc-list       <ol> the desktop links are injected into
 *   - #guide-toc-mobile     mobile tap-to-expand wrapper, starts hidden
 *   - #guide-toc-mobile-list <ol> the mobile links are injected into
 *   - #guide-toc-mobile-toggle  <button> that expands/collapses the mobile list
 *   - .guide-body           the article body whose H2/H3 are scanned
 *
 * No plugin, no framework, no AJAX. Degrades gracefully: if there are fewer
 * than two headings the ToC stays hidden and the article reads normally.
 */
(function () {
    'use strict';

    var body = document.querySelector('.guide-body');
    if (!body) return;

    var headings = body.querySelectorAll('h2, h3');
    if (headings.length < 2) return;

    var deskList   = document.getElementById('guide-toc-list');
    var mobList    = document.getElementById('guide-toc-mobile-list');
    var deskNav    = document.getElementById('guide-toc');
    var mobNav     = document.getElementById('guide-toc-mobile');
    var mobToggle  = document.getElementById('guide-toc-mobile-toggle');
    if (!deskList || !mobList) return;

    var links = []; // {id, deskLink, mobLink}

    function slugify(text, fallbackIndex) {
        var slug = text.toLowerCase()
            .replace(/[^\w\s-]/g, '')
            .trim()
            .replace(/\s+/g, '-');
        return slug ? 'g-' + slug : 'guide-section-' + fallbackIndex;
    }

    Array.prototype.forEach.call(headings, function (h, i) {
        // Reuse an editor-supplied id if present; otherwise generate a stable one.
        var id = h.id || slugify(h.textContent, i);
        // Guard against duplicate ids.
        if (document.getElementById(id) && document.getElementById(id) !== h) {
            id = id + '-' + i;
        }
        h.id = id;

        var level = h.tagName.toLowerCase(); // 'h2' | 'h3'
        var text  = h.textContent;

        // Desktop rail item
        var dLi = document.createElement('li');
        dLi.className = 'guide-toc__item guide-toc__item--' + level;
        var dA = document.createElement('a');
        dA.href = '#' + id;
        dA.textContent = text;
        dA.className = 'guide-toc__link';
        dLi.appendChild(dA);
        deskList.appendChild(dLi);

        // Mobile item
        var mLi = document.createElement('li');
        mLi.className = 'guide-toc__item guide-toc__item--' + level;
        var mA = document.createElement('a');
        mA.href = '#' + id;
        mA.textContent = text;
        mA.className = 'guide-toc__link';
        mLi.appendChild(mA);
        mobList.appendChild(mLi);

        links.push({ id: id, el: h, deskLink: dA, mobLink: mA });
    });

    if (deskNav) deskNav.hidden = false;
    if (mobNav)  mobNav.hidden = false;

    // ── Smooth scroll (respects reduced-motion) ──────────────────────────────
    var reduceMotion = window.matchMedia &&
        window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    function onLinkClick(e) {
        var href = this.getAttribute('href');
        if (!href || href.charAt(0) !== '#') return;
        var target = document.getElementById(href.slice(1));
        if (!target) return;
        e.preventDefault();
        target.scrollIntoView({
            behavior: reduceMotion ? 'auto' : 'smooth',
            block: 'start'
        });
        // Update the hash without a jump.
        if (history.replaceState) history.replaceState(null, '', href);
        // On mobile, collapse the list after picking a section.
        collapseMobile();
    }

    links.forEach(function (l) {
        l.deskLink.addEventListener('click', onLinkClick);
        l.mobLink.addEventListener('click', onLinkClick);
    });

    // ── Active-section highlight via IntersectionObserver ────────────────────
    function setActive(id) {
        links.forEach(function (l) {
            var on = l.id === id;
            l.deskLink.classList.toggle('is-active', on);
            l.mobLink.classList.toggle('is-active', on);
            if (on) l.deskLink.setAttribute('aria-current', 'true');
            else    l.deskLink.removeAttribute('aria-current');
        });
    }

    if ('IntersectionObserver' in window) {
        var visible = {};
        var observer = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                visible[entry.target.id] = entry.isIntersecting;
            });
            // Pick the first heading (document order) currently in view.
            for (var i = 0; i < links.length; i++) {
                if (visible[links[i].id]) { setActive(links[i].id); return; }
            }
        }, {
            // Trigger when a heading reaches the top third of the viewport.
            rootMargin: '0px 0px -70% 0px',
            threshold: 0
        });
        links.forEach(function (l) { observer.observe(l.el); });
    }

    // ── Mobile tap-to-expand ─────────────────────────────────────────────────
    function collapseMobile() {
        if (!mobToggle) return;
        mobToggle.setAttribute('aria-expanded', 'false');
        if (mobList) mobList.hidden = true;
    }
    function toggleMobile() {
        var open = mobToggle.getAttribute('aria-expanded') === 'true';
        mobToggle.setAttribute('aria-expanded', open ? 'false' : 'true');
        if (mobList) mobList.hidden = open;
    }
    if (mobToggle) {
        collapseMobile(); // start collapsed
        mobToggle.addEventListener('click', toggleMobile);
    }
})();
