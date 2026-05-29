<?php
/**
 * Template Name: Best-of Roundup
 * Template Post Type: page
 *
 * File: template-roundup.php
 *
 * For "Best X for Y" commercial-intent pages.
 * Structure: ranked list of individual picks with affiliate CTAs,
 * a summary comparison table at the top, FAQ schema at the bottom.
 *
 * AUTHORING GUIDE:
 * Use the standard WordPress editor for the introduction.
 * For each pick, use an H2 with the bean name, then add the verdict
 * as a blockquote, a specs table (HTML table is fine), and an affiliate
 * link. The template wraps everything in the roundup layout and adds
 * the disclosure and schema automatically.
 *
 * To add a comparison table, insert an HTML block with class "comparison-table".
 * To add an FAQ accordion, insert HTML blocks with class "cbi-faq".
 */

get_header();

while ( have_posts() ) : the_post();
    $post_id = get_the_ID();
    $title   = get_the_title();
    $url     = get_permalink();
    $excerpt = get_the_excerpt();

    // Schema: ItemList (positions will be numbered via CSS counter)
    $schema = [
        '@context' => 'https://schema.org',
        '@type'    => 'Article',
        'headline' => $title,
        'url'      => $url,
        'publisher'=> [
            '@type' => 'Organization',
            'name'  => 'Coffee Bean Index',
            'url'   => home_url(),
        ],
    ];
?>

<script type="application/ld+json"><?php echo wp_json_encode( $schema, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE ); ?></script>

<!-- Roundup Hero -->
<section class="roundup-hero">
    <div class="cbi-container">
        <?php
        cbi_breadcrumb( [
            [ 'label' => 'Home',  'url' => home_url() ],
            [ 'label' => 'Roundups', 'url' => home_url( '/category/roundups/' ) ],
            [ 'label' => $title, 'url' => $url ],
        ] );
        ?>
        <p class="roundup-hero__eyebrow">Roundup &middot; <?php echo get_the_date( 'F Y' ); ?></p>
        <h1 class="roundup-hero__title"><?php the_title(); ?></h1>
        <?php if ( $excerpt ) : ?>
            <p class="roundup-hero__intro"><?php echo esc_html( $excerpt ); ?></p>
        <?php endif; ?>
    </div>
</section>

<!-- Affiliate disclosure — required near top of any page with affiliate links -->
<div class="cbi-disclosure-inline" style="border-radius:0;border-left:none;border-right:none;border-top:none;">
    <div class="cbi-container">
        This page contains affiliate links. We may earn commissions from qualifying purchases at no extra cost to you. Prices are checked daily.
    </div>
</div>

<!-- Roundup Body -->
<div class="cbi-container" style="padding-top:var(--space-12);padding-bottom:var(--space-16);">
    <div style="max-width:var(--content-width);">
        <article class="roundup-body">
            <?php
            // The WordPress editor content contains the introduction, comparison table,
            // individual picks, FAQs etc. — all styled via our CSS classes.
            the_content();
            ?>
        </article>

        <!-- Post navigation -->
        <div style="margin-top:var(--space-12);padding-top:var(--space-8);border-top:1px solid var(--cbi-border);">
            <?php the_post_navigation( [
                'prev_text' => '&larr; %title',
                'next_text' => '%title &rarr;',
            ] ); ?>
        </div>
    </div>
</div>

<?php endwhile; ?>

<?php get_footer(); ?>
