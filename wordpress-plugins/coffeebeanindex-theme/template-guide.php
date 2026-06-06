<?php
/**
 * Template Name: Origin / Brew Guide
 * Template Post Type: page
 *
 * File: template-guide.php
 *
 * HOW TO USE (non-dev): create a normal Page, write the body with H2 (main
 * sections) and H3 (subsections) headings, then in the editor's right-hand
 * "Page" panel set Template → "Origin / Brew Guide". That's it — the ToC,
 * reading time, related beans, and related guides all build themselves.
 *
 * WHY a page template (template-guide.php) and not page-guide.php:
 * page-guide.php would force EVERY page to use this layout. A selectable
 * Template lets the editor opt specific pages in from the Page Attributes
 * dropdown while leaving About/Privacy/etc. on the plain page.php — the
 * cleaner choice for a non-developer picking it in the editor.
 *
 * Layout (desktop ≥1100px):  [ sticky ToC rail | article ~68ch ]
 *                            → Related beans (cards)  → Related guides
 * Mobile: ToC collapses to a tap-to-expand block above the article.
 *
 * The body class .guide-page (added in functions.php) scopes all CSS so guide
 * typography can't bleed into bean reviews. ToC JS: js/guide-toc.js.
 *
 * RELATED BEANS resolution: shares a taxonomy term with the guide. Auto-matched
 * from the page slug/title (e.g. /ethiopia-coffee/ → origin "ethiopia"), or set
 * an ACF text field "related_taxonomy_slug" (comma-separated term slugs) to
 * override. See cbi_guide_related_beans() in functions.php.
 */

get_header();

while ( have_posts() ) : the_post();
    $post_id    = get_the_ID();
    $title      = get_the_title();
    $url        = get_permalink();
    $excerpt    = get_the_excerpt();
    $categories = get_the_category();
    $category   = $categories ? $categories[0]->name : 'Guide';

    // Reading time — words / 200 wpm, floored at 1 min.
    $word_count   = str_word_count( wp_strip_all_tags( get_the_content() ) );
    $reading_time = max( 1, (int) ceil( $word_count / 200 ) );

    // Schema — Article
    $schema = [
        '@context'      => 'https://schema.org',
        '@type'         => 'Article',
        'headline'      => $title,
        'url'           => $url,
        'datePublished' => get_the_date( 'c' ),
        'dateModified'  => get_the_modified_date( 'c' ),
        'description'   => $excerpt ?: '',
        'publisher'     => [
            '@type' => 'Organization',
            'name'  => 'Coffee Bean Index',
            'url'   => home_url(),
        ],
        'author'        => [
            '@type' => 'Organization',
            'name'  => 'Coffee Bean Index',
        ],
    ];
    if ( has_post_thumbnail() ) {
        $schema['image'] = get_the_post_thumbnail_url( $post_id, 'large' );
    }
?>

<script type="application/ld+json"><?php echo wp_json_encode( $schema, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE ); ?></script>

<main id="primary" class="guide-main">

    <!-- ============================================================
         AFFILIATE DISCLOSURE (FTC requirement, near top of content)
         ============================================================ -->
    <div class="cbi-disclosure-inline" style="border-radius:0;border-left:none;border-right:none;border-top:none;">
        <div class="cbi-container">
            This page contains affiliate links. We may earn commissions from qualifying purchases at no extra cost to you.
        </div>
    </div>

    <!-- ============================================================
         HERO BAND — H1, dek, reading time
         ============================================================ -->
    <section class="guide-hero">
        <div class="cbi-container guide-hero__inner">
            <?php
            cbi_breadcrumb( [
                [ 'label' => 'Home',  'url' => home_url() ],
                [ 'label' => $title,  'url' => $url ],
            ] );
            ?>
            <p class="guide-hero__category"><?php echo esc_html( $category ); ?></p>
            <h1 class="guide-hero__title"><?php the_title(); ?></h1>
            <?php if ( $excerpt ) : ?>
                <p class="guide-hero__intro"><?php echo esc_html( $excerpt ); ?></p>
            <?php endif; ?>
            <div class="guide-meta">
                <span>Updated <?php echo esc_html( get_the_modified_date( 'F j, Y' ) ); ?></span>
                <span aria-hidden="true">&middot;</span>
                <span><?php echo esc_html( $reading_time ); ?> min read</span>
            </div>
        </div>
    </section>

    <!-- ============================================================
         BODY — sticky ToC rail (desktop) + article
         ============================================================ -->
    <div class="cbi-container">
        <div class="guide-layout">

            <!-- ToC: desktop left rail (≥1100px). Populated by guide-toc.js. -->
            <nav class="guide-toc" id="guide-toc" aria-label="Table of contents" hidden>
                <p class="guide-toc__title">In this guide</p>
                <ol class="guide-toc__list" id="guide-toc-list"></ol>
            </nav>

            <!-- Main article -->
            <article class="guide-body entry-content">

                <!-- ToC: mobile tap-to-expand (<1100px). Populated by guide-toc.js. -->
                <div class="guide-toc-mobile" id="guide-toc-mobile" hidden>
                    <button type="button" class="guide-toc-mobile__toggle" id="guide-toc-mobile-toggle" aria-expanded="false" aria-controls="guide-toc-mobile-list">
                        <span>In this guide</span>
                        <span class="guide-toc-mobile__chevron" aria-hidden="true">&#9662;</span>
                    </button>
                    <ol class="guide-toc__list" id="guide-toc-mobile-list" hidden></ol>
                </div>

                <?php the_content(); ?>
            </article>
        </div>
    </div>

    <!-- ============================================================
         RELATED BEANS — cards sharing a taxonomy term (rating desc, max 6)
         ============================================================ -->
    <?php
    $related = cbi_guide_related_beans( $post_id, 6 );
    if ( $related->have_posts() ) : ?>
        <section class="guide-related">
            <div class="cbi-container">
                <div class="home-section__head home-section__head--row">
                    <div>
                        <h2>Beans worth tasting next</h2>
                        <p class="text-muted">Reviews connected to this guide.</p>
                    </div>
                    <a class="home-section__more" href="<?php echo esc_url( get_post_type_archive_link( 'bean' ) ?: home_url( '/beans/' ) ); ?>">All beans &rarr;</a>
                </div>
                <div class="cbi-card-grid">
                    <?php
                    while ( $related->have_posts() ) : $related->the_post();
                        echo cbi_bean_card( get_the_ID() ); // dofollow review permalink inside
                    endwhile;
                    wp_reset_postdata();
                    ?>
                </div>
            </div>
        </section>
    <?php endif; ?>

    <!-- ============================================================
         RELATED GUIDES — 3 sibling guides (text links + descriptions)
         ============================================================ -->
    <?php
    $sibling_guides = cbi_get_guides( 3, $post_id );
    if ( $sibling_guides->have_posts() ) : ?>
        <section class="guide-siblings">
            <div class="cbi-container">
                <div class="home-section__head">
                    <h2>Keep reading</h2>
                    <p class="text-muted">More from the guide library.</p>
                </div>
                <ul class="guide-siblings__list">
                    <?php while ( $sibling_guides->have_posts() ) : $sibling_guides->the_post();
                        $g_excerpt = get_the_excerpt();
                    ?>
                        <li class="guide-siblings__item">
                            <a class="guide-siblings__link" href="<?php the_permalink(); ?>" rel="dofollow"><?php the_title(); ?></a>
                            <?php if ( $g_excerpt ) : ?>
                                <p class="guide-siblings__desc"><?php echo esc_html( wp_trim_words( $g_excerpt, 22 ) ); ?></p>
                            <?php endif; ?>
                        </li>
                    <?php endwhile;
                    wp_reset_postdata(); ?>
                </ul>
            </div>
        </section>
    <?php endif; ?>

    <!-- Prev / next guide navigation -->
    <div class="cbi-container">
        <div class="guide-postnav">
            <?php the_post_navigation( [
                'prev_text' => '&larr; %title',
                'next_text' => '%title &rarr;',
            ] ); ?>
        </div>
    </div>

</main>

<?php endwhile; ?>

<?php get_footer(); ?>
