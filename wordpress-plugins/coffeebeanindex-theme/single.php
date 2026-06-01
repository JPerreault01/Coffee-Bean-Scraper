<?php
/**
 * Template: Generic Post (blog/news)
 * File: single.php
 *
 * Editorial default for standard WordPress posts (news, updates, etc.).
 * Bean CPT uses single-bean.php — this file only fires for post_type=post.
 */

get_header(); ?>

<?php while ( have_posts() ) : the_post(); ?>

<article class="post-editorial" <?php post_class(); ?>>

    <header class="post-editorial__header">
        <?php
        $cats = get_the_category();
        if ( $cats ) : ?>
            <div class="post-editorial__category">
                <a href="<?php echo esc_url( get_category_link( $cats[0]->term_id ) ); ?>"><?php echo esc_html( $cats[0]->name ); ?></a>
            </div>
        <?php endif; ?>

        <h1 class="post-editorial__title"><?php the_title(); ?></h1>

        <div class="post-editorial__meta">
            <?php echo get_the_date( 'F j, Y' ); ?>
            <?php
            $author_id = get_the_author_meta( 'ID' );
            if ( $author_id ) {
                echo ' &middot; ' . esc_html( get_the_author() );
            }
            ?>
        </div>
    </header>

    <div class="post-editorial__body">
        <?php the_content(); ?>

        <?php
        wp_link_pages( [
            'before' => '<div class="post-pages" style="margin-top:var(--space-8);font-family:var(--font-mono);font-size:var(--text-sm);">Pages: ',
            'after'  => '</div>',
        ] );
        ?>
    </div>

    <!-- Post tags -->
    <?php if ( has_tag() ) : ?>
    <footer style="margin-top:var(--space-8);padding-top:var(--space-6);border-top:1px solid var(--cbi-border);">
        <span style="font-size:var(--text-xs);font-family:var(--font-mono);text-transform:uppercase;letter-spacing:0.1em;color:var(--cbi-text-dim);margin-right:var(--space-2);">Tags:</span>
        <?php the_tags( '', ' ', '' ); ?>
    </footer>
    <?php endif; ?>

</article>

<!-- Adjacent post navigation -->
<div style="max-width:var(--content-width);margin:0 auto;padding:0 var(--space-6) var(--space-12);">
    <?php the_post_navigation( [
        'prev_text' => '&larr; %title',
        'next_text' => '%title &rarr;',
    ] ); ?>
</div>

<?php endwhile; ?>

<?php get_footer(); ?>
