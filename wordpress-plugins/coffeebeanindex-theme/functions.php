<?php
/**
 * Coffee Bean Index — Child Theme Functions
 * Registers: bean CPT, all taxonomies, ACF field sync, enqueues
 */

// ============================================================
// 1. ENQUEUE PARENT + CHILD STYLES
// ============================================================

add_action( 'wp_enqueue_scripts', 'cbi_enqueue_styles' );
function cbi_enqueue_styles() {
    wp_enqueue_style(
        'generatepress-parent',
        get_template_directory_uri() . '/style.css'
    );
    wp_enqueue_style(
        'cbi-child',
        get_stylesheet_directory_uri() . '/style.css',
        [ 'generatepress-parent' ],
        '1.0.0'
    );
    // Chart.js for radar charts on bean pages
    if ( is_singular( 'bean' ) ) {
        wp_enqueue_script(
            'chartjs',
            'https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js',
            [],
            '4.4.1',
            true
        );
    }
}

// ============================================================
// 2. BEAN CUSTOM POST TYPE
// ============================================================

add_action( 'init', 'cbi_register_bean_cpt' );
function cbi_register_bean_cpt() {
    register_post_type( 'bean', [
        'labels' => [
            'name'               => 'Beans',
            'singular_name'      => 'Bean',
            'add_new'            => 'Add New Bean',
            'add_new_item'       => 'Add New Bean',
            'edit_item'          => 'Edit Bean',
            'new_item'           => 'New Bean',
            'view_item'          => 'View Bean',
            'search_items'       => 'Search Beans',
            'not_found'          => 'No beans found',
            'not_found_in_trash' => 'No beans found in trash',
            'menu_name'          => 'Beans',
        ],
        'public'             => true,
        'publicly_queryable' => true,
        'show_ui'            => true,
        'show_in_menu'       => true,
        'show_in_nav_menus'  => true,
        'show_in_rest'       => true,
        'query_var'          => true,
        'rewrite'            => [ 'slug' => 'beans', 'with_front' => false ],
        'capability_type'    => 'post',
        'has_archive'        => true,
        'hierarchical'       => false,
        'menu_position'      => 5,
        'menu_icon'          => 'dashicons-coffee',
        'supports'           => [
            'title',
            'editor',       // review body
            'thumbnail',
            'excerpt',      // one-line verdict
            'revisions',
            'custom-fields',
        ],
    ] );
}

// ============================================================
// 3. TAXONOMIES
// ============================================================

add_action( 'init', 'cbi_register_taxonomies' );
function cbi_register_taxonomies() {

    // Flavor Notes — the Fragrantica core
    register_taxonomy( 'flavor-note', 'bean', [
        'labels' => [
            'name'              => 'Flavor Notes',
            'singular_name'     => 'Flavor Note',
            'search_items'      => 'Search Flavor Notes',
            'all_items'         => 'All Flavor Notes',
            'edit_item'         => 'Edit Flavor Note',
            'update_item'       => 'Update Flavor Note',
            'add_new_item'      => 'Add New Flavor Note',
            'new_item_name'     => 'New Flavor Note Name',
            'menu_name'         => 'Flavor Notes',
        ],
        'hierarchical'      => true,   // parent families, child notes
        'public'            => true,
        'show_ui'           => true,
        'show_in_rest'      => true,
        'show_admin_column' => true,
        'rewrite'           => [ 'slug' => 'flavor', 'with_front' => false ],
    ] );

    // Origin
    register_taxonomy( 'origin', 'bean', [
        'labels' => [
            'name'          => 'Origins',
            'singular_name' => 'Origin',
            'menu_name'     => 'Origins',
        ],
        'hierarchical'      => true,   // e.g. Africa → Ethiopia
        'public'            => true,
        'show_ui'           => true,
        'show_in_rest'      => true,
        'show_admin_column' => true,
        'rewrite'           => [ 'slug' => 'origin', 'with_front' => false ],
    ] );

    // Roast Level
    register_taxonomy( 'roast-level', 'bean', [
        'labels' => [
            'name'          => 'Roast Levels',
            'singular_name' => 'Roast Level',
            'menu_name'     => 'Roast Levels',
        ],
        'hierarchical'      => false,
        'public'            => true,
        'show_ui'           => true,
        'show_in_rest'      => true,
        'show_admin_column' => true,
        'rewrite'           => [ 'slug' => 'roast', 'with_front' => false ],
    ] );

    // Process Method
    register_taxonomy( 'process-method', 'bean', [
        'labels' => [
            'name'          => 'Process Methods',
            'singular_name' => 'Process Method',
            'menu_name'     => 'Process',
        ],
        'hierarchical'      => false,
        'public'            => true,
        'show_ui'           => true,
        'show_in_rest'      => true,
        'show_admin_column' => true,
        'rewrite'           => [ 'slug' => 'process', 'with_front' => false ],
    ] );

    // Brew Method
    register_taxonomy( 'brew-method', 'bean', [
        'labels' => [
            'name'          => 'Brew Methods',
            'singular_name' => 'Brew Method',
            'menu_name'     => 'Brew Methods',
        ],
        'hierarchical'      => false,
        'public'            => true,
        'show_ui'           => true,
        'show_in_rest'      => true,
        'show_admin_column' => true,
        'rewrite'           => [ 'slug' => 'brew', 'with_front' => false ],
    ] );

    // Roaster
    register_taxonomy( 'roaster', 'bean', [
        'labels' => [
            'name'          => 'Roasters',
            'singular_name' => 'Roaster',
            'menu_name'     => 'Roasters',
        ],
        'hierarchical'      => false,
        'public'            => true,
        'show_ui'           => true,
        'show_in_rest'      => true,
        'show_admin_column' => true,
        'rewrite'           => [ 'slug' => 'roaster', 'with_front' => false ],
    ] );
}

// ============================================================
// 4. FLUSH REWRITE RULES ON ACTIVATION
// ============================================================

add_action( 'after_switch_theme', 'cbi_flush_rewrites' );
function cbi_flush_rewrites() {
    cbi_register_bean_cpt();
    cbi_register_taxonomies();
    flush_rewrite_rules();
}

// ============================================================
// 5. ACF — POINT TO LOCAL JSON
// ============================================================

add_filter( 'acf/settings/save_json', 'cbi_acf_json_save_point' );
function cbi_acf_json_save_point( $path ) {
    return get_stylesheet_directory() . '/acf-json';
}

add_filter( 'acf/settings/load_json', 'cbi_acf_json_load_point' );
function cbi_acf_json_load_point( $paths ) {
    unset( $paths[0] );
    $paths[] = get_stylesheet_directory() . '/acf-json';
    return $paths;
}

// ============================================================
// 6. BEAN PAGE TITLE — use excerpt as verdict in <head>
// ============================================================

add_filter( 'the_excerpt', 'cbi_bean_excerpt' );
function cbi_bean_excerpt( $excerpt ) {
    if ( get_post_type() === 'bean' && ! $excerpt ) {
        $verdict = get_field( 'verdict' );
        return $verdict ? esc_html( $verdict ) : $excerpt;
    }
    return $excerpt;
}

// ============================================================
// 7. CUSTOM COLUMN — RATING in admin list
// ============================================================

add_filter( 'manage_bean_posts_columns', 'cbi_bean_columns' );
function cbi_bean_columns( $cols ) {
    $cols['rating']  = 'Rating';
    $cols['roaster'] = 'Roaster';
    return $cols;
}

add_action( 'manage_bean_posts_custom_column', 'cbi_bean_column_content', 10, 2 );
function cbi_bean_column_content( $col, $post_id ) {
    if ( $col === 'rating' ) {
        $r = get_field( 'rating', $post_id );
        echo $r ? esc_html( $r ) . '/10' : '—';
    }
    if ( $col === 'roaster' ) {
        $terms = get_the_terms( $post_id, 'roaster' );
        echo $terms ? esc_html( $terms[0]->name ) : '—';
    }
}

// ============================================================
// 8. HELPER — SENSORY BAR HTML
// ============================================================

function cbi_sensory_bar( $label, $value, $max = 5 ) {
    $pct = ( intval( $value ) / $max ) * 100;
    printf(
        '<div class="sensory-bar">
            <span class="sensory-bar__label">%s</span>
            <div class="sensory-bar__track">
                <div class="sensory-bar__fill" style="width:%s%%"></div>
            </div>
            <span class="sensory-bar__value">%s</span>
        </div>',
        esc_html( $label ),
        esc_attr( $pct ),
        esc_html( $value )
    );
}

// ============================================================
// 9. HELPER — BEAN CARD HTML (used in archive + similar beans)
// ============================================================

function cbi_bean_card( $post_id ) {
    $title   = get_the_title( $post_id );
    $link    = get_permalink( $post_id );
    $verdict = get_field( 'verdict', $post_id ) ?: get_the_excerpt( $post_id );
    $rating  = get_field( 'rating', $post_id );

    $roasters = get_the_terms( $post_id, 'roaster' );
    $roaster  = $roasters ? $roasters[0]->name : '';

    $flavors  = get_the_terms( $post_id, 'flavor-note' );
    $roasts   = get_the_terms( $post_id, 'roast-level' );
    $origins  = get_the_terms( $post_id, 'origin' );

    ob_start(); ?>
    <div class="bean-card">
        <div class="bean-card__body">
            <?php if ( $roaster ) : ?>
                <div class="bean-card__roaster"><?php echo esc_html( $roaster ); ?></div>
            <?php endif; ?>
            <div class="bean-card__name"><?php echo esc_html( $title ); ?></div>
            <?php if ( $verdict ) : ?>
                <div class="bean-card__verdict"><?php echo esc_html( $verdict ); ?></div>
            <?php endif; ?>
            <div class="bean-card__tags">
                <?php if ( $roasts && ! is_wp_error( $roasts ) ) :
                    foreach ( array_slice( $roasts, 0, 1 ) as $term ) : ?>
                        <a href="<?php echo get_term_link( $term ); ?>" class="bean-tag bean-tag--roast"><?php echo esc_html( $term->name ); ?></a>
                    <?php endforeach;
                endif; ?>
                <?php if ( $origins && ! is_wp_error( $origins ) ) :
                    foreach ( array_slice( $origins, 0, 1 ) as $term ) : ?>
                        <a href="<?php echo get_term_link( $term ); ?>" class="bean-tag bean-tag--origin"><?php echo esc_html( $term->name ); ?></a>
                    <?php endforeach;
                endif; ?>
                <?php if ( $flavors && ! is_wp_error( $flavors ) ) :
                    foreach ( array_slice( $flavors, 0, 2 ) as $term ) : ?>
                        <a href="<?php echo get_term_link( $term ); ?>" class="bean-tag bean-tag--flavor"><?php echo esc_html( $term->name ); ?></a>
                    <?php endforeach;
                endif; ?>
            </div>
        </div>
        <div class="bean-card__footer">
            <div>
                <?php if ( $rating ) : ?>
                    <div class="bean-card__rating"><?php echo esc_html( $rating ); ?></div>
                    <div class="bean-card__rating-label">/ 10</div>
                <?php endif; ?>
            </div>
            <a href="<?php echo esc_url( $link ); ?>" class="bean-card__link">Full Review →</a>
        </div>
    </div>
    <?php return ob_get_clean();
}

// ============================================================
// 10. SCHEMA MARKUP — Product + Review schema on bean pages
// ============================================================

add_action( 'wp_head', 'cbi_bean_schema' );
function cbi_bean_schema() {
    if ( ! is_singular( 'bean' ) ) return;

    $post_id     = get_the_ID();
    $title       = get_the_title();
    $description = get_field( 'verdict' ) ?: get_the_excerpt();
    $rating      = get_field( 'rating' );
    $price       = get_field( 'current_price' );
    $asin        = get_field( 'amazon_asin' );
    $url         = get_permalink();

    $schema = [
        '@context' => 'https://schema.org',
        '@type'    => 'Product',
        'name'     => $title,
        'description' => $description,
        'url'      => $url,
    ];

    if ( $rating ) {
        $schema['aggregateRating'] = [
            '@type'       => 'AggregateRating',
            'ratingValue' => $rating,
            'bestRating'  => '10',
            'worstRating' => '1',
            'ratingCount' => '1',
        ];
    }

    if ( $price ) {
        $schema['offers'] = [
            '@type'         => 'Offer',
            'price'         => $price,
            'priceCurrency' => 'USD',
            'availability'  => 'https://schema.org/InStock',
            'url'           => $asin
                ? 'https://www.amazon.com/dp/' . $asin
                : $url,
        ];
    }

    echo '<script type="application/ld+json">' . wp_json_encode( $schema, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE ) . '</script>' . "\n";
}

// ============================================================
// 11. ROUTE TAXONOMY ARCHIVES TO OUR TEMPLATE
// ============================================================

add_filter( 'template_include', 'cbi_taxonomy_template' );
function cbi_taxonomy_template( $template ) {
    $our_taxes = [ 'flavor-note', 'origin', 'roast-level', 'process-method', 'brew-method', 'roaster' ];
    if ( is_tax( $our_taxes ) ) {
        $custom = get_stylesheet_directory() . '/taxonomy-bean-archive.php';
        if ( file_exists( $custom ) ) return $custom;
    }
    return $template;
}

// ============================================================
// 12. CUSTOM FOOTER CONTENT
// ============================================================

add_action( 'generate_footer', 'cbi_footer_content' );
function cbi_footer_content() { ?>
<div class="footer-inner">
    <div class="footer-disclosure">
        Coffee Bean Index participates in the Amazon Services LLC Associates Program and other affiliate programs. We earn commissions on qualifying purchases at no extra cost to you. Prices are updated daily and may differ from those shown.
    </div>
    <div class="footer-grid">
        <div class="footer-brand">
            <div class="footer-brand__name">Coffee Bean Index</div>
            <div class="footer-brand__desc">Data-driven coffee reviews. Price tracking, flavor profiles, and honest recommendations — no marketing fluff.</div>
        </div>
        <div class="footer-col">
            <div class="footer-col__heading">Reviews</div>
            <ul>
                <li><a href="<?php echo get_post_type_archive_link('bean'); ?>">All Beans</a></li>
                <li><a href="<?php echo get_term_link('espresso', 'brew-method'); ?>">Espresso</a></li>
                <li><a href="<?php echo get_term_link('french-press', 'brew-method'); ?>">French Press</a></li>
                <li><a href="<?php echo get_term_link('pour-over', 'brew-method'); ?>">Pour Over</a></li>
            </ul>
        </div>
        <div class="footer-col">
            <div class="footer-col__heading">Explore</div>
            <ul>
                <li><a href="<?php echo home_url('/flavor/'); ?>">By Flavor</a></li>
                <li><a href="<?php echo home_url('/origin/'); ?>">By Origin</a></li>
                <li><a href="<?php echo home_url('/roast/'); ?>">By Roast</a></li>
                <li><a href="<?php echo home_url('/explore/'); ?>">Flavor Explorer</a></li>
            </ul>
        </div>
        <div class="footer-col">
            <div class="footer-col__heading">Learn</div>
            <ul>
                <li><a href="<?php echo home_url('/price-tracker/'); ?>">Price Tracker</a></li>
                <li><a href="<?php echo home_url('/ethiopia-coffee/'); ?>">Ethiopian Coffee</a></li>
                <li><a href="<?php echo home_url('/best-espresso-beans/'); ?>">Best Espresso Beans</a></li>
            </ul>
        </div>
    </div>
    <div class="footer-bottom">
        <span>© <?php echo date('Y'); ?> Coffee Bean Index</span>
        <span>Rotterdam, NL</span>
    </div>
</div>
<?php }

// ============================================================
// 13. ADD BEAN CPT TO MAIN QUERY ON ARCHIVE PAGES
// ============================================================

add_action( 'pre_get_posts', 'cbi_include_beans_in_queries' );
function cbi_include_beans_in_queries( $query ) {
    if ( is_admin() || ! $query->is_main_query() ) return;
    if ( $query->is_home() || $query->is_feed() ) {
        $types = $query->get( 'post_type' );
        if ( ! $types ) {
            $query->set( 'post_type', [ 'post', 'bean' ] );
        }
    }
}
