<?php
/**
 * Populate amazon_asin + amazon_affiliate_url ACF fields on EXISTING bean posts
 * from products.json.
 *
 * create_beans.php skips any bean whose slug already exists, so it never updates
 * the ASIN on a bean that was created before the ASIN was known. This script
 * fills that gap: for every product in products.json that has an amazon_asin, it
 * finds the matching bean post and updates the two affiliate ACF fields.
 * Idempotent and safe to re-run. Only beans with an ASIN are touched.
 *
 * Affiliate URL format: https://www.amazon.com/dp/{ASIN}?tag={affiliate_tag}
 *
 * Run from WordPress root on the VPS:
 *   wp eval-file /opt/scrapers/scrapers/update_bean_asins.php --allow-root
 *   wp eval-file /opt/scrapers/scrapers/update_bean_asins.php /custom/products.json --allow-root
 *
 * Beans are matched by ACF product_id first, then by post slug.
 */

if ( ! defined( 'ABSPATH' ) ) {
    WP_CLI::error( 'This script must be run via wp eval-file.' );
    exit;
}

$default_products = '/opt/scrapers/scrapers/products.json';
$products_path    = ! empty( $args[0] ) ? $args[0] : $default_products;

if ( ! file_exists( $products_path ) ) {
    WP_CLI::error( "products.json not found at {$products_path}" );
    exit;
}

$products = json_decode( file_get_contents( $products_path ), true );
if ( ! is_array( $products ) ) {
    WP_CLI::error( 'Failed to parse products.json.' );
    exit;
}

/**
 * Find a bean post by ACF product_id, falling back to post slug.
 * Mirrors the matching logic in set_featured_images.php.
 */
function cbi_find_bean_post( $product_id ) {
    $q = new WP_Query( [
        'post_type'      => 'bean',
        'post_status'    => 'any',
        'posts_per_page' => 1,
        'no_found_rows'  => true,
        'meta_query'     => [
            [
                'key'   => 'product_id',
                'value' => $product_id,
            ],
        ],
    ] );
    if ( $q->have_posts() ) {
        return $q->posts[0];
    }
    $by_slug = get_page_by_path( $product_id, OBJECT, 'bean' );
    return $by_slug ?: null;
}

$updated = 0;
$skipped = 0;
$missing = 0;

foreach ( $products as $p ) {
    $id   = $p['id'] ?? '';
    $asin = $p['amazon_asin'] ?? '';

    if ( ! $id || empty( $asin ) ) {
        continue; // No ASIN to write for this bean.
    }

    $post = cbi_find_bean_post( $id );
    if ( ! $post ) {
        WP_CLI::warning( "SKIP  {$id} — no matching bean post" );
        $missing++;
        continue;
    }

    update_field( 'amazon_asin', $asin, $post->ID );

    $tag = $p['affiliate_tag'] ?? '';
    if ( $tag ) {
        $url = "https://www.amazon.com/dp/{$asin}?tag={$tag}";
        update_field( 'amazon_affiliate_url', $url, $post->ID );
        WP_CLI::success( "SET   {$id} → post #{$post->ID}  ASIN {$asin}  ({$url})" );
    } else {
        WP_CLI::success( "SET   {$id} → post #{$post->ID}  ASIN {$asin}  (no affiliate_tag — URL left unchanged)" );
    }
    $updated++;
}

WP_CLI::log( '' );
WP_CLI::log( "Done — Updated: {$updated}  |  No ASIN (skipped): {$skipped}  |  Missing post: {$missing}" );
