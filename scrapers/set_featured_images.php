<?php
/**
 * Set featured images on bean CPT posts from the image-cache manifest.
 *
 * Reads the manifest produced by fetch_bean_images.py and, for each bean that
 * has a cached image AND no existing featured image, sideloads the local file
 * into the Media Library and sets it as the post thumbnail. Manual uploads are
 * never overwritten. Idempotent — safe to re-run.
 *
 * Run from WordPress root on the VPS:
 *   wp eval-file /opt/scrapers/set_featured_images.php --allow-root
 *   wp eval-file /opt/scrapers/set_featured_images.php /custom/path/manifest.json --allow-root
 *
 * Beans are matched by the ACF `product_id` field first, then by post slug.
 */

if ( ! defined( 'ABSPATH' ) ) {
    WP_CLI::error( 'This script must be run via wp eval-file.' );
    exit;
}

// WordPress media-handling helpers are not loaded by default in WP-CLI context.
require_once ABSPATH . 'wp-admin/includes/file.php';
require_once ABSPATH . 'wp-admin/includes/media.php';
require_once ABSPATH . 'wp-admin/includes/image.php';

// --- Manifest path: first positional arg, else default ---
$default_manifest = '/opt/scrapers/.image-cache/manifest.json';
$manifest_path    = $default_manifest;
if ( ! empty( $args[0] ) ) {
    $manifest_path = $args[0];
}

if ( ! file_exists( $manifest_path ) ) {
    WP_CLI::error( "Manifest not found at {$manifest_path}" );
    exit;
}

$manifest = json_decode( file_get_contents( $manifest_path ), true );
if ( ! is_array( $manifest ) ) {
    WP_CLI::error( 'Failed to parse manifest JSON.' );
    exit;
}

/**
 * Find a bean post by ACF product_id, falling back to post slug.
 */
function cbi_find_bean_post( $product_id ) {
    // Match on ACF product_id meta first.
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

    // Fall back to post slug.
    $by_slug = get_page_by_path( $product_id, OBJECT, 'bean' );
    return $by_slug ?: null;
}

/**
 * Resolve a correct filename (with the real extension) for a local image file,
 * so wp_check_filetype accepts it even if Python saved everything as .jpg.
 */
function cbi_sideload_filename( $local_path ) {
    $info = @getimagesize( $local_path );
    $ext  = 'jpg';
    if ( $info && ! empty( $info['mime'] ) ) {
        $map = [
            'image/jpeg' => 'jpg',
            'image/png'  => 'png',
            'image/gif'  => 'gif',
            'image/webp' => 'webp',
        ];
        $ext = $map[ $info['mime'] ] ?? 'jpg';
    }
    $base = pathinfo( $local_path, PATHINFO_FILENAME );
    return $base . '.' . $ext;
}

$set     = 0;
$skipped = 0;
$failed  = 0;

foreach ( $manifest as $product_id => $local_path ) {

    if ( empty( $local_path ) ) {
        WP_CLI::log( "SKIP  {$product_id} — no cached image (manual upload needed)" );
        $skipped++;
        continue;
    }

    if ( ! file_exists( $local_path ) ) {
        WP_CLI::warning( "SKIP  {$product_id} — cached file missing on disk: {$local_path}" );
        $skipped++;
        continue;
    }

    $post = cbi_find_bean_post( $product_id );
    if ( ! $post ) {
        WP_CLI::warning( "SKIP  {$product_id} — no matching bean post" );
        $skipped++;
        continue;
    }

    // Never overwrite an existing featured image (protects manual uploads).
    if ( has_post_thumbnail( $post->ID ) ) {
        WP_CLI::log( "SKIP  {$product_id} — post #{$post->ID} already has a featured image" );
        $skipped++;
        continue;
    }

    // Copy the cached file to a temp path; media_handle_sideload consumes
    // (deletes) tmp_name, and we don't want it deleting the cache file.
    $filename = cbi_sideload_filename( $local_path );
    $tmp      = wp_tempnam( $filename );
    if ( ! $tmp || ! copy( $local_path, $tmp ) ) {
        WP_CLI::warning( "FAILED {$product_id} — could not stage temp file" );
        if ( $tmp && file_exists( $tmp ) ) {
            @unlink( $tmp );
        }
        $failed++;
        continue;
    }

    $file_array = [
        'name'     => $filename,
        'tmp_name' => $tmp,
    ];

    $attachment_id = media_handle_sideload( $file_array, $post->ID );

    if ( is_wp_error( $attachment_id ) ) {
        WP_CLI::warning( "FAILED {$product_id} — sideload error: " . $attachment_id->get_error_message() );
        if ( file_exists( $tmp ) ) {
            @unlink( $tmp );
        }
        $failed++;
        continue;
    }

    set_post_thumbnail( $post->ID, $attachment_id );

    // Alt text: "{Brand} {Name} coffee"
    $roasters = get_the_terms( $post->ID, 'roaster' );
    $brand    = ( $roasters && ! is_wp_error( $roasters ) ) ? $roasters[0]->name : '';
    $alt      = trim( "{$brand} {$post->post_title} coffee" );
    update_post_meta( $attachment_id, '_wp_attachment_image_alt', $alt );

    WP_CLI::success( "SET   {$product_id} → post #{$post->ID}, attachment #{$attachment_id} (alt: \"{$alt}\")" );
    $set++;
}

WP_CLI::log( '' );
WP_CLI::log( "Done — Set: {$set}  |  Skipped: {$skipped}  |  Failed: {$failed}" );
