<?php
/**
 * Template Name: Origin / Brew Guide
 * Template Post Type: page
 *
 * File: template-guide.php
 *
 * Long-form editorial template for origin guides, brew method explainers,
 * and other informational content. Protects the 40%+ informational ratio
 * required by Google's affiliate content guidelines.
 *
 * Layout: full-width hero → two-column (article + sidebar)
 * Sidebar: auto-generated table of contents + related beans from the DB.
 *
 * AUTHORING GUIDE:
 * Use the standard WordPress editor. Structure headings (H2 for main sections,
 * H3 for subsections) — the JS TOC builder picks up H2s automatically.
 * For "related beans" in the sidebar, the template auto-queries beans tagged
 * with a matching origin or brew-method term whose slug matches a custom field
 * you set on the page: "related_taxonomy_slug" (text field, free ACF).
 * If no ACF field is set, it falls back to the most-recently reviewed beans.
 */

get_header();

while ( have_posts() ) : the_post();
    $post_id    = get_the_ID();
    $title      = get_the_title();
    $url        = get_permalink();
    $excerpt    = get_the_excerpt();
    $categories = get_the_category();
    $category   = $categories ? $categories[0]->name : 'Guide';

    // Schema — Article
    $schema = [
        '@context'         => 'https://schema.org',
        '@type'            => 'Article',
        'headline'         => $title,
        'url'              => $url,
        'datePublished'    => get_the_date( 'c' ),
        'dateModified'     => get_the_modified_date( 'c' ),
        'description'      => $excerpt ?: '',
        'publisher'        => [
            '@type' => 'Organization',
            'name'  => 'Coffee Bean Index',
            'url'   => home_url(),
        ],
        'author'           => [
            '@type' => 'Organization',
            'name'  => 'Coffee Bean Index',
        ],
    ];

    if ( has_post_thumbnail() ) {
        $schema['image'] = get_the_post_thumbnail_url( $post_id, 'large' );
    }
?>

<script type="application/ld+json"><?php echo wp_json_encode( $schema, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE ); ?></script>

<!-- Guide Hero -->
<section class="guide-hero">
    <div class="cbi-container">
        <?php
        cbi_breadcrumb( [
            [ 'label' => 'Home',          'url' => home_url() ],
            [ 'label' => 'Guides',        'url' => home_url( '/guides/' ) ],
            [ 'label' => $title,          'url' => $url ],
        ] );
        ?>
        <p class="guide-hero__category"><?php echo esc_html( $category ); ?></p>
        <h1 class="guide-hero__title"><?php the_title(); ?></h1>
        <?php if ( $excerpt ) : ?>
            <p class="guide-hero__intro"><?php echo esc_html( $excerpt ); ?></p>
        <?php endif; ?>
        <div class="guide-meta">
            <span>Updated <?php echo get_the_modified_date( 'F j, Y' ); ?></span>
            <span>&middot;</span>
            <span><?php echo esc_html( ceil( str_word_count( strip_tags( get_the_content() ) ) / 200 ) ); ?> min read</span>
        </div>
    </div>
</section>

<!-- Body: article + sidebar -->
<div class="cbi-container">
    <div class="guide-layout">

        <!-- Main article -->
        <article class="guide-body">
            <!-- TOC placeholder — filled by JS below based on H2s -->
            <nav class="guide-toc" id="guide-toc" aria-label="Table of contents" style="display:none;">
                <div class="guide-toc__title">In this guide</div>
                <ol class="guide-toc__list" id="guide-toc-list"></ol>
            </nav>

            <?php the_content(); ?>

            <!-- Post nav -->
            <div style="margin-top:var(--space-12);padding-top:var(--space-8);border-top:1px solid var(--cbi-border);">
                <?php the_post_navigation( [
                    'prev_text' => '&larr; %title',
                    'next_text' => '%title &rarr;',
                ] ); ?>
            </div>
        </article>

        <!-- Sidebar -->
        <aside class="guide-sidebar">

            <!-- Related Beans -->
            <?php
            $related_tax_slug = '';
            if ( function_exists( 'get_field' ) ) {
                $related_tax_slug = get_field( 'related_taxonomy_slug', $post_id );
            }

            // Try to find beans from a matching taxonomy term
            $related_query_args = [
                'post_type'      => 'bean',
                'posts_per_page' => 4,
                'post_status'    => 'publish',
                'orderby'        => 'meta_value_num',
                'meta_key'       => 'rating',
                'order'          => 'DESC',
                'no_found_rows'  => true,
            ];

            if ( $related_tax_slug ) {
                // Try origin first, then brew-method
                foreach ( [ 'origin', 'brew-method', 'flavor-note' ] as $try_tax ) {
                    $related_term = get_term_by( 'slug', $related_tax_slug, $try_tax );
                    if ( $related_term && ! is_wp_error( $related_term ) ) {
                        $related_query_args['tax_query'] = [
                            [
                                'taxonomy' => $try_tax,
                                'field'    => 'slug',
                                'terms'    => $related_tax_slug,
                            ]
                        ];
                        break;
                    }
                }
            }

            $related = new WP_Query( $related_query_args );
            if ( $related->have_posts() ) : ?>
                <div class="guide-sidebar__section">
                    <div class="guide-sidebar__heading">Related Beans</div>
                    <?php while ( $related->have_posts() ) : $related->the_post();
                        $sid      = get_the_ID();
                        $srating  = function_exists( 'get_field' ) ? get_field( 'rating', $sid ) : '';
                        $sroaster = get_the_terms( $sid, 'roaster' );
                        $sroaster = ( $sroaster && ! is_wp_error( $sroaster ) ) ? $sroaster[0]->name : '';
                    ?>
                        <a href="<?php the_permalink(); ?>" class="similar-bean-card" style="display:flex;">
                            <div>
                                <span class="similar-bean-card__name"><?php the_title(); ?></span>
                                <?php if ( $sroaster ) : ?>
                                    <span class="similar-bean-card__meta"><?php echo esc_html( $sroaster ); ?></span>
                                <?php endif; ?>
                            </div>
                            <?php if ( $srating !== '' && $srating !== null ) : ?>
                                <span class="similar-bean-card__score"><?php echo esc_html( $srating ); ?>/10</span>
                            <?php endif; ?>
                        </a>
                    <?php endwhile;
                    wp_reset_postdata(); ?>
                    <a href="<?php echo esc_url( get_post_type_archive_link( 'bean' ) ?: home_url( '/beans/' ) ); ?>" style="font-size:var(--text-xs);font-family:var(--font-mono);color:var(--cbi-accent);text-transform:uppercase;letter-spacing:0.08em;display:block;margin-top:var(--space-3);">All beans &rarr;</a>
                </div>
            <?php endif; ?>

            <!-- Quick navigation within guide -->
            <div class="guide-sidebar__section" id="guide-sidebar-toc" style="display:none;">
                <div class="guide-sidebar__heading">Jump to</div>
                <ol id="guide-sidebar-toc-list" style="list-style:none;padding:0;margin:0;font-size:var(--text-sm);"></ol>
            </div>

        </aside>
    </div>
</div>

<!-- Build TOC from H2s -->
<script>
(function() {
    var headings = document.querySelectorAll('.guide-body h2');
    if ( headings.length < 2 ) return;

    var tocEl        = document.getElementById('guide-toc');
    var tocList      = document.getElementById('guide-toc-list');
    var sidebarToc   = document.getElementById('guide-sidebar-toc');
    var sidebarList  = document.getElementById('guide-sidebar-toc-list');

    headings.forEach( function( h, i ) {
        var id = 'guide-section-' + i;
        h.setAttribute('id', id);

        var text = h.textContent;

        var li = document.createElement('li');
        var a  = document.createElement('a');
        a.href        = '#' + id;
        a.textContent = text;
        li.appendChild(a);
        tocList.appendChild(li);

        var li2 = document.createElement('li');
        li2.style.cssText = 'padding:0.25rem 0;border-bottom:1px solid var(--cbi-border);font-size:var(--text-sm);';
        var a2  = document.createElement('a');
        a2.href        = '#' + id;
        a2.textContent = text;
        a2.style.color = 'var(--cbi-text)';
        li2.appendChild(a2);
        sidebarList.appendChild(li2);
    });

    if ( tocEl )     tocEl.style.display     = '';
    if ( sidebarToc ) sidebarToc.style.display = '';
})();
</script>

<?php endwhile; ?>

<?php get_footer(); ?>
