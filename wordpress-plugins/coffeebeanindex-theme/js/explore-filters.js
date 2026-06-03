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

    // ── Mobile sidebar drawer ────────────────────────────────────────────────

    if (sidebarToggle && sidebarInner) {
        sidebarToggle.addEventListener('click', function () {
            var expanded = sidebarToggle.getAttribute('aria-expanded') === 'true';
            var next     = !expanded;
            sidebarToggle.setAttribute('aria-expanded', next);
            sidebarInner.classList.toggle('is-open', next);
        });
    }

    // ── Rating slider live label ─────────────────────────────────────────────

    if (ratingSlider && ratingValEl) {
        ratingSlider.addEventListener('input', function () {
            ratingValEl.textContent = ratingSlider.value;
            applyFilters();
        });
    }

    // ── Checkbox changes ────────────────────────────────────────────────────

    document.querySelectorAll('.explore-filter-cb').forEach(function (cb) {
        cb.addEventListener('change', applyFilters);
    });

    // ── Sort ────────────────────────────────────────────────────────────────

    if (sortSelect) {
        sortSelect.addEventListener('change', function () {
            applySort(sortSelect.value);
            applyFilters();
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
        applyFilters();
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

    function applyFilters() {
        var checkedOrigin  = getChecked('origin');
        var checkedRoast   = getChecked('roast');
        var checkedProcess = getChecked('process');
        var checkedFlavor  = getChecked('flavor');
        var checkedBrew    = getChecked('brew');
        var minRating      = ratingSlider ? parseInt(ratingSlider.value, 10) : 1;

        var cards   = grid.querySelectorAll('.explore-card');
        var visible = 0;

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

            card.style.display = show ? '' : 'none';
            if (show) visible++;
        });

        if (countEl) {
            countEl.textContent = visible + ' bean' + (visible !== 1 ? 's' : '') + ' found';
        }
        if (emptyEl) {
            emptyEl.style.display = visible === 0 ? '' : 'none';
        }
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
