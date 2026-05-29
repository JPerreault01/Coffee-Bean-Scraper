<?php
/**
 * Template: All Beans Archive
 * File: archive-bean.php
 *
 * Browsable database of all reviewed beans.
 * Supports URL-based sorting (?sort=rating, ?sort=price, ?sort=name).
 * Filter chips link to taxonomy archives.
 */

get_header();

// Sort handling — safe whitelist
$allowed_sorts = [ 'rating', 'price', 'name', 'date' ];
$sort          = isset( $_GET['sort'] ) && in_array( $_GET['sort'], $allowed_sorts, true ) ? $_GET['sort'] : 'date';

switch ( $sort ) {
    case 'rating':
        $orderby  = 'meta_value_num';
        $meta_key = 'rating';
        $order    = 'DESC';
        break;
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
    default: // date
        $orderby  = 'date';
        $meta_key = '';
        $order    = 'DESC';
        break;
}

$paged    = max( 1, get_query_var( 'paged', 1 ) );
$per_page = 18;

$args = [
    'post_type'      => 'bean',
    'post_status'    => 'publish',
    'posts_per_page' => $per_page,
    'paged'          => $paged,
    'orderby'        => $orderby,
    'order'          => $order,
];
if ( $meta_key ) {
    $args['meta_key']     = $meta_key;
    $args['meta_type']    = 'NUMERIC';
}

$bean_query  = new WP_Query( $args );
$total_beans = $bean_query->found_posts;

// Schema — ItemList
$schema_items = [];
if ( $bean_query->have_posts() ) {
    $i = 1;
    foreach ( $bean_query->posts as $post ) {
        $schema_items[] = [
            '@type'    => 'ListItem',
            'position' => $i++,
            'url'      => get_permalink( $post->ID ),
            'name'     => get_the_title( $post->ID ),
        ];
    }
}
?>

<?php if ( ! empty( $schema_items ) ) : ?>
<script type="application/ld+json"><?php
echo wp_json_encode( [
    '@context'        => 'https://schema.org',
    '@type'           => 'ItemList',
    'name'            => 'All Coffee Beans — Coffee Bean Index',
    'itemListElement' => $schema_items,
], JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE );
?></script>
<?php endif; ?>

<!-- Archive Hero -->
<section class="archive-hero">
    <div class="cbi-container">
        <div class="archive-hero__eyebrow">The Database</div>
        <h1 class="archive-hero__title">All Coffee Beans</h1>
        <p class="archive-hero__desc">
            Every bean we&rsquo;ve reviewed, sorted by how we score them.
            Price-tracked daily. Filter by flavor, origin, or roast below.
        </p>
        <p class="archive-hero__count">
            <?php echo esc_html( $total_beans ); ?> bean<?php echo 1 !== $total_beans ? 's' : ''; ?> in the index
        </p>
    </div>
</section>

<!-- Affiliate disclosure -->
<div class="cbi-disclosure-inline" style="border-radius:0;border-left:none;border-right:none;border-top:none;">
    <div class="cbi-container">
        This page contains affiliate links. We may earn commissions from qualifying purchases.
    </div>
</div>

<!-- Sort Bar -->
<nav class="sort-bar" aria-label="Sort beans">
    <div class="sort-bar__inner">
        <span class="sort-bar__label">Sort by</span>
        <div class="sort-bar__links">
            <?php
            $sort_options = [
                'date'   => 'Newest',
                'rating' => 'Rating',
                'price'  => 'Price (low)',
                'name'   => 'Name (A&ndash;Z)',
            ];
            foreach ( $sort_options as $slug => $label ) :
                $url     = add_query_arg( 'sort', $slug, get_post_type_archive_link( 'bean' ) );
                $is_active = ( $sort === $slug ) ? ' active' : '';
            ?>
                <a href="<?php echo esc_url( $url ); ?>" class="sort-bar__link<?php echo esc_attr( $is_active ); ?>"><?php echo $label; ?></a>
            <?php endforeach; ?>
        </div>

        <!-- Quick taxonomy filter chips -->
        <span class="sort-bar__label" style="margin-left:auto;">Filter</span>
        <?php
        $quick_filters = [
            [ 'label' => 'Espresso',    'tax' => 'brew-method',  'slug' => 'espresso' ],
            [ 'label' => 'Pour Over',   'tax' => 'brew-method',  'slug' => 'pour-over' ],
            [ 'label' => 'Dark Roast',  'tax' => 'roast-level',  'slug' => 'dark' ],
            [ 'label' => 'Light Roast', 'tax' => 'roast-level',  'slug' => 'light' ],
            [ 'label' => 'Ethiopia',    'tax' => 'origin',       'slug' => 'ethiopia' ],
        ];
        foreach ( $quick_filters as $f ) {
            $term = get_term_by( 'slug', $f['slug'], $f['tax'] );
            if ( $term && ! is_wp_error( $term ) ) {
                printf(
                    '<a href="%s" class="sort-bar__link">%s</a>',
                    esc_url( get_term_link( $term ) ),
                    esc_html( $f['label'] )
                );
            }
        }
        ?>
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
                <p style="color:var(--cbi-text-dim);">No beans in the index yet &mdash; check back soon.</p>
                <a href="<?php echo esc_url( home_url() ); ?>" class="cbi-btn cbi-btn--secondary" style="margin-top:var(--space-4);">Back to homepage</a>
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
            'add_args'  => $sort !== 'date' ? [ 'sort' => $sort ] : [],
        ] );
        ?>
    </div>
</div>

<?php get_footer(); ?>
