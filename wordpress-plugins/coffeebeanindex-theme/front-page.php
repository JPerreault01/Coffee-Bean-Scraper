<?php
/**
 * Front Page — Coffee Bean Index homepage
 *
 * Loads automatically for the site front page (Settings > Reading either mode).
 * Editorial review-publication layout, top to bottom:
 *   1. Hero        full-bleed warm placeholder + value prop + search + 2 CTAs
 *   2. Featured    6 latest bean reviews (reuses cbi_bean_card / .cbi-card-grid)
 *   3. Browse      category tiles → Roast, Origin, Brew (authority distribution)
 *   4. Deals strip beans below 30-day average (cbi_price_drop_beans())
 *   5. Guides      latest informational guide pages (cbi_get_guides())
 *   6. Email       price-drop alert signup band (WPForms via filter)
 *   Footer: generate_footer (FTC disclosure) — unchanged.
 *
 * All sections self-wrap in .cbi-container so they're immune to GP width.
 *
 * IMAGES: the hero uses a CSS-driven placeholder. To drop in a real photo, see
 * .home-hero--full in style.css — supply a 2400×1200px (2:1) optimised JPG/WebP.
 * Never hotlink copyrighted photos.
 */

get_header();

$bean_count    = (int) wp_count_posts( 'bean' )->publish;
$origin_terms  = get_terms( [ 'taxonomy' => 'origin',  'hide_empty' => false ] );
$roaster_terms = get_terms( [ 'taxonomy' => 'roaster', 'hide_empty' => false ] );
$origin_count  = is_wp_error( $origin_terms )  ? 0 : count( $origin_terms );
$roaster_count = is_wp_error( $roaster_terms ) ? 0 : count( $roaster_terms );

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
         1. HERO — full-bleed warm placeholder + overlay
         IMAGE DROP-IN: replace the .home-hero__bg background in style.css
         (search ".home-hero--full") with a 2400×1200px (2:1) photo or a
         subtle looping MP4/GIF. Keep the dark overlay for text contrast.
         ============================================================ -->
    <section class="home-hero home-hero--full">
        <div class="home-hero__bg" aria-hidden="true"><!-- placeholder: drop hero image/video here (2400×1200) --></div>
        <div class="home-hero__overlay" aria-hidden="true"></div>
        <div class="home-hero__inner cbi-container">
            <span class="home-hero__eyebrow">Independent &middot; Data-driven &middot; Daily price tracking</span>
            <h1 class="home-hero__title"><?php echo esc_html( get_bloginfo( 'name' ) ); ?></h1>
            <p class="home-hero__lede">Honest, data-backed coffee reviews and live price tracking &mdash; for the beans worth buying and the ones worth skipping.</p>

            <form role="search" method="get" class="home-search" action="<?php echo esc_url( home_url( '/' ) ); ?>">
                <label class="screen-reader-text" for="home-search-input">Search bean reviews</label>
                <input type="search" id="home-search-input" class="home-search__input" name="s" placeholder="Search a bean, roaster, or origin&hellip;" />
                <input type="hidden" name="post_type" value="bean" />
                <button type="submit" class="home-search__btn">Search</button>
            </form>

            <div class="home-hero__cta">
                <a class="cbi-btn cbi-btn--primary" href="<?php echo esc_url( $beans_url ); ?>">Browse reviews</a>
                <a class="cbi-btn cbi-btn--secondary cbi-btn--on-dark" href="<?php echo esc_url( home_url( '/explore/' ) ); ?>">Find your coffee &rarr;</a>
            </div>

            <ul class="home-hero__stats">
                <li class="home-hero__stat"><strong><?php echo esc_html( $bean_count ?: '—' ); ?></strong><span>beans reviewed</span></li>
                <li class="home-hero__stat"><strong><?php echo esc_html( $origin_count ?: '—' ); ?></strong><span>origins tracked</span></li>
                <li class="home-hero__stat"><strong><?php echo esc_html( $roaster_count ?: '—' ); ?></strong><span>roasters indexed</span></li>
                <li class="home-hero__stat"><strong>Daily</strong><span>price checks</span></li>
            </ul>
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
         3. BROWSE BY CATEGORY — primary authority-distribution tiles
            Routes link equity into the Roast / Origin / Brew hubs.
         ============================================================ -->
    <section class="home-section home-section--tint">
        <div class="cbi-container">
            <div class="home-section__head">
                <h2>Browse by category</h2>
                <p class="text-muted">Three ways into the index &mdash; pick a thread and pull.</p>
            </div>
            <div class="home-cat-tiles">
                <?php
                // ICON DROP-IN: each tile uses a CSS gradient placeholder. To use
                // images, set a background on .home-cat-tile--{slug} in style.css
                // (recommended 800×600px). Tiles link to taxonomy term archives.
                $categories = [
                    [
                        'label' => 'By Roast Level',
                        'blurb' => 'Light, medium, dark, French.',
                        'tax'   => 'roast-level',
                        'url'   => home_url( '/roast/' ),
                    ],
                    [
                        'label' => 'By Origin',
                        'blurb' => 'Ethiopia, Colombia, Sumatra and more.',
                        'tax'   => 'origin',
                        'url'   => home_url( '/origin/' ),
                    ],
                    [
                        'label' => 'By Brew Method',
                        'blurb' => 'Espresso, pour-over, French press.',
                        'tax'   => 'brew-method',
                        'url'   => home_url( '/brew/' ),
                    ],
                ];
                foreach ( $categories as $cat ) :
                    $terms = get_terms( [
                        'taxonomy'   => $cat['tax'],
                        'hide_empty' => false,
                        'number'     => 5,
                        'orderby'    => 'count',
                        'order'      => 'DESC',
                    ] );
                ?>
                    <a class="home-cat-tile home-cat-tile--<?php echo esc_attr( $cat['tax'] ); ?>" href="<?php echo esc_url( $cat['url'] ); ?>">
                        <span class="home-cat-tile__media" aria-hidden="true"></span>
                        <span class="home-cat-tile__body">
                            <span class="home-cat-tile__label"><?php echo esc_html( $cat['label'] ); ?></span>
                            <span class="home-cat-tile__blurb"><?php echo esc_html( $cat['blurb'] ); ?></span>
                            <?php if ( ! is_wp_error( $terms ) && ! empty( $terms ) ) : ?>
                                <span class="home-cat-tile__terms">
                                    <?php echo esc_html( implode( ' · ', wp_list_pluck( array_slice( $terms, 0, 4 ), 'name' ) ) ); ?>
                                </span>
                            <?php endif; ?>
                        </span>
                    </a>
                <?php endforeach; ?>
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
                    <p>An email the moment a bean we rate drops in price. No spam &mdash; just price drops.</p>
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
