<?php
/**
 * Phase 6 Seed Script — Roundup Posts
 *
 * Run via WP-CLI:
 *   sudo -u www-data wp --path=/var/www/coffeebeans eval-file /path/to/seeds/seed-phase6-roundups.php
 *
 * Idempotent: matches on post_name (slug), updates if exists.
 * Posts are created as DRAFT. Publish manually once all referenced bean pages are live.
 *
 * Required before publishing:
 *   best-espresso-beans-under-20  → lavazza, illy, cafe-don-pablo, cafe-bustelo, kicking-horse bean pages
 *   best-dark-roast-coffee-beans  → peets, camano-island, kicking-horse, death-wish, community-coffee, cafe-bustelo
 *
 * To publish when ready:
 *   wp post update $(wp post list --name=best-espresso-beans-under-20 --field=ID --path=/var/www/coffeebeans) \
 *       --post_status=publish --path=/var/www/coffeebeans
 */

function cbi_seed_roundup( array $args ) {
    $slug   = $args['post_name'];
    $exists = get_posts( [
        'name'        => $slug,
        'post_type'   => 'post',
        'post_status' => [ 'any' ],
        'numberposts' => 1,
    ] );

    $post_data = [
        'post_title'   => $args['post_title'],
        'post_name'    => $slug,
        'post_content' => $args['post_content'] ?? '',
        'post_status'  => $args['post_status'] ?? 'draft',
        'post_type'    => 'post',
        'post_author'  => 1,
    ];

    if ( ! empty( $exists ) ) {
        $post_data['ID'] = $exists[0]->ID;
        $post_id = wp_update_post( $post_data, true );
        if ( is_wp_error( $post_id ) ) {
            WP_CLI::warning( "Could not update roundup '$slug': " . $post_id->get_error_message() );
            return null;
        }
        WP_CLI::log( "Updated roundup: $slug (ID $post_id)" );
    } else {
        $post_id = wp_insert_post( $post_data, true );
        if ( is_wp_error( $post_id ) ) {
            WP_CLI::warning( "Could not create roundup '$slug': " . $post_id->get_error_message() );
            return null;
        }
        WP_CLI::log( "Created roundup: $slug (ID $post_id)" );
    }

    // RankMath SEO meta
    if ( ! empty( $args['seo_title'] ) ) {
        update_post_meta( $post_id, 'rank_math_title', $args['seo_title'] );
    }
    if ( ! empty( $args['seo_description'] ) ) {
        update_post_meta( $post_id, 'rank_math_description', $args['seo_description'] );
    }
    if ( ! empty( $args['focus_keyword'] ) ) {
        update_post_meta( $post_id, 'rank_math_focus_keyword', $args['focus_keyword'] );
    }
    // Page template
    update_post_meta( $post_id, '_wp_page_template', 'template-roundup.php' );

    // Ensure 'roundups' category exists and assign
    $cat = get_term_by( 'slug', 'roundups', 'category' );
    if ( ! $cat ) {
        $cat_result = wp_insert_term( 'Roundups', 'category', [ 'slug' => 'roundups' ] );
        $cat_id     = is_wp_error( $cat_result ) ? 1 : $cat_result['term_id'];
    } else {
        $cat_id = $cat->term_id;
    }
    wp_set_post_categories( $post_id, [ $cat_id ] );

    return $post_id;
}

WP_CLI::log( "\n=== Phase 6: Roundup Posts ===" );

$data_dir = __DIR__ . '/data';
$roundups = include $data_dir . '/roundups.php';

foreach ( $roundups as $roundup ) {
    cbi_seed_roundup( $roundup );
}

WP_CLI::success( "\nPhase 6 complete. Both roundups created as DRAFT." );
WP_CLI::log( "Check WP Admin → Posts to confirm drafts. Publish manually when all referenced bean pages are live." );
WP_CLI::log( "" );
WP_CLI::log( "To publish espresso roundup when ready:" );
WP_CLI::log( '  wp post update $(wp post list --name=best-espresso-beans-under-20 --field=ID --path=/var/www/coffeebeans) --post_status=publish --path=/var/www/coffeebeans' );
WP_CLI::log( "" );
WP_CLI::log( "To publish dark roast roundup when ready:" );
WP_CLI::log( '  wp post update $(wp post list --name=best-dark-roast-coffee-beans --field=ID --path=/var/www/coffeebeans) --post_status=publish --path=/var/www/coffeebeans' );
