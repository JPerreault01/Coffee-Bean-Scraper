
<?php
/**
 * Template Name: Bean Comparison (X vs Y)
 * Template Post Type: page
 *
 * File: template-comparison.php
 *
 * Head-to-head comparison layout for two specific beans.
 * Outputs a spec comparison table and a clear winner recommendation.
 *
 * AUTHORING GUIDE:
 * Write the page content in the standard WordPress editor.
 * Structure: short intro → head-to-head table (HTML table with class "vs-table")
 * → recommendation section → FAQ → affiliate CTAs.
 * The template provides the hero and disclosure automatically.
 * Bean names in the title become the H1 — keep the page title in the format
 * "Bean A vs Bean B — Which Should You Buy?"
 */

get_header();

while ( have_posts() ) : the_post();
    $post_id = get_the_ID();
    $title   = get_the_title();
    $url     = get_permalink();
    $excerpt = get_the_excerpt();

    $schema = [
        '@context'  => 'https://schema.org',
        '@type'     => 'Article',
        'headline'  => $title,
        'url'       => $url,
        'publisher' => [
            '@type' => 'Organization',
            'name'  => 'Coffee Bean Index',
            'url'   => home_url(),
        ],
    ];
?>

<script type="application/ld+json"><?php echo wp_json_encode( $schema, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE ); ?></script>

<!-- Comparison Hero -->
<section class="vs-hero">
    <div class="cbi-container">
        <?php
        cbi_breadcrumb( [
            [ 'label' => 'Home',    'url' => home_url() ],
            [ 'label' => 'Reviews', 'url' => get_post_type_archive_link( 'bean' ) ?: home_url( '/beans/' ) ],
            [ 'label' => $title,    'url' => $url ],
        ] );
        ?>
        <p class="vs-hero__label">Comparison &middot; <?php echo get_the_date( 'F Y' ); ?></p>
        <h1 class="vs-hero__title"><?php the_title(); ?></h1>
        <?php if ( $excerpt ) : ?>
            <p style="font-size:var(--text-lg);color:var(--cbi-text-muted);max-width:60ch;line-height:1.6;"><?php echo esc_html( $excerpt ); ?></p>
        <?php endif; ?>
    </div>
</section>

<!-- Affiliate disclosure -->
<div class="cbi-disclosure-inline" style="border-radius:0;border-left:none;border-right:none;border-top:none;">
    <div class="cbi-container">
        This page contains affiliate links. We may earn commissions from qualifying purchases at no extra cost to you.
    </div>
</div>

<!-- Comparison Body -->
<div class="cbi-container" style="padding-top:var(--space-12);padding-bottom:var(--space-16);">
    <div style="max-width:var(--content-width);">
        <article>
            <?php the_content(); ?>
        </article>

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
