<?php
/**
 * Template: Taxonomy Archive
 * File: taxonomy-bean-archive.php
 *
 * Used for: flavor-note, origin, roast-level, process-method, brew-method, roaster
 * Routed via template_include filter in functions.php.
 *
 * v3.0 layout: hero (breadcrumb, term, excerpt, live data stats) →
 * sibling-term chips → sort bar → bean card grid → pagination →
 * full term guide content ("About …") → cross-taxonomy related guides.
 * Beans lead; the long-form guide reads below the product grid.
 */

get_header();

$term        = get_queried_object();
$taxonomy    = $term ? $term->taxonomy : '';
$term_name   = $term ? $term->name : '';
$description = $term ? $term->description : '';
$bean_count  = $term ? (int) $term->count : 0;
$has_acf     = function_exists( 'get_field' );

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

// Schema — BreadcrumbList (rendered + JSON-LD by cbi_breadcrumb)
$breadcrumb_items = [
    [ 'label' => 'Home',  'url' => home_url() ],
    [ 'label' => $eyebrow . 's', 'url' => home_url( '/' . ( get_taxonomy( $taxonomy )->rewrite['slug'] ?? $taxonomy ) . '/' ) ],
    [ 'label' => $term_name, 'url' => get_term_link( $term ) ],
];

// ── Sort handling (mirrors archive-bean.php) ───────────────────────────────
$allowed_sorts = [ 'rating', 'price', 'name', 'date' ];
$sort          = isset( $_GET['sort'] ) && in_array( $_GET['sort'], $allowed_sorts, true ) ? $_GET['sort'] : 'rating';

switch ( $sort ) {
    case 'price':
        $orderby  = 'meta_value_num';
        $meta_key = 'price_per_oz';
        $order    = 'ASC';
        break;
    case 'name':
        $orderby  = 'title';
        $meta_key = '';
        $order    = 'ASC';
        break;
    case 'date':
        $orderby  = 'date';
        $meta_key = '';
        $order    = 'DESC';
        break;
    default: // rating — a review database leads with its scores
        $orderby  = 'meta_value_num';
        $meta_key = 'rating';
        $order    = 'DESC';
        break;
}

$paged    = max( 1, (int) get_query_var( 'paged', 1 ) );
$per_page = 18;

$args = [
    'post_type'      => 'bean',
    'post_status'    => 'publish',
    'posts_per_page' => $per_page,
    'paged'          => $paged,
    'orderby'        => $orderby,
    'order'          => $order,
    'tax_query'      => [
        [
            'taxonomy' => $taxonomy,
            'field'    => 'term_id',
            'terms'    => $term ? $term->term_id : 0,
        ],
    ],
];
if ( $meta_key ) {
    $args['meta_key']  = $meta_key;
    $args['meta_type'] = 'NUMERIC';
}

$bean_query = new WP_Query( $args );

// ── Live data stats for the hero (avg score, price range) ─────────────────
$avg_rating = null;
$price_min  = null;
$price_max  = null;
if ( $has_acf && $term && $bean_count > 0 && $bean_count <= 200 ) {
    $stat_ids = get_posts( [
        'post_type'      => 'bean',
        'post_status'    => 'publish',
        'posts_per_page' => 200,
        'fields'         => 'ids',
        'no_found_rows'  => true,
        'tax_query'      => [
            [
                'taxonomy' => $taxonomy,
                'field'    => 'term_id',
                'terms'    => $term->term_id,
            ],
        ],
    ] );
    $ratings = [];
    foreach ( $stat_ids as $sid ) {
        $r = get_field( 'rating', $sid );
        if ( $r !== '' && $r !== null ) {
            $ratings[] = (float) $r;
        }
        $p = get_field( 'price_per_oz', $sid );
        if ( $p !== '' && $p !== null && (float) $p > 0 ) {
            $p = (float) $p;
            $price_min = ( $price_min === null ) ? $p : min( $price_min, $p );
            $price_max = ( $price_max === null ) ? $p : max( $price_max, $p );
        }
    }
    if ( ! empty( $ratings ) ) {
        $avg_rating = array_sum( $ratings ) / count( $ratings );
    }
}

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

        <div class="archive-hero__stats">
            <span class="archive-stat"><strong class="tabular-nums"><?php echo esc_html( $bean_count ); ?></strong> bean<?php echo 1 !== $bean_count ? 's' : ''; ?></span>
            <?php if ( $avg_rating !== null ) : ?>
                <span class="archive-stat"><strong class="tabular-nums"><?php echo esc_html( number_format( $avg_rating, 1 ) ); ?></strong> avg score</span>
            <?php endif; ?>
            <?php if ( $price_min !== null && $price_max !== null ) : ?>
                <span class="archive-stat"><strong class="tabular-nums">$<?php echo esc_html( number_format( $price_min, 2 ) ); ?>&ndash;$<?php echo esc_html( number_format( $price_max, 2 ) ); ?></strong> /oz</span>
            <?php endif; ?>
        </div>
    </div>
</section>

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

<!-- Sort Bar -->
<nav class="sort-bar" aria-label="Sort beans">
    <div class="sort-bar__inner">
        <span class="sort-bar__label">Sort by</span>
        <div class="sort-bar__links">
            <?php
            $term_url     = get_term_link( $term );
            $sort_options = [
                'rating' => 'Rating',
                'price'  => 'Price (low)',
                'date'   => 'Newest',
                'name'   => 'Name (A&ndash;Z)',
            ];
            foreach ( $sort_options as $slug => $label ) :
                $url       = ( 'rating' === $slug ) ? $term_url : add_query_arg( 'sort', $slug, $term_url );
                $is_active = ( $sort === $slug ) ? ' active' : '';
            ?>
                <a href="<?php echo esc_url( $url ); ?>" class="sort-bar__link<?php echo esc_attr( $is_active ); ?>"><?php echo $label; ?></a>
            <?php endforeach; ?>
        </div>
    </div>
</nav>

<!-- Bean Grid -->
<div class="cbi-container">
    <div class="bean-grid">
        <?php if ( $bean_query->have_posts() ) :
            while ( $bean_query->have_posts() ) : $bean_query->the_post();
                echo cbi_bean_card( get_the_ID() );
            endwhile;
            wp_reset_postdata();
        else : ?>
            <div style="grid-column:1/-1;padding:var(--space-16) 0;text-align:center;">
                <p class="text-dim">No beans tagged &ldquo;<?php echo esc_html( $term_name ); ?>&rdquo; yet. Check back soon.</p>
                <a href="<?php echo esc_url( get_post_type_archive_link( 'bean' ) ?: home_url( '/beans/' ) ); ?>" class="cbi-btn cbi-btn--secondary" style="margin-top:var(--space-4);">Browse all beans</a>
            </div>
        <?php endif; ?>
    </div>

    <!-- Pagination -->
    <div class="cbi-pagination">
        <?php
        echo paginate_links( [
            'total'     => $bean_query->max_num_pages,
            'current'   => $paged,
            'prev_text' => '&larr; Prev',
            'next_text' => 'Next &rarr;',
            'add_args'  => $sort !== 'rating' ? [ 'sort' => $sort ] : [],
        ] );
        ?>
    </div>
</div>

<!-- Term guide — full description as long-form content BELOW the grid,
     so shoppers hit beans first and readers still get the guide (SEO intact) -->
<?php if ( $description ) : ?>
<div class="term-guide">
    <div class="cbi-container">
        <div class="cbi-section__heading">About <?php echo esc_html( $term_name ); ?> coffee</div>
        <div class="guide-body">
            <?php echo wp_kses_post( $description ); ?>
        </div>
    </div>
</div>
<?php endif; ?>

<!-- Cross-Taxonomy Related Guides -->
<?php
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

if ( ! empty( $guide_links ) ) : ?>
<div class="cbi-container" style="margin-top:var(--space-12);">
    <div class="cbi-section">
        <div class="cbi-section__heading">Related Guides</div>
        <div class="explore-groups__set" style="margin-top:var(--space-4);">
            <?php foreach ( $guide_links as $gl ) : ?>
                <a href="<?php echo esc_url( $gl['url'] ); ?>" class="bean-tag">
                    <?php echo esc_html( $gl['label'] ); ?> &rarr;
                </a>
            <?php endforeach; ?>
        </div>
    </div>
</div>
<?php endif; ?>

<?php get_footer(); ?>
