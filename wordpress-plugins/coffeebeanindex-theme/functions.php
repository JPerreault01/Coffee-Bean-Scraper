<?php
/**
 * Coffee Bean Index — Child Theme Functions
 * Registers: bean CPT, all taxonomies, ACF field sync, enqueues, schema
 */

// ============================================================
// 1. ENQUEUE STYLES & SCRIPTS
//    Fonts loaded with preconnect — no render-blocking @import
// ============================================================

add_action( 'wp_enqueue_scripts', 'cbi_enqueue_styles' );
function cbi_enqueue_styles() {
    // Google Fonts — enqueued properly so WP can manage load order
    wp_enqueue_style(
        'cbi-fonts',
        'https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,600;0,700;1,400&family=DM+Sans:wght@300;400;500;600&family=DM+Mono:wght@400;500&display=swap',
        [],
        null
    );

    // Parent theme
    wp_enqueue_style(
        'generatepress-parent',
        get_template_directory_uri() . '/style.css'
    );

    // Child theme
    wp_enqueue_style(
        'cbi-child',
        get_stylesheet_directory_uri() . '/style.css',
        [ 'generatepress-parent', 'cbi-fonts' ],
        '2.0.0'
    );

    // Chart.js — only on bean pages (reduces page weight everywhere else)
    if ( is_singular( 'bean' ) ) {
        wp_enqueue_script(
            'chartjs',
            'https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js',
            [],
            '4.4.1',
            true // footer
        );
    }

    // Explore filters JS — only on the explore page template
    if ( is_page_template( 'page-explore.php' ) ) {
        wp_enqueue_script(
            'cbi-explore-filters',
            get_stylesheet_directory_uri() . '/js/explore-filters.js',
            [],
            '1.0.0',
            true // footer
        );
    }
}

// Preconnect hints for Google Fonts (output before any render-blocking resources)
add_action( 'wp_head', 'cbi_font_preconnect', 1 );
function cbi_font_preconnect() {
    echo '<link rel="preconnect" href="https://fonts.googleapis.com">' . "\n";
    echo '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>' . "\n";
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
            'editor',      // review body
            'thumbnail',
            'excerpt',     // one-line verdict fallback
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

    register_taxonomy( 'flavor-note', 'bean', [
        'labels'            => [ 'name' => 'Flavor Notes', 'singular_name' => 'Flavor Note', 'menu_name' => 'Flavor Notes' ],
        'hierarchical'      => true,
        'public'            => true,
        'show_ui'           => true,
        'show_in_rest'      => true,
        'show_admin_column' => true,
        'rewrite'           => [ 'slug' => 'flavor', 'with_front' => false ],
    ] );

    register_taxonomy( 'origin', 'bean', [
        'labels'            => [ 'name' => 'Origins', 'singular_name' => 'Origin', 'menu_name' => 'Origins' ],
        'hierarchical'      => true,
        'public'            => true,
        'show_ui'           => true,
        'show_in_rest'      => true,
        'show_admin_column' => true,
        'rewrite'           => [ 'slug' => 'origin', 'with_front' => false ],
    ] );

    register_taxonomy( 'roast-level', 'bean', [
        'labels'            => [ 'name' => 'Roast Levels', 'singular_name' => 'Roast Level', 'menu_name' => 'Roast Levels' ],
        'hierarchical'      => false,
        'public'            => true,
        'show_ui'           => true,
        'show_in_rest'      => true,
        'show_admin_column' => true,
        'rewrite'           => [ 'slug' => 'roast', 'with_front' => false ],
    ] );

    register_taxonomy( 'process-method', 'bean', [
        'labels'            => [ 'name' => 'Process Methods', 'singular_name' => 'Process Method', 'menu_name' => 'Process' ],
        'hierarchical'      => false,
        'public'            => true,
        'show_ui'           => true,
        'show_in_rest'      => true,
        'show_admin_column' => true,
        'rewrite'           => [ 'slug' => 'process', 'with_front' => false ],
    ] );

    register_taxonomy( 'brew-method', 'bean', [
        'labels'            => [ 'name' => 'Brew Methods', 'singular_name' => 'Brew Method', 'menu_name' => 'Brew Methods' ],
        'hierarchical'      => false,
        'public'            => true,
        'show_ui'           => true,
        'show_in_rest'      => true,
        'show_admin_column' => true,
        'rewrite'           => [ 'slug' => 'brew', 'with_front' => false ],
    ] );

    register_taxonomy( 'roaster', 'bean', [
        'labels'            => [ 'name' => 'Roasters', 'singular_name' => 'Roaster', 'menu_name' => 'Roasters' ],
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
// 5. ACF — LOCAL JSON SYNC
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
// 6. EXCERPT — use verdict field as fallback for beans
// ============================================================

add_filter( 'the_excerpt', 'cbi_bean_excerpt' );
function cbi_bean_excerpt( $excerpt ) {
    if ( function_exists( 'get_field' ) && get_post_type() === 'bean' && ! $excerpt ) {
        $verdict = get_field( 'verdict' );
        return $verdict ? esc_html( $verdict ) : $excerpt;
    }
    return $excerpt;
}

// ============================================================
// 7. ADMIN COLUMNS — rating + roaster in bean list
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
        $r = function_exists( 'get_field' ) ? get_field( 'rating', $post_id ) : '';
        echo $r ? esc_html( $r ) . '/10' : '—';
    }
    if ( $col === 'roaster' ) {
        $terms = get_the_terms( $post_id, 'roaster' );
        echo ( $terms && ! is_wp_error( $terms ) ) ? esc_html( $terms[0]->name ) : '—';
    }
}

// ============================================================
// 8. HELPER — SENSORY BAR HTML
// ============================================================

function cbi_sensory_bar( $label, $value, $max = 5 ) {
    $pct = round( ( intval( $value ) / $max ) * 100 );
    printf(
        '<div class="sensory-bar">
            <span class="sensory-bar__label">%s</span>
            <div class="sensory-bar__track" role="meter" aria-valuenow="%s" aria-valuemin="0" aria-valuemax="%s">
                <div class="sensory-bar__fill" style="width:%s%%"></div>
            </div>
            <span class="sensory-bar__value">%s</span>
        </div>',
        esc_html( $label ),
        esc_attr( $value ),
        esc_attr( $max ),
        esc_attr( $pct ),
        esc_html( $value )
    );
}

// ============================================================
// 9. HELPER — BEAN CARD HTML (used in archives + homepage)
// ============================================================

function cbi_bean_card( $post_id ) {
    $title   = get_the_title( $post_id );
    $link    = get_permalink( $post_id );
    $verdict = function_exists( 'get_field' ) ? get_field( 'verdict', $post_id ) : '';
    if ( ! $verdict ) $verdict = get_the_excerpt( $post_id );
    $rating  = function_exists( 'get_field' ) ? get_field( 'rating', $post_id ) : '';

    $roasters = get_the_terms( $post_id, 'roaster' );
    $roaster  = ( $roasters && ! is_wp_error( $roasters ) ) ? $roasters[0]->name : '';

    $flavors = get_the_terms( $post_id, 'flavor-note' );
    $roasts  = get_the_terms( $post_id, 'roast-level' );
    $origins = get_the_terms( $post_id, 'origin' );

    ob_start();
    ?>
    <div class="bean-card">
        <?php if ( has_post_thumbnail( $post_id ) ) : ?>
        <div class="bean-card__image">
            <?php echo get_the_post_thumbnail( $post_id, 'medium', [ 'loading' => 'lazy', 'width' => '400', 'height' => '225' ] ); ?>
            <?php if ( $rating !== '' && $rating !== null ) : ?>
                <span class="bean-card__rating-badge"><?php echo esc_html( $rating ); ?>/10</span>
            <?php endif; ?>
        </div>
        <?php endif; ?>
        <div class="bean-card__body">
            <?php if ( $roaster ) : ?>
                <div class="bean-card__roaster"><?php echo esc_html( $roaster ); ?></div>
            <?php endif; ?>
            <div class="bean-card__name"><?php echo esc_html( $title ); ?></div>
            <?php if ( $verdict ) : ?>
                <div class="bean-card__verdict"><?php echo esc_html( $verdict ); ?></div>
            <?php endif; ?>
            <div class="bean-card__tags">
                <?php
                if ( $roasts && ! is_wp_error( $roasts ) ) {
                    foreach ( array_slice( $roasts, 0, 1 ) as $term ) {
                        printf( '<a href="%s" class="bean-tag bean-tag--roast">%s</a>', esc_url( get_term_link( $term ) ), esc_html( $term->name ) );
                    }
                }
                if ( $origins && ! is_wp_error( $origins ) ) {
                    foreach ( array_slice( $origins, 0, 1 ) as $term ) {
                        printf( '<a href="%s" class="bean-tag bean-tag--origin">%s</a>', esc_url( get_term_link( $term ) ), esc_html( $term->name ) );
                    }
                }
                if ( $flavors && ! is_wp_error( $flavors ) ) {
                    foreach ( array_slice( $flavors, 0, 2 ) as $term ) {
                        printf( '<a href="%s" class="bean-tag bean-tag--flavor">%s</a>', esc_url( get_term_link( $term ) ), esc_html( $term->name ) );
                    }
                }
                ?>
            </div>
        </div>
        <div class="bean-card__footer">
            <div>
                <?php if ( $rating !== '' && $rating !== null ) : ?>
                    <div class="bean-card__rating tabular-nums"><?php echo esc_html( $rating ); ?></div>
                    <div class="bean-card__rating-label">/ 10</div>
                <?php endif; ?>
            </div>
            <a href="<?php echo esc_url( $link ); ?>" class="bean-card__link">Full Review &rarr;</a>
        </div>
    </div>
    <?php
    return ob_get_clean();
}

// ============================================================
// 10. HELPER — SVG coffee cup placeholder (no emoji)
// ============================================================

function cbi_coffee_placeholder( $class = 'cbi-img-placeholder' ) {
    ?>
    <div class="<?php echo esc_attr( $class ); ?>">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
            <path d="M17 8h1a4 4 0 0 1 0 8h-1"/>
            <path d="M3 8h14v9a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4Z"/>
            <line x1="6" x2="6" y1="2" y2="4"/>
            <line x1="10" x2="10" y1="2" y2="4"/>
            <line x1="14" x2="14" y1="2" y2="4"/>
        </svg>
    </div>
    <?php
}

// ============================================================
// 11. HELPER — BREADCRUMB HTML
// ============================================================

function cbi_breadcrumb( $items = [] ) {
    if ( empty( $items ) ) return;
    $schema_items = [];
    $position     = 1;
    ?>
    <nav class="cbi-breadcrumb" aria-label="Breadcrumb">
        <?php foreach ( $items as $i => $item ) :
            $is_last = ( $i === count( $items ) - 1 );
            if ( ! $is_last ) {
                $schema_items[] = [
                    '@type'    => 'ListItem',
                    'position' => $position++,
                    'name'     => $item['label'],
                    'item'     => $item['url'],
                ];
                printf( '<a href="%s">%s</a>', esc_url( $item['url'] ), esc_html( $item['label'] ) );
                echo '<span class="cbi-breadcrumb__sep">/</span>';
            } else {
                printf( '<span>%s</span>', esc_html( $item['label'] ) );
            }
        endforeach; ?>
    </nav>
    <script type="application/ld+json"><?php
        echo wp_json_encode( [
            '@context'        => 'https://schema.org',
            '@type'           => 'BreadcrumbList',
            'itemListElement' => $schema_items,
        ], JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE );
    ?></script>
    <?php
}

// ============================================================
// 12. SCHEMA MARKUP — bean pages (Product + Review + Rating)
// ============================================================

add_action( 'wp_head', 'cbi_bean_schema' );
function cbi_bean_schema() {
    if ( ! is_singular( 'bean' ) ) return;

    $post_id     = get_the_ID();
    $title       = get_the_title();
    $has_acf     = function_exists( 'get_field' );
    $description = $has_acf ? get_field( 'verdict' ) : get_the_excerpt();
    $rating      = $has_acf ? get_field( 'rating' ) : null;
    $price       = $has_acf ? get_field( 'current_price' ) : null;
    $asin        = $has_acf ? get_field( 'amazon_asin' ) : '';
    $url         = get_permalink();

    $roasters   = get_the_terms( $post_id, 'roaster' );
    $brand_name = ( $roasters && ! is_wp_error( $roasters ) ) ? $roasters[0]->name : '';

    $schema = [
        '@context'    => 'https://schema.org',
        '@type'       => 'Product',
        'name'        => $title,
        'description' => $description ?: '',
        'url'         => $url,
    ];

    if ( $brand_name ) {
        $schema['brand'] = [ '@type' => 'Brand', 'name' => $brand_name ];
    }

    if ( has_post_thumbnail( $post_id ) ) {
        $schema['image'] = get_the_post_thumbnail_url( $post_id, 'large' );
    }

    if ( $rating ) {
        $schema['review'] = [
            '@type'        => 'Review',
            'reviewRating' => [
                '@type'       => 'Rating',
                'ratingValue' => floatval( $rating ),
                'bestRating'  => 10,
                'worstRating' => 1,
            ],
            'author'       => [ '@type' => 'Organization', 'name' => 'Coffee Bean Index' ],
        ];
        $schema['aggregateRating'] = [
            '@type'       => 'AggregateRating',
            'ratingValue' => floatval( $rating ),
            'bestRating'  => 10,
            'worstRating' => 1,
            'reviewCount' => 1,
        ];
    }

    if ( $price ) {
        $schema['offers'] = [
            '@type'         => 'Offer',
            'price'         => number_format( floatval( $price ), 2, '.', '' ),
            'priceCurrency' => 'USD',
            'availability'  => 'https://schema.org/InStock',
            'url'           => $asin ? 'https://www.amazon.com/dp/' . $asin : $url,
        ];
    }

    echo '<script type="application/ld+json">' . wp_json_encode( $schema, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE ) . '</script>' . "\n";
}

// ============================================================
// 13. SCHEMA MARKUP — site-wide Organization + WebSite
// ============================================================

add_action( 'wp_head', 'cbi_site_schema' );
function cbi_site_schema() {
    $schema = [
        '@context' => 'https://schema.org',
        '@graph'   => [
            [
                '@type' => 'Organization',
                '@id'   => home_url( '/#organization' ),
                'name'  => get_bloginfo( 'name' ),
                'url'   => home_url(),
            ],
            [
                '@type'           => 'WebSite',
                '@id'             => home_url( '/#website' ),
                'url'             => home_url(),
                'name'            => get_bloginfo( 'name' ),
                'publisher'       => [ '@id' => home_url( '/#organization' ) ],
                'potentialAction' => [
                    '@type'       => 'SearchAction',
                    'target'      => home_url( '/?s={search_term_string}' ),
                    'query-input' => 'required name=search_term_string',
                ],
            ],
        ],
    ];
    echo '<script type="application/ld+json">' . wp_json_encode( $schema, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE ) . '</script>' . "\n";
}

// ============================================================
// 14. ROUTE TAXONOMY ARCHIVES TO OUR TEMPLATE
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
// 15. FOOTER — content hooked into GeneratePress generate_footer
// ============================================================

add_action( 'generate_footer', 'cbi_footer_content' );
function cbi_footer_content() {
    // Safe helper: returns term link or fallback '#'
    $safe_term_link = function( $slug, $taxonomy ) {
        $term = get_term_by( 'slug', $slug, $taxonomy );
        if ( $term && ! is_wp_error( $term ) ) {
            return get_term_link( $term );
        }
        return home_url( '/' );
    };

    $beans_url   = get_post_type_archive_link( 'bean' ) ?: home_url( '/beans/' );
    $espresso    = $safe_term_link( 'espresso', 'brew-method' );
    $frenchpress = $safe_term_link( 'french-press', 'brew-method' );
    $pourover    = $safe_term_link( 'pour-over', 'brew-method' );
    ?>
    <div class="footer-inner">
        <div class="footer-disclosure">
            Coffee Bean Index participates in the Amazon Services LLC Associates Program and other affiliate programs. We earn commissions on qualifying purchases at no extra cost to you. Prices are updated daily and may differ from those shown. Some content is generated or assisted by AI systems using structured product and review data.
        </div>
        <div class="footer-grid">
            <div class="footer-brand">
                <div class="footer-brand__name">Coffee Bean Index</div>
                <div class="footer-brand__desc">Data-driven coffee reviews. Price tracking, flavor profiles, and honest recommendations.</div>
            </div>
            <div class="footer-col">
                <div class="footer-col__heading">Reviews</div>
                <ul>
                    <li><a href="<?php echo esc_url( $beans_url ); ?>">All Beans</a></li>
                    <li><a href="<?php echo esc_url( $espresso ); ?>">Espresso</a></li>
                    <li><a href="<?php echo esc_url( $frenchpress ); ?>">French Press</a></li>
                    <li><a href="<?php echo esc_url( $pourover ); ?>">Pour Over</a></li>
                </ul>
            </div>
            <div class="footer-col">
                <div class="footer-col__heading">Explore</div>
                <ul>
                    <li><a href="<?php echo esc_url( home_url( '/flavor/' ) ); ?>">By Flavor</a></li>
                    <li><a href="<?php echo esc_url( home_url( '/origin/' ) ); ?>">By Origin</a></li>
                    <li><a href="<?php echo esc_url( home_url( '/roast/' ) ); ?>">By Roast</a></li>
                    <li><a href="<?php echo esc_url( home_url( '/roaster/' ) ); ?>">By Roaster</a></li>
                </ul>
            </div>
            <div class="footer-col">
                <div class="footer-col__heading">Info</div>
                <ul>
                    <li><a href="<?php echo esc_url( home_url( '/about/' ) ); ?>">About</a></li>
                    <li><a href="<?php echo esc_url( home_url( '/affiliate-disclosure/' ) ); ?>">Affiliate Disclosure</a></li>
                    <li><a href="<?php echo esc_url( home_url( '/editorial-standards/' ) ); ?>">How We Review</a></li>
                    <li><a href="<?php echo esc_url( home_url( '/privacy-policy/' ) ); ?>">Privacy Policy</a></li>
                </ul>
            </div>
        </div>
        <div class="footer-bottom">
            <span>&copy; <?php echo esc_html( date( 'Y' ) ); ?> Coffee Bean Index</span>
            <span>
                <a href="<?php echo esc_url( home_url( '/affiliate-disclosure/' ) ); ?>" style="color:inherit;">Affiliate Disclosure</a>
                &nbsp;&middot;&nbsp;
                <a href="<?php echo esc_url( home_url( '/privacy-policy/' ) ); ?>" style="color:inherit;">Privacy</a>
            </span>
        </div>
    </div>
    <?php
}

// ============================================================
// 16. INCLUDE BEANS IN MAIN QUERY ON BLOG/FEED
// ============================================================

add_action( 'pre_get_posts', 'cbi_include_beans_in_queries' );
function cbi_include_beans_in_queries( $query ) {
    if ( is_admin() || ! $query->is_main_query() ) return;
    if ( $query->is_home() || $query->is_feed() ) {
        if ( ! $query->get( 'post_type' ) ) {
            $query->set( 'post_type', [ 'post', 'bean' ] );
        }
    }
}

// ============================================================
// 17. GP — remove default page title on our custom templates
//     (we render our own hero headings)
// ============================================================

add_filter( 'generate_show_title', 'cbi_hide_title_on_custom_templates' );
function cbi_hide_title_on_custom_templates( $show ) {
    if ( is_singular( 'bean' ) ) return false;
    if ( is_post_type_archive( 'bean' ) ) return false;
    if ( is_tax( [ 'flavor-note', 'origin', 'roast-level', 'process-method', 'brew-method', 'roaster' ] ) ) return false;
    if ( is_page_template( [ 'template-roundup.php', 'template-comparison.php', 'template-guide.php', 'page-explore.php' ] ) ) return false;
    return $show;
}
