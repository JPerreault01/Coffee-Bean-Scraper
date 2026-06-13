<?php
/**
 * Front Page — Coffee Bean Index homepage (v3.0, database-first)
 *
 * Top to bottom:
 *   1. Hero      full-width CSS background (LCP), search box, dual CTA,
 *                live index stats (bean/roaster/origin counts)
 *   2. Top rated 6 highest-scored beans (the database's best face forward)
 *   3. Category  4 image cards: Espresso, Dark Roast, Single Origin, Ground
 *   4. Browse    origins / roast levels / flavor families as counted chip
 *                clouds — this section grows with the database
 *   5. Latest    6 newest reviews (excluding beans already shown in Top rated)
 *   6. Deals     price-drop strip (cbi_price_drop_beans()) + disclosure
 *   7. Brew      4 inline-SVG device icons linking to brew-method guides
 *   8. Guides    latest informational guide pages (cbi_get_guides())
 *   9. Trust     how we score / price tracking / AI+human methodology
 *  10. Email     price-drop alert signup band (WPForms via filter)
 *
 * All sections self-wrap in .cbi-container. Hero image is injected by
 * cbi_hero_head() from the cbi_home_image_ids option (deploy-homepage.ps1).
 */

get_header();

$beans_url   = get_post_type_archive_link( 'bean' ) ?: home_url( '/beans/' );
$explore_url = home_url( '/explore/' );

// Live index stats — these scale the page's credibility with the database
$bean_counts   = wp_count_posts( 'bean' );
$bean_total    = $bean_counts ? (int) $bean_counts->publish : 0;
$roaster_total = wp_count_terms( [ 'taxonomy' => 'roaster', 'hide_empty' => true ] );
$roaster_total = is_wp_error( $roaster_total ) ? 0 : (int) $roaster_total;
$origin_total  = wp_count_terms( [ 'taxonomy' => 'origin', 'hide_empty' => true ] );
$origin_total  = is_wp_error( $origin_total ) ? 0 : (int) $origin_total;

/**
 * Resolve a term-archive URL by slug regardless of rewrite base.
 * Falls back to the taxonomy base so links never 404 to a dead term path.
 */
$cbi_term_url = static function ( $slug, $taxonomy, $fallback ) {
    $term = get_term_by( 'slug', $slug, $taxonomy );
    if ( $term && ! is_wp_error( $term ) ) {
        $link = get_term_link( $term );
        if ( ! is_wp_error( $link ) ) {
            return $link;
        }
    }
    return home_url( $fallback );
};
?>

<main id="primary" class="cbi-home">

    <!-- ============================================================
         1. HERO (LCP) — search-first entry into the database
         ============================================================ -->
    <section class="cbi-hero">
        <div class="cbi-hero__bg" aria-hidden="true"></div>
        <div class="cbi-hero__overlay" aria-hidden="true"></div>
        <div class="cbi-hero__inner cbi-container">
            <span class="cbi-hero__eyebrow">Independent &middot; Data-driven &middot; Daily price tracking</span>
            <h1 class="cbi-hero__title">Find the coffee beans actually worth buying.</h1>
            <p class="cbi-hero__subhead">Every bean scored against an anchored 10-point rubric, with flavor profiles and live price history. We call out the ones that don't earn it.</p>

            <form role="search" method="get" action="<?php echo esc_url( home_url( '/' ) ); ?>" class="home-search">
                <label class="sr-only" for="cbi-hero-search">Search coffee beans</label>
                <input class="home-search__input" id="cbi-hero-search" type="search" name="s" placeholder="Search beans, roasters, flavors&hellip;" autocomplete="off">
                <input type="hidden" name="post_type" value="bean">
                <button class="home-search__btn" type="submit">Search</button>
            </form>

            <div class="cbi-hero__cta-row">
                <a class="cbi-btn cbi-btn--primary" href="<?php echo esc_url( $explore_url ); ?>">Explore the index &rarr;</a>
                <a class="cbi-btn cbi-btn--on-dark" href="<?php echo esc_url( add_query_arg( 'sort', 'rating', $beans_url ) ); ?>">Top-rated beans</a>
            </div>

            <?php if ( $bean_total > 0 ) : ?>
            <ul class="home-stats">
                <li><strong class="tabular-nums"><?php echo esc_html( $bean_total ); ?></strong><span>beans scored</span></li>
                <?php if ( $roaster_total > 0 ) : ?>
                    <li><strong class="tabular-nums"><?php echo esc_html( $roaster_total ); ?></strong><span>roasters</span></li>
                <?php endif; ?>
                <?php if ( $origin_total > 0 ) : ?>
                    <li><strong class="tabular-nums"><?php echo esc_html( $origin_total ); ?></strong><span>origins</span></li>
                <?php endif; ?>
                <li><strong>Daily</strong><span>price checks</span></li>
            </ul>
            <?php endif; ?>
        </div>
    </section>

    <!-- Affiliate disclosure — near the top, before any affiliate-linked
         content (FTC; non-negotiable per content standards) -->
    <div class="cbi-disclosure-inline">
        <div class="cbi-container">
            This page contains affiliate links. We may earn commissions from qualifying purchases at no extra cost to you.
        </div>
    </div>

    <!-- ============================================================
         2. TOP RATED — the database leads with its best evidence
         ============================================================ -->
    <?php
    $top_ids = [];
    $top = new WP_Query( [
        'post_type'      => 'bean',
        'posts_per_page' => 6,
        'post_status'    => 'publish',
        'orderby'        => 'meta_value_num',
        'meta_key'       => 'rating',
        'meta_type'      => 'NUMERIC',
        'order'          => 'DESC',
        'no_found_rows'  => true,
    ] );
    if ( $top->have_posts() ) : ?>
        <section class="home-section cbi-container">
            <div class="home-section__head home-section__head--row">
                <div>
                    <h2>Top-rated beans</h2>
                    <p class="text-muted">The highest scores on the anchored rubric. Earned, not given.</p>
                </div>
                <a class="home-section__more" href="<?php echo esc_url( add_query_arg( 'sort', 'rating', $beans_url ) ); ?>">All by rating &rarr;</a>
            </div>
            <div class="cbi-card-grid">
                <?php
                while ( $top->have_posts() ) : $top->the_post();
                    $top_ids[] = get_the_ID();
                    echo cbi_bean_card( get_the_ID() );
                endwhile;
                wp_reset_postdata();
                ?>
            </div>
        </section>
    <?php endif; ?>

    <!-- ============================================================
         3. CATEGORY CARDS — 4 image entries (images resolve from the
            Media Library via cbi_home_image_url; placeholder until then)
         ============================================================ -->
    <?php
    $cbi_cats = [
        [
            'label' => 'Espresso',
            'blurb' => 'Beans built for pressure and crema.',
            'url'   => $cbi_term_url( 'espresso', 'brew-method', '/brew/' ),
            'img'   => cbi_home_image_url( 'espresso' ),
            'alt'   => 'A double shot of espresso pouring into a white cup',
        ],
        [
            'label' => 'Dark Roast',
            'blurb' => 'Bold, low-acid, built to hold up to milk.',
            'url'   => $cbi_term_url( 'dark', 'roast-level', '/roast/' ),
            'img'   => cbi_home_image_url( 'dark_roast' ),
            'alt'   => 'Dark roasted coffee beans with an oily sheen',
        ],
        [
            'label' => 'Single Origin',
            'blurb' => 'Traceable beans from one farm or region.',
            'url'   => home_url( '/origin/' ),
            'img'   => cbi_home_image_url( 'beans' ),
            'alt'   => 'A pile of roasted single origin coffee beans',
        ],
        [
            'label' => 'Ground Coffee',
            'blurb' => 'Pre-ground picks for French press and drip.',
            'url'   => $cbi_term_url( 'french-press', 'brew-method', '/brew/' ),
            'img'   => cbi_home_image_url( 'ground_coffee' ),
            'alt'   => 'Freshly ground coffee in a metal scoop',
        ],
    ];
    ?>
    <section class="home-section cbi-container">
        <div class="home-section__head">
            <h2>Start with a category</h2>
            <p class="text-muted">Four ways into the index. Pick a thread and pull.</p>
        </div>
        <div class="cbi-cats">
            <?php foreach ( $cbi_cats as $cat ) : ?>
                <a class="cbi-cat" href="<?php echo esc_url( $cat['url'] ); ?>">
                    <span class="cbi-cat__media">
                        <?php if ( $cat['img'] ) : ?>
                            <img class="cbi-cat__img"
                                 src="<?php echo esc_url( $cat['img'] ); ?>"
                                 width="600" height="400"
                                 loading="lazy" decoding="async"
                                 alt="<?php echo esc_attr( $cat['alt'] ); ?>">
                        <?php else : ?>
                            <span class="cbi-cat__img cbi-cat__img--placeholder" aria-hidden="true"></span>
                        <?php endif; ?>
                    </span>
                    <span class="cbi-cat__body">
                        <span class="cbi-cat__label"><?php echo esc_html( $cat['label'] ); ?></span>
                        <span class="cbi-cat__blurb"><?php echo esc_html( $cat['blurb'] ); ?></span>
                    </span>
                </a>
            <?php endforeach; ?>
        </div>
    </section>

    <!-- ============================================================
         4. BROWSE THE INDEX — counted chip clouds. This is the section
            that scales: more beans means richer clouds, never emptier.
         ============================================================ -->
    <?php
    $browse_groups = [];

    $browse_origins = get_terms( [
        'taxonomy'   => 'origin',
        'hide_empty' => true,
        'orderby'    => 'count',
        'order'      => 'DESC',
        'number'     => 10,
    ] );
    if ( ! is_wp_error( $browse_origins ) && ! empty( $browse_origins ) ) {
        $browse_groups[] = [
            'heading' => 'By Origin',
            'terms'   => $browse_origins,
            'class'   => 'bean-tag--origin',
            'all_url' => home_url( '/origin/' ),
            'all_txt' => 'All origins',
        ];
    }

    $browse_roasts = get_terms( [
        'taxonomy'   => 'roast-level',
        'hide_empty' => true,
        'orderby'    => 'count',
        'order'      => 'DESC',
    ] );
    if ( ! is_wp_error( $browse_roasts ) && ! empty( $browse_roasts ) ) {
        $browse_groups[] = [
            'heading' => 'By Roast Level',
            'terms'   => $browse_roasts,
            'class'   => 'bean-tag--roast',
            'all_url' => home_url( '/roast/' ),
            'all_txt' => 'All roast levels',
        ];
    }

    // Flavor families: top-level terms with pad_counts so child-note
    // assignments roll up into the family count.
    $browse_flavors = get_terms( [
        'taxonomy'   => 'flavor-note',
        'hide_empty' => true,
        'parent'     => 0,
        'orderby'    => 'count',
        'order'      => 'DESC',
        'pad_counts' => true,
        'number'     => 10,
    ] );
    if ( ! is_wp_error( $browse_flavors ) && ! empty( $browse_flavors ) ) {
        $browse_groups[] = [
            'heading' => 'By Flavor',
            'terms'   => $browse_flavors,
            'class'   => 'bean-tag--flavor',
            'all_url' => $explore_url,
            'all_txt' => 'Filter by flavor in Explore',
        ];
    }

    if ( ! empty( $browse_groups ) ) : ?>
    <section class="home-section--tint">
        <div class="cbi-container">
            <div class="home-section__head">
                <h2>Browse the index</h2>
                <p class="text-muted">Every tag links to a live archive with scores and prices.</p>
            </div>
            <div class="home-browse">
                <?php foreach ( $browse_groups as $group ) : ?>
                    <div class="home-browse__group">
                        <h3 class="home-browse__heading"><?php echo esc_html( $group['heading'] ); ?></h3>
                        <div class="home-browse__chips">
                            <?php foreach ( $group['terms'] as $term ) : ?>
                                <a href="<?php echo esc_url( get_term_link( $term ) ); ?>" class="bean-tag <?php echo esc_attr( $group['class'] ); ?>">
                                    <?php echo esc_html( $term->name ); ?><span class="bean-tag__count tabular-nums"><?php echo absint( $term->count ); ?></span>
                                </a>
                            <?php endforeach; ?>
                        </div>
                        <a class="home-browse__all" href="<?php echo esc_url( $group['all_url'] ); ?>"><?php echo esc_html( $group['all_txt'] ); ?> &rarr;</a>
                    </div>
                <?php endforeach; ?>
            </div>
        </div>
    </section>
    <?php endif; ?>

    <!-- ============================================================
         5. LATEST REVIEWS — newest beans not already shown above
         ============================================================ -->
    <?php
    $latest = new WP_Query( [
        'post_type'      => 'bean',
        'posts_per_page' => 6,
        'post_status'    => 'publish',
        'post__not_in'   => $top_ids,
        'no_found_rows'  => true,
    ] );
    if ( $latest->have_posts() ) : ?>
        <section class="home-section cbi-container">
            <div class="home-section__head home-section__head--row">
                <div>
                    <h2>Latest reviews</h2>
                    <p class="text-muted">Freshly scored, with live price per ounce.</p>
                </div>
                <a class="home-section__more" href="<?php echo esc_url( $beans_url ); ?>">All beans &rarr;</a>
            </div>
            <div class="cbi-card-grid">
                <?php
                while ( $latest->have_posts() ) : $latest->the_post();
                    echo cbi_bean_card( get_the_ID() );
                endwhile;
                wp_reset_postdata();
                ?>
            </div>
        </section>
    <?php endif; ?>

    <!-- ============================================================
         6. PRICE DROPS — beans below their 30-day average
         ============================================================ -->
    <section class="home-deals">
        <div class="cbi-container">
            <div class="home-section__head home-section__head--row">
                <div>
                    <h2>Price drops</h2>
                    <p class="text-muted">Beans we rate, currently below their 30-day average.</p>
                </div>
                <a class="home-section__more" href="<?php echo esc_url( $explore_url ); ?>">Explore all &rarr;</a>
            </div>
            <?php
            $deals = cbi_price_drop_beans( 4 );
            if ( ! empty( $deals ) ) : ?>
                <div class="home-deals__strip">
                    <?php foreach ( $deals as $deal ) :
                        $did = (int) ( $deal['post_id'] ?? 0 );
                        if ( ! $did ) continue;
                    ?>
                        <a class="home-deal" href="<?php echo esc_url( get_permalink( $did ) ); ?>">
                            <span class="home-deal__name"><?php echo esc_html( get_the_title( $did ) ); ?></span>
                            <span class="home-deal__prices tabular-nums">
                                <span class="home-deal__now">$<?php echo esc_html( number_format( (float) $deal['current'], 2 ) ); ?></span>
                                <span class="home-deal__was">$<?php echo esc_html( number_format( (float) $deal['avg30'], 2 ) ); ?></span>
                            </span>
                            <span class="home-deal__badge tabular-nums">&minus;<?php echo esc_html( (int) $deal['pct'] ); ?>% vs 30-day avg</span>
                        </a>
                    <?php endforeach; ?>
                </div>
            <?php else : ?>
                <?php /* Wire the 'cbi_price_drop_beans' filter from the scraper.
                         Row shape: [ 'post_id'=>int, 'current'=>float,
                         'avg30'=>float, 'pct'=>int ] ordered by pct desc. */ ?>
                <div class="home-deals__placeholder">
                    <p>Price-drop tracking switches on once the daily scraper feeds 30-day averages into the site. <a href="<?php echo esc_url( $beans_url ); ?>">Browse all reviews &rarr;</a></p>
                </div>
            <?php endif; ?>
        </div>
    </section>

    <!-- ============================================================
         7. BREW GUIDES — inline SVG device icons (decorative, labeled)
         ============================================================ -->
    <section class="cbi-brew home-section--tint">
        <div class="cbi-container">
            <div class="home-section__head">
                <h2>Brew guides</h2>
                <p class="text-muted">Dial in the method. Four ways to pull the most from a bag.</p>
            </div>
            <div class="cbi-brew__grid">
                <!-- Espresso machine -->
                <a class="cbi-brew__item" href="<?php echo esc_url( $cbi_term_url( 'espresso', 'brew-method', '/brew/' ) ); ?>">
                    <span class="cbi-brew__icon">
                        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                            <rect x="3" y="3" width="11" height="7" rx="1"/>
                            <path d="M3 6.5h11"/>
                            <path d="M9 10v1.4"/>
                            <path d="M7.5 11.4h3l-.4 1.3a.5.5 0 0 1-.48.36h-1.24a.5.5 0 0 1-.48-.36z"/>
                            <path d="M8.7 13.1v1M9.8 13.1v1"/>
                            <path d="M7 15h4v2a1.5 1.5 0 0 1-1.5 1.5h-1A1.5 1.5 0 0 1 7 17z"/>
                            <path d="M11 15.8h1a1 1 0 0 1 0 2h-.5"/>
                            <path d="M3 20h14"/>
                        </svg>
                    </span>
                    <span class="cbi-brew__label">Espresso</span>
                </a>
                <!-- French press -->
                <a class="cbi-brew__item" href="<?php echo esc_url( $cbi_term_url( 'french-press', 'brew-method', '/brew/' ) ); ?>">
                    <span class="cbi-brew__icon">
                        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                            <path d="M11 2.5h2"/>
                            <path d="M12 2.5v2"/>
                            <path d="M7 4.5h10"/>
                            <path d="M8 4.5v13a1.5 1.5 0 0 0 1.5 1.5h5a1.5 1.5 0 0 0 1.5-1.5V4.5"/>
                            <path d="M8 8.5h8"/>
                            <path d="M16 8h2.5a.5.5 0 0 1 .5.5v3a.5.5 0 0 1-.5.5H16"/>
                        </svg>
                    </span>
                    <span class="cbi-brew__label">French Press</span>
                </a>
                <!-- Pour over (V60 cone + carafe) -->
                <a class="cbi-brew__item" href="<?php echo esc_url( $cbi_term_url( 'pour-over', 'brew-method', '/brew/' ) ); ?>">
                    <span class="cbi-brew__icon">
                        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                            <path d="M6 4.5h12l-5 6.5h-2z"/>
                            <path d="M10.2 11l-.7 1.5M13.8 11l.7 1.5"/>
                            <path d="M9 13h6v2.5a3 3 0 0 1-6 0z"/>
                            <path d="M15 13.5h1.5a1 1 0 0 1 0 2H15"/>
                        </svg>
                    </span>
                    <span class="cbi-brew__label">Pour Over</span>
                </a>
                <!-- AeroPress -->
                <a class="cbi-brew__item" href="<?php echo esc_url( $cbi_term_url( 'aeropress', 'brew-method', '/brew/' ) ); ?>">
                    <span class="cbi-brew__icon">
                        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                            <path d="M9 3h6"/>
                            <path d="M10 3v3h4V3"/>
                            <path d="M8.5 6h7"/>
                            <path d="M9 6v6h6V6"/>
                            <path d="M9.5 12h5l-.6 5a1 1 0 0 1-1 .9h-1.8a1 1 0 0 1-1-.9z"/>
                            <path d="M14.3 13.5h1.4a1.4 1.4 0 0 1 0 2.8H14"/>
                        </svg>
                    </span>
                    <span class="cbi-brew__label">AeroPress</span>
                </a>
            </div>
        </div>
    </section>

    <!-- ============================================================
         8. GUIDES — informational hubs (40% informational ratio)
         ============================================================ -->
    <?php
    $guides = cbi_get_guides( 3 );
    if ( $guides->have_posts() ) : ?>
        <section class="home-section cbi-container">
            <div class="home-section__head">
                <h2>Coffee guides</h2>
                <p class="text-muted">Origins, brew methods, and the why behind the beans.</p>
            </div>
            <div class="home-guides">
                <?php while ( $guides->have_posts() ) : $guides->the_post();
                    $g_excerpt = get_the_excerpt();
                ?>
                    <a class="home-guide-card" href="<?php the_permalink(); ?>">
                        <span class="home-guide-card__kicker">Guide</span>
                        <span class="home-guide-card__title"><?php the_title(); ?></span>
                        <?php if ( $g_excerpt ) : ?>
                            <span class="home-guide-card__desc"><?php echo esc_html( wp_trim_words( $g_excerpt, 22 ) ); ?></span>
                        <?php endif; ?>
                        <span class="home-guide-card__more">Read guide &rarr;</span>
                    </a>
                <?php endwhile;
                wp_reset_postdata(); ?>
            </div>
        </section>
    <?php endif; ?>

    <!-- ============================================================
         9. HOW WE SCORE — methodology cues where they earn trust
         ============================================================ -->
    <section class="home-trust">
        <div class="cbi-container">
            <h2>Why trust the Index</h2>
            <div class="home-trust__grid">
                <div class="home-trust__item">
                    <span class="home-trust__num">01</span>
                    <h3>Anchored 10-point rubric</h3>
                    <p>Every score is a decimal set against fixed band definitions, decided last, after the critique. A 7.3 here means the same thing on every page. <a href="<?php echo esc_url( home_url( '/editorial-standards/' ) ); ?>">Read how we score</a>.</p>
                </div>
                <div class="home-trust__item">
                    <span class="home-trust__num">02</span>
                    <h3>Live price tracking</h3>
                    <p>A scraper checks prices daily and charts 30-day history on every tracked bean, so you buy on the dips instead of the spikes.</p>
                </div>
                <div class="home-trust__item">
                    <span class="home-trust__num">03</span>
                    <h3>Structured data, human judgment</h3>
                    <p>Reviews are built from verified product specs and public tasting data, AI-assisted, and edited and approved by a human before anything publishes.</p>
                </div>
            </div>
        </div>
    </section>

    <!-- ============================================================
         10. EMAIL CAPTURE — price-drop alert signup
         ============================================================ -->
    <section class="home-cta-band">
        <div class="cbi-container">
            <div class="home-cta-band__inner">
                <div class="home-cta-band__copy">
                    <h2>Get price-drop alerts</h2>
                    <p>An email the moment a bean we rate drops in price. No spam, just price drops.</p>
                </div>
                <div class="home-cta-band__form">
                    <?php
                    // Set your WPForms form ID via the cbi_newsletter_form_id filter.
                    $form_id = apply_filters( 'cbi_newsletter_form_id', '' );
                    if ( $form_id ) {
                        echo do_shortcode( '[wpforms id="' . esc_attr( $form_id ) . '" title="false" description="false"]' );
                    } else { ?>
                        <p class="text-dim font-mono" style="font-size:0.85rem;">
                            [PLACEHOLDER] Set your WPForms ID via the <code>cbi_newsletter_form_id</code> filter or replace this block with your form shortcode.
                        </p>
                    <?php } ?>
                </div>
            </div>
        </div>
    </section>

</main>

<?php get_footer(); ?>
