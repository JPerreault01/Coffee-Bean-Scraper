<?php
/**
 * Front Page — Coffee Bean Index homepage
 *
 * Template hierarchy: front-page.php loads automatically for the site front page
 * whether Settings > Reading is "latest posts" or a static page.
 *
 * All sections are self-wrapping so they are immune to GP container width.
 */

get_header();

$bean_count    = (int) wp_count_posts( 'bean' )->publish;
$origin_terms  = get_terms( [ 'taxonomy' => 'origin',  'hide_empty' => false ] );
$roaster_terms = get_terms( [ 'taxonomy' => 'roaster', 'hide_empty' => false ] );
$origin_count  = is_wp_error( $origin_terms )  ? 0 : count( $origin_terms );
$roaster_count = is_wp_error( $roaster_terms ) ? 0 : count( $roaster_terms );
$has_acf       = function_exists( 'get_field' );
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
         HERO — two-column layout (content left, stats right)
         ============================================================ -->
    <section class="home-hero">
        <div class="home-hero__inner cbi-container">
            <div class="home-hero__content">
                <span class="home-hero__eyebrow">Independent &middot; Data-driven &middot; Daily price tracking</span>
                <h1 class="home-hero__title">Every bean, <em>ranked</em>.</h1>
                <p class="home-hero__lede">
                    Honest reviews, flavor breakdowns, and live price tracking for the
                    coffee worth buying&mdash;and the coffee worth skipping.
                </p>
                <div class="home-hero__cta">
                    <a class="cbi-btn cbi-btn--primary" href="<?php echo esc_url( get_post_type_archive_link( 'bean' ) ?: home_url( '/beans/' ) ); ?>">Browse all beans</a>
                    <a class="cbi-btn cbi-btn--secondary" href="<?php echo esc_url( home_url( '/explore/' ) ); ?>">Explore by flavor &amp; origin &rarr;</a>
                </div>
            </div>
            <ul class="home-hero__stats">
                <li class="home-hero__stat">
                    <strong><?php echo esc_html( $bean_count ?: '&mdash;' ); ?></strong>
                    <span>beans reviewed</span>
                </li>
                <li class="home-hero__stat">
                    <strong><?php echo esc_html( $origin_count ?: '&mdash;' ); ?></strong>
                    <span>origins tracked</span>
                </li>
                <li class="home-hero__stat">
                    <strong><?php echo esc_html( $roaster_count ?: '&mdash;' ); ?></strong>
                    <span>roasters indexed</span>
                </li>
                <li class="home-hero__stat">
                    <strong>Daily</strong>
                    <span>price checks</span>
                </li>
            </ul>
        </div>
    </section>

    <!-- ============================================================
         BROWSE BY — Fragrantica-style taxonomy entry points
         ============================================================ -->
    <section class="home-section cbi-container">
        <div class="home-section__head">
            <h2>Start exploring</h2>
            <p class="text-muted">Five ways into the index &mdash; pick a thread and pull.</p>
        </div>

        <div class="browse-grid">
            <?php
            $entry_points = [
                [ 'label' => 'By flavor',      'tax' => 'flavor-note',  'blurb' => 'Dark chocolate, stone fruit, jasmine.' ],
                [ 'label' => 'By origin',      'tax' => 'origin',       'blurb' => 'Ethiopia, Colombia, Sumatra.' ],
                [ 'label' => 'By roast',       'tax' => 'roast-level',  'blurb' => 'Light through dark and French.' ],
                [ 'label' => 'By brew method', 'tax' => 'brew-method',  'blurb' => 'Espresso, pour-over, French press.' ],
                [ 'label' => 'By roaster',     'tax' => 'roaster',      'blurb' => 'Lavazza, Stumptown, Death Wish.' ],
            ];

            foreach ( $entry_points as $ep ) :
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
            <?php endforeach; ?>
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
                    <p class="text-muted">Freshly scored.</p>
                </div>
                <a class="home-section__more" href="<?php echo esc_url( get_post_type_archive_link( 'bean' ) ?: home_url( '/beans/' ) ); ?>">All beans &rarr;</a>
            </div>

            <div class="home-review-grid">
                <?php while ( $latest->have_posts() ) : $latest->the_post();
                    $rating     = $has_acf ? get_field( 'rating' ) : '';
                    $verdict    = $has_acf ? get_field( 'verdict' ) : '';
                    $price_oz   = $has_acf ? get_field( 'price_per_oz' ) : '';
                    $roaster    = get_the_terms( get_the_ID(), 'roaster' );
                    $roaster_nm = ( $roaster && ! is_wp_error( $roaster ) ) ? $roaster[0]->name : '';
                    if ( empty( $verdict ) ) $verdict = get_the_excerpt();
                ?>
                    <a class="home-review-card" href="<?php the_permalink(); ?>">
                        <div class="home-review-card__media">
                            <?php if ( has_post_thumbnail() ) :
                                the_post_thumbnail( 'medium', [
                                    'class'   => 'home-review-card__img',
                                    'loading' => 'lazy',
                                    'width'   => '400',
                                    'height'  => '300',
                                ] );
                            else :
                                // SVG coffee cup — no emoji
                                echo '<div class="home-review-card__img home-review-card__img--placeholder">';
                                echo '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">';
                                echo '<path d="M17 8h1a4 4 0 0 1 0 8h-1"/>';
                                echo '<path d="M3 8h14v9a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4Z"/>';
                                echo '<line x1="6" x2="6" y1="2" y2="4"/>';
                                echo '<line x1="10" x2="10" y1="2" y2="4"/>';
                                echo '<line x1="14" x2="14" y1="2" y2="4"/>';
                                echo '</svg>';
                                echo '</div>';
                            endif; ?>
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
                <?php endwhile;
                wp_reset_postdata(); ?>
            </div>
        </section>
    <?php endif; ?>

    <!-- ============================================================
         WHY TRUST THE INDEX — E-E-A-T block
         ============================================================ -->
    <section class="home-trust">
        <div class="cbi-container">
            <h2>Why trust the index</h2>
            <div class="home-trust__grid">
                <div class="home-trust__item">
                    <span class="home-trust__num">01</span>
                    <h3>We track data, then taste</h3>
                    <p>Price history, sensory profiles, and tasting notes are assembled from structured product data and direct evaluation criteria&mdash;not marketing copy.</p>
                </div>
                <div class="home-trust__item">
                    <span class="home-trust__num">02</span>
                    <h3>We check the price daily</h3>
                    <p>Prices move. We log them every morning so you know whether today is a good day to buy or whether to wait.</p>
                </div>
                <div class="home-trust__item">
                    <span class="home-trust__num">03</span>
                    <h3>We tell you what to skip</h3>
                    <p>Not every bean earns its price. When something underdelivers for the money, we say so&mdash;specifically, not vaguely.</p>
                </div>
                <div class="home-trust__item">
                    <span class="home-trust__num">04</span>
                    <h3>Transparent methodology</h3>
                    <p>Reviews are built from structured product data, public tasting notes, and editorial criteria. <a href="<?php echo esc_url( home_url( '/editorial-standards/' ) ); ?>">Read our methodology &rarr;</a></p>
                </div>
            </div>
        </div>
    </section>

    <!-- ============================================================
         NEWSLETTER / PRICE-DROP ALERTS
         ============================================================ -->
    <section class="home-cta-band">
        <div class="cbi-container">
            <div class="home-cta-band__inner">
                <div class="home-cta-band__copy">
                    <h2>Never overpay for good coffee</h2>
                    <p>Get an alert the moment a bean we rate drops in price. No spam&mdash;just price drops.</p>
                </div>
                <div class="home-cta-band__form">
                    <?php
                    // Replace XXX with your WPForms form ID in the WordPress admin.
                    // Until then the copy above still shows cleanly.
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
