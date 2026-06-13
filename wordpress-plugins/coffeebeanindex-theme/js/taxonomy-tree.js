/**
 * taxonomy-tree.js
 * Expand/collapse for the hierarchical taxonomy tree (.cbi-tree).
 *
 * Shared by:
 *   - the Explore filter tree (flavor-note + origin facets, checkbox rows)
 *   - the archive nav tree (flavor-note + origin archives, link rows)
 *
 * Markup contract (both contexts):
 *   .cbi-tree
 *     .cbi-tree__node
 *       .cbi-tree__row.cbi-tree__row--parent
 *         …row content (checkbox/link + name + count)…
 *         button.cbi-tree__chevron[aria-expanded][aria-controls="ID"]
 *       ul.cbi-tree__children#ID            (collapsed unless .is-open)
 *
 * This file ONLY toggles expansion: it flips aria-expanded on the chevron and
 * the .is-open class on the controlled children container. No AJAX, no filter
 * logic (that stays in explore-filters.js), no dependencies.
 */

(function () {
    'use strict';

    var trees = document.querySelectorAll('.cbi-tree');
    if (!trees.length) return;

    function childrenFor(btn) {
        var id = btn.getAttribute('aria-controls');
        if (id) {
            var byId = document.getElementById(id);
            if (byId) return byId;
        }
        // Fallback: the children list immediately following the chevron's row.
        var row = btn.closest('.cbi-tree__row');
        var next = row ? row.nextElementSibling : null;
        return (next && next.classList.contains('cbi-tree__children')) ? next : null;
    }

    function toggle(btn) {
        var expanded = btn.getAttribute('aria-expanded') === 'true';
        var next = !expanded;
        btn.setAttribute('aria-expanded', next ? 'true' : 'false');
        var panel = childrenFor(btn);
        if (panel) panel.classList.toggle('is-open', next);
    }

    trees.forEach(function (tree) {
        tree.addEventListener('click', function (e) {
            var btn = e.target.closest('.cbi-tree__chevron');
            if (!btn || !tree.contains(btn)) return;
            // Chevron sits beside the checkbox/link row; keep the click from
            // bubbling into a parent label or anchor.
            e.preventDefault();
            e.stopPropagation();
            toggle(btn);
        });
    });
})();
