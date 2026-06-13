<?php
/**
 * Template Name: Explore Beans
 * Template Post Type: page
 *
 * File: page-explore.php
 *
 * Fragrantica-style bean discovery page at /explore/.
 * All beans rendered server-side; filtering and sorting via explore-filters.js.
 *
 * WP Admin Setup:
 * Pages → Add New → Title: "Explore Coffee Beans" → Slug: explore
 * Page Attributes → Template: Explore Beans
 * Publish.
 */

get_header();

$has_acf = function_exists( 'get_field' );

// Query all published beans in a single pass — no pagination, filter client-side
$beans = new WP_Query( [
    'post_type'      => 'bean',
    'posts_per_page' => -1,
    'post_status'    => 'publish',
    'orderby'        => 'title',
    'order'          => 'ASC',
    'no_found_rows'  => true,
] );

$bean_count = $beans->post_count;

// Taxonomy facet groups — terms actually assigned to published beans only
$facet_config = [
    'origin'         => 'Origin',
    'roast-level'    => 'Roast Level',
    'process-method' => 'Processing',
    'flavor-note'    => 'Flavor Note',
    'brew-method'    => 'Best For',
];

// Map taxonomy slug to the data-* attribute key used on each card
$tax_to_data = [
    'origin'         => 'origin',
    'roast-level'    => 'roast',
    'process-method' => 'process',
    'flavor-note'    => 'flavor',
    'brew-method'    => 'brew',
];

$facet_terms = [];
foreach ( $facet_config as $tax_slug => $label ) {
    $terms = get_terms( [
        'taxonomy'   => $tax_slug,
        'hide_empty' => true,
        'orderby'    => 'name',
        'order'      => 'ASC',
    ] );
    if ( ! is_wp_error( $terms ) && ! empty( $terms ) ) {
        $facet_terms[ $tax_slug ] = [
            'label'    => $label,
            'data_key' => $tax_to_data[ $tax_slug ],
            'terms'    => $terms,
        ];
    }
}

/* ── Flavor-note hierarchy (two-tier: families → notes) ────────────────────
 * The flavor-note taxonomy is hierarchical: parent terms are FAMILIES
 * (Chocolate, Fruit, Nutty …) and children are individual NOTES (Dark
 * Chocolate, Hazelnut, Strawberry …). The Explore flavor facet renders a
 * Simple view (family chips) and an Advanced view (families with nested
 * notes). Counts below are distinct-bean tallies, not raw term counts. */

// Full term set (including empty parents) so the family structure resolves.
$all_flavor_terms = get_terms( [ 'taxonomy' => 'flavor-note', 'hide_empty' => false ] );
$terms_by_id   = [];
$terms_by_slug = [];
if ( ! is_wp_error( $all_flavor_terms ) ) {
    foreach ( $all_flavor_terms as $t ) {
        $terms_by_id[ $t->term_id ] = $t;
        $terms_by_slug[ $t->slug ]  = $t;
    }
} else {
    $all_flavor_terms = [];
}

// Distinct-bean counts per note slug and per family slug.
$flavor_note_counts   = [];
$flavor_family_counts = [];
foreach ( $beans->posts as $bp ) {
    $bt = get_the_terms( $bp->ID, 'flavor-note' );
    if ( ! $bt || is_wp_error( $bt ) ) {
        continue;
    }
    $seen_fam = [];
    foreach ( $bt as $t ) {
        $flavor_note_counts[ $t->slug ] = ( $flavor_note_counts[ $t->slug ] ?? 0 ) + 1;
        // A note's family is its parent; a directly-assigned family term is its own family.
        $fam_slug = ( (int) $t->parent !== 0 && isset( $terms_by_id[ $t->parent ] ) )
            ? $terms_by_id[ $t->parent ]->slug
            : $t->slug;
        if ( ! isset( $seen_fam[ $fam_slug ] ) ) {
            $flavor_family_counts[ $fam_slug ] = ( $flavor_family_counts[ $fam_slug ] ?? 0 ) + 1;
            $seen_fam[ $fam_slug ] = true;
        }
    }
}

// Known families in tasting order (not alphabetical). Add new families here.
$flavor_family_order = [
    'chocolate'     => 'Chocolate',
    'caramel-sweet' => 'Caramel & Sweet',
    'nutty'         => 'Nutty',
    'fruit'         => 'Fruit',
    'citrus-floral' => 'Citrus & Floral',
    'earthy-smoky'  => 'Earthy & Smoky',
];

// Index children by parent id.
$flavor_children = [];
foreach ( $all_flavor_terms as $t ) {
    if ( (int) $t->parent !== 0 ) {
        $flavor_children[ $t->parent ][] = $t;
    }
}

// Order families: known families first (tasting order), then any other
// top-level term that has children. Orphans (top-level, unknown, childless)
// fall through to the "Other" group. After the taxonomy cleanup there should
// be none — this is defensive so a stray term never silently disappears.
$flavor_families_ordered = [];
$flavor_other_terms      = [];
$used_family_ids         = [];

foreach ( array_keys( $flavor_family_order ) as $fam_slug ) {
    if ( isset( $terms_by_slug[ $fam_slug ] ) ) {
        $fam = $terms_by_slug[ $fam_slug ];
        $flavor_families_ordered[]            = $fam;
        $used_family_ids[ $fam->term_id ]     = true;
    }
}
foreach ( $all_flavor_terms as $t ) {
    if ( (int) $t->parent !== 0 || isset( $used_family_ids[ $t->term_id ] ) ) {
        continue;
    }
    if ( ! empty( $flavor_children[ $t->term_id ] ) ) {
        $flavor_families_ordered[] = $t; // unknown family that has children
    } else {
        $flavor_other_terms[] = $t;      // orphan top-level term
    }
}

// Assemble render-ready Simple + Advanced structures (assigned terms only).
$flavor_simple   = []; // [ slug, name, count ]
$flavor_advanced = []; // [ name, options[ slug, name, count ] ]

foreach ( $flavor_families_ordered as $fam ) {
    $fam_count = $flavor_family_counts[ $fam->slug ] ?? 0;
    $options   = [];

    // A directly-assigned family term is itself selectable in Advanced.
    if ( ( $flavor_note_counts[ $fam->slug ] ?? 0 ) > 0 ) {
        $options[] = [
            'slug'  => $fam->slug,
            'name'  => $fam->name . ' (general)',
            'count' => $flavor_note_counts[ $fam->slug ],
        ];
    }

    $kids = $flavor_children[ $fam->term_id ] ?? [];
    usort( $kids, static function ( $a, $b ) { return strcmp( $a->name, $b->name ); } );
    foreach ( $kids as $kid ) {
        $kc = $flavor_note_counts[ $kid->slug ] ?? 0;
        if ( $kc > 0 ) {
            $options[] = [ 'slug' => $kid->slug, 'name' => $kid->name, 'count' => $kc ];
        }
    }

    if ( $fam_count > 0 || ! empty( $options ) ) {
        $flavor_simple[]   = [ 'slug' => $fam->slug, 'name' => $fam->name, 'count' => $fam_count ];
        $flavor_advanced[] = [ 'name' => $fam->name, 'options' => $options ];
    }
}

// Orphan "Other" options (assigned only).
$flavor_other_options = [];
foreach ( $flavor_other_terms as $t ) {
    $c = $flavor_note_counts[ $t->slug ] ?? 0;
    if ( $c > 0 ) {
        $flavor_other_options[] = [ 'slug' => $t->slug, 'name' => $t->name, 'count' => $c ];
    }
}

// ItemList schema — index all beans for SEO
$schema_items = [];
$pos = 1;
foreach ( $beans->posts as $bp ) {
    $schema_items[] = [
        '@type'    => 'ListItem',
        'position' => $pos++,
        'name'     => $bp->post_title,
        'url'      => get_permalink( $bp->ID ),
    ];
}
?>

<script type="application/ld+json"><?php
echo wp_json_encode( [
    '@context'        => 'https://schema.org',
    '@type'           => 'ItemList',
    'name'            => 'Explore Coffee Beans — Coffee Bean Index',
    'url'             => get_permalink(),
    'numberOfItems'   => $bean_count,
    'itemListElement' => $schema_items,
], JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE );
?></script>

<!-- Explore Hero -->
<section class="explore-hero">
    <div class="cbi-container">
        <?php cbi_breadcrumb( [
            [ 'label' => 'Home',    'url' => home_url() ],
            [ 'label' => 'Explore', 'url' => get_permalink() ],
        ] ); ?>
        <div class="explore-hero__eyebrow">Discovery</div>
        <h1 class="explore-hero__title">Explore Coffee Beans</h1>
        <p class="explore-hero__desc">Every bean in the index, browsable by origin, roast level, flavor profile, process method, and brew type. Filter by minimum rating and sort by price to find exactly what you want next.</p>
        <div class="archive-hero__stats">
            <span class="archive-stat"><strong class="tabular-nums"><?php echo esc_html( $bean_count ); ?></strong> bean<?php echo 1 !== $bean_count ? 's' : ''; ?> in the index</span>
            <span class="archive-stat"><strong class="tabular-nums">5</strong> filter dimensions</span>
        </div>
    </div>
</section>

<!-- Affiliate disclosure — FTC requirement near affiliate-linked content -->
<div class="cbi-disclosure-inline">
    <div class="cbi-container">
        This page contains affiliate links. We may earn commissions from qualifying purchases at no extra cost to you.
    </div>
</div>

<!-- Main layout: filter sidebar + bean grid -->
<div class="cbi-container">
    <div class="explore-layout">

        <!-- Filter sidebar -->
        <aside class="explore-sidebar" aria-label="Filter beans">

            <!-- Mobile toggle — hidden on desktop via CSS -->
            <button
                class="explore-sidebar__toggle"
                id="explore-sidebar-toggle"
                type="button"
                aria-expanded="false"
                aria-controls="explore-sidebar-inner">
                <span>Filters</span>
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
                    <path d="M2 4h12M4 8h8M6 12h4"/>
                </svg>
            </button>

            <div class="explore-sidebar__inner" id="explore-sidebar-inner">

                <!-- Clear all -->
                <button class="explore-sidebar__clear" id="explore-clear-all" type="button">Clear all filters</button>

                <!-- Taxonomy facet groups -->
                <?php foreach ( $facet_terms as $tax_slug => $group ) : ?>
                    <?php if ( 'flavor-note' === $tax_slug ) : ?>

                        <!-- Flavor Note: two-tier Simple/Advanced facet -->
                        <div class="explore-facet explore-facet--flavor" data-facet="<?php echo esc_attr( $group['data_key'] ); ?>">
                            <div class="explore-facet__heading"><?php echo esc_html( $group['label'] ); ?></div>

                            <!-- Simple / Advanced toggle -->
                            <div class="explore-flavor-toggle" role="group" aria-label="Flavor filter detail level">
                                <button type="button" class="explore-flavor-toggle__btn is-active" data-flavor-view="simple" aria-pressed="true">Simple</button>
                                <button type="button" class="explore-flavor-toggle__btn" data-flavor-view="advanced" aria-pressed="false">Advanced</button>
                            </div>

                            <!-- SIMPLE: family chips (default) -->
                            <div class="explore-flavor-simple" data-flavor-view-panel="simple">
                                <div class="explore-flavor-chips">
                                    <?php foreach ( $flavor_simple as $fam ) : ?>
                                        <label class="explore-chip">
                                            <input
                                                type="checkbox"
                                                class="explore-filter-cb"
                                                data-filter-group="<?php echo esc_attr( $group['data_key'] ); ?>"
                                                value="<?php echo esc_attr( $fam['slug'] ); ?>">
                                            <span class="explore-chip__label"><?php echo esc_html( $fam['name'] ); ?></span>
                                            <span class="explore-chip__count"><?php echo absint( $fam['count'] ); ?></span>
                                        </label>
                                    <?php endforeach; ?>
                                </div>
                            </div>

                            <!-- ADVANCED: families with nested notes -->
                            <div class="explore-flavor-advanced" data-flavor-view-panel="advanced" hidden>
                                <?php foreach ( $flavor_advanced as $fam ) : ?>
                                    <div class="explore-flavor-group">
                                        <div class="explore-flavor-group__heading"><?php echo esc_html( $fam['name'] ); ?></div>
                                        <div class="explore-facet__options explore-flavor-group__options">
                                            <?php foreach ( $fam['options'] as $opt ) : ?>
                                                <label class="explore-facet__option">
                                                    <input
                                                        type="checkbox"
                                                        class="explore-filter-cb"
                                                        data-filter-group="<?php echo esc_attr( $group['data_key'] ); ?>"
                                                        value="<?php echo esc_attr( $opt['slug'] ); ?>">
                                                    <span class="explore-facet__option-label"><?php echo esc_html( $opt['name'] ); ?></span>
                                                    <span class="explore-facet__option-count"><?php echo absint( $opt['count'] ); ?></span>
                                                </label>
                                            <?php endforeach; ?>
                                        </div>
                                    </div>
                                <?php endforeach; ?>

                                <?php if ( ! empty( $flavor_other_options ) ) : ?>
                                    <details class="explore-flavor-group explore-flavor-group--other">
                                        <summary class="explore-flavor-group__heading">Other</summary>
                                        <div class="explore-facet__options explore-flavor-group__options">
                                            <?php foreach ( $flavor_other_options as $opt ) : ?>
                                                <label class="explore-facet__option">
                                                    <input
                                                        type="checkbox"
                                                        class="explore-filter-cb"
                                                        data-filter-group="<?php echo esc_attr( $group['data_key'] ); ?>"
                                                        value="<?php echo esc_attr( $opt['slug'] ); ?>">
                                                    <span class="explore-facet__option-label"><?php echo esc_html( $opt['name'] ); ?></span>
                                                    <span class="explore-facet__option-count"><?php echo absint( $opt['count'] ); ?></span>
                                                </label>
                                            <?php endforeach; ?>
                                        </div>
                                    </details>
                                <?php endif; ?>
                            </div>
                        </div>

                    <?php else : ?>

                        <div class="explore-facet" data-facet="<?php echo esc_attr( $group['data_key'] ); ?>">
                            <div class="explore-facet__heading"><?php echo esc_html( $group['label'] ); ?></div>
                            <div class="explore-facet__options">
                                <?php foreach ( $group['terms'] as $term ) : ?>
                                    <label class="explore-facet__option">
                                        <input
                                            type="checkbox"
                                            class="explore-filter-cb"
                                            data-filter-group="<?php echo esc_attr( $group['data_key'] ); ?>"
                                            value="<?php echo esc_attr( $term->slug ); ?>">
                                        <span class="explore-facet__option-label"><?php echo esc_html( $term->name ); ?></span>
                                        <span class="explore-facet__option-count"><?php echo absint( $term->count ); ?></span>
                                    </label>
                                <?php endforeach; ?>
                            </div>
                        </div>

                    <?php endif; ?>
                <?php endforeach; ?>

                <!-- Minimum rating slider -->
                <div class="explore-facet explore-facet--range">
                    <div class="explore-facet__heading">Min Rating</div>
                    <div class="explore-rating-control">
                        <input type="range" id="filter-rating" min="1" max="10" value="1" step="1">
                        <div class="explore-rating-display">
                            <span id="filter-rating-value">1</span><span class="explore-rating-display__denom">/10</span>
                        </div>
                    </div>
                </div>

            </div><!-- .explore-sidebar__inner -->
        </aside>

        <!-- Main content: toolbar + grid -->
        <main class="explore-main">

            <div class="explore-toolbar">
                <div class="explore-count" id="explore-count" aria-live="polite">
                    <?php echo esc_html( $bean_count ); ?> bean<?php echo 1 !== $bean_count ? 's' : ''; ?> found
                </div>
                <!-- Sort lives in the toolbar (visible on mobile even with
                     filters collapsed); explore-filters.js binds by ID -->
                <div class="explore-facet explore-facet--sort">
                    <label class="explore-facet__heading" for="explore-sort">Sort by</label>
                    <select id="explore-sort" class="explore-sort-select">
                        <option value="rating">Rating (high &rarr; low)</option>
                        <option value="price">Price/oz (low &rarr; high)</option>
                        <option value="name">Name (A &rarr; Z)</option>
                    </select>
                </div>
            </div>

            <!-- Bean grid — all cards in DOM, JS shows/hides -->
            <div class="explore-grid" id="explore-grid">

                <?php if ( $beans->have_posts() ) : ?>

                    <?php while ( $beans->have_posts() ) : $beans->the_post();
                        $post_id = get_the_ID();
                        $title   = get_the_title();
                        $link    = get_permalink();

                        // ACF fields
                        $rating       = $has_acf ? get_field( 'rating',       $post_id ) : '';
                        $price_per_oz = $has_acf ? get_field( 'price_per_oz', $post_id ) : '';

                        // Taxonomy terms
                        $roasters_tax = get_the_terms( $post_id, 'roaster' );
                        $origins_tax  = get_the_terms( $post_id, 'origin' );
                        $roast_tax    = get_the_terms( $post_id, 'roast-level' );
                        $process_tax  = get_the_terms( $post_id, 'process-method' );
                        $flavor_tax   = get_the_terms( $post_id, 'flavor-note' );
                        $brew_tax     = get_the_terms( $post_id, 'brew-method' );

                        $roaster_name = ( $roasters_tax && ! is_wp_error( $roasters_tax ) ) ? $roasters_tax[0]->name : '';

                        // Space-separated slugs for data-* attributes
                        $data_origin  = ( $origins_tax  && ! is_wp_error( $origins_tax ) )  ? implode( ' ', wp_list_pluck( $origins_tax,  'slug' ) ) : '';
                        $data_roast   = ( $roast_tax    && ! is_wp_error( $roast_tax ) )     ? implode( ' ', wp_list_pluck( $roast_tax,    'slug' ) ) : '';
                        $data_process = ( $process_tax  && ! is_wp_error( $process_tax ) )   ? implode( ' ', wp_list_pluck( $process_tax,  'slug' ) ) : '';
                        // Flavor: include each note slug AND its parent family slug, so a
                        // Simple-view family chip matches any bean carrying a note in that family.
                        $flavor_slug_set = [];
                        if ( $flavor_tax && ! is_wp_error( $flavor_tax ) ) {
                            foreach ( $flavor_tax as $ft ) {
                                $flavor_slug_set[ $ft->slug ] = true;
                                if ( (int) $ft->parent !== 0 && isset( $terms_by_id[ $ft->parent ] ) ) {
                                    $flavor_slug_set[ $terms_by_id[ $ft->parent ]->slug ] = true;
                                }
                            }
                        }
                        $data_flavor  = implode( ' ', array_keys( $flavor_slug_set ) );
                        $data_brew    = ( $brew_tax     && ! is_wp_error( $brew_tax ) )       ? implode( ' ', wp_list_pluck( $brew_tax,     'slug' ) ) : '';

                        $data_rating = ( $rating !== '' && $rating !== null ) ? floatval( $rating ) : 0;
                        $data_price  = ( $price_per_oz !== '' && $price_per_oz !== null ) ? floatval( $price_per_oz ) : 0;
                    ?>

                    <article class="explore-card"
                        data-origin="<?php echo esc_attr( $data_origin ); ?>"
                        data-roast="<?php echo esc_attr( $data_roast ); ?>"
                        data-process="<?php echo esc_attr( $data_process ); ?>"
                        data-flavor="<?php echo esc_attr( $data_flavor ); ?>"
                        data-brew="<?php echo esc_attr( $data_brew ); ?>"
                        data-rating="<?php echo esc_attr( $data_rating ); ?>"
                        data-price="<?php echo esc_attr( $data_price ); ?>"
                        data-name="<?php echo esc_attr( $title ); ?>">

                        <!-- Media: featured image (image-ready) or placeholder SVG.
                             cbi_coffee_placeholder() echoes its own wrapping <div class="…">,
                             so we pass the placeholder classes straight to it. -->
                        <a href="<?php echo esc_url( $link ); ?>" class="explore-card__media" aria-hidden="true" tabindex="-1">
                            <?php if ( has_post_thumbnail( $post_id ) ) :
                                echo get_the_post_thumbnail( $post_id, 'medium', [ 'class' => 'explore-card__img', 'loading' => 'lazy' ] );
                            else :
                                cbi_coffee_placeholder( 'explore-card__img explore-card__img--placeholder' );
                            endif; ?>
                        </a>

                        <!-- Head: name + roaster + rating badge (fields 1, 2, 7) -->
                        <div class="explore-card__head">
                            <div class="explore-card__head-text">
                                <?php if ( $roaster_name ) : ?>
                                    <div class="explore-card__roaster"><?php echo esc_html( $roaster_name ); ?></div>
                                <?php endif; ?>
                                <a href="<?php echo esc_url( $link ); ?>" class="explore-card__name"><?php echo esc_html( $title ); ?></a>
                            </div>
                            <?php if ( $data_rating > 0 ) : ?>
                                <div class="explore-card__rating" aria-label="Rating: <?php echo esc_attr( $data_rating ); ?> out of 10">
                                    <span class="explore-card__rating-score"><?php echo esc_html( $data_rating ); ?></span>
                                    <span class="explore-card__rating-denom">/10</span>
                                </div>
                            <?php endif; ?>
                        </div>

                        <!-- Body: origin (field 3) + flavor notes visual hero (field 4) -->
                        <div class="explore-card__body">

                            <?php if ( $origins_tax && ! is_wp_error( $origins_tax ) ) : ?>
                                <div class="explore-card__origin">
                                    <?php foreach ( $origins_tax as $t ) : ?>
                                        <a href="<?php echo esc_url( get_term_link( $t ) ); ?>" class="bean-tag bean-tag--origin"><?php echo esc_html( $t->name ); ?></a>
                                    <?php endforeach; ?>
                                </div>
                            <?php endif; ?>

                            <?php if ( $flavor_tax && ! is_wp_error( $flavor_tax ) ) : ?>
                                <div class="explore-card__flavors">
                                    <?php foreach ( $flavor_tax as $t ) : ?>
                                        <a href="<?php echo esc_url( get_term_link( $t ) ); ?>" class="bean-tag bean-tag--flavor explore-card__flavor-tag"><?php echo esc_html( $t->name ); ?></a>
                                    <?php endforeach; ?>
                                </div>
                            <?php endif; ?>

                        </div>

                        <!-- Footer: roast (5), process (6), price (8), brew methods (9) -->
                        <div class="explore-card__footer">

                            <div class="explore-card__specs">
                                <?php if ( $roast_tax && ! is_wp_error( $roast_tax ) ) : ?>
                                    <span class="explore-card__spec-item"><?php echo esc_html( $roast_tax[0]->name ); ?></span>
                                <?php endif; ?>
                                <?php if ( $process_tax && ! is_wp_error( $process_tax ) ) : ?>
                                    <span class="explore-card__spec-item"><?php echo esc_html( $process_tax[0]->name ); ?></span>
                                <?php endif; ?>
                                <?php if ( $data_price > 0 ) : ?>
                                    <span class="explore-card__price tabular-nums">$<?php echo esc_html( number_format( $data_price, 2 ) ); ?>/oz</span>
                                <?php endif; ?>
                            </div>

                            <?php if ( $brew_tax && ! is_wp_error( $brew_tax ) ) : ?>
                                <div class="explore-card__brews">
                                    <?php foreach ( $brew_tax as $t ) : ?>
                                        <a href="<?php echo esc_url( get_term_link( $t ) ); ?>" class="bean-tag bean-tag--brew"><?php echo esc_html( $t->name ); ?></a>
                                    <?php endforeach; ?>
                                </div>
                            <?php endif; ?>

                        </div>

                    </article>

                    <?php endwhile;
                    wp_reset_postdata(); ?>

                <?php else : ?>
                    <div class="explore-empty" style="display:block;">
                        <p>No beans in the index yet. Check back soon.</p>
                        <a href="<?php echo esc_url( home_url() ); ?>" class="cbi-btn cbi-btn--secondary">Go home</a>
                    </div>
                <?php endif; ?>

            </div><!-- #explore-grid -->

            <!-- Empty state shown by JS when all cards are filtered out -->
            <div class="explore-empty" id="explore-empty" style="display:none;" aria-live="polite">
                <p>No beans match these filters.</p>
                <button class="cbi-btn cbi-btn--secondary" id="explore-empty-clear" type="button">Clear all filters</button>
            </div>

        </main><!-- .explore-main -->

    </div><!-- .explore-layout -->
</div><!-- .cbi-container -->

<?php get_footer(); ?>
