<?php
/**
 * Phase 2 Seed Script — Flavor family and note taxonomy terms
 *
 * Run via WP-CLI:
 *   sudo -u www-data wp --path=/var/www/coffeebeans eval-file /path/to/seeds/seed-phase2-flavors.php
 *
 * Idempotent: matches on slug, updates if exists.
 * Creates parent family terms first, then child note terms with parent_id set.
 */

function cbi_seed_flavor_term( array $data, array &$slug_to_id ) {
    $taxonomy    = 'flavor-note';
    $slug        = $data['slug'];
    $name        = $data['name'];
    $description = $data['description'] ?? '';
    $parent_id   = 0;

    if ( ! empty( $data['parent_slug'] ) ) {
        $parent_id = $slug_to_id[ $data['parent_slug'] ] ?? 0;
        if ( ! $parent_id ) {
            WP_CLI::warning( "Parent term '{$data['parent_slug']}' not found for '$slug' — inserting without parent." );
        }
    }

    $existing = get_term_by( 'slug', $slug, $taxonomy );

    if ( $existing && ! is_wp_error( $existing ) ) {
        $result = wp_update_term( $existing->term_id, $taxonomy, [
            'name'        => $name,
            'description' => $description,
            'parent'      => $parent_id,
        ] );
        if ( is_wp_error( $result ) ) {
            WP_CLI::warning( "Could not update flavor term '$slug': " . $result->get_error_message() );
            return null;
        }
        $term_id = $existing->term_id;
        WP_CLI::log( "Updated flavor-note term: $slug (ID $term_id)" );
    } else {
        $result = wp_insert_term( $name, $taxonomy, [
            'slug'        => $slug,
            'description' => $description,
            'parent'      => $parent_id,
        ] );
        if ( is_wp_error( $result ) ) {
            WP_CLI::warning( "Could not insert flavor term '$slug': " . $result->get_error_message() );
            return null;
        }
        $term_id = $result['term_id'];
        WP_CLI::log( "Created flavor-note term: $slug (ID $term_id)" );
    }

    // RankMath SEO meta (families only — individual notes are stubs)
    if ( empty( $data['parent_slug'] ) ) {
        if ( ! empty( $data['seo_title'] ) ) {
            update_term_meta( $term_id, 'rank_math_title', $data['seo_title'] );
        }
        if ( ! empty( $data['seo_description'] ) ) {
            update_term_meta( $term_id, 'rank_math_description', $data['seo_description'] );
        }
        if ( ! empty( $data['focus_keyword'] ) ) {
            update_term_meta( $term_id, 'rank_math_focus_keyword', $data['focus_keyword'] );
        }
    }

    $slug_to_id[ $slug ] = $term_id;
    return $term_id;
}

WP_CLI::log( "\n=== Phase 2: Flavor note terms ===" );

$data_dir   = __DIR__ . '/data';
$flavor_data = include $data_dir . '/flavor-note-terms.php';
$slug_to_id  = [];

// Two passes: families first (parent_slug === null), then notes
$families = array_filter( $flavor_data, fn( $t ) => empty( $t['parent_slug'] ) );
$notes    = array_filter( $flavor_data, fn( $t ) => ! empty( $t['parent_slug'] ) );

WP_CLI::log( "Creating flavor family terms..." );
foreach ( $families as $term_data ) {
    cbi_seed_flavor_term( $term_data, $slug_to_id );
}

WP_CLI::log( "Creating individual flavor note terms..." );
foreach ( $notes as $term_data ) {
    cbi_seed_flavor_term( $term_data, $slug_to_id );
}

WP_CLI::success( "\nPhase 2 complete. Verify at /flavor/chocolate/, /flavor/fruit/, /flavor/earthy-smoky/" );
