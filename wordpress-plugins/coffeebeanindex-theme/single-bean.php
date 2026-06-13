<?php
/**
 * Template: Single Bean Page
 * File: single-bean.php
 *
 * v3.0 — money-page scan order:
 *   Hero: breadcrumb / roaster / name / verdict / score band / price + CTA
 *   (CTA + price visible above the fold on mobile; sticky CTA bar below 1025px)
 *   Profile (specs | sensory + radar) → Tasting notes → Buy/Skip fit cards →
 *   Full review → Price analysis + price-history chart → FAQ → flavor chips →
 *   related guides. Sidebar: buy box, at-a-glance, similar beans, explore links.
 * Affiliate disclosure near the top (FTC requirement).
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
    $amazon_asin    = $has_acf ? get_field( 'amazon_asin' )          : '';
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
    $has_rating  = ( $rating !== '' && $rating !== null );

    // Build Amazon URL from ASIN if amazon_affiliate_url is empty.
    // Every outbound Amazon link must carry the affiliate tag — never link bare.
    if ( ! $amazon_url && $amazon_asin ) {
        $amazon_url = 'https://www.amazon.com/dp/' . rawurlencode( $amazon_asin ) . '?tag=coffeebeanind-20';
    }
    $primary_cta_url = $amazon_url ?: $roaster_url;
    $primary_cta_txt = $amazon_url ? 'Buy on Amazon' : 'Buy from Roaster';
?>

<!-- ============================================================
     BEAN HERO — name + score + verdict + price + CTA above the fold
     ============================================================ -->
<section class="bean-hero">
    <div class="bean-hero__inner">

        <!-- Breadcrumb (schema emitted by cbi_bean_schema in functions.php) -->
        <nav class="bean-hero__breadcrumb" aria-label="Breadcrumb">
            <a href="<?php echo esc_url( home_url() ); ?>">Home</a>
            <span>/</span>
            <a href="<?php echo esc_url( get_post_type_archive_link( 'bean' ) ?: home_url( '/beans/' ) ); ?>">Beans</a>
            <?php if ( $roaster_name ) : ?>
                <span>/</span>
                <a href="<?php echo esc_url( get_term_link( $roasters[0] ) ); ?>"><?php echo esc_html( $roaster_name ); ?></a>
            <?php endif; ?>
            <span>/</span>
            <span aria-current="page"><?php echo esc_html( $title ); ?></span>
        </nav>

        <div class="bean-hero__grid">

            <!-- Identity column -->
            <div>
                <?php if ( $roaster_name ) : ?>
                    <div class="bean-hero__roaster">
                        <a href="<?php echo esc_url( get_term_link( $roasters[0] ) ); ?>"><?php echo esc_html( $roaster_name ); ?></a>
                    </div>
                <?php endif; ?>

                <h1 class="bean-hero__title"><?php echo esc_html( $title ); ?></h1>

                <?php if ( $verdict ) : ?>
                    <p class="bean-hero__verdict"><?php echo esc_html( $verdict ); ?></p>
                <?php endif; ?>

                <div class="bean-hero__meta">
                    <?php if ( $last_reviewed ) : ?>
                        <span>Reviewed <?php echo esc_html( date( 'M j, Y', strtotime( $last_reviewed ) ) ); ?></span>
                    <?php endif; ?>
                    <?php if ( $personal_mode ) : ?>
                        <span>Personally reviewed by the site author</span>
                    <?php endif; ?>
                    <?php if ( $product_id ) : ?>
                        <span>Price tracked daily</span>
                    <?php endif; ?>
                </div>
            </div>

            <!-- Decision panel: score + price + CTA -->
            <div class="bean-hero__panel">
                <div class="bean-hero__panel-row">
                    <?php if ( $has_rating ) {
                        echo cbi_score_badge( $rating, 'xl' );
                    } ?>
                    <?php if ( $current_price || $price_per_oz ) : ?>
                    <div class="bean-hero__price-block">
                        <?php if ( $current_price ) : ?>
                            <div class="bean-hero__price">$<?php echo esc_html( number_format( (float) $current_price, 2 ) ); ?></div>
                        <?php endif; ?>
                        <div class="bean-hero__price-sub">
                            <?php if ( $price_per_oz ) echo '$' . esc_html( number_format( (float) $price_per_oz, 2 ) ) . '/oz'; ?>
                            <?php if ( $product_id ) echo $price_per_oz ? ' &middot; updated daily' : 'updated daily'; ?>
                        </div>
                    </div>
                    <?php endif; ?>
                </div>

                <?php if ( $primary_cta_url ) : ?>
                    <a href="<?php echo esc_url( $primary_cta_url ); ?>" class="cbi-btn cbi-btn--primary bean-hero__cta" target="_blank" rel="nofollow sponsored noopener">
                        <?php echo esc_html( $primary_cta_txt ); ?>
                    </a>
                    <p class="bean-hero__panel-note">Affiliate link. We earn a commission at no extra cost to you.</p>
                <?php else : ?>
                    <p class="bean-hero__panel-note">Purchase links coming soon. Price history below.</p>
                <?php endif; ?>
            </div>

        </div>

        <!-- Taxonomy chips: every chip is a door into the database -->
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

    </div>
</section>

<!-- Affiliate disclosure — near top, above buy links (FTC requirement) -->
<div class="cbi-disclosure-inline">
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

            <!-- Profile: spec table + sensory bars + flavor radar -->
            <div class="cbi-section">
                <h2 class="cbi-section__heading">Profile</h2>
                <div class="bean-profile<?php echo $has_sensory ? '' : ' bean-profile--specs-only'; ?>">

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
                                        <a href="<?php echo esc_url( get_term_link( $term ) ); ?>" class="bean-tag bean-tag--brew"><?php echo cbi_term_chip_icon( $term ) . esc_html( $term->name ); ?></a>
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

                    <?php
                    // Sensory bars + flavor radar. Shared helper (functions.php) so the
                    // [coffee_profile] shortcode and this template draw an identical chart,
                    // and so the radar renders for every bean from its own ACF scores.
                    echo cbi_render_sensory_profile( $post_id );
                    ?>

                </div>
            </div>

            <!-- Tasting Notes -->
            <?php if ( $tasting_notes ) : ?>
            <div class="cbi-section">
                <h2 class="cbi-section__heading">Tasting Notes</h2>
                <ul class="tasting-notes">
                    <?php foreach ( array_filter( array_map( 'trim', explode( "\n", $tasting_notes ) ) ) as $note ) : ?>
                        <li><?php echo esc_html( $note ); ?></li>
                    <?php endforeach; ?>
                </ul>
            </div>
            <?php endif; ?>

            <!-- Buy it / Skip it — the decision section, side by side -->
            <?php if ( $whos_for || $whos_not_for ) : ?>
            <div class="cbi-section">
                <h2 class="cbi-section__heading">Who It&rsquo;s For</h2>
                <div class="fit-cards">
                    <?php if ( $whos_for ) : ?>
                    <div class="fit-card">
                        <div class="fit-card__label">Buy it if</div>
                        <p><?php echo esc_html( $whos_for ); ?></p>
                    </div>
                    <?php endif; ?>
                    <?php if ( $whos_not_for ) : ?>
                    <div class="fit-card fit-card--skip">
                        <div class="fit-card__label">Skip it if</div>
                        <p><?php echo esc_html( $whos_not_for ); ?></p>
                    </div>
                    <?php endif; ?>
                </div>
            </div>
            <?php endif; ?>

            <!-- Full review (editor content) -->
            <?php if ( get_the_content() ) : ?>
            <div class="cbi-section">
                <div class="review-body">
                    <h2>Full review</h2>
                    <?php the_content(); ?>
                </div>
            </div>
            <?php endif; ?>

            <!-- Price analysis + history — the differentiator, one section -->
            <?php if ( $price_analysis || $product_id ) : ?>
            <div class="cbi-section" id="price">
                <h2 class="cbi-section__heading">Price &amp; History</h2>
                <?php if ( $price_analysis ) : ?>
                    <div class="review-body" style="margin-bottom:var(--space-5);">
                        <p><?php echo esc_html( $price_analysis ); ?></p>
                    </div>
                <?php endif; ?>
                <?php if ( $product_id ) : ?>
                    <div class="price-chart-wrap">
                        <?php echo do_shortcode( '[coffee_price_chart product_id="' . esc_attr( $product_id ) . '"]' ); ?>
                    </div>
                <?php endif; ?>
            </div>
            <?php endif; ?>

            <!-- Rating, presented as a system -->
            <?php if ( $has_rating ) : ?>
            <div class="cbi-section">
                <h2 class="cbi-section__heading">Rating</h2>
                <?php echo cbi_score_badge( $rating, 'md' ); ?>
            </div>
            <?php endif; ?>

            <!-- FAQ Accordion — sourced from ACF fields; visible + searchable -->
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
                <h2 class="cbi-section__heading">FAQ</h2>
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

            <!-- All Flavor Tags -->
            <?php if ( $flavor_notes && ! is_wp_error( $flavor_notes ) ) : ?>
            <div class="cbi-section">
                <h2 class="cbi-section__heading">Flavor Notes</h2>
                <div class="explore-groups__set">
                    <?php foreach ( $flavor_notes as $term ) : ?>
                        <a href="<?php echo esc_url( get_term_link( $term ) ); ?>" class="bean-tag bean-tag--flavor"><?php echo cbi_term_chip_icon( $term ) . esc_html( $term->name ); ?></a>
                    <?php endforeach; ?>
                </div>
            </div>
            <?php endif; ?>

            <!-- Related Guides — built from the bean's taxonomy terms -->
            <?php
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
                <h2 class="cbi-section__heading">Related Guides</h2>
                <div class="related-list">
                    <?php foreach ( $dynamic_guide_links as $gl ) : ?>
                        <a href="<?php echo esc_url( $gl['url'] ); ?>" class="related-list__item"><?php echo esc_html( $gl['label'] ); ?></a>
                    <?php endforeach; ?>
                </div>
            </div>
            <?php endif; ?>

            <!-- Linked Recipes -->
            <?php if ( ! empty( $linked_recipes ) ) : ?>
            <div class="cbi-section">
                <h2 class="cbi-section__heading">Recipes Using This Bean</h2>
                <div class="related-list">
                    <?php foreach ( (array) $linked_recipes as $recipe_id ) : ?>
                        <a href="<?php echo esc_url( get_permalink( $recipe_id ) ); ?>" class="related-list__item"><?php echo esc_html( get_the_title( $recipe_id ) ); ?></a>
                    <?php endforeach; ?>
                </div>
            </div>
            <?php endif; ?>

            <!-- Last reviewed -->
            <?php if ( $last_reviewed ) : ?>
            <p class="review-meta">
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
                    <p class="buy-box__disclosure">Purchase links coming soon.</p>
                <?php endif; ?>

                <div class="buy-box__disclosure">
                    Affiliate links. We earn a small commission at no extra cost to you.
                </div>
            </div>

            <!-- At a glance -->
            <?php if ( $has_rating || $roast_name || $origin_name || $price_per_oz ) : ?>
            <div class="glance-card">
                <div class="cbi-section__heading">At a glance</div>
                <dl class="glance">
                    <?php if ( $has_rating ) :
                        $glance_band = cbi_score_band( $rating ); ?>
                    <div class="glance__row"><dt>Score</dt><dd class="tabular-nums"><?php echo esc_html( number_format( (float) $rating, 1 ) ); ?>/10 &middot; <?php echo esc_html( $glance_band['label'] ); ?></dd></div>
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
                                <span class="similar-bean-card__score"><?php echo esc_html( number_format( (float) $sim_rating, 1 ) ); ?>/10</span>
                            <?php endif; ?>
                        </a>
                        <?php endwhile;
                        wp_reset_postdata();
                    endif;
                }

                // Sparse-state fallback: keep the rail useful with fewer than 2 matches
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
                        <?php foreach ( $explore_groups as $group ) : ?>
                        <div class="explore-groups__label"><?php echo esc_html( $group['label'] ); ?></div>
                        <div class="explore-groups__set">
                            <?php foreach ( $group['terms'] as $term ) : ?>
                                <a href="<?php echo esc_url( get_term_link( $term ) ); ?>" class="bean-tag <?php echo esc_attr( $group['class'] ); ?>">
                                    All <?php echo esc_html( $term->name ); ?> &rarr;
                                </a>
                            <?php endforeach; ?>
                        </div>
                        <?php endforeach; ?>
                    </div>
                    <?php else : ?>
                    <p class="text-dim" style="font-size:var(--text-sm);">More beans coming soon.</p>
                    <?php endif; ?>
                <?php endif; ?>
            </div>

            <!-- Keep exploring: origin + roaster archives -->
            <?php if ( ( $origins && ! is_wp_error( $origins ) ) || ( $roasters && ! is_wp_error( $roasters ) ) ) : ?>
            <div class="cbi-section">
                <div class="cbi-section__heading">Keep Exploring</div>
                <?php if ( $origins && ! is_wp_error( $origins ) ) : ?>
                    <div class="explore-groups__label">Origin</div>
                    <div class="explore-groups__set">
                        <?php foreach ( $origins as $term ) : ?>
                            <a href="<?php echo esc_url( get_term_link( $term ) ); ?>" class="bean-tag bean-tag--origin">All <?php echo esc_html( $term->name ); ?> coffees &rarr;</a>
                        <?php endforeach; ?>
                    </div>
                <?php endif; ?>
                <?php if ( $roasters && ! is_wp_error( $roasters ) ) : ?>
                    <div class="explore-groups__label">Roaster</div>
                    <div class="explore-groups__set">
                        <?php foreach ( $roasters as $term ) : ?>
                            <a href="<?php echo esc_url( get_term_link( $term ) ); ?>" class="bean-tag">All <?php echo esc_html( $term->name ); ?> beans &rarr;</a>
                        <?php endforeach; ?>
                    </div>
                <?php endif; ?>
            </div>
            <?php endif; ?>

        </aside>

    </div>
</div>

<!-- Sticky mobile CTA — price + buy action always in reach below 1025px -->
<?php if ( $primary_cta_url ) : ?>
<div class="bean-ctabar">
    <div class="bean-ctabar__info">
        <?php if ( $current_price ) : ?>
            <span class="bean-ctabar__price tabular-nums">$<?php echo esc_html( number_format( (float) $current_price, 2 ) ); ?></span>
        <?php endif; ?>
        <?php if ( $price_per_oz ) : ?>
            <span class="bean-ctabar__sub tabular-nums">$<?php echo esc_html( number_format( (float) $price_per_oz, 2 ) ); ?>/oz</span>
        <?php endif; ?>
    </div>
    <a href="<?php echo esc_url( $primary_cta_url ); ?>" class="bean-ctabar__btn" target="_blank" rel="nofollow sponsored noopener">
        <?php echo esc_html( $primary_cta_txt ); ?>
    </a>
</div>
<?php endif; ?>

<?php endwhile; ?>

<?php get_footer(); ?>
