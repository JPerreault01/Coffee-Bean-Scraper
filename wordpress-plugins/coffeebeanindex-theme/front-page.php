<?php
/**
 * Front Page — Coffee Bean Index homepage
 *
 * Loads automatically for the site front page (Settings > Reading either mode).
 * Editorial review-publication layout, top to bottom:
 *   1. Hero        full-width CSS-background (LCP), value prop, single CTA
 *   2. Featured    6 latest bean reviews (reuses cbi_bean_card / .cbi-card-grid)
 *   3. Category    4 image cards: Espresso, Dark Roast, Single Origin, Ground
 *   3b. Brew       4 inline-SVG device icons linking to brew-method guides
 *   4. Deals strip beans below 30-day average (cbi_price_drop_beans())
 *   5. Guides      latest informational guide pages (cbi_get_guides())
 *   6. Email       price-drop alert signup band (WPForms via filter)
 *   Footer: generate_footer (FTC disclosure), unchanged.
 *
 * All sections self-wrap in .cbi-container so they're immune to GP width.
 *
 * IMAGES: fully automated. convert-images.py makes the WebPs; deploy-homepage.ps1
 * runs `wp media import` and stores the attachment IDs in the cbi_home_image_ids
 * option. The hero (cbi_hero_head in functions.php) and the cards (cbi_home_image_url
 * below) read that option, so no URLs are ever pasted. Never hotlink copyrighted photos.
 */

get_header();

$beans_url = get_post_type_archive_link( 'bean' ) ?: home_url( '/beans/' );
?>

<main id="primary" class="cbi-home">

    <!-- ============================================================
         AFFILIATE DISCLOSURE (FTC requirement, near top of content)
         ============================================================ -->
    <div class="cbi-disclosure-inline" style="border-radius:0;border-left:none;border-right:none;border-top:none;">
        <div class="cbi-container">
            This page contains affiliate links. We may earn commissions from qualifying purchases at no extra cost to you.
        </div>
    </div>

    <!-- ============================================================
         1. HERO (LCP) — full-width CSS background, dark overlay, single CTA.
         The hero photo is injected (background-image + preload) by cbi_hero_head()
         in functions.php from the cbi_home_image_ids option, so it stays the LCP
         element with no <img> and no layout shift. Until the WebP is imported, the
         CSS gradient fallback on .cbi-hero__bg shows. Nothing to paste.
         ============================================================ -->
    <section class="cbi-hero">
        <div class="cbi-hero__bg" aria-hidden="true"></div>
        <div class="cbi-hero__overlay" aria-hidden="true"></div>
        <div class="cbi-hero__inner cbi-container">
            <span class="cbi-hero__eyebrow">Independent &middot; Data-driven &middot; Daily price tracking</span>
            <h1 class="cbi-hero__title">Find the coffee beans actually worth buying.</h1>
            <p class="cbi-hero__subhead">Honest, data-backed reviews and live price tracking. We score the beans that earn it and call out the ones that don't.</p>
            <a class="cbi-btn cbi-btn--primary cbi-hero__cta" href="<?php echo esc_url( home_url( '/best-espresso-beans-under-20/' ) ); ?>">See the best espresso beans under $20 &rarr;</a>
        </div>
    </section>

    <!-- ============================================================
         2. FEATURED / LATEST REVIEWS — 6 most recent beans
         ============================================================ -->
    <?php
    $latest = new WP_Query( [
        'post_type'      => 'bean',
        'posts_per_page' => 6,
        'post_status'    => 'publish',
        'no_found_rows'  => true,
    ] );
    if ( $latest->have_posts() ) : ?>
        <section class="home-section cbi-container">
            <div class="home-section__head home-section__head--row">
                <div>
                    <h2>Latest reviews</h2>
                    <p class="text-muted">Freshly scored, with live price/oz.</p>
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
         3. CATEGORY CARDS — 4 image cards (authority distribution).
            Image URLs resolve automatically from the Media Library via
            cbi_home_image_url() (IDs set by deploy-homepage.ps1 -> wp media
            import). Nothing to paste. Until a WebP is imported, the matching
            card shows its styled placeholder.
         ============================================================ -->
    <?php
    $cat_img_espresso = cbi_home_image_url( 'espresso' );
    $cat_img_dark     = cbi_home_image_url( 'dark_roast' );
    $cat_img_origin   = cbi_home_image_url( 'beans' );
    $cat_img_ground   = cbi_home_image_url( 'ground_coffee' );

    /**
     * Resolve a term-archive URL by slug, regardless of the taxonomy's
     * rewrite base (brew-method registers as /brew/, roast-level as /roast/).
     * Falls back to the archive base used elsewhere in the theme if the term
     * does not exist yet, so links never 404 to a dead term path.
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

    $cbi_cats = [
        [
            'label' => 'Espresso',
            'blurb' => 'Beans built for pressure and crema.',
            'url'   => $cbi_term_url( 'espresso', 'brew-method', '/brew/' ),
            'img'   => $cat_img_espresso,
            'alt'   => 'A double shot of espresso pouring into a white cup',
        ],
        [
            'label' => 'Dark Roast',
            'blurb' => 'Bold, low-acid, built to hold up to milk.',
            'url'   => $cbi_term_url( 'dark', 'roast-level', '/roast/' ),
            'img'   => $cat_img_dark,
            'alt'   => 'Dark roasted coffee beans with an oily sheen',
        ],
        [
            'label' => 'Single Origin',
            'blurb' => 'Traceable beans from one farm or region.',
            'url'   => home_url( '/origin/' ),
            'img'   => $cat_img_origin,
            'alt'   => 'A pile of roasted single origin coffee beans',
        ],
        [
            'label' => 'Ground Coffee',
            'blurb' => 'Pre-ground picks for French press and drip.',
            'url'   => $cbi_term_url( 'french-press', 'brew-method', '/brew/' ),
            'img'   => $cat_img_ground,
            'alt'   => 'Freshly ground coffee in a metal scoop',
        ],
    ];
    ?>
    <section class="home-section cbi-container">
        <div class="home-section__head">
            <h2>Browse by category</h2>
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
         3b. BREW GUIDES — 4 hand-drawn inline SVG device icons.
            Each links to its brew-method guide. The SVGs are decorative
            (aria-hidden); the visible text label is each link's accessible
            name. Icons inherit the oxblood accent via stroke="currentColor".
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
         4. PRICE-DROP / DEALS STRIP — beans below 30-day average
            Data source: cbi_price_drop_beans() (functions.php). Returns []
            until the scraper feeds it — renders a labelled placeholder then.
         ============================================================ -->
    <section class="home-deals">
        <div class="cbi-container">
            <div class="home-section__head home-section__head--row">
                <div>
                    <h2>Price drops</h2>
                    <p class="text-muted">Beans we rate, currently below their 30-day average.</p>
                </div>
                <a class="home-section__more" href="<?php echo esc_url( home_url( '/explore/' ) ); ?>">Explore all &rarr;</a>
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
                            <span class="home-deal__badge tabular-nums">&minus;<?php echo esc_html( (int) $deal['pct'] ); ?>%</span>
                        </a>
                    <?php endforeach; ?>
                </div>
            <?php else : ?>
                <?php /* TODO: wire the 'cbi_price_drop_beans' filter from the scraper.
                         Expected row shape: [ 'post_id'=>int, 'current'=>float,
                         'avg30'=>float, 'pct'=>int ] ordered by pct desc. */ ?>
                <div class="home-deals__placeholder">
                    <p>Price-drop tracking switches on once the daily scraper feeds 30-day averages into the site. <a href="<?php echo esc_url( $beans_url ); ?>">Browse all reviews &rarr;</a></p>
                </div>
            <?php endif; ?>
        </div>
    </section>

    <!-- ============================================================
         5. GUIDES — latest informational guide pages
            Reinforces the 40% informational ratio + links the hubs.
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
         6. EMAIL CAPTURE — price-drop alert signup
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
                        <p style="font-size:0.85rem;color:var(--cbi-text-dim);font-family:var(--font-mono);">
                            [PLACEHOLDER] Set your WPForms ID via the <code>cbi_newsletter_form_id</code> filter or replace this block with your form shortcode.
                        </p>
                    <?php } ?>
                </div>
            </div>
        </div>
    </section>

</main>

<?php get_footer(); ?>
