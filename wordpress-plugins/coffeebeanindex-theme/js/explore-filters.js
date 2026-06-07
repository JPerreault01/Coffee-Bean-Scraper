/**
 * explore-filters.js
 * Client-side filtering and sorting for the /explore/ bean discovery page.
 *
 * Logic:
 *   - Within one facet group: OR  (Ethiopia OR Colombia)
 *   - Across facet groups:   AND  (Ethiopia AND Light AND Washed)
 *   - Minimum rating:        >= N (unrated beans always pass)
 *   - Sort: reorders DOM nodes in the grid container
 *
 * No AJAX, no REST, no external libraries. All cards are in the DOM on load.
 */

(function () {
    'use strict';

    var grid          = document.getElementById('explore-grid');
    var countEl       = document.getElementById('explore-count');
    var emptyEl       = document.getElementById('explore-empty');
    var sortSelect    = document.getElementById('explore-sort');
    var ratingSlider  = document.getElementById('filter-rating');
    var ratingValEl   = document.getElementById('filter-rating-value');
    var clearBtn      = document.getElementById('explore-clear-all');
    var emptyClearBtn = document.getElementById('explore-empty-clear');
    var sidebarToggle = document.getElementById('explore-sidebar-toggle');
    var sidebarInner  = document.getElementById('explore-sidebar-inner');

    if (!grid) return;

    // ── Pagination state ─────────────────────────────────────────────────────
    // The page renders every matched bean server-side for instant filtering,
    // but only one page's worth is shown at a time so the visible DOM (and the
    // bag images, once they land) isn't all painted at once. Off-page images
    // keep loading="lazy" and never fetch until paged into view.

    var PAGE_SIZE   = 24;
    var currentPage = 1;

    // Pagination control lives directly below the grid; inject it if absent.
    var paginationEl = document.getElementById('explore-pagination');
    if (!paginationEl) {
        paginationEl = document.createElement('nav');
        paginationEl.id = 'explore-pagination';
        paginationEl.className = 'explore-pagination';
        paginationEl.setAttribute('aria-label', 'Bean grid pagination');
        grid.insertAdjacentElement('afterend', paginationEl);
    }

    // ── Mobile sidebar drawer ────────────────────────────────────────────────

    if (sidebarToggle && sidebarInner) {
        sidebarToggle.addEventListener('click', function () {
            var expanded = sidebarToggle.getAttribute('aria-expanded') === 'true';
            var next     = !expanded;
            sidebarToggle.setAttribute('aria-expanded', next);
            sidebarInner.classList.toggle('is-open', next);
        });
    }

    // ── Flavor facet: Simple / Advanced toggle ───────────────────────────────
    // Both views share the "flavor" filter group. On switch, the now-hidden
    // panel's checkboxes are cleared so stale selections don't leak into the
    // active view's filter. No reload — pure show/hide on rendered DOM.

    var flavorToggleBtns = document.querySelectorAll('.explore-flavor-toggle__btn');
    var flavorPanels     = document.querySelectorAll('[data-flavor-view-panel]');

    function setFlavorView(view) {
        flavorToggleBtns.forEach(function (btn) {
            var active = btn.getAttribute('data-flavor-view') === view;
            btn.classList.toggle('is-active', active);
            btn.setAttribute('aria-pressed', active ? 'true' : 'false');
        });

        var changed = false;
        flavorPanels.forEach(function (panel) {
            var show = panel.getAttribute('data-flavor-view-panel') === view;
            panel.hidden = !show;
            if (!show) {
                panel.querySelectorAll('.explore-filter-cb:checked').forEach(function (cb) {
                    cb.checked = false;
                    changed = true;
                });
            }
        });

        if (changed) applyFiltersReset();
    }

    flavorToggleBtns.forEach(function (btn) {
        btn.addEventListener('click', function () {
            setFlavorView(btn.getAttribute('data-flavor-view'));
        });
    });

    // ── Rating slider live label ─────────────────────────────────────────────

    if (ratingSlider && ratingValEl) {
        ratingSlider.addEventListener('input', function () {
            ratingValEl.textContent = ratingSlider.value;
            applyFiltersReset();
        });
    }

    // ── Checkbox changes ────────────────────────────────────────────────────

    document.querySelectorAll('.explore-filter-cb').forEach(function (cb) {
        cb.addEventListener('change', applyFiltersReset);
    });

    // ── Sort ────────────────────────────────────────────────────────────────

    if (sortSelect) {
        sortSelect.addEventListener('change', function () {
            applySort(sortSelect.value);
            applyFiltersReset();
        });
    }

    // ── Clear all ───────────────────────────────────────────────────────────

    function clearAll() {
        document.querySelectorAll('.explore-filter-cb').forEach(function (cb) {
            cb.checked = false;
        });
        if (ratingSlider) {
            ratingSlider.value = 1;
            if (ratingValEl) ratingValEl.textContent = '1';
        }
        applyFiltersReset();
    }

    if (clearBtn)      clearBtn.addEventListener('click', clearAll);
    if (emptyClearBtn) emptyClearBtn.addEventListener('click', clearAll);

    // ── Core helpers ────────────────────────────────────────────────────────

    function getChecked(group) {
        return Array.from(
            document.querySelectorAll('.explore-filter-cb[data-filter-group="' + group + '"]:checked')
        ).map(function (el) { return el.value; });
    }

    function slugsOf(cardDataValue) {
        return (cardDataValue || '').split(' ').filter(Boolean);
    }

    function matchesGroup(checkedValues, cardSlugs) {
        if (!checkedValues.length) return true;
        for (var i = 0; i < checkedValues.length; i++) {
            if (cardSlugs.indexOf(checkedValues[i]) > -1) return true;
        }
        return false;
    }

    // ── Filter ──────────────────────────────────────────────────────────────
    // Filter or sort changes reset to page 1; page-button clicks call
    // applyFilters() directly so the current page is preserved.

    function applyFiltersReset() {
        currentPage = 1;
        applyFilters();
    }

    function applyFilters() {
        var checkedOrigin  = getChecked('origin');
        var checkedRoast   = getChecked('roast');
        var checkedProcess = getChecked('process');
        var checkedFlavor  = getChecked('flavor');
        var checkedBrew    = getChecked('brew');
        var minRating      = ratingSlider ? parseInt(ratingSlider.value, 10) : 1;

        // grid.querySelectorAll returns cards in DOM order, which applySort()
        // keeps in sorted order — so `matched` is already filtered AND sorted.
        var cards   = grid.querySelectorAll('.explore-card');
        var matched = [];

        cards.forEach(function (card) {
            var origins  = slugsOf(card.dataset.origin);
            var roasts   = slugsOf(card.dataset.roast);
            var procs    = slugsOf(card.dataset.process);
            var flavors  = slugsOf(card.dataset.flavor);
            var brews    = slugsOf(card.dataset.brew);
            var rating   = parseFloat(card.dataset.rating) || 0;

            // Unrated beans always pass the rating filter
            var passRating = !rating || rating >= minRating;

            var show =
                matchesGroup(checkedOrigin,  origins)  &&
                matchesGroup(checkedRoast,   roasts)   &&
                matchesGroup(checkedProcess, procs)    &&
                matchesGroup(checkedFlavor,  flavors)  &&
                matchesGroup(checkedBrew,    brews)    &&
                passRating;

            if (show) {
                matched.push(card);
            } else {
                card.style.display = 'none';
            }
        });

        renderPage(matched);

        if (emptyEl) {
            emptyEl.style.display = matched.length === 0 ? '' : 'none';
        }
    }

    // ── Pagination over the filtered + sorted result set ──────────────────────

    function renderPage(matched) {
        var total      = matched.length;
        var totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
        if (currentPage > totalPages) currentPage = totalPages;

        var start = (currentPage - 1) * PAGE_SIZE;
        var end   = start + PAGE_SIZE;

        matched.forEach(function (card, i) {
            card.style.display = (i >= start && i < end) ? '' : 'none';
        });

        if (countEl) {
            if (total === 0) {
                countEl.textContent = '0 beans found';
            } else {
                var from = start + 1;
                var to   = Math.min(end, total);
                countEl.textContent =
                    total + ' bean' + (total !== 1 ? 's' : '') + ' found · showing ' + from + '-' + to;
            }
        }

        renderPagination(totalPages);
    }

    function renderPagination(totalPages) {
        if (!paginationEl) return;

        // One page (or none): nothing to page through.
        if (totalPages <= 1) {
            paginationEl.innerHTML = '';
            paginationEl.style.display = 'none';
            return;
        }
        paginationEl.style.display = '';
        paginationEl.innerHTML = '';

        function makeBtn(label, page, opts) {
            opts = opts || {};
            var b = document.createElement('button');
            b.type = 'button';
            b.textContent = label;
            if (opts.disabled)  b.disabled = true;
            if (opts.current)   b.setAttribute('aria-current', 'page');
            if (opts.ariaLabel) b.setAttribute('aria-label', opts.ariaLabel);
            if (!opts.disabled && !opts.current) {
                b.addEventListener('click', function () {
                    currentPage = page;
                    applyFilters();
                    grid.scrollIntoView({ behavior: 'smooth', block: 'start' });
                });
            }
            paginationEl.appendChild(b);
        }

        makeBtn('‹', currentPage - 1, { disabled: currentPage === 1, ariaLabel: 'Previous page' });
        for (var p = 1; p <= totalPages; p++) {
            makeBtn(String(p), p, { current: p === currentPage });
        }
        makeBtn('›', currentPage + 1, { disabled: currentPage === totalPages, ariaLabel: 'Next page' });
    }

    // ── Sort ────────────────────────────────────────────────────────────────

    function applySort(sortValue) {
        var cards = Array.from(grid.querySelectorAll('.explore-card'));

        cards.sort(function (a, b) {
            var rA, rB, pA, pB, nA, nB;

            if (sortValue === 'rating') {
                rA = parseFloat(a.dataset.rating) || 0;
                rB = parseFloat(b.dataset.rating) || 0;
                return rB - rA;
            }

            if (sortValue === 'price') {
                pA = parseFloat(a.dataset.price) || 0;
                pB = parseFloat(b.dataset.price) || 0;
                // Unpriced beans sort to end
                if (pA === 0 && pB !== 0) return 1;
                if (pB === 0 && pA !== 0) return -1;
                return pA - pB;
            }

            if (sortValue === 'name') {
                nA = a.dataset.name || '';
                nB = b.dataset.name || '';
                return nA.localeCompare(nB);
            }

            return 0;
        });

        cards.forEach(function (card) { grid.appendChild(card); });
    }

    // ── Init ────────────────────────────────────────────────────────────────

    applySort('rating');
    applyFilters();

})();
