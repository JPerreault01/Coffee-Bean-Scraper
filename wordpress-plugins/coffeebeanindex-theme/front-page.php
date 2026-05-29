<?php
/**
 * Front Page — Coffee Bean Index homepage
 *
 * Loads automatically for the site front page via the WordPress template
 * hierarchy (works whether Settings > Reading is set to "latest posts" or a
 * static page). No Customizer changes needed.
 *
 * All sections are self-wrapping (.cbi-container) so they are immune to the
 * GeneratePress container-width fight that affects untemplated pages.
 */

get_header();

// --- Data pulls (all guarded so the page never fatals on a fresh install) ---
$bean_count    = (int) wp_count_posts( 'bean' )->publish;
$origin_terms  = get_terms( [ 'taxonomy' => 'origin',  'hide_empty' => false ] );
$roaster_terms = get_terms( [ 'taxonomy' => 'roaster', 'hide_empty' => false ] );
$origin_count  = is_wp_error( $origin_terms )  ? 0 : count( $origin_terms );
$roaster_count = is_wp_error( $roaster_terms ) ? 0 : count( $roaster_terms );
$has_acf       = function_exists( 'get_field' );
?>

<main id="primary" class="cbi-home">

    <!-- ============================================================
         HERO
         ============================================================ -->
    <section class="home-hero">
        <div class="home-hero__inner cbi-container">
            <p class="home-hero__eyebrow">Independent &middot; Tasted &middot; Tracked</p>
            <h1 class="home-hero__title">Every bean, <span class="text-accent">tasted and ranked</span>.</h1>
            <p class="home-hero__lede">
                Honest reviews, flavor breakdowns, and live price tracking for the
                coffee worth buying &mdash; and the coffee worth skipping.
            </p>
            <div class="home-hero__cta">
                <a class="home-btn home-btn--primary" href="<?php echo esc_url( get_post_type_archive_link( 'bean' ) ); ?>">Browse all beans</a>
                <a class="home-btn home-btn--ghost" href="/find-your-coffee/">Find your coffee &rarr;</a>
            </div>
            <ul class="home-hero__stats">
                <li><strong><?php echo esc_html( $bean_count ); ?></strong><span>beans reviewed</span></li>
                <li><strong><?php echo esc_html( $origin_count ); ?></strong><span>origins</span></li>
                <li><strong><?php echo esc_html( $roaster_count ); ?></strong><span>roasters</span></li>
                <li><strong>Daily</strong><span>price checks</span></li>
            </ul>
        </div>
    </section>

    <!-- ============================================================
         BROWSE BY (taxonomy entry points — Fragrantica-style)
         ============================================================ -->
    <section class="home-section cbi-container">
        <div class="home-section__head">
            <h2>Start exploring</h2>
            <p class="text-muted">Five ways into the index &mdash; pick a thread and pull.</p>
        </div>

        <div class="browse-grid">
            <?php
            $entry_points = [
                [ 'label' => 'By flavor',      'tax' => 'flavor-note',    'blurb' => 'Dark chocolate, stone fruit, jasmine.' ],
                [ 'label' => 'By origin',      'tax' => 'origin',         'blurb' => 'Ethiopia, Colombia, Sumatra.' ],
                [ 'label' => 'By roast',       'tax' => 'roast-level',    'blurb' => 'Light through dark and French.' ],
                [ 'label' => 'By brew method', 'tax' => 'brew-method',    'blurb' => 'Espresso, pour-over, French press.' ],
                [ 'label' => 'By roaster',     'tax' => 'roaster',        'blurb' => 'Lavazza, Stumptown, Death Wish.' ],
            ];

            foreach ( $entry_points as $ep ) {
                $terms = get_terms( [
                    'taxonomy'   => $ep['tax'],
                    'hide_empty' => false,
                    'number'     => 6,
                    'orderby'    => 'count',
                    'order'      => 'DESC',
                ] );
                ?>
                <div class="browse-card">
                    <h3 class="browse-card__title"><?php echo esc_html( $ep['label'] ); ?></h3>
                    <p class="browse-card__blurb"><?php echo esc_html( $ep['blurb'] ); ?></p>
                    <div class="browse-card__chips">
                        <?php
                        if ( ! is_wp_error( $terms ) && ! empty( $terms ) ) {
                            foreach ( $terms as $term ) {
                                printf(
                                    '<a class="chip" href="%s">%s</a>',
                                    esc_url( get_term_link( $term ) ),
                                    esc_html( $term->name )
                                );
                            }
                        } else {
                            echo '<span class="chip chip--empty">Coming soon</span>';
                        }
                        ?>
                    </div>
                </div>
            <?php } ?>
        </div>
    </section>

    <!-- ============================================================
         LATEST REVIEWS
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
                    <p class="text-muted">Freshly tasted, freshly scored.</p>
                </div>
                <a class="home-section__more" href="<?php echo esc_url( get_post_type_archive_link( 'bean' ) ); ?>">All beans &rarr;</a>
            </div>

            <div class="home-review-grid">
                <?php while ( $latest->have_posts() ) : $latest->the_post();
                    $rating     = $has_acf ? get_field( 'rating' ) : '';
                    $verdict    = $has_acf ? get_field( 'verdict' ) : '';
                    $price_oz   = $has_acf ? get_field( 'price_per_oz' ) : '';
                    $roaster    = get_the_terms( get_the_ID(), 'roaster' );
                    $roaster_nm = ( $roaster && ! is_wp_error( $roaster ) ) ? $roaster[0]->name : '';
                    if ( empty( $verdict ) ) { $verdict = get_the_excerpt(); }
                    ?>
                    <a class="home-review-card" href="<?php the_permalink(); ?>">
                        <div class="home-review-card__media">
                            <?php if ( has_post_thumbnail() ) {
                                the_post_thumbnail( 'medium', [ 'class' => 'home-review-card__img', 'loading' => 'lazy' ] );
                            } else { ?>
                                <div class="home-review-card__img home-review-card__img--placeholder">&#9788;</div>
                            <?php } ?>
                            <?php if ( $rating !== '' && $rating !== null ) : ?>
                                <span class="home-review-card__rating"><?php echo esc_html( $rating ); ?><small>/10</small></span>
                            <?php endif; ?>
                        </div>
                        <div class="home-review-card__body">
                            <?php if ( $roaster_nm ) : ?>
                                <span class="home-review-card__roaster"><?php echo esc_html( $roaster_nm ); ?></span>
                            <?php endif; ?>
                            <h3 class="home-review-card__title"><?php the_title(); ?></h3>
                            <?php if ( $verdict ) : ?>
                                <p class="home-review-card__verdict"><?php echo esc_html( wp_trim_words( $verdict, 18 ) ); ?></p>
                            <?php endif; ?>
                            <?php if ( $price_oz !== '' && $price_oz !== null ) : ?>
                                <span class="home-review-card__price">$<?php echo esc_html( number_format( (float) $price_oz, 2 ) ); ?>/oz</span>
                            <?php endif; ?>
                        </div>
                    </a>
                <?php endwhile; ?>
            </div>
        </section>
        <?php wp_reset_postdata(); ?>
    <?php endif; ?>

    <!-- ============================================================
         WHY TRUST THE INDEX (E-E-A-T + editorial)
         ============================================================ -->
    <section class="home-trust">
        <div class="home-trust__inner cbi-container">
            <h2>Why trust the index</h2>
            <div class="home-trust__grid">
                <div class="home-trust__item">
                    <span class="home-trust__num">01</span>
                    <h3>We actually taste it</h3>
                    <p>Every review comes from a cup in hand, not a spec sheet. Notes are specific, scores are earned.</p>
                </div>
                <div class="home-trust__item">
                    <span class="home-trust__num">02</span>
                    <h3>We track the price daily</h3>
                    <p>Prices move. We log them every morning so you know whether today is a good day to buy.</p>
                </div>
                <div class="home-trust__item">
                    <span class="home-trust__num">03</span>
                    <h3>We tell you what to skip</h3>
                    <p>Not every bean is worth it. When something underdelivers for the money, we say so.</p>
                </div>
            </div>
        </div>
    </section>

    <!-- ============================================================
         NEWSLETTER / PRICE-DROP ALERTS
         ============================================================ -->
    <section class="home-cta-band">
        <div class="home-cta-band__inner cbi-container">
            <div class="home-cta-band__copy">
                <h2>Never overpay for good coffee</h2>
                <p>Get an email the moment a bean we rate drops in price. No spam, just price drops.</p>
            </div>
            <div class="home-cta-band__form">
                <?php
                // Replace XXX with your WPForms form ID once the email form is configured.
                // Until then this renders nothing and the copy above still shows.
                echo do_shortcode( '[wpforms id="XXX" title="false" description="false"]' );
                ?>
            </div>
        </div>
    </section>

</main>

<?php
get_footer();
