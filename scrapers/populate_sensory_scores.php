<?php
/**
 * Push AI-generated sensory scores from data/sensory_scores.json into ACF fields.
 *
 * Run from WordPress root on the VPS:
 *   wp eval-file /opt/scrapers/scrapers/populate_sensory_scores.php --allow-root
 *
 * Reads /opt/data/sensory_scores.json (keyed by product_id) and updates five
 * ACF fields per bean post: acidity, body, sweetness, bitterness, roast_intensity.
 * Safe to re-run — overwrites fields each time.
 */

$scores_file = '/opt/data/sensory_scores.json';

if ( ! file_exists( $scores_file ) ) {
    WP_CLI::error( "Scores file not found: {$scores_file}" );
    exit;
}

$json = file_get_contents( $scores_file );
$scores = json_decode( $json, true );

if ( ! $scores ) {
    WP_CLI::error( "Could not parse JSON from {$scores_file}" );
    exit;
}

$updated   = 0;
$not_found = [];

foreach ( $scores as $product_id => $entry ) {
    $post = get_page_by_path( $product_id, OBJECT, 'bean' );
    if ( ! $post ) {
        $not_found[] = $product_id;
        continue;
    }

    $s = $entry['scores'];
    update_field( 'acidity',         intval( $s['acidity'] ),         $post->ID );
    update_field( 'body',            intval( $s['body'] ),            $post->ID );
    update_field( 'sweetness',       intval( $s['sweetness'] ),       $post->ID );
    update_field( 'bitterness',      intval( $s['bitterness'] ),      $post->ID );
    update_field( 'roast_intensity', intval( $s['roast_intensity'] ), $post->ID );

    $conf = $entry['confidence'];
    WP_CLI::success( "Updated {$product_id} (#{$post->ID}) — a:{$s['acidity']} b:{$s['body']} sw:{$s['sweetness']} bi:{$s['bitterness']} ri:{$s['roast_intensity']} [{$conf}]" );
    $updated++;
}

WP_CLI::log( '' );
WP_CLI::log( "Done. Updated: {$updated}  Not found: " . count( $not_found ) );

if ( $not_found ) {
    WP_CLI::warning( 'Bean posts not found for these IDs:' );
    foreach ( $not_found as $id ) {
        WP_CLI::log( "  - {$id}" );
    }
}
