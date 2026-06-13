<?php
/**
 * Re-parent the flat 'origin' taxonomy into a continent → country hierarchy.
 *
 * Run from WordPress root on the VPS:
 *   wp eval-file /opt/scrapers/scrapers/set_origin_continents.php --allow-root
 *
 * What it does:
 *   1. Ensures the six continent parent terms exist (creates if absent).
 *   2. Re-parents every known country/region term under its continent.
 *   3. Forces structural/cross-region markers (blend, latin-america,
 *      multi-origin-blend) to stay at the TOP level (parent 0).
 *
 * Safe to re-run (idempotent): terms are looked up before creating, and a
 * parent is only updated when it differs from the target. Nothing touches
 * post → term assignments, post content, or any other taxonomy.
 *
 * NOTE: 'south-america' is BOTH a continent parent slug and a region term
 * used by blends. It resolves to a single top-level continent term; the
 * country loop detects the self-map and leaves it at parent 0.
 */

if ( ! defined( 'ABSPATH' ) ) {
    fwrite( STDERR, "This script must be run via: wp eval-file ... --allow-root\n" );
    exit( 1 );
}

$taxonomy = 'origin';

// ---------------------------------------------------------------------------
// Continent parents (slug => display name)
// keep in sync with create_beans.php
// ---------------------------------------------------------------------------
$continent_parents = [
    'africa'        => 'Africa',
    'asia'          => 'Asia',
    'north-america' => 'North America',
    'south-america' => 'South America',
    'oceania'       => 'Oceania',
    'europe'        => 'Europe',
];

// ---------------------------------------------------------------------------
// Country/region slug => continent slug
// keep in sync with create_beans.php
// (no countries map to oceania/europe yet — parents created for future use)
// ---------------------------------------------------------------------------
$country_to_continent = [
    // Africa
    'ethiopia'           => 'africa',
    'kenya'              => 'africa',
    'burundi'            => 'africa',
    'tanzania'           => 'africa',
    'rwanda'             => 'africa',
    'uganda'             => 'africa',
    // Asia
    'sumatra'            => 'asia',
    'indonesia'          => 'asia',
    'india'              => 'asia',
    'papua-new-guinea'   => 'asia',
    'vietnam'            => 'asia',
    'timor'              => 'asia',
    // North America
    'mexico'             => 'north-america',
    'guatemala'          => 'north-america',
    'costa-rica'         => 'north-america',
    'honduras'           => 'north-america',
    'nicaragua'          => 'north-america',
    'el-salvador'        => 'north-america',
    'panama'             => 'north-america',
    'hawaii'             => 'north-america',
    'jamaica'            => 'north-america',
    'dominican-republic' => 'north-america',
    'central-america'    => 'north-america',
    'united-states'      => 'north-america',
    // South America
    'colombia'           => 'south-america',
    'brazil'             => 'south-america',
    'peru'               => 'south-america',
    'bolivia'            => 'south-america',
    'ecuador'            => 'south-america',
    'south-america'      => 'south-america', // region term IS the continent
];

// ---------------------------------------------------------------------------
// Structural / cross-region markers that must stay TOP-LEVEL (parent 0).
// 'latin-america' spans two continents, so it stays as a cross-region marker.
// keep in sync with create_beans.php
// ---------------------------------------------------------------------------
$structural_top_level = [ 'blend', 'latin-america', 'multi-origin-blend' ];

// ===========================================================================
// 1. Ensure continent parents exist and sit at the top level
// ===========================================================================
$parent_ids       = [];
$parents_created  = [];
$parents_verified = [];

foreach ( $continent_parents as $slug => $name ) {
    $term = get_term_by( 'slug', $slug, $taxonomy );
    if ( $term && ! is_wp_error( $term ) ) {
        // Continent must be top-level — correct it if something nested it.
        if ( (int) $term->parent !== 0 ) {
            wp_update_term( $term->term_id, $taxonomy, [ 'parent' => 0 ] );
        }
        $parent_ids[ $slug ] = (int) $term->term_id;
        $parents_verified[]  = $slug;
        continue;
    }

    $res = wp_insert_term( $name, $taxonomy, [ 'slug' => $slug ] );
    if ( is_wp_error( $res ) ) {
        WP_CLI::warning( "Could not create continent parent '{$name}' ({$slug}): " . $res->get_error_message() );
        continue;
    }
    $parent_ids[ $slug ] = (int) $res['term_id'];
    $parents_created[]    = $slug;
}

// ===========================================================================
// 2. Re-parent country/region terms under their continent
// ===========================================================================
$reparented   = [];  // slug => continent (parent actually changed)
$already_ok    = [];  // slug (parent already correct)
$skipped_absent = []; // slug not present as a term — skipped silently

foreach ( $country_to_continent as $country_slug => $continent_slug ) {
    // The region term that IS the continent (south-america) was already
    // ensured top-level above; never make a term its own parent.
    if ( $country_slug === $continent_slug ) {
        continue;
    }

    $term = get_term_by( 'slug', $country_slug, $taxonomy );
    if ( ! $term || is_wp_error( $term ) ) {
        $skipped_absent[] = $country_slug;
        continue;
    }

    $parent_id = $parent_ids[ $continent_slug ] ?? 0;
    if ( ! $parent_id ) {
        // Parent creation failed earlier; leave the country untouched.
        $skipped_absent[] = $country_slug;
        continue;
    }

    if ( (int) $term->parent === $parent_id ) {
        $already_ok[] = $country_slug;
        continue;
    }

    $res = wp_update_term( $term->term_id, $taxonomy, [ 'parent' => $parent_id ] );
    if ( is_wp_error( $res ) ) {
        WP_CLI::warning( "Could not re-parent '{$country_slug}' → {$continent_slug}: " . $res->get_error_message() );
        continue;
    }
    $reparented[ $country_slug ] = $continent_slug;
}

// ===========================================================================
// 3. Force structural/cross-region markers to stay top-level
// ===========================================================================
$structural_present = []; // slug => 'left' | 'fixed'

foreach ( $structural_top_level as $slug ) {
    $term = get_term_by( 'slug', $slug, $taxonomy );
    if ( ! $term || is_wp_error( $term ) ) {
        continue; // not present — nothing to enforce
    }
    if ( (int) $term->parent !== 0 ) {
        wp_update_term( $term->term_id, $taxonomy, [ 'parent' => 0 ] );
        $structural_present[ $slug ] = 'fixed';
    } else {
        $structural_present[ $slug ] = 'left';
    }
}

// Clear the term hierarchy cache so the new parents resolve immediately.
clean_term_cache( [], $taxonomy );

// ===========================================================================
// Summary
// ===========================================================================
WP_CLI::log( '' );
WP_CLI::log( '=== Origin continent hierarchy migration ===' );
WP_CLI::log( '' );

WP_CLI::log( 'Continent parents:' );
WP_CLI::log( '  created : ' . ( $parents_created ? implode( ', ', $parents_created ) : '(none)' ) );
WP_CLI::log( '  verified: ' . ( $parents_verified ? implode( ', ', $parents_verified ) : '(none)' ) );

WP_CLI::log( '' );
WP_CLI::log( 'Countries re-parented (' . count( $reparented ) . '):' );
if ( $reparented ) {
    foreach ( $reparented as $slug => $continent ) {
        WP_CLI::log( "  {$slug} → {$continent}" );
    }
} else {
    WP_CLI::log( '  (none — all already correct or absent)' );
}

if ( $already_ok ) {
    WP_CLI::log( '' );
    WP_CLI::log( 'Countries already correctly parented (' . count( $already_ok ) . '): ' . implode( ', ', $already_ok ) );
}

if ( $skipped_absent ) {
    WP_CLI::log( '' );
    WP_CLI::log( 'Slugs skipped — not found as terms (' . count( $skipped_absent ) . '): ' . implode( ', ', array_unique( $skipped_absent ) ) );
}

WP_CLI::log( '' );
WP_CLI::log( 'Structural markers left top-level:' );
if ( $structural_present ) {
    foreach ( $structural_present as $slug => $state ) {
        WP_CLI::log( "  {$slug} (" . ( 'fixed' === $state ? 'moved back to top level' : 'already top-level' ) . ')' );
    }
} else {
    WP_CLI::log( '  (none present)' );
}

WP_CLI::log( '' );
WP_CLI::success( 'Done. Re-run anytime — the migration is idempotent.' );
