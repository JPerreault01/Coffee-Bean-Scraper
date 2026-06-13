<?php
/**
 * Template: Taxonomy Hub (shared renderer)
 * File: taxonomy-hub-base.php
 *
 * ONE renderer for all five taxonomy hub roots: /origin/ /flavor/ /brew/
 * /process/ /roast/. Loaded by cbi_hub_template() (functions.php §24) when the
 * cbi_hub query var is set. Per-hub copy/keyword/section-toggles come from
 * cbi_hub_config(); intro + FAQ HTML come from cbi_hub_split_content().
 *
 * Section order (each conditional section runs its query FIRST and emits the
 * block only if it returns results — no empty shells, no "coming soon"):
 *   1. Hero + intro            (always)
 *   2. Term grid               (always — the primary internal-linking hub)
 *   3. Highest-rated beans      (if >=1 bean in this taxonomy)
 *   4. Best-of roundups         (if pages tagged cbi_hub_taxonomy=<tax> + roundup template)
 *   5. Guides & explainers      (if pages tagged cbi_hub_taxonomy=<tax> + guide template)
 *   6. Machines / equipment     (FUTURE — gated on post_type_exists('machine'))
 *   7. Accessories              (FUTURE — gated on post_type_exists('accessory'))
 *   8. FAQ accordion            (always)
 *
 * Sections 6-7 no-op until those post types exist. See HUB_EXTENSION_NOTES.md.
 */

get_header();

$hub = cbi_current_hub();
if ( ! $hub ) {
    get_footer();
    return;
}

$base     = $hub['base'];
$taxonomy = $hub['taxonomy'];
$tax_obj  = get_taxonomy( $taxonomy );
$tax_name = $tax_obj ? $tax_obj->labels->name : $hub['h1'];
$hub_url  = home_url( '/' . $base . '/' );
$sections = $hub['sections'];
$kses     = cbi_hub_kses_allowed();

list( $intro_html, $faq_html ) = cbi_hub_split_content( $base );

$breadcrumb_items = [
    [ 'label' => 'Home',      'url' => home_url() ],
    [ 'label' => $hub['h1'],  'url' => $hub_url ],
];

/**
 * Inline renderer for a content document card (roundups, guides, future
 * machines/accessories). Keeps sections 4-7 visually consistent.
 */
$render_doc_card = function ( $post_id, $kicker, $cta ) {
    $excerpt = get_the_excerpt( $post_id );
    ?>
    <a class="hub-doc-card" href="<?php echo esc_url( get_permalink( $post_id ) ); ?>">
        <span class="hub-doc-card__kicker"><?php echo esc_html( $kicker ); ?></span>
        <span class="hub-doc-card__title"><?php echo esc_html( get_the_title( $post_id ) ); ?></span>
        <?php if ( $excerpt ) : ?>
            <span class="hub-doc-card__excerpt"><?php echo esc_html( wp_trim_words( $excerpt, 22 ) ); ?></span>
        <?php endif; ?>
        <span class="hub-doc-card__cta"><?php echo esc_html( $cta ); ?> &rarr;</span>
    </a>
    <?php
};
?>

<!-- ============================================================
     SECTION 1 — HERO + INTRO  (template owns the single H1)
     ============================================================ -->
<section class="archive-hero hub-hero">
    <div class="cbi-container">
        <?php cbi_breadcrumb( $breadcrumb_items ); ?>
        <div class="archive-hero__eyebrow"><?php echo esc_html( $hub['eyebrow'] ); ?></div>
        <h1 class="archive-hero__title"><?php echo esc_html( $hub['h1'] ); ?></h1>
        <?php if ( $intro_html ) : ?>
            <div class="hub-hero__intro"><?php echo wp_kses( $intro_html, $kses ); ?></div>
        <?php endif; ?>
        <div class="hub-hero__actions">
            <a href="<?php echo esc_url( get_post_type_archive_link( 'bean' ) ?: home_url( '/beans/' ) ); ?>" class="cbi-btn cbi-btn--secondary">Browse all reviews</a>
        </div>
    </div>
</section>

<div class="cbi-container">

    <!-- ========================================================
         SECTION 2 — TERM GRID  (always)
         Curated cards, each linking to its /<base>/<term>/ archive.
         grid='curated' (flavor, process) shows only intentional terms
         (a description or child notes) and hides imported descriptor/
         per-lot noise; grid='all' (origin, brew, roast) shows every real
         term. Counts are archive-accurate (parents include their children).
         Child terms render as note chips, never as their own card.
         ======================================================== -->
    <?php
    $grid_mode = isset( $hub['grid'] ) ? $hub['grid'] : 'all';
    $exclude   = isset( $hub['exclude'] ) ? (array) $hub['exclude'] : [];

    $all_terms = get_terms( [ 'taxonomy' => $taxonomy, 'hide_empty' => false ] );
    if ( is_wp_error( $all_terms ) ) {
        $all_terms = [];
    }
    $children_map = [];
    foreach ( $all_terms as $t ) {
        if ( $t->parent ) {
            $children_map[ $t->parent ][] = $t;
        }
    }

    // Browse-accurate count: a parent term's archive includes its child terms
    // (hierarchical tax_query include_children), so the card must reflect that
    // total, not the parent's own (often zero) direct count.
    $hub_term_count = function ( $term ) use ( $children_map, $taxonomy ) {
        if ( empty( $children_map[ $term->term_id ] ) ) {
            return (int) $term->count;
        }
        $q = new WP_Query( [
            'post_type'      => 'bean',
            'post_status'    => 'publish',
            'fields'         => 'ids',
            'posts_per_page' => 1,
            'no_found_rows'  => false,
            'tax_query'      => [ [ 'taxonomy' => $taxonomy, 'field' => 'term_id', 'terms' => $term->term_id, 'include_children' => true ] ],
        ] );
        $n = (int) $q->found_posts;
        wp_reset_postdata();
        return $n;
    };

    // Build the visible card set.
    $cards = [];
    foreach ( $all_terms as $t ) {
        if ( $t->parent ) {
            continue; // children become chips, not cards
        }
        if ( in_array( $t->slug, $exclude, true ) ) {
            continue;
        }
        $kids     = isset( $children_map[ $t->term_id ] ) ? $children_map[ $t->term_id ] : [];
        $has_desc = trim( (string) $t->description ) !== '';
        if ( 'curated' === $grid_mode && ! $has_desc && empty( $kids ) ) {
            continue; // imported noise: no editorial description, no curated children
        }
        $count = $hub_term_count( $t );
        if ( $count < 1 ) {
            continue; // nothing to browse
        }
        if ( $kids ) {
            usort( $kids, function ( $a, $b ) { return strcasecmp( $a->name, $b->name ); } );
        }
        $cards[] = [ 'term' => $t, 'count' => $count, 'kids' => $kids, 'has_desc' => $has_desc ];
    }
    // Most-populated first, then alphabetical.
    usort( $cards, function ( $a, $b ) {
        if ( $b['count'] !== $a['count'] ) {
            return $b['count'] - $a['count'];
        }
        return strcasecmp( $a['term']->name, $b['term']->name );
    } );
    ?>
    <section class="cbi-section hub-section">
        <h2 class="cbi-section__heading">All <?php echo esc_html( $tax_name ); ?></h2>
        <?php if ( ! empty( $cards ) ) : ?>
        <div class="hub-term-grid">
            <?php foreach ( $cards as $card ) :
                $t        = $card['term'];
                $kids     = $card['kids'];
                $count    = $card['count'];
                $term_url = get_term_link( $t );
            ?>
            <article class="hub-term-card">
                <a class="hub-term-card__link" href="<?php echo esc_url( $term_url ); ?>">
                    <span class="hub-term-card__name"><?php echo esc_html( $t->name ); ?></span>
                    <span class="hub-term-card__count"><strong class="tabular-nums"><?php echo (int) $count; ?></strong> <?php echo 1 === (int) $count ? 'bean' : 'beans'; ?></span>
                </a>
                <?php if ( $card['has_desc'] ) : ?>
                    <p class="hub-term-card__desc"><?php echo esc_html( wp_trim_words( wp_strip_all_tags( $t->description ), 20 ) ); ?></p>
                <?php endif; ?>
                <?php if ( $kids ) : ?>
                    <div class="hub-term-card__notes">
                        <?php foreach ( $kids as $kid ) : ?>
                            <a class="hub-note-chip" href="<?php echo esc_url( get_term_link( $kid ) ); ?>"><?php echo esc_html( $kid->name ); ?></a>
                        <?php endforeach; ?>
                    </div>
                <?php endif; ?>
                <a class="hub-term-card__cta" href="<?php echo esc_url( $term_url ); ?>">Browse <?php echo esc_html( $t->name ); ?> &rarr;</a>
            </article>
            <?php endforeach; ?>
        </div>
        <?php else : ?>
            <p class="text-dim">Terms are being added. <a href="<?php echo esc_url( get_post_type_archive_link( 'bean' ) ?: home_url( '/beans/' ) ); ?>">Browse all beans</a> in the meantime.</p>
        <?php endif; ?>
    </section>

    <!-- ========================================================
         SECTION 3 — HIGHEST-RATED BEANS  (conditional)
         ======================================================== -->
    <?php
    if ( ! empty( $sections['featured'] ) ) :
        $featured = new WP_Query( [
            'post_type'      => 'bean',
            'post_status'    => 'publish',
            'posts_per_page' => 6,
            'orderby'        => 'meta_value_num',
            'meta_key'       => 'rating',
            'meta_type'      => 'NUMERIC',
            'order'          => 'DESC',
            'no_found_rows'  => true,
            'tax_query'      => [ [ 'taxonomy' => $taxonomy, 'operator' => 'EXISTS' ] ],
        ] );
        if ( $featured->have_posts() ) : ?>
        <section class="cbi-section hub-section">
            <h2 class="cbi-section__heading">Highest-rated coffees</h2>
            <div class="cbi-card-grid">
                <?php while ( $featured->have_posts() ) : $featured->the_post();
                    echo cbi_bean_card( get_the_ID() );
                endwhile; ?>
            </div>
        </section>
        <?php endif;
        wp_reset_postdata();
    endif;
    ?>

    <!-- ========================================================
         SECTION 4 — BEST-OF ROUNDUPS  (conditional)
         Linkage: page on template-roundup.php tagged with custom
         field cbi_hub_taxonomy = '<?php echo esc_html( $taxonomy ); ?>'.
         ======================================================== -->
    <?php
    if ( ! empty( $sections['roundups'] ) ) :
        $roundups = new WP_Query( [
            'post_type'      => 'page',
            'post_status'    => 'publish',
            'posts_per_page' => 6,
            'orderby'        => 'menu_order title',
            'order'          => 'ASC',
            'no_found_rows'  => true,
            'meta_query'     => [
                'relation' => 'AND',
                [ 'key' => '_wp_page_template', 'value' => 'template-roundup.php' ],
                [ 'key' => 'cbi_hub_taxonomy',  'value' => $taxonomy ],
            ],
        ] );
        if ( $roundups->have_posts() ) : ?>
        <section class="cbi-section hub-section">
            <h2 class="cbi-section__heading">Best-of rankings</h2>
            <div class="hub-doc-grid">
                <?php while ( $roundups->have_posts() ) : $roundups->the_post();
                    $render_doc_card( get_the_ID(), 'Ranked guide', 'View ranking' );
                endwhile; ?>
            </div>
        </section>
        <?php endif;
        wp_reset_postdata();
    endif;
    ?>

    <!-- ========================================================
         SECTION 5 — GUIDES & EXPLAINERS  (conditional)
         Linkage: page on template-guide.php tagged with custom
         field cbi_hub_taxonomy = '<?php echo esc_html( $taxonomy ); ?>'.
         ======================================================== -->
    <?php
    if ( ! empty( $sections['guides'] ) ) :
        $guides = new WP_Query( [
            'post_type'      => 'page',
            'post_status'    => 'publish',
            'posts_per_page' => 6,
            'orderby'        => 'menu_order title',
            'order'          => 'ASC',
            'no_found_rows'  => true,
            'meta_query'     => [
                'relation' => 'AND',
                [ 'key' => '_wp_page_template', 'value' => 'template-guide.php' ],
                [ 'key' => 'cbi_hub_taxonomy',  'value' => $taxonomy ],
            ],
        ] );
        if ( $guides->have_posts() ) : ?>
        <section class="cbi-section hub-section">
            <h2 class="cbi-section__heading">Guides &amp; explainers</h2>
            <div class="hub-doc-grid">
                <?php while ( $guides->have_posts() ) : $guides->the_post();
                    $render_doc_card( get_the_ID(), 'Guide', 'Read guide' );
                endwhile; ?>
            </div>
        </section>
        <?php endif;
        wp_reset_postdata();
    endif;
    ?>

    <!-- ========================================================
         SECTION 6 — MACHINES / EQUIPMENT  (FUTURE, gated)
         No-ops until a 'machine' post type exists. To activate with
         zero template edits: register post type 'machine' and tag each
         machine with custom field cbi_hub_taxonomy = the taxonomy name
         (e.g. 'brew-method' for espresso machines). See HUB_EXTENSION_NOTES.md.
         ======================================================== -->
    <?php
    if ( ! empty( $sections['machines'] ) && post_type_exists( 'machine' ) ) :
        $machines = new WP_Query( [
            'post_type'      => 'machine',
            'post_status'    => 'publish',
            'posts_per_page' => 6,
            'no_found_rows'  => true,
            'meta_query'     => [ [ 'key' => 'cbi_hub_taxonomy', 'value' => $taxonomy ] ],
        ] );
        if ( $machines->have_posts() ) : ?>
        <section class="cbi-section hub-section">
            <h2 class="cbi-section__heading">Machines &amp; equipment</h2>
            <div class="hub-doc-grid">
                <?php while ( $machines->have_posts() ) : $machines->the_post();
                    $render_doc_card( get_the_ID(), 'Equipment', 'Read review' );
                endwhile; ?>
            </div>
        </section>
        <?php endif;
        wp_reset_postdata();
    endif;
    ?>

    <!-- ========================================================
         SECTION 7 — ACCESSORIES  (FUTURE, gated)
         Same pattern as machines, gated on a 'accessory' post type.
         ======================================================== -->
    <?php
    if ( ! empty( $sections['accessories'] ) && post_type_exists( 'accessory' ) ) :
        $accessories = new WP_Query( [
            'post_type'      => 'accessory',
            'post_status'    => 'publish',
            'posts_per_page' => 6,
            'no_found_rows'  => true,
            'meta_query'     => [ [ 'key' => 'cbi_hub_taxonomy', 'value' => $taxonomy ] ],
        ] );
        if ( $accessories->have_posts() ) : ?>
        <section class="cbi-section hub-section">
            <h2 class="cbi-section__heading">Accessories</h2>
            <div class="hub-doc-grid">
                <?php while ( $accessories->have_posts() ) : $accessories->the_post();
                    $render_doc_card( get_the_ID(), 'Accessory', 'Read review' );
                endwhile; ?>
            </div>
        </section>
        <?php endif;
        wp_reset_postdata();
    endif;
    ?>

    <!-- ========================================================
         SECTION 8 — FAQ ACCORDION  (always)
         Markup is the theme's .cbi-faq <details>/<summary> contract;
         FAQPage JSON-LD is emitted in wp_head by cbi_hub_head().
         ======================================================== -->
    <?php if ( $faq_html ) : ?>
    <section class="cbi-section hub-section hub-faq">
        <h2 class="cbi-section__heading">Common questions</h2>
        <?php echo wp_kses( $faq_html, $kses ); ?>
    </section>
    <?php endif; ?>

</div>

<?php get_footer(); ?>
