<?php
/**
 * Template: Taxonomy Archive
 * File: taxonomy-bean-archive.php
 *
 * Used for: flavor-note, origin, roast-level, process-method, brew-method, roaster
 * Registered via template_include filter in functions.php
 *
 * Shows: archive hero with taxonomy description + bean grid
 */

get_header();

$term        = get_queried_object();
$taxonomy    = $term ? $term->taxonomy : '';
$term_name   = $term ? $term->name : '';
$description = $term ? $term->description : '';

// Eyebrow label per taxonomy
$eyebrow_map = [
    'flavor-note'    => 'Flavor Note',
    'origin'         => 'Origin',
    'roast-level'    => 'Roast Level',
    'process-method' => 'Process Method',
    'brew-method'    => 'Best For',
    'roaster'        => 'Roaster',
];
$eyebrow = isset( $eyebrow_map[ $taxonomy ] ) ? $eyebrow_map[ $taxonomy ] : 'Category';

// Count
$bean_count = $term ? $term->count : 0;
?>

<!-- Archive Hero -->
<section class="archive-hero">
    <div class="cbi-container">
        <div class="archive-hero__eyebrow"><?php echo esc_html( $eyebrow ); ?></div>
        <h1 class="archive-hero__title"><?php echo esc_html( $term_name ); ?></h1>
        <?php if ( $description ) : ?>
            <p class="archive-hero__desc"><?php echo esc_html( $description ); ?></p>
        <?php endif; ?>
        <p style="font-size:0.8rem;color:var(--cbi-text-dim);font-family:var(--font-mono);margin-top:16px;">
            <?php echo esc_html( $bean_count ); ?> bean<?php echo $bean_count !== 1 ? 's' : ''; ?>
        </p>
    </div>
</section>

<!-- Bean Grid -->
<div class="cbi-container">
    <div class="bean-grid">
        <?php if ( have_posts() ) :
            while ( have_posts() ) : the_post();
                echo cbi_bean_card( get_the_ID() );
            endwhile;
        else : ?>
            <p style="color:var(--cbi-text-dim);grid-column:1/-1;">No beans found yet — check back soon.</p>
        <?php endif; ?>
    </div>

    <!-- Pagination -->
    <div style="padding:32px 0;text-align:center;">
        <?php the_posts_pagination( [
            'mid_size'  => 2,
            'prev_text' => '← Newer',
            'next_text' => 'Older →',
        ] ); ?>
    </div>
</div>

<?php get_footer(); ?>
