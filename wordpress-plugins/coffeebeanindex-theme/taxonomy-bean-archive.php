<?php
/**
 * Template: Taxonomy Archive
 * File: taxonomy-bean-archive.php
 *
 * Used for: flavor-note, origin, roast-level, process-method, brew-method, roaster
 * Routed via template_include filter in functions.php.
 *
 * Layout:
 *   - Full-width archive hero (breadcrumb, eyebrow, H1, bean count)
 *   - Full-width "Also Browse" sibling strip
 *   - Two-column body: main (description + bean grid + pagination) | sidebar (related guides)
 *   - Sidebar suppressed when no guide links exist (uses archive-layout--full)
 */

get_header();

$term        = get_queried_object();
$taxonomy    = $term ? $term->taxonomy : '';
$term_name   = $term ? $term->name : '';
$description = $term ? $term->description : '';
$bean_count  = $term ? $term->count : 0;

// Eyebrow label per taxonomy
$eyebrow_map = [
    'flavor-note'    => 'Flavor Note',
    'origin'         => 'Origin',
    'roast-level'    => 'Roast Level',
    'process-method' => 'Process Method',
    'brew-method'    => 'Best For',
    'roaster'        => 'Roaster',
];
$eyebrow = $eyebrow_map[ $taxonomy ] ?? 'Browse';

// Schema — BreadcrumbList (output via cbi_breadcrumb helper)
$breadcrumb_items = [
    [ 'label' => 'Home',  'url' => home_url() ],
    [ 'label' => $eyebrow . 's', 'url' => home_url( '/' . ( get_taxonomy( $taxonomy )->rewrite['slug'] ?? $taxonomy ) . '/' ) ],
    [ 'label' => $term_name, 'url' => get_term_link( $term ) ],
];

// Sibling terms (same taxonomy, excluding current, ordered by popularity)
$siblings = get_terms( [
    'taxonomy'   => $taxonomy,
    'hide_empty' => true,
    'exclude'    => $term ? [ $term->term_id ] : [],
    'number'     => 12,
    'orderby'    => 'count',
    'order'      => 'DESC',
] );

// Parent term (hierarchical taxonomies like origin/flavor-note)
$parent_term = null;
if ( $term && $term->parent ) {
    $parent_term = get_term( $term->parent, $taxonomy );
}

// Cross-taxonomy related guide links — only terms with guide content (descriptions set)
$cross_link_map = [
    'origin'         => [ 'roast-level', 'brew-method', 'process-method' ],
    'roast-level'    => [ 'brew-method', 'origin', 'process-method' ],
    'brew-method'    => [ 'roast-level', 'origin', 'flavor-note' ],
    'process-method' => [ 'origin', 'roast-level' ],
    'flavor-note'    => [ 'origin', 'roast-level', 'brew-method' ],
    'roaster'        => [ 'origin', 'roast-level' ],
];

$related_taxs = $cross_link_map[ $taxonomy ] ?? [];
$guide_links  = [];

foreach ( $related_taxs as $rel_tax ) {
    $rel_terms = get_terms( [
        'taxonomy'   => $rel_tax,
        'hide_empty' => false,
        'number'     => 5,
        'orderby'    => 'count',
        'order'      => 'DESC',
    ] );
    if ( is_wp_error( $rel_terms ) || empty( $rel_terms ) ) {
        continue;
    }
    $tax_obj   = get_taxonomy( $rel_tax );
    $tax_label = $tax_obj ? $tax_obj->labels->singular_name : $rel_tax;
    foreach ( $rel_terms as $rt ) {
        if ( empty( $rt->description ) ) {
            continue; // Only link to terms that have guide content
        }
        $guide_links[] = [
            'label' => $tax_label . ': ' . $rt->name,
            'url'   => get_term_link( $rt ),
        ];
    }
}
?>

<!-- ============================================================
     ARCHIVE HERO — full-width, outside column constraints
     ============================================================ -->
<section class="archive-hero">
    <div class="cbi-container">
        <?php cbi_breadcrumb( $breadcrumb_items ); ?>
        <div class="archive-hero__eyebrow"><?php echo esc_html( $eyebrow ); ?></div>
        <h1 class="archive-hero__title"><?php echo esc_html( $term_name ); ?></h1>
        <p class="archive-hero__count">
            <?php echo esc_html( $bean_count ); ?> bean<?php echo 1 !== $bean_count ? 's' : ''; ?>
        </p>
    </div>
</section>

<!-- ============================================================
     ALSO BROWSE — full-width sibling taxonomy strip
     ============================================================ -->
<?php if ( ! is_wp_error( $siblings ) && ! empty( $siblings ) ) : ?>
<div class="related-terms">
    <div class="related-terms__inner">
        <span class="related-terms__label">Also browse:</span>
        <?php if ( $parent_term && ! is_wp_error( $parent_term ) ) : ?>
            <a href="<?php echo esc_url( get_term_link( $parent_term ) ); ?>" class="bean-tag">
                &larr; All <?php echo esc_html( $parent_term->name ); ?>
            </a>
        <?php endif; ?>
        <?php foreach ( $siblings as $sibling ) : ?>
            <a href="<?php echo esc_url( get_term_link( $sibling ) ); ?>" class="bean-tag">
                <?php echo esc_html( $sibling->name ); ?>
            </a>
        <?php endforeach; ?>
    </div>
</div>
<?php endif; ?>

<!-- ============================================================
     TWO-COLUMN BODY: main content + related guides sidebar
     archive-layout--full collapses to single column when no sidebar
     ============================================================ -->
<div class="cbi-container">
    <div class="archive-layout<?php echo empty( $guide_links ) ? ' archive-layout--full' : ''; ?>">

        <!-- MAIN COLUMN: description prose + bean grid + pagination -->
        <main class="archive-main">

            <!-- Term description (guide prose — set in Taxonomy editor) -->
            <?php if ( $description ) : ?>
                <div class="guide-body archive-description">
                    <?php echo wp_kses_post( $description ); ?>
                </div>
            <?php else : ?>
                <p class="archive-description--placeholder">
                    [Guide content coming soon &mdash; add a description for this <?php echo esc_html( strtolower( $eyebrow ) ); ?> in the Taxonomy editor to populate this section.]
                </p>
            <?php endif; ?>

            <!-- Bean grid — auto-fill min 280px, graceful at 0 or 1 beans -->
            <div class="bean-grid">
                <?php if ( have_posts() ) :
                    while ( have_posts() ) : the_post();
                        echo cbi_bean_card( get_the_ID() );
                    endwhile;
                else : ?>
                    <div class="archive-empty">
                        <p>No beans tagged &ldquo;<?php echo esc_html( $term_name ); ?>&rdquo; yet &mdash; check back soon.</p>
                        <a href="<?php echo esc_url( get_post_type_archive_link( 'bean' ) ?: home_url( '/beans/' ) ); ?>" class="cbi-btn cbi-btn--secondary">Browse all beans</a>
                    </div>
                <?php endif; ?>
            </div>

            <!-- Pagination -->
            <div class="cbi-pagination">
                <?php the_posts_pagination( [
                    'mid_size'  => 2,
                    'prev_text' => '&larr; Prev',
                    'next_text' => 'Next &rarr;',
                ] ); ?>
            </div>

        </main>

        <!-- SIDEBAR COLUMN: related guides — only rendered when links exist -->
        <?php if ( ! empty( $guide_links ) ) : ?>
        <aside class="archive-sidebar">
            <div class="cbi-section">
                <div class="cbi-section__heading">Related Guides</div>
                <div class="archive-pills">
                    <?php foreach ( $guide_links as $gl ) : ?>
                        <a href="<?php echo esc_url( $gl['url'] ); ?>" class="bean-tag">
                            <?php echo esc_html( $gl['label'] ); ?> &rarr;
                        </a>
                    <?php endforeach; ?>
                </div>
            </div>
        </aside>
        <?php endif; ?>

    </div>
</div>

<?php get_footer(); ?>
