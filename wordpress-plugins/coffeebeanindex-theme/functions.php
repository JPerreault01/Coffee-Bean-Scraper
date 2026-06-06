<?php
/**
 * Coffee Bean Index — Child Theme Functions
 * Registers: bean CPT, all taxonomies, ACF field sync, enqueues, schema
 *
 * ============================================================================
 * EDITOR SHORTCODES (see section 20 below) — drop these into any guide/page
 * from the WordPress block editor (use a "Shortcode" block) without writing HTML:
 *
 *   [cbi_callout type="tip" title="Pro tip"]Body text…[/cbi_callout]
 *       type = tip | note | warning   (default: tip). Renders a .guide-callout box.
 *
 *   [cbi_pullquote cite="Editor"]A short, punchy line worth emphasising.[/cbi_pullquote]
 *       Renders a styled .guide-pullquote. cite is optional.
 *
 *   [cbi_bean id="123"]      OR   [cbi_bean slug="lavazza-super-crema"]
 *       Inline "related bean" mention — a compact linked card (name, roaster,
 *       rating) that pulls live data from the Bean CPT. Dofollow internal link.
 *
 * Matching block patterns are also registered (category "Coffee Bean Index"):
 *   "Guide callout box" and "Inline bean mention" — insert via the block
 *   inserter → Patterns tab for a visual starting point.
 * ============================================================================
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

    // Child theme stylesheet.
    // S3 fix: previously this loaded our style.css a SECOND time (handle 'cbi-child')
    // BEFORE GeneratePress's main.css, while GP auto-enqueued it again as 'generate-child'
    // AFTER main.css. Two <link>s to the same file + a fragile cascade. We now enqueue once,
    // depending on 'generate-style' (GP's main.css) so our overrides reliably cascade LAST,
    // and dequeue GP's duplicate auto-enqueue in cbi_dequeue_duplicate_child_css().
    wp_enqueue_style(
        'cbi-child',
        get_stylesheet_directory_uri() . '/style.css',
        [ 'generate-style', 'cbi-fonts' ],
        '2.1.0'
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

    // Guide ToC + smooth-scroll JS — only on the guide page template.
    // Builds the sticky table of contents from the article's H2/H3 headings.
    if ( is_page_template( 'template-guide.php' ) ) {
        wp_enqueue_script(
            'cbi-guide-toc',
            get_stylesheet_directory_uri() . '/js/guide-toc.js',
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

// S3 fix: remove GeneratePress's automatic child-theme stylesheet enqueue so our
// style.css is not loaded twice. We enqueue it ourselves as 'cbi-child' (depends on
// 'generate-style', so it still cascades after GP's main.css). Priority 100 ensures
// this runs after GP has registered 'generate-child'.
add_action( 'wp_enqueue_scripts', 'cbi_dequeue_duplicate_child_css', 100 );
function cbi_dequeue_duplicate_child_css() {
    wp_dequeue_style( 'generate-child' );
}

// ============================================================
// 1b. BODY CLASSES — layout contract for custom templates
//
//     GeneratePress lays out .site-content as a desktop flex ROW that expects a
//     single .content-area child. Our custom templates emit several direct children
//     (hero band, disclosure, content container), which GP squeezed into cramped
//     side-by-side columns at >768px. We tag every custom template with:
//       - 'full-width-content'  → GP's own rules drop the 1200px container cap and the
//                                  40px .site-content padding (full-bleed heroes).
//       - 'cbi-app'             → our hook for the .site-content { display:block } reset
//                                  in style.css (GP has no body class that unsets the
//                                  flex row, so CSS handles that half).
// ============================================================

add_filter( 'body_class', 'cbi_template_body_classes' );
function cbi_template_body_classes( $classes ) {
    $is_cbi_template = (
        is_singular( 'bean' )
        || is_post_type_archive( 'bean' )
        || is_tax( [ 'flavor-note', 'origin', 'roast-level', 'process-method', 'brew-method', 'roaster' ] )
        || is_front_page()
        || is_page_template( [ 'template-roundup.php', 'template-comparison.php', 'template-guide.php', 'page-explore.php' ] )
    );
    if ( $is_cbi_template ) {
        $classes[] = 'cbi-app';
        if ( ! in_array( 'full-width-content', $classes, true ) ) {
            $classes[] = 'full-width-content';
        }
    }
    // Scope guide-page CSS so its typographic + ToC styles can't bleed into
    // bean reviews or other templates. All guide CSS in style.css is nested
    // under .guide-page.
    if ( is_page_template( 'template-guide.php' ) ) {
        $classes[] = 'guide-page';
    }
    return $classes;
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
    $title    = get_the_title( $post_id );
    $link     = get_permalink( $post_id );
    $verdict  = function_exists( 'get_field' ) ? get_field( 'verdict', $post_id ) : '';
    if ( ! $verdict ) $verdict = get_the_excerpt( $post_id );
    $rating   = function_exists( 'get_field' ) ? get_field( 'rating', $post_id ) : '';
    $price_oz = function_exists( 'get_field' ) ? get_field( 'price_per_oz', $post_id ) : '';

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
            <?php echo get_the_post_thumbnail( $post_id, 'medium', [ 'loading' => 'lazy', 'width' => '400', 'height' => '225', 'alt' => esc_attr( $title ) ] ); ?>
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
            <div class="bean-card__metrics">
                <?php if ( $rating !== '' && $rating !== null ) : ?>
                    <div class="bean-card__rating tabular-nums"><?php echo esc_html( $rating ); ?><span class="bean-card__rating-label">/ 10</span></div>
                <?php endif; ?>
                <?php if ( $price_oz !== '' && $price_oz !== null ) : ?>
                    <div class="bean-card__price tabular-nums">$<?php echo esc_html( number_format( (float) $price_oz, 2 ) ); ?><span class="bean-card__price-label">/oz</span></div>
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
            '@type'         => 'Review',
            'reviewRating'  => [
                '@type'       => 'Rating',
                'ratingValue' => floatval( $rating ),
                'bestRating'  => 10,
                'worstRating' => 1,
            ],
            'author'        => [ '@type' => 'Organization', 'name' => 'Coffee Bean Index' ],
            'reviewBody'    => $description ?: '',
            'datePublished' => get_the_date( 'c' ),
            'url'           => $url,
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

    // BreadcrumbList — mirrors the .bean-hero__breadcrumb nav in single-bean.php
    $roasters_bc  = get_the_terms( $post_id, 'roaster' );
    $bc_items     = [
        [ '@type' => 'ListItem', 'position' => 1, 'name' => 'Home',  'item' => home_url() ],
        [ '@type' => 'ListItem', 'position' => 2, 'name' => 'Beans', 'item' => get_post_type_archive_link( 'bean' ) ?: home_url( '/beans/' ) ],
    ];
    $bc_pos = 3;
    if ( $roasters_bc && ! is_wp_error( $roasters_bc ) ) {
        $bc_items[] = [
            '@type'    => 'ListItem',
            'position' => $bc_pos++,
            'name'     => $roasters_bc[0]->name,
            'item'     => get_term_link( $roasters_bc[0] ),
        ];
    }
    $bc_items[] = [ '@type' => 'ListItem', 'position' => $bc_pos, 'name' => $title, 'item' => $url ];
    echo '<script type="application/ld+json">' . wp_json_encode( [
        '@context'        => 'https://schema.org',
        '@type'           => 'BreadcrumbList',
        'itemListElement' => $bc_items,
    ], JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE ) . '</script>' . "\n";

    // FAQPage — built from ACF fields; only outputs when field data exists
    if ( $has_acf ) {
        $faq_entries = [];

        $tasting_raw = get_field( 'tasting_notes' );
        if ( $tasting_raw ) {
            $notes = array_filter( array_map( 'trim', explode( "\n", $tasting_raw ) ) );
            if ( ! empty( $notes ) ) {
                $faq_entries[] = [
                    'q' => 'What does ' . $title . ' taste like?',
                    'a' => implode( ' ', array_slice( $notes, 0, 3 ) ),
                ];
            }
        }

        $whos_for_raw = get_field( 'whos_for' );
        if ( $whos_for_raw ) {
            $faq_entries[] = [
                'q' => 'Who is ' . $title . ' best for?',
                'a' => $whos_for_raw,
            ];
        }

        $whos_not_raw = get_field( 'whos_not_for' );
        if ( $whos_not_raw ) {
            $faq_entries[] = [
                'q' => 'Who should skip ' . $title . '?',
                'a' => $whos_not_raw,
            ];
        }

        if ( ! empty( $faq_entries ) ) {
            $faq_schema = [
                '@context'   => 'https://schema.org',
                '@type'      => 'FAQPage',
                'mainEntity' => array_map( function ( $faq ) {
                    return [
                        '@type'          => 'Question',
                        'name'           => $faq['q'],
                        'acceptedAnswer' => [ '@type' => 'Answer', 'text' => $faq['a'] ],
                    ];
                }, $faq_entries ),
            ];
            echo '<script type="application/ld+json">' . wp_json_encode( $faq_schema, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE ) . '</script>' . "\n";
        }
    }
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

// ============================================================
// 18. GP — force no-sidebar + full-width on all custom templates
//
//     Without this filter, GP falls back to its global Customizer
//     layout (usually "Content + Sidebar") and injects an empty
//     .widget-area column next to custom content, shrinking
//     .content-area and breaking every custom grid layout.
//     This is the primary fix for the phantom sidebar / squeezed
//     column issues on bean, taxonomy, and homepage templates.
// ============================================================

add_filter( 'generate_sidebar_layout', 'cbi_force_no_sidebar' );
function cbi_force_no_sidebar( $layout ) {
    if (
        is_singular( 'bean' )
        || is_post_type_archive( 'bean' )
        || is_tax( [ 'flavor-note', 'origin', 'roast-level', 'process-method', 'brew-method', 'roaster' ] )
        || is_page_template( [ 'template-roundup.php', 'template-comparison.php', 'template-guide.php', 'page-explore.php' ] )
        || is_front_page()
    ) {
        return 'no-sidebar';
    }
    return $layout;
}

// ============================================================
// 19. SCHEMA MARKUP — taxonomy archive pages (ItemList)
//
//     archive-bean.php already outputs its own ItemList inline.
//     This covers the six custom taxonomy archives routed via
//     taxonomy-bean-archive.php, which previously had only BreadcrumbList.
// ============================================================

add_action( 'wp_head', 'cbi_taxonomy_schema' );
function cbi_taxonomy_schema() {
    $our_taxes = [ 'flavor-note', 'origin', 'roast-level', 'process-method', 'brew-method', 'roaster' ];
    if ( ! is_tax( $our_taxes ) ) return;

    global $wp_query;
    if ( empty( $wp_query->posts ) ) return;

    $term  = get_queried_object();
    $items = [];
    foreach ( $wp_query->posts as $i => $post ) {
        $items[] = [
            '@type'    => 'ListItem',
            'position' => $i + 1,
            'name'     => get_the_title( $post->ID ),
            'url'      => get_permalink( $post->ID ),
        ];
    }

    $schema = [
        '@context'        => 'https://schema.org',
        '@type'           => 'ItemList',
        'name'            => $term->name . ' Coffee Beans — Coffee Bean Index',
        'numberOfItems'   => count( $items ),
        'itemListElement' => $items,
    ];
    if ( $term->description ) {
        $schema['description'] = wp_strip_all_tags( $term->description );
    }

    echo '<script type="application/ld+json">' . wp_json_encode( $schema, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE ) . '</script>' . "\n";
}

// Explicitly signal GP that custom pages use the full container width.
// Prevents GP's content-width calculation from reserving sidebar space
// even when the sidebar filter already suppresses the widget-area output.
add_filter( 'generate_content_width', 'cbi_force_full_content_width' );
function cbi_force_full_content_width( $width ) {
    if (
        is_singular( 'bean' )
        || is_post_type_archive( 'bean' )
        || is_tax( [ 'flavor-note', 'origin', 'roast-level', 'process-method', 'brew-method', 'roaster' ] )
        || is_page_template( [ 'template-roundup.php', 'template-comparison.php', 'template-guide.php', 'page-explore.php' ] )
        || is_front_page()
    ) {
        return 100;
    }
    return $width;
}

// ============================================================
// 20. GUIDE-PAGE HELPERS — hub-and-spoke queries
//
//     Guides are HUB pages. These helpers wire the spokes:
//     related bean reviews (sharing a taxonomy term) and sibling
//     guides. Used by template-guide.php and the homepage guides grid.
// ============================================================

/**
 * Resolve which bean-taxonomy terms a guide relates to.
 *
 * Resolution order:
 *   1. ACF text field "related_taxonomy_slug" on the page (comma-separated
 *      term slugs — explicit editor override, highest priority).
 *   2. Auto-match: tokenise the page slug and title and look those tokens up
 *      against term slugs/names across the bean taxonomies. An origin guide at
 *      /ethiopia-coffee/ auto-resolves the origin term "ethiopia".
 *
 * @return WP_Term[]  Matched terms (may be empty).
 */
function cbi_guide_taxonomy_terms( $post_id ) {
    $taxes = [ 'origin', 'brew-method', 'flavor-note', 'roast-level', 'process-method' ];
    $found = [];
    $seen  = [];

    $add_term = function ( $term ) use ( &$found, &$seen ) {
        if ( $term && ! is_wp_error( $term ) && empty( $seen[ $term->taxonomy . ':' . $term->term_id ] ) ) {
            $found[] = $term;
            $seen[ $term->taxonomy . ':' . $term->term_id ] = true;
        }
    };

    // 1. Explicit ACF override.
    if ( function_exists( 'get_field' ) ) {
        $slugs = get_field( 'related_taxonomy_slug', $post_id );
        if ( $slugs ) {
            foreach ( array_filter( array_map( 'trim', explode( ',', $slugs ) ) ) as $slug ) {
                foreach ( $taxes as $tax ) {
                    $term = get_term_by( 'slug', $slug, $tax );
                    if ( $term && ! is_wp_error( $term ) ) { $add_term( $term ); break; }
                }
            }
        }
    }

    // 2. Auto-match from slug + title tokens.
    if ( empty( $found ) ) {
        $haystack = get_post_field( 'post_name', $post_id ) . '-' . sanitize_title( get_the_title( $post_id ) );
        $tokens   = array_unique( array_filter( explode( '-', $haystack ) ) );
        foreach ( $taxes as $tax ) {
            foreach ( $tokens as $token ) {
                if ( strlen( $token ) < 3 ) continue; // skip "of", "to", noise
                $term = get_term_by( 'slug', $token, $tax );
                if ( $term && ! is_wp_error( $term ) ) { $add_term( $term ); }
            }
        }
    }

    return $found;
}

/**
 * WP_Query of bean reviews related to a guide, ordered by rating desc.
 * Falls back to top-rated beans when no shared term resolves.
 *
 * @param int $post_id  Guide page ID.
 * @param int $limit    Max cards (default 6, per spec).
 */
function cbi_guide_related_beans( $post_id, $limit = 6 ) {
    $args = [
        'post_type'      => 'bean',
        'posts_per_page' => $limit,
        'post_status'    => 'publish',
        'orderby'        => 'meta_value_num',
        'meta_key'       => 'rating',
        'order'          => 'DESC',
        'no_found_rows'  => true,
    ];

    $terms = cbi_guide_taxonomy_terms( $post_id );
    if ( ! empty( $terms ) ) {
        $tax_query = [ 'relation' => 'OR' ];
        foreach ( $terms as $term ) {
            $tax_query[] = [
                'taxonomy' => $term->taxonomy,
                'field'    => 'term_id',
                'terms'    => $term->term_id,
            ];
        }
        $args['tax_query'] = $tax_query;
    }

    return new WP_Query( $args );
}

/**
 * Pages that use template-guide.php, excluding $exclude_id.
 * "Sibling guides" for the related-guides block + homepage guides grid.
 */
function cbi_get_guides( $limit = 3, $exclude_id = 0 ) {
    return new WP_Query( [
        'post_type'      => 'page',
        'posts_per_page' => $limit,
        'post_status'    => 'publish',
        'post__not_in'   => $exclude_id ? [ $exclude_id ] : [],
        'orderby'        => 'modified',
        'order'          => 'DESC',
        'no_found_rows'  => true,
        'meta_query'     => [
            [
                'key'   => '_wp_page_template',
                'value' => 'template-guide.php',
            ],
        ],
    ] );
}

/**
 * Beans currently priced below their 30-day average.
 *
 * The price-history database lives on the VPS (/opt/data/prices.db) and is NOT
 * exposed to WordPress yet, so this returns [] by default and the homepage
 * renders a labelled placeholder. To light it up, hook this filter and return
 * an array of rows in EXACTLY this shape:
 *
 *   add_filter( 'cbi_price_drop_beans', function () {
 *       return [
 *           [ 'post_id' => 42, 'current' => 11.49, 'avg30' => 13.20, 'pct' => 13 ],
 *           // …ordered by pct desc, best deals first
 *       ];
 *   } );
 *
 * The scraper (price_scraper.py) is the natural producer: write a daily JSON
 * snapshot or a wp_options transient the filter can read.
 *
 * @return array<int,array{post_id:int,current:float,avg30:float,pct:int}>
 */
function cbi_price_drop_beans( $limit = 4 ) {
    $rows = apply_filters( 'cbi_price_drop_beans', [] );
    return is_array( $rows ) ? array_slice( $rows, 0, $limit ) : [];
}

// ============================================================
// 21. EDITOR SHORTCODES — callout, pull quote, inline bean mention
//     (Documented in the comment block at the top of this file.)
// ============================================================

add_shortcode( 'cbi_callout', 'cbi_shortcode_callout' );
function cbi_shortcode_callout( $atts, $content = '' ) {
    $a = shortcode_atts( [ 'type' => 'tip', 'title' => '' ], $atts, 'cbi_callout' );
    $type  = in_array( $a['type'], [ 'tip', 'note', 'warning' ], true ) ? $a['type'] : 'tip';
    $label = $a['title'] !== '' ? $a['title'] : ucfirst( $type );

    $body = wpautop( do_shortcode( $content ) );

    ob_start(); ?>
    <aside class="guide-callout guide-callout--<?php echo esc_attr( $type ); ?>" role="note">
        <p class="guide-callout__label"><?php echo esc_html( $label ); ?></p>
        <div class="guide-callout__body"><?php echo wp_kses_post( $body ); ?></div>
    </aside>
    <?php
    return ob_get_clean();
}

add_shortcode( 'cbi_pullquote', 'cbi_shortcode_pullquote' );
function cbi_shortcode_pullquote( $atts, $content = '' ) {
    $a = shortcode_atts( [ 'cite' => '' ], $atts, 'cbi_pullquote' );
    ob_start(); ?>
    <blockquote class="guide-pullquote">
        <p><?php echo wp_kses_post( do_shortcode( $content ) ); ?></p>
        <?php if ( $a['cite'] !== '' ) : ?>
            <cite class="guide-pullquote__cite"><?php echo esc_html( $a['cite'] ); ?></cite>
        <?php endif; ?>
    </blockquote>
    <?php
    return ob_get_clean();
}

add_shortcode( 'cbi_bean', 'cbi_shortcode_bean' );
function cbi_shortcode_bean( $atts ) {
    $a = shortcode_atts( [ 'id' => '', 'slug' => '' ], $atts, 'cbi_bean' );

    $bean = null;
    if ( $a['id'] ) {
        $post = get_post( (int) $a['id'] );
        if ( $post && $post->post_type === 'bean' && $post->post_status === 'publish' ) $bean = $post;
    } elseif ( $a['slug'] ) {
        $post = get_page_by_path( sanitize_title( $a['slug'] ), OBJECT, 'bean' );
        if ( $post && $post->post_status === 'publish' ) $bean = $post;
    }

    if ( ! $bean ) {
        return '<span class="cbi-bean-inline cbi-bean-inline--missing">[bean not found]</span>';
    }

    $bid      = $bean->ID;
    $rating   = function_exists( 'get_field' ) ? get_field( 'rating', $bid ) : '';
    $roasters = get_the_terms( $bid, 'roaster' );
    $roaster  = ( $roasters && ! is_wp_error( $roasters ) ) ? $roasters[0]->name : '';

    ob_start(); ?>
    <a class="cbi-bean-inline" href="<?php echo esc_url( get_permalink( $bid ) ); ?>" rel="dofollow">
        <span class="cbi-bean-inline__label">Reviewed</span>
        <span class="cbi-bean-inline__name"><?php echo esc_html( get_the_title( $bid ) ); ?></span>
        <?php if ( $roaster ) : ?>
            <span class="cbi-bean-inline__roaster"><?php echo esc_html( $roaster ); ?></span>
        <?php endif; ?>
        <?php if ( $rating !== '' && $rating !== null ) : ?>
            <span class="cbi-bean-inline__rating tabular-nums"><?php echo esc_html( $rating ); ?>/10</span>
        <?php endif; ?>
    </a>
    <?php
    return ob_get_clean();
}

// ============================================================
// 22. BLOCK PATTERNS — visual starting points for the shortcodes
// ============================================================

add_action( 'init', 'cbi_register_block_patterns' );
function cbi_register_block_patterns() {
    if ( ! function_exists( 'register_block_pattern_category' ) ) return;

    register_block_pattern_category( 'cbi', [ 'label' => 'Coffee Bean Index' ] );

    register_block_pattern( 'cbi/guide-callout', [
        'title'       => 'Guide callout box',
        'description' => 'A tip / note / warning box for guide pages.',
        'categories'  => [ 'cbi' ],
        'content'     => "<!-- wp:shortcode -->\n[cbi_callout type=\"tip\" title=\"Pro tip\"]Swap in your tip here. Keep it to a sentence or two.[/cbi_callout]\n<!-- /wp:shortcode -->",
    ] );

    register_block_pattern( 'cbi/inline-bean', [
        'title'       => 'Inline bean mention',
        'description' => 'A compact linked card pulling live data from a bean review.',
        'categories'  => [ 'cbi' ],
        'content'     => "<!-- wp:shortcode -->\n[cbi_bean slug=\"lavazza-super-crema\"]\n<!-- /wp:shortcode -->",
    ] );
}
