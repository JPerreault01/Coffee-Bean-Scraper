<?php
/**
 * Bulk-create bean CPT posts from products.json
 *
 * Run from WordPress root on the VPS:
 *   wp eval-file /opt/scrapers/create_beans.php --allow-root
 *
 * - Skips lavazza-super-crema (already created)
 * - Skips any bean whose slug already exists (safe to re-run)
 * - Sets all ACF fields, taxonomy terms, and affiliate URLs
 * - Posts created as 'draft' — publish manually after adding review copy
 */

$products_file = '/opt/scrapers/products.json';

if ( ! file_exists( $products_file ) ) {
    WP_CLI::error( "products.json not found at {$products_file}" );
    exit;
}

$products = json_decode( file_get_contents( $products_file ), true );
if ( ! $products ) {
    WP_CLI::error( 'Failed to parse products.json — check file is valid JSON.' );
    exit;
}

// Already created — skip these
$skip_ids = [ 'lavazza-super-crema' ];

$created = 0;
$skipped = 0;
$failed  = 0;

foreach ( $products as $p ) {
    $id = $p['id'];

    if ( in_array( $id, $skip_ids, true ) ) {
        WP_CLI::log( "SKIP  {$id} (already created)" );
        $skipped++;
        continue;
    }

    // Check if slug already exists as a bean post
    $existing = get_page_by_path( $id, OBJECT, 'bean' );
    if ( $existing ) {
        WP_CLI::log( "SKIP  {$id} — already exists as post #{$existing->ID}" );
        $skipped++;
        continue;
    }

    // --- Create the post ---
    $post_id = wp_insert_post( [
        'post_type'   => 'bean',
        'post_title'  => $p['name'],
        'post_name'   => $id,
        'post_status' => 'draft',
    ], true );

    if ( is_wp_error( $post_id ) ) {
        WP_CLI::warning( "FAILED {$id} — " . $post_id->get_error_message() );
        $failed++;
        continue;
    }

    // --- Taxonomies ---

    // roaster  (brand name)
    wp_set_object_terms( $post_id, sanitize_title( $p['brand'] ), 'roaster' );

    // roast-level
    wp_set_object_terms( $post_id, sanitize_title( $p['roast_level'] ), 'roast-level' );

    // origin
    wp_set_object_terms( $post_id, sanitize_title( $p['origin'] ), 'origin' );

    // process-method
    wp_set_object_terms( $post_id, sanitize_title( $p['process_method'] ), 'process-method' );

    // brew-method  (array)
    $brew_slugs = array_map( 'sanitize_title', $p['best_brew_methods'] ?? [] );
    wp_set_object_terms( $post_id, $brew_slugs, 'brew-method' );

    // flavor-note  (array)
    $flavor_slugs = array_map( 'sanitize_title', $p['flavor_notes'] ?? [] );
    wp_set_object_terms( $post_id, $flavor_slugs, 'flavor-note' );

    // --- ACF fields ---

    // Sensory scores
    update_field( 'acidity',        $p['acidity'],        $post_id );
    update_field( 'body',           $p['body'],           $post_id );
    update_field( 'sweetness',      $p['sweetness'],      $post_id );
    update_field( 'bitterness',     $p['bitterness'],     $post_id );
    update_field( 'roast_intensity',$p['roast_intensity'],$post_id );

    // Specs
    update_field( 'weight_oz',  $p['weight_oz'], $post_id );
    update_field( 'product_id', $id,             $post_id );

    if ( ! empty( $p['amazon_asin'] ) ) {
        update_field( 'amazon_asin', $p['amazon_asin'], $post_id );
    }

    if ( ! empty( $p['roaster_url'] ) ) {
        update_field( 'roaster_url', $p['roaster_url'], $post_id );
    }

    // Build affiliate URL: Amazon affiliate takes priority, else roaster URL
    $asin = $p['amazon_asin'] ?? '';
    $tag  = $p['affiliate_tag'] ?? '';

    if ( $asin && $tag ) {
        update_field( 'amazon_affiliate_url', "https://www.amazon.com/dp/{$asin}?tag={$tag}", $post_id );
    } elseif ( ! empty( $p['roaster_url'] ) ) {
        update_field( 'amazon_affiliate_url', $p['roaster_url'], $post_id );
    }

    WP_CLI::success( "CREATED {$id} → post #{$post_id}" );
    $created++;
}

WP_CLI::log( "" );
WP_CLI::log( "Done — Created: {$created}  |  Skipped: {$skipped}  |  Failed: {$failed}" );
