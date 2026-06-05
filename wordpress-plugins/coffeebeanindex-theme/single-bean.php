<?php
/**
 * Template: Single Bean Page
 * File: single-bean.php
 *
 * Full bean profile page — review, specs, sensory profile,
 * radar chart, price chart, similar beans, taxonomy links.
 * Affiliate disclosure is placed near the top (FTC requirement).
 */

get_header(); ?>

<?php while ( have_posts() ) : the_post();
    $post_id        = get_the_ID();
    $title          = get_the_title();
    $has_acf        = function_exists( 'get_field' );
    $verdict        = $has_acf ? get_field( 'verdict' )         : '';
    $rating         = $has_acf ? get_field( 'rating' )          : '';
    $weight_oz      = $has_acf ? get_field( 'weight_oz' )       : '';
    $price_per_oz   = $has_acf ? get_field( 'price_per_oz' )    : '';
    $current_price  = $has_acf ? get_field( 'current_price' )   : '';
    $amazon_url     = $has_acf ? get_field( 'amazon_affiliate_url' ) : '';
    $roaster_url    = $has_acf ? get_field( 'roaster_url' )     : '';
    $product_id     = $has_acf ? get_field( 'product_id' )      : '';
    $acidity        = $has_acf ? get_field( 'acidity' )         : '';
    $body           = $has_acf ? get_field( 'body' )            : '';
    $sweetness      = $has_acf ? get_field( 'sweetness' )       : '';
    $bitterness     = $has_acf ? get_field( 'bitterness' )      : '';
    $roast_int      = $has_acf ? get_field( 'roast_intensity' ) : '';
    $tasting_notes  = $has_acf ? get_field( 'tasting_notes' )   : '';
    $whos_for       = $has_acf ? get_field( 'whos_for' )        : '';
    $whos_not_for   = $has_acf ? get_field( 'whos_not_for' )    : '';
    $price_analysis = $has_acf ? get_field( 'price_analysis' )  : '';
    $linked_recipes = $has_acf ? get_field( 'linked_recipes' )  : [];
    $linked_guides  = $has_acf ? get_field( 'linked_guides' )   : [];
    $last_reviewed  = $has_acf ? get_field( 'last_reviewed' )   : '';
    $personal_mode  = $has_acf ? get_field( 'personal_mode' )   : false;

    // Taxonomy terms
    $roasters     = get_the_terms( $post_id, 'roaster' );
    $origins      = get_the_terms( $post_id, 'origin' );
    $roast_levels = get_the_terms( $post_id, 'roast-level' );
    $processes    = get_the_terms( $post_id, 'process-method' );
    $brew_methods = get_the_terms( $post_id, 'brew-method' );
    $flavor_notes = get_the_terms( $post_id, 'flavor-note' );

    $roaster_name = ( $roasters  && ! is_wp_error( $roasters ) )     ? $roasters[0]->name  : '';
    $origin_name  = ( $origins   && ! is_wp_error( $origins ) )      ? $origins[0]->name   : '';
    $roast_name   = ( $roast_levels && ! is_wp_error( $roast_levels ) ) ? $roast_levels[0]->name : '';
    $process_name = ( $processes && ! is_wp_error( $processes ) )     ? $processes[0]->name : '';

    $has_sensory = ( $acidity || $body || $sweetness || $bitterness || $roast_int );
?>

<!-- ============================================================
     BEAN HERO
     ============================================================ -->
<section class="bean-hero">
    <div class="bean-hero__inner">

        <!-- Breadcrumb -->
        <div class="bean-hero__breadcrumb">
            <a href="<?php echo esc_url( home_url() ); ?>">Home</a>
            <span>/</span>
            <a href="<?php echo esc_url( get_post_type_archive_link( 'bean' ) ?: home_url( '/beans/' ) ); ?>">Beans</a>
            <?php if ( $roaster_name ) : ?>
                <span>/</span>
                <a href="<?php echo esc_url( get_term_link( $roasters[0] ) ); ?>"><?php echo esc_html( $roaster_name ); ?></a>
            <?php endif; ?>
            <span>/</span>
            <span><?php echo esc_html( $title ); ?></span>
        </div>

        <div class="bean-hero__top">
            <div>
                <?php if ( $roaster_name ) : ?>
                    <div class="bean-hero__roaster"><?php echo esc_html( $roaster_name ); ?></div>
                <?php endif; ?>
                <h1 class="bean-hero__title"><?php echo esc_html( $title ); ?></h1>
                <?php if ( $verdict ) : ?>
                    <div class="bean-hero__verdict"><?php echo esc_html( $verdict ); ?></div>
                <?php endif; ?>

                <!-- Taxonomy tags -->
                <div class="bean-hero__tags">
                    <?php if ( $roast_levels && ! is_wp_error( $roast_levels ) ) :
                        foreach ( $roast_levels as $term ) : ?>
                            <a href="<?php echo esc_url( get_term_link( $term ) ); ?>" class="bean-tag bean-tag--roast"><?php echo esc_html( $term->name ); ?></a>
                        <?php endforeach;
                    endif; ?>
                    <?php if ( $origins && ! is_wp_error( $origins ) ) :
                        foreach ( $origins as $term ) : ?>
                            <a href="<?php echo esc_url( get_term_link( $term ) ); ?>" class="bean-tag bean-tag--origin"><?php echo esc_html( $term->name ); ?></a>
                        <?php endforeach;
                    endif; ?>
                    <?php if ( $processes && ! is_wp_error( $processes ) ) :
                        foreach ( $processes as $term ) : ?>
                            <a href="<?php echo esc_url( get_term_link( $term ) ); ?>" class="bean-tag"><?php echo esc_html( $term->name ); ?></a>
                        <?php endforeach;
                    endif; ?>
                    <?php if ( $brew_methods && ! is_wp_error( $brew_methods ) ) :
                        foreach ( $brew_methods as $term ) : ?>
                            <a href="<?php echo esc_url( get_term_link( $term ) ); ?>" class="bean-tag bean-tag--brew"><?php echo esc_html( $term->name ); ?></a>
                        <?php endforeach;
                    endif; ?>
                    <?php if ( $flavor_notes && ! is_wp_error( $flavor_notes ) ) :
                        foreach ( array_slice( $flavor_notes, 0, 4 ) as $term ) : ?>
                            <a href="<?php echo esc_url( get_term_link( $term ) ); ?>" class="bean-tag bean-tag--flavor"><?php echo esc_html( $term->name ); ?></a>
                        <?php endforeach;
                    endif; ?>
                </div>

                <?php if ( $personal_mode ) : ?>
                    <p style="font-size:var(--text-xs);color:var(--cbi-text-dim);font-family:var(--font-mono);margin-top:var(--space-3);margin-bottom:0;">
                        Personally reviewed by the site author.
                    </p>
                <?php endif; ?>
            </div>

            <?php if ( $rating !== '' && $rating !== null ) : ?>
                <div class="bean-rating" aria-label="Rating: <?php echo esc_attr( $rating ); ?> out of 10">
                    <div class="bean-rating__score"><?php echo esc_html( $rating ); ?></div>
                    <div class="bean-rating__label">/ 10</div>
                </div>
            <?php endif; ?>
        </div>

    </div>
</section>

<!-- Affiliate disclosure — near top, above buy links (FTC requirement) -->
<div class="cbi-disclosure-inline" style="border-radius:0;border-left:none;border-right:none;border-top:none;">
    <div class="cbi-container">
        This page contains affiliate links. We may earn commissions from qualifying purchases at no extra cost to you.
    </div>
</div>

<!-- ============================================================
     MAIN CONTENT GRID
     ============================================================ -->
<div class="cbi-container">
    <div class="cbi-content-grid">

        <!-- ===================== LEFT COLUMN ===================== -->
        <main class="bean-main">

            <!-- Profile: spec table + sensory bars + flavor radar, grouped into
                 one balanced two-column card so the radar reads as part of the
                 product profile instead of floating in dead space. -->
            <div class="cbi-section">
                <div class="cbi-section__heading">Profile</div>
                <div class="bean-profile<?php echo $has_sensory ? '' : ' bean-profile--specs-only'; ?>">

                    <!-- Left column: specs -->
                    <div class="bean-profile__col">
                        <div class="bean-specs">
                            <?php if ( $roaster_name ) : ?>
                            <div class="bean-specs__row">
                                <div class="bean-specs__label">Roaster</div>
                                <div class="bean-specs__value">
                                    <a href="<?php echo esc_url( get_term_link( $roasters[0] ) ); ?>"><?php echo esc_html( $roaster_name ); ?></a>
                                </div>
                            </div>
                            <?php endif; ?>

                            <?php if ( $roast_name ) : ?>
                            <div class="bean-specs__row">
                                <div class="bean-specs__label">Roast</div>
                                <div class="bean-specs__value">
                                    <a href="<?php echo esc_url( get_term_link( $roast_levels[0] ) ); ?>"><?php echo esc_html( $roast_name ); ?></a>
                                </div>
                            </div>
                            <?php endif; ?>

                            <?php if ( $origin_name ) : ?>
                            <div class="bean-specs__row">
                                <div class="bean-specs__label">Origin</div>
                                <div class="bean-specs__value">
                                    <a href="<?php echo esc_url( get_term_link( $origins[0] ) ); ?>"><?php echo esc_html( $origin_name ); ?></a>
                                </div>
                            </div>
                            <?php endif; ?>

                            <?php if ( $process_name ) : ?>
                            <div class="bean-specs__row">
                                <div class="bean-specs__label">Process</div>
                                <div class="bean-specs__value">
                                    <a href="<?php echo esc_url( get_term_link( $processes[0] ) ); ?>"><?php echo esc_html( $process_name ); ?></a>
                                </div>
                            </div>
                            <?php endif; ?>

                            <?php if ( $brew_methods && ! is_wp_error( $brew_methods ) ) : ?>
                            <div class="bean-specs__row">
                                <div class="bean-specs__label">Best For</div>
                                <div class="bean-specs__value">
                                    <?php foreach ( $brew_methods as $term ) : ?>
                                        <a href="<?php echo esc_url( get_term_link( $term ) ); ?>" class="bean-tag bean-tag--brew"><?php echo esc_html( $term->name ); ?></a>
                                    <?php endforeach; ?>
                                </div>
                            </div>
                            <?php endif; ?>

                            <?php if ( $weight_oz ) : ?>
                            <div class="bean-specs__row">
                                <div class="bean-specs__label">Weight</div>
                                <div class="bean-specs__value tabular-nums"><?php echo esc_html( $weight_oz ); ?> oz</div>
                            </div>
                            <?php endif; ?>

                            <?php if ( $price_per_oz ) : ?>
                            <div class="bean-specs__row">
                                <div class="bean-specs__label">Price / oz</div>
                                <div class="bean-specs__value tabular-nums">$<?php echo esc_html( number_format( $price_per_oz, 2 ) ); ?></div>
                            </div>
                            <?php endif; ?>
                        </div>
                    </div>

                    <?php if ( $has_sensory ) :
                        $radar_id   = 'bean-radar-' . $post_id;
                        $radar_data = wp_json_encode( [
                            intval( $acidity ),
                            intval( $body ),
                            intval( $sweetness ),
                            intval( $bitterness ),
                            intval( $roast_int ),
                        ] );
                    ?>
                    <!-- Right column: sensory bars over the flavor radar -->
                    <div class="bean-profile__col bean-profile__viz">
                        <div class="sensory-profile">
                            <?php
                            if ( $acidity )    cbi_sensory_bar( 'Acidity',    $acidity );
                            if ( $body )       cbi_sensory_bar( 'Body',       $body );
                            if ( $sweetness )  cbi_sensory_bar( 'Sweetness',  $sweetness );
                            if ( $bitterness ) cbi_sensory_bar( 'Bitterness', $bitterness );
                            if ( $roast_int )  cbi_sensory_bar( 'Roast',      $roast_int );
                            ?>
                        </div>
                        <div class="radar-wrap">
                            <canvas id="<?php echo esc_attr( $radar_id ); ?>" role="img" aria-label="Flavor radar chart for <?php echo esc_attr( $title ); ?>"></canvas>
                        </div>
                        <script>
                        (function() {
                            function renderRadar() {
                                var canvas = document.getElementById('<?php echo esc_js( $radar_id ); ?>');
                                if ( ! canvas || typeof Chart === 'undefined' ) return;
                                new Chart( canvas, {
                                    type: 'radar',
                                    data: {
                                        labels: ['Acidity', 'Body', 'Sweetness', 'Bitterness', 'Roast'],
                                        datasets: [{
                                            data: <?php echo $radar_data; ?>,
                                            backgroundColor: 'rgba(158, 43, 14, 0.10)',
                                            borderColor: 'rgba(158, 43, 14, 0.75)',
                                            borderWidth: 2,
                                            pointBackgroundColor: '#9e2b0e',
                                            pointRadius: 4,
                                            pointHoverRadius: 5,
                                        }]
                                    },
                                    options: {
                                        maintainAspectRatio: true,
                                        scales: {
                                            r: {
                                                min: 0,
                                                max: 5,
                                                ticks: { stepSize: 1, display: false },
                                                grid: { color: 'rgba(28, 20, 16, 0.10)' },
                                                angleLines: { color: 'rgba(28, 20, 16, 0.10)' },
                                                pointLabels: {
                                                    color: '#5c5048',
                                                    font: { family: "'DM Mono', monospace", size: 11 }
                                                }
                                            }
                                        },
                                        plugins: { legend: { display: false } },
                                        animation: {
                                            duration: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 800
                                        }
                                    }
                                });
                            }
                            if ( typeof Chart !== 'undefined' ) {
                                renderRadar();
                            } else {
                                window.addEventListener('load', renderRadar);
                            }
                        })();
                        </script>
                    </div>
                    <?php endif; ?>

                </div>
            </div>

            <!-- Tasting Notes -->
            <?php if ( $tasting_notes ) : ?>
            <div class="cbi-section">
                <div class="cbi-section__heading">Tasting Notes</div>
                <ul class="tasting-notes">
                    <?php foreach ( array_filter( array_map( 'trim', explode( "\n", $tasting_notes ) ) ) as $note ) : ?>
                        <li><?php echo esc_html( $note ); ?></li>
                    <?php endforeach; ?>
                </ul>
            </div>
            <?php endif; ?>

            <!-- Review Body — section headings use H2 (direct subsections of the H1 bean title) -->
            <div class="cbi-section">
                <div class="review-body">
                    <?php if ( $whos_for ) : ?>
                    <h2>Who it&rsquo;s for</h2>
                    <p><?php echo esc_html( $whos_for ); ?></p>
                    <?php endif; ?>

                    <?php if ( $whos_not_for ) : ?>
                    <h2>Who should skip it</h2>
                    <p><?php echo esc_html( $whos_not_for ); ?></p>
                    <?php endif; ?>

                    <?php if ( get_the_content() ) : ?>
                    <h2>Full review</h2>
                    <?php the_content(); ?>
                    <?php endif; ?>

                    <?php if ( $price_analysis ) : ?>
                    <h2>Price analysis</h2>
                    <p><?php echo esc_html( $price_analysis ); ?></p>
                    <?php endif; ?>

                    <?php if ( $rating !== '' && $rating !== null ) : ?>
                    <h2>Rating</h2>
                    <p style="font-family:var(--font-mono);font-size:var(--text-2xl);font-weight:500;color:var(--cbi-accent);font-variant-numeric:tabular-nums;">
                        <?php echo esc_html( $rating ); ?>/10
                    </p>
                    <?php endif; ?>
                </div>
            </div>

            <!-- FAQ Accordion — sourced from ACF fields; visible + searchable  -->
            <?php
            $faq_items = [];
            if ( $tasting_notes ) {
                $notes_arr = array_filter( array_map( 'trim', explode( "\n", $tasting_notes ) ) );
                if ( ! empty( $notes_arr ) ) {
                    $faq_items[] = [
                        'q' => 'What does ' . $title . ' taste like?',
                        'a' => implode( ' ', array_slice( $notes_arr, 0, 3 ) ),
                    ];
                }
            }
            if ( $whos_for ) {
                $faq_items[] = [
                    'q' => 'Who is ' . $title . ' best for?',
                    'a' => $whos_for,
                ];
            }
            if ( $whos_not_for ) {
                $faq_items[] = [
                    'q' => 'Who should skip ' . $title . '?',
                    'a' => $whos_not_for,
                ];
            }
            if ( ! empty( $faq_items ) ) : ?>
            <div class="cbi-section">
                <div class="cbi-section__heading">FAQ</div>
                <div class="cbi-faq">
                    <?php foreach ( $faq_items as $faq_item ) : ?>
                    <details class="cbi-faq__item">
                        <summary class="cbi-faq__question"><?php echo esc_html( $faq_item['q'] ); ?></summary>
                        <div class="cbi-faq__answer">
                            <p><?php echo esc_html( $faq_item['a'] ); ?></p>
                        </div>
                    </details>
                    <?php endforeach; ?>
                </div>
            </div>
            <?php endif; ?>

            <!-- Price History Chart — shortcode preserves product_id linkage to SQLite -->
            <?php if ( $product_id ) : ?>
            <div class="cbi-section">
                <div class="cbi-section__heading">Price History</div>
                <div class="price-chart-wrap">
                    <?php echo do_shortcode( '[coffee_price_chart product_id="' . esc_attr( $product_id ) . '"]' ); ?>
                </div>
            </div>
            <?php endif; ?>

            <!-- All Flavor Tags -->
            <?php if ( $flavor_notes && ! is_wp_error( $flavor_notes ) ) : ?>
            <div class="cbi-section">
                <div class="cbi-section__heading">Flavor Notes</div>
                <div style="display:flex;flex-wrap:wrap;gap:var(--space-2);">
                    <?php foreach ( $flavor_notes as $term ) : ?>
                        <a href="<?php echo esc_url( get_term_link( $term ) ); ?>" class="bean-tag bean-tag--flavor"><?php echo esc_html( $term->name ); ?></a>
                    <?php endforeach; ?>
                </div>
            </div>
            <?php endif; ?>

            <!-- Related Guides — dynamically built from the bean's taxonomy terms -->
            <?php
            // Build guide links from each of the bean's taxonomy terms that have descriptions (= guide content)
            $guide_sections = [
                'origin'         => $origins,
                'roast-level'    => $roast_levels,
                'process-method' => $processes,
                'brew-method'    => $brew_methods,
            ];
            $dynamic_guide_links = [];
            foreach ( $guide_sections as $tax => $terms_list ) {
                if ( ! $terms_list || is_wp_error( $terms_list ) ) {
                    continue;
                }
                $tax_obj   = get_taxonomy( $tax );
                $tax_label = $tax_obj ? $tax_obj->labels->singular_name : $tax;
                foreach ( $terms_list as $gt ) {
                    if ( empty( $gt->description ) ) {
                        continue; // Only link if there is guide content
                    }
                    $dynamic_guide_links[] = [
                        'label' => $tax_label . ' Guide: ' . $gt->name,
                        'url'   => get_term_link( $gt ),
                    ];
                }
            }
            // Also include any manually linked guides from ACF (legacy / editorial overrides)
            if ( ! empty( $linked_guides ) ) {
                foreach ( (array) $linked_guides as $guide_id ) {
                    $gurl = get_permalink( $guide_id );
                    if ( $gurl ) {
                        $dynamic_guide_links[] = [
                            'label' => get_the_title( $guide_id ),
                            'url'   => $gurl,
                        ];
                    }
                }
            }
            if ( ! empty( $dynamic_guide_links ) ) : ?>
            <div class="cbi-section">
                <div class="cbi-section__heading">Related Guides</div>
                <?php foreach ( $dynamic_guide_links as $gl ) : ?>
                    <a href="<?php echo esc_url( $gl['url'] ); ?>" style="display:block;color:var(--cbi-text-muted);font-size:var(--text-sm);padding:var(--space-3) 0;border-bottom:1px solid var(--cbi-border);">
                        &rarr; <?php echo esc_html( $gl['label'] ); ?>
                    </a>
                <?php endforeach; ?>
            </div>
            <?php endif; ?>

            <!-- Linked Recipes -->
            <?php if ( ! empty( $linked_recipes ) ) : ?>
            <div class="cbi-section">
                <div class="cbi-section__heading">Recipes Using This Bean</div>
                <?php foreach ( (array) $linked_recipes as $recipe_id ) : ?>
                    <a href="<?php echo esc_url( get_permalink( $recipe_id ) ); ?>" style="display:block;color:var(--cbi-text-muted);font-size:var(--text-sm);padding:var(--space-3) 0;border-bottom:1px solid var(--cbi-border);">
                        &rarr; <?php echo esc_html( get_the_title( $recipe_id ) ); ?>
                    </a>
                <?php endforeach; ?>
            </div>
            <?php endif; ?>

            <!-- Last reviewed -->
            <?php if ( $last_reviewed ) : ?>
            <p style="font-size:var(--text-xs);color:var(--cbi-text-dim);font-family:var(--font-mono);margin-top:var(--space-6);">
                Last reviewed: <?php echo esc_html( date( 'F j, Y', strtotime( $last_reviewed ) ) ); ?>
            </p>
            <?php endif; ?>

        </main>

        <!-- ===================== RIGHT SIDEBAR ===================== -->
        <aside class="bean-sidebar">

            <!-- Buy Box -->
            <div class="buy-box">
                <div class="buy-box__title">Buy This Bean</div>

                <?php if ( $current_price ) : ?>
                    <div class="buy-box__price">$<?php echo esc_html( number_format( (float) $current_price, 2 ) ); ?></div>
                    <div class="buy-box__price-sub">
                        <?php if ( $price_per_oz ) echo '$' . esc_html( number_format( (float) $price_per_oz, 2 ) ) . ' / oz &middot; '; ?>
                        updated daily
                    </div>
                <?php endif; ?>

                <?php if ( $amazon_url ) : ?>
                    <a href="<?php echo esc_url( $amazon_url ); ?>" class="buy-box__btn" target="_blank" rel="nofollow sponsored noopener">
                        Buy on Amazon
                    </a>
                <?php endif; ?>

                <?php if ( $roaster_url ) : ?>
                    <a href="<?php echo esc_url( $roaster_url ); ?>" class="buy-box__btn buy-box__btn--secondary" target="_blank" rel="nofollow sponsored noopener">
                        Buy Direct from Roaster
                    </a>
                <?php endif; ?>

                <?php if ( ! $amazon_url && ! $roaster_url ) : ?>
                    <p style="color:var(--cbi-text-dim);font-size:var(--text-xs);margin-top:var(--space-2);">Purchase links coming soon.</p>
                <?php endif; ?>

                <div class="buy-box__disclosure">
                    Affiliate links &mdash; we earn a small commission at no extra cost to you.
                </div>
            </div>

            <!-- At a glance — quick-scan summary that stays beside the review -->
            <?php if ( ( $rating !== '' && $rating !== null ) || $roast_name || $origin_name || $price_per_oz ) : ?>
            <div class="glance-card">
                <div class="cbi-section__heading">At a glance</div>
                <dl class="glance">
                    <?php if ( $rating !== '' && $rating !== null ) : ?>
                    <div class="glance__row"><dt>Rating</dt><dd class="tabular-nums"><?php echo esc_html( $rating ); ?>/10</dd></div>
                    <?php endif; ?>
                    <?php if ( $roast_name ) : ?>
                    <div class="glance__row"><dt>Roast</dt><dd><?php echo esc_html( $roast_name ); ?></dd></div>
                    <?php endif; ?>
                    <?php if ( $origin_name ) : ?>
                    <div class="glance__row"><dt>Origin</dt><dd><?php echo esc_html( $origin_name ); ?></dd></div>
                    <?php endif; ?>
                    <?php if ( $process_name ) : ?>
                    <div class="glance__row"><dt>Process</dt><dd><?php echo esc_html( $process_name ); ?></dd></div>
                    <?php endif; ?>
                    <?php if ( $price_per_oz ) : ?>
                    <div class="glance__row"><dt>Price / oz</dt><dd class="tabular-nums">$<?php echo esc_html( number_format( (float) $price_per_oz, 2 ) ); ?></dd></div>
                    <?php endif; ?>
                </dl>
            </div>
            <?php endif; ?>

            <!-- Similar Beans -->
            <div class="cbi-section similar-beans">
                <div class="cbi-section__heading">Similar Beans</div>
                <?php
                $similar_count = 0;
                if ( $flavor_notes && ! is_wp_error( $flavor_notes ) ) {
                    $flavor_ids = wp_list_pluck( $flavor_notes, 'term_id' );
                    $similar    = new WP_Query( [
                        'post_type'      => 'bean',
                        'posts_per_page' => 4,
                        'post__not_in'   => [ $post_id ],
                        'tax_query'      => [
                            [
                                'taxonomy' => 'flavor-note',
                                'field'    => 'term_id',
                                'terms'    => $flavor_ids,
                                'operator' => 'IN',
                            ],
                        ],
                        'orderby'        => 'rand',
                        'no_found_rows'  => true,
                    ] );

                    if ( $similar->have_posts() ) :
                        while ( $similar->have_posts() ) : $similar->the_post();
                            $similar_count++;
                            $sim_id       = get_the_ID();
                            $sim_rating   = $has_acf ? get_field( 'rating', $sim_id ) : '';
                            $sim_roasters = get_the_terms( $sim_id, 'roaster' );
                            $sim_roaster  = ( $sim_roasters && ! is_wp_error( $sim_roasters ) ) ? $sim_roasters[0]->name : '';
                            $sim_roast    = get_the_terms( $sim_id, 'roast-level' );
                            $sim_roast_n  = ( $sim_roast && ! is_wp_error( $sim_roast ) ) ? $sim_roast[0]->name : '';
                        ?>
                        <a href="<?php the_permalink(); ?>" class="similar-bean-card">
                            <div>
                                <span class="similar-bean-card__name"><?php the_title(); ?></span>
                                <span class="similar-bean-card__meta">
                                    <?php echo esc_html( implode( ' &middot; ', array_filter( [ $sim_roaster, $sim_roast_n ] ) ) ); ?>
                                </span>
                            </div>
                            <?php if ( $sim_rating !== '' && $sim_rating !== null ) : ?>
                                <span class="similar-bean-card__score"><?php echo esc_html( $sim_rating ); ?>/10</span>
                            <?php endif; ?>
                        </a>
                        <?php endwhile;
                        wp_reset_postdata();
                    endif;
                }

                // Sparse-state fallback: give the right column useful weight on pages with
                // fewer than 2 similar-bean matches (early library state, niche flavor combos).
                if ( $similar_count < 2 ) :
                    $explore_groups = [];
                    if ( $roast_levels && ! is_wp_error( $roast_levels ) ) {
                        $explore_groups[] = [ 'label' => 'Roast', 'terms' => $roast_levels, 'class' => 'bean-tag--roast' ];
                    }
                    if ( $origins && ! is_wp_error( $origins ) ) {
                        $explore_groups[] = [ 'label' => 'Origin', 'terms' => $origins, 'class' => 'bean-tag--origin' ];
                    }
                    if ( $brew_methods && ! is_wp_error( $brew_methods ) ) {
                        $explore_groups[] = [ 'label' => 'Brew Method', 'terms' => $brew_methods, 'class' => 'bean-tag--brew' ];
                    }
                    if ( ! empty( $explore_groups ) ) : ?>
                    <div style="margin-top:var(--space-4);">
                        <div style="font-size:var(--text-xs);color:var(--cbi-text-dim);font-family:var(--font-mono);margin-bottom:var(--space-3);">Browse by category</div>
                        <?php foreach ( $explore_groups as $group ) : ?>
                        <div style="margin-bottom:var(--space-4);">
                            <div style="font-size:var(--text-xs);color:var(--cbi-text-dim);font-family:var(--font-mono);margin-bottom:var(--space-2);"><?php echo esc_html( $group['label'] ); ?></div>
                            <div style="display:flex;flex-wrap:wrap;gap:var(--space-2);">
                                <?php foreach ( $group['terms'] as $term ) : ?>
                                    <a href="<?php echo esc_url( get_term_link( $term ) ); ?>" class="bean-tag <?php echo esc_attr( $group['class'] ); ?>">
                                        All <?php echo esc_html( $term->name ); ?> &rarr;
                                    </a>
                                <?php endforeach; ?>
                            </div>
                        </div>
                        <?php endforeach; ?>
                    </div>
                    <?php else : ?>
                    <p style="color:var(--cbi-text-dim);font-size:var(--text-sm);">More beans coming soon.</p>
                    <?php endif; ?>
                <?php endif; ?>
            </div>

            <!-- Origin Link -->
            <?php if ( $origins && ! is_wp_error( $origins ) ) : ?>
            <div class="cbi-section">
                <div class="cbi-section__heading">Origin</div>
                <?php foreach ( $origins as $term ) : ?>
                    <a href="<?php echo esc_url( get_term_link( $term ) ); ?>" class="bean-tag bean-tag--origin" style="display:inline-block;margin-bottom:var(--space-2);">
                        All <?php echo esc_html( $term->name ); ?> coffees &rarr;
                    </a>
                <?php endforeach; ?>
            </div>
            <?php endif; ?>

            <!-- Roaster Link -->
            <?php if ( $roasters && ! is_wp_error( $roasters ) ) : ?>
            <div class="cbi-section">
                <div class="cbi-section__heading">Roaster</div>
                <?php foreach ( $roasters as $term ) : ?>
                    <a href="<?php echo esc_url( get_term_link( $term ) ); ?>" class="bean-tag" style="display:inline-block;margin-bottom:var(--space-2);">
                        All <?php echo esc_html( $term->name ); ?> beans &rarr;
                    </a>
                <?php endforeach; ?>
            </div>
            <?php endif; ?>

        </aside>

    </div>
</div>

<?php endwhile; ?>

<?php get_footer(); ?>
