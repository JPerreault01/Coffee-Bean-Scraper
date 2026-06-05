You are working on Coffee Bean Index, a WordPress affiliate site. You are editing the LOCAL
repo at this folder — NOT the live server. The deploy flow is: you edit repo files → I push to
GitHub → I run `deploy-theme` over SSH to publish. So make code edits directly in the repo
files listed below. For anything that is a Rank Math/WP-admin setting or a server WP-CLI
command, do NOT try to edit a file — output the exact setting path or command for me to run,
labeled clearly as "RUN ON SERVER" or "WP-ADMIN SETTING".

READ THESE FIRST, before any work:
- docs/PROJECT_STATUS.md   — full architecture, file map, template/section inventory, URL patterns
- docs/AUDIT.md            — current SEO health audit + priority sequence (the fix list)
- docs/SEO_PLAYBOOK.md     — standing operating doc: tool division of labor, per-content-type
                             schema/meta/internal-link requirements, pre-publish checklists
- CLAUDE.md                — content-integrity rules and review voice system (HARD RULES)

Two capability sources are installed: the claude-seo plugin (/seo commands) for the technical
HOW + markup validation, and the rampstack claude-skills library for design, IA, and content
judgment (WHAT + WHY). Follow SEO_PLAYBOOK.md §1 division of labor exactly. Never run two
overlapping keyword/SEO audits on the same page.

REPO FILE MAP (edit these locally):
- Theme:  wordpress-plugins/coffeebeanindex-theme/
            style.css                 (full design system + GP overrides + component CSS)
            functions.php             (bean CPT, 6 taxonomies, ACF sync, Chart.js enqueue, schema)
            single-bean.php           (bean page template, 10 sections — see PROJECT_STATUS.md)
            taxonomy-bean-archive.php  (flavor/origin/roast/brew/roaster archives)
            acf-json/group_bean_specs.json
- Review generator:  scrapers/generate_review.py   (--mock and --personal flags must keep working)
- Product source of truth:  scrapers/products.json  (20 products, flavor vectors)

Work in phases. After each phase, give me a one-line-per-change summary, then STOP and wait for
my go-ahead. Don't restructure URLs or break permalinks (beans live at /beans/<slug>/). Don't
commit /opt/.env, *.db, *.log, /opt/data/, or /opt/drafts/ (all gitignored).

PHASE 1 — Critical + High structural fixes (AUDIT.md, dependency order)
1. Bean CPT missing from the Rank Math sitemap (C1). This is the #1 blocker — Google can't see
   the 20 reviews. Give me the exact Rank Math setting path AND a WP-CLI fallback command,
   labeled "WP-ADMIN SETTING" / "RUN ON SERVER".
2. hello-world test post (H1): give me the WP-CLI command to delete it (PROJECT_STATUS says it
   was removed; verify and handle if still present).
3. CPT title-tag template (H2): "%post_title% Review — Coffee Bean Index" — Rank Math setting,
   give me the path. Bean archive title is the default "Beans Archive" (L4) — fix in the template
   or via Rank Math, your call, tell me which.
4. CPT meta-description fallback template (C2 prep) — Rank Math setting path.
5. Schema (H4, H5): in functions.php / single-bean.php, output JSON-LD per SEO_PLAYBOOK.md
   Individual Review spec: Product + Review + AggregateRating + Offer + BreadcrumbList + FAQPage,
   built from the ACF fields. Validate with /seo schema before declaring done.
6. /explore/ nav/link issue (C5) and the price-tracker dead end (H3): PROJECT_STATUS.md lists
   both as not-built. Either remove the references or scaffold minimal pages — recommend which
   and do it.
7. Fix the 404 internal links flagged in AUDIT.md.

PHASE 2 — Design system, IA, template rework (rampstack design-system, design-standards,
information-architecture; reference PROJECT_STATUS.md "Site architecture")
8. Define/clean up design tokens in style.css (color, type scale, spacing) and apply
   consistently. Coffee-appropriate, readable, not generic-AI-looking. Resolve the known GP
   container-width issue (PROJECT_STATUS.md outstanding issue #1) if still present.
9. Rework single-bean.php and taxonomy-bean-archive.php for visual quality and clear hierarchy.
   Confirm the inline Chart.js radar renders and doesn't block paint.
10. Build the navigation menu and a homepage template around the graph model (bean/flavor/
    origin/roast/brew/roaster as interlinked nodes) — both are listed as not-built.
11. Run accessibility-audit and performance-optimization passes; fix cheap high-impact items.
12. Add OG/social meta (L5) and verify image alt texts (Images 30/100).

PHASE 3 — Build the missing content-type templates (SEO_PLAYBOOK.md §2 references these but they
do not exist yet)
13. Create template-roundup.php (Article + ItemList + BreadcrumbList + FAQPage; each pick links
    to its single-bean review), template-guide.php (Article + BreadcrumbList; ≥800 words slot;
    ≥3 internal bean links), and template-comparison.php (Article + BreadcrumbList; clear winner,
    no hedging). Match the per-type meta-title formats and internal-link rules in the playbook.

PHASE 4 — Make generate_review.py output SEO-ready pages
14. Update scrapers/generate_review.py (and the style guide it reads) so generated Individual
    Review drafts conform to SEO_PLAYBOOK.md: the established review format from CLAUDE.md
    (verdict, specs table, tasting notes, who-it's-for, who-to-skip, price analysis, rating);
    a 3-question FAQ block (taste / who it's for / who to skip) wired for FAQPage schema; meta
    title "[Product] Review — [Roaster] | Coffee Bean Index"; a meta description; and ≥1 internal
    link each to a relevant origin guide + roast-level guide + the roaster taxonomy archive.
    OBEY CLAUDE.md HARD RULES: two-mode voice (analytical default, --personal flag), no first-
    person consumption claims in analytical mode, no crowd attribution, no hedging, required
    disclosure string near the top. Keep --mock and --personal working.

PHASE 5 — Content gaps that protect rankings (AUDIT.md Week 2–4)
15. Draft the "Best Espresso Beans Under $20" and "Best Dark Roast" roundups using the new
    roundup template (≥60% editorial), and 4 origin guides using the guide template (these
    protect the ≥40% informational content ratio in SEO_PLAYBOOK.md §7).

Validate SEO-technical changes with claude-seo (/seo schema, /seo technical, /seo page). Make
content/IA/design judgment calls with the rampstack skills. End the whole run with the git
add/commit/push commands grouped logically, then remind me to run `deploy-theme` over SSH.