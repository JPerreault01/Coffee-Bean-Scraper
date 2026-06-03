<?php
/**
 * Phase 1 Seed Script — Origin, Brew Method, Roast Level, Process Method guides
 *
 * Run via WP-CLI:
 *   sudo -u www-data wp --path=/var/www/coffeebeans eval-file /path/to/seeds/seed-phase1-terms.php
 *
 * Idempotent: matches on slug, updates description if the term already exists.
 */

// ── Helper: create or update a taxonomy term with description + SEO meta ──────
function cbi_seed_taxonomy_term( array $data ) {
    $taxonomy    = $data['taxonomy'];
    $slug        = $data['slug'];
    $name        = $data['name'];
    $description = $data['description'] ?? '';
    $parent_id   = 0;

    $existing = get_term_by( 'slug', $slug, $taxonomy );

    if ( $existing && ! is_wp_error( $existing ) ) {
        $result = wp_update_term( $existing->term_id, $taxonomy, [
            'name'        => $name,
            'description' => $description,
        ] );
        if ( is_wp_error( $result ) ) {
            WP_CLI::warning( "Could not update term '$slug' in $taxonomy: " . $result->get_error_message() );
            return null;
        }
        $term_id = $existing->term_id;
        WP_CLI::log( "Updated $taxonomy term: $slug (ID $term_id)" );
    } else {
        $result = wp_insert_term( $name, $taxonomy, [
            'slug'        => $slug,
            'description' => $description,
        ] );
        if ( is_wp_error( $result ) ) {
            WP_CLI::warning( "Could not insert term '$slug' in $taxonomy: " . $result->get_error_message() );
            return null;
        }
        $term_id = $result['term_id'];
        WP_CLI::log( "Created $taxonomy term: $slug (ID $term_id)" );
    }

    // RankMath term SEO meta
    if ( ! empty( $data['seo_title'] ) ) {
        update_term_meta( $term_id, 'rank_math_title', $data['seo_title'] );
    }
    if ( ! empty( $data['seo_description'] ) ) {
        update_term_meta( $term_id, 'rank_math_description', $data['seo_description'] );
    }
    if ( ! empty( $data['focus_keyword'] ) ) {
        update_term_meta( $term_id, 'rank_math_focus_keyword', $data['focus_keyword'] );
    }

    return $term_id;
}

// ── Run seeds ──────────────────────────────────────────────────────────────────

$data_dir = __DIR__ . '/data';

// Origin guides
WP_CLI::log( "\n=== Phase 1a: Origin terms ===" );
$origin_terms = include $data_dir . '/origin-terms.php';
foreach ( $origin_terms as $term_data ) {
    cbi_seed_taxonomy_term( $term_data );
}

// Brew method guides
WP_CLI::log( "\n=== Phase 1b: Brew method terms ===" );
$brew_terms = include $data_dir . '/brew-method-terms.php';
foreach ( $brew_terms as $term_data ) {
    cbi_seed_taxonomy_term( $term_data );
}

// Roast level guides
WP_CLI::log( "\n=== Phase 1c: Roast level terms ===" );
$roast_terms = include $data_dir . '/roast-level-terms.php';
foreach ( $roast_terms as $term_data ) {
    cbi_seed_taxonomy_term( $term_data );
}

// Process method guides
WP_CLI::log( "\n=== Phase 1d: Process method terms ===" );
$process_terms = include $data_dir . '/process-method-terms.php';
foreach ( $process_terms as $term_data ) {
    cbi_seed_taxonomy_term( $term_data );
}

WP_CLI::success( "\nPhase 1 complete. Verify at /origin/ethiopia/, /brew/espresso/, /roast/dark/, /process/washed/" );
