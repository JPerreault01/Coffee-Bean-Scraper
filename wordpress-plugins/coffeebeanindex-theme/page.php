<?php
/**
 * Template: Generic Page
 * File: page.php
 *
 * Editorial default for untemplated WordPress pages (About, Contact,
 * Affiliate Disclosure, Privacy Policy, etc.).
 * Uses the .page-editorial wrapper which gives a clean centered column.
 */

get_header(); ?>

<?php while ( have_posts() ) : the_post(); ?>

<div class="page-editorial">
    <header class="page-editorial__header">
        <h1 class="page-editorial__title"><?php the_title(); ?></h1>
        <?php if ( get_the_excerpt() ) : ?>
            <p class="page-editorial__subtitle"><?php echo esc_html( get_the_excerpt() ); ?></p>
        <?php endif; ?>
    </header>

    <div class="page-editorial__body">
        <?php the_content(); ?>
    </div>
</div>

<?php endwhile; ?>

<?php get_footer(); ?>
