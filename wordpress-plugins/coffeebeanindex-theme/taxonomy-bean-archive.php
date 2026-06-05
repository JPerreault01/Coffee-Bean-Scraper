<?php
/**
 * Template: Taxonomy Archive
 * File: taxonomy-bean-archive.php
 *
 * Used for: flavor-note, origin, roast-level, process-method, brew-method, roaster
 * Routed via template_include filter in functions.php.
 *
 * Shows: hero with term description → related sibling terms → bean grid.
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

// Schema — BreadcrumbList
$breadcrumb_items = [
    [ 'label' => 'Home',  'url' => home_url() ],
    [ 'label' => $eyebrow . 's', 'url' => home_url( '/' . ( get_taxonomy( $taxonomy )->rewrite['slug'] ?? $taxonomy ) . '/' ) ],
    [ 'label' => $term_name, 'url' => get_term_link( $term ) ],
];

// Sibling terms (same taxonomy, excluding current)
$siblings = get_terms( [
    'taxonomy'   => $taxonomy,
    'hide_empty' => true,
    'exclude'    => $term ? [ $term->term_id ] : [],
    'number'     => 10,
    'orderby'    => 'count',
    'order'      => 'DESC',
] );

// Parent term (for hierarchical taxonomies like origin/flavor-note)
$parent_term = null;
if ( $term && $term->parent ) {
    $parent_term = get_term( $term->parent, $taxonomy );
}
?>

<!-- Archive Hero -->
<section class="archive-hero">
    <div class="cbi-container">
        <?php cbi_breadcrumb( $breadcrumb_items ); ?>
        <div class="archive-hero__eyebrow"><?php echo esc_html( $eyebrow ); ?></div>
        <h1 class="archive-hero__title"><?php echo esc_html( $term_name ); ?></h1>
        <?php if ( $description ) : ?>
        <p class="archive-hero__desc"><?php echo esc_html( wp_trim_words( wp_strip_all_tags( $description ), 30 ) ); ?></p>
        <?php endif; ?>
        <p class="archive-hero__count">
            <?php echo esc_html( $bean_count ); ?> bean<?php echo 1 !== $bean_count ? 's' : ''; ?>
        </p>
    </div>
</section>

<!-- Guide Body — full term description as HTML -->
<?php if ( $description ) : ?>
<div class="cbi-container">
    <div class="guide-body">
        <?php echo wp_kses_post( $description ); ?>
    </div>
</div>
<?php endif; ?>

<!-- Related / sibling terms -->
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

<!-- Bean Grid -->
<div class="cbi-container">
    <h2 class="cbi-section__heading" style="margin-top:var(--space-8);">
        <?php echo esc_html( $bean_count ); ?> <?php echo esc_html( $term_name ); ?> bean<?php echo 1 !== $bean_count ? 's' : ''; ?>
    </h2>
    <div class="bean-grid">
        <?php if ( have_posts() ) :
            while ( have_posts() ) : the_post();
                echo cbi_bean_card( get_the_ID() );
            endwhile;
        else : ?>
            <div style="grid-column:1/-1;padding:var(--space-16) 0;text-align:center;">
                <p style="color:var(--cbi-text-dim);">No beans tagged &ldquo;<?php echo esc_html( $term_name ); ?>&rdquo; yet &mdash; check back soon.</p>
                <a href="<?php echo esc_url( get_post_type_archive_link( 'bean' ) ?: home_url( '/beans/' ) ); ?>" class="cbi-btn cbi-btn--secondary" style="margin-top:var(--space-4);">Browse all beans</a>
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
</div>

<!-- Cross-Taxonomy Related Guides — links sideways to sibling taxonomy archives -->
<?php
// Define which taxonomies to cross-link for each taxonomy
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
    // Get the top terms by bean count in this related taxonomy (those with descriptions = guide content)
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

if ( ! empty( $guide_links ) ) : ?>
<div class="cbi-container" style="margin-top:var(--space-12);">
    <div class="cbi-section">
        <div class="cbi-section__heading">Related Guides</div>
        <div style="display:flex;flex-wrap:wrap;gap:var(--space-3);margin-top:var(--space-4);">
            <?php foreach ( $guide_links as $gl ) : ?>
                <a href="<?php echo esc_url( $gl['url'] ); ?>" class="bean-tag" style="font-size:var(--text-sm);">
                    <?php echo esc_html( $gl['label'] ); ?> &rarr;
                </a>
            <?php endforeach; ?>
        </div>
    </div>
</div>
<?php endif; ?>

<?php get_footer(); ?>
