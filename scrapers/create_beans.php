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
 *
 * Origin and flavor-note taxonomies use canonical curated terms rather than
 * raw sanitize_title() on freeform strings. Unmapped/dropped strings are
 * reported in the summary at the end.
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

// ---------------------------------------------------------------------------
// Origin canonical map
// Keys: exact "origin" strings from products.json
// Values: list of [ slug, display name ] canonical country/region pairs.
//
// A bean's origin resolves to MULTIPLE country tags so it surfaces under each
// country's filter and archive. Single-origin beans get one entry; blends get
// one entry per named country plus a ['blend','Blend'] marker so "show me only
// blends" stays possible. Where a source only names a region (e.g. "Latin
// America") with no countries, the regional term is kept alongside the marker.
// ---------------------------------------------------------------------------

$origin_map = [
    // Single-country / single-region — one tag each
    'Colombia'                  => [ ['colombia',   'Colombia']   ],
    'Sumatra'                   => [ ['sumatra',    'Sumatra']    ],
    'Nicaragua (single origin)' => [ ['nicaragua',  'Nicaragua']  ],
    'Limu, Ethiopia'            => [ ['ethiopia',   'Ethiopia']   ],
    'Yirgacheffe, Ethiopia'     => [ ['ethiopia',   'Ethiopia']   ],
    'Guji, Ethiopia'            => [ ['ethiopia',   'Ethiopia']   ],
    'Chiapas, Mexico'           => [ ['mexico',     'Mexico']     ],
    'Kona, Hawaii'              => [ ['hawaii',     'Hawaii']     ],
    'Tarrazu, Costa Rica'       => [ ['costa-rica', 'Costa Rica'] ],

    // Latin-America blends — tag each named country + a blend marker.
    // Where the source only says "Latin America" / "Central & South America"
    // with no countries named, keep the regional term + blend marker.
    'Latin America blend'             => [ ['latin-america', 'Latin America'], ['blend','Blend'] ],
    'Central and South America blend' => [ ['latin-america', 'Latin America'], ['blend','Blend'] ],
    'Colombia, Brazil, Honduras blend'=> [ ['colombia','Colombia'], ['brazil','Brazil'], ['honduras','Honduras'], ['blend','Blend'] ],
    'Colombia, Central America blend' => [ ['colombia','Colombia'], ['central-america','Central America'], ['blend','Blend'] ],

    // Cross-region blends — tag each named country/region + blend marker.
    'Brazil, Colombia, Indonesia blend'               => [ ['brazil','Brazil'], ['colombia','Colombia'], ['indonesia','Indonesia'], ['blend','Blend'] ],
    '9-country Arabica blend'                         => [ ['blend','Blend'] ], // no countries named
    'Latin America, Indonesia blend'                  => [ ['latin-america','Latin America'], ['indonesia','Indonesia'], ['blend','Blend'] ],
    'Latin America, East Africa blend'                => [ ['latin-america','Latin America'], ['east-africa','East Africa'], ['blend','Blend'] ],
    'India, Peru blend'                               => [ ['india','India'], ['peru','Peru'], ['blend','Blend'] ],
    'Indonesia, Central America, South America blend' => [ ['indonesia','Indonesia'], ['central-america','Central America'], ['south-america','South America'], ['blend','Blend'] ],
    'Ethiopia, Colombia blend'                        => [ ['ethiopia','Ethiopia'], ['colombia','Colombia'], ['blend','Blend'] ],
    'Ethiopia, Latin America blend'                   => [ ['ethiopia','Ethiopia'], ['latin-america','Latin America'], ['blend','Blend'] ],
    'Indonesia, South America blend'                  => [ ['indonesia','Indonesia'], ['south-america','South America'], ['blend','Blend'] ],
];

// ---------------------------------------------------------------------------
// Flavor-note canonical map
// Keys: exact lowercase strings from products.json "flavor_notes" arrays
// Values:
//   string  = curated flavor-note slug (must already exist from seed data)
//   null    = genuine flavor with no curated term — warn + skip
//   false   = structural/sensory descriptor, not a flavor — drop silently
//
// Structural descriptors (bold, smooth, full body, etc.) are already captured
// by ACF sensory bars (acidity, body, sweetness, bitterness, roast_intensity).
// Creating flavor-note taxonomy terms for them pollutes the flavor hierarchy.
// ---------------------------------------------------------------------------

$flavor_structural_drops = [
    // Body/texture
    'bold', 'smooth', 'mild', 'intense',
    'full body', 'medium body', 'thick body', 'smooth body', 'creamy body', 'thick crema',
    // Acidity/bitterness
    'low acid', 'low acidity', 'low bitterness', 'bright acidity',
    // Finish/balance
    'balanced', 'clean', 'clean finish', 'lingering finish',
];

$flavor_canonical_map = [
    // Chocolate family (slugs from seeds/data/flavor-note-terms.php)
    'dark chocolate'       => 'dark-chocolate',
    'milk chocolate'       => 'milk-chocolate',
    'bittersweet chocolate' => 'bittersweet-chocolate',
    'mild cocoa'           => 'mild-cocoa',
    'light cocoa'          => 'mild-cocoa',
    'mild chocolate'       => 'mild-cocoa',
    'light chocolate'      => 'mild-cocoa',
    'chocolate'            => 'chocolate',       // parent family term

    // Caramel & Sweet family
    'caramel'              => 'caramel',
    'light caramel'        => 'caramel',
    'brown sugar'          => 'brown-sugar',
    'toffee'               => 'toffee',
    'molasses'             => 'molasses',

    // Nutty family
    'hazelnut'             => 'hazelnut',
    'walnut'               => 'walnut',
    'nuts'                 => 'nutty',           // parent family term
    'nutty'                => 'nutty',           // parent family term

    // Fruit family
    'dark cherry'          => 'dark-cherry',
    'dried fruit'          => 'dried-fruit',
    'stone fruit'          => 'stone-fruit',
    'strawberry'           => 'strawberry',
    'mild fruit'           => 'fruit',           // parent family term

    // Citrus & Floral family
    'bergamot'             => 'bergamot',
    'orange blossom'       => 'orange-blossom',
    'jasmine'              => 'jasmine',
    'citrus'               => 'citrus-floral',   // no child slug for generic citrus; use parent
    'mild citrus'          => 'citrus-floral',

    // Earthy & Smoky family
    'earthy'               => 'earthy',
    'cedar'                => 'cedar',
    'smoky'                => 'smoky',
    'mild smokiness'       => 'smoky',
    'tobacco'              => 'tobacco',

    // Genuine flavors with no curated term — warn + skip
    'cream soda'           => null,

    // Additional flavor strings from bulk import (2026-06)
    'spice'          => 'spice',
    'raisin'         => 'dried-fruit',
    'sweet citrus'   => 'citrus-floral',
    'graham cracker' => 'caramel',
    'cocoa'          => 'chocolate',
    'toasted nut'    => 'nutty',
    'toasted almond' => 'nutty',
    'red fruit'      => 'red-fruit',
    'berry'          => 'red-fruit',
    'honey'          => 'caramel',
    'blueberry'      => 'blueberry',
    'floral'         => 'floral',
    'charred'        => 'smoky',
    'toasted malt'   => 'nutty',
    'soft cocoa'     => 'chocolate',
    'chicory'        => 'earthy',
    'marshmallow'    => 'caramel',
    'raspberry'      => 'red-fruit',
    'cherry'         => 'red-fruit',
    'plum'           => 'dried-fruit',
    'sweet'          => 'caramel',
    'bright'         => false,
    'light body'     => false,
];

// ---------------------------------------------------------------------------
// Helper: ensure a term with the given slug and display name exists in a
// taxonomy, then return its term_id. Creates it if absent.
// ---------------------------------------------------------------------------

function cbi_get_or_create_term( $slug, $name, $taxonomy ) {
    $term = get_term_by( 'slug', $slug, $taxonomy );
    if ( $term && ! is_wp_error( $term ) ) {
        return (int) $term->term_id;
    }
    $result = wp_insert_term( $name, $taxonomy, [ 'slug' => $slug ] );
    if ( is_wp_error( $result ) ) {
        WP_CLI::warning( "  Could not create term '{$name}' ({$slug}) in {$taxonomy}: " . $result->get_error_message() );
        return null;
    }
    return (int) $result['term_id'];
}

// ---------------------------------------------------------------------------
// Already created — skip these
// ---------------------------------------------------------------------------

$skip_ids = [ 'lavazza-super-crema' ];

// Counters and summary accumulators
$created  = 0;
$skipped  = 0;
$failed   = 0;

$unmapped_origins    = [];  // origin string => product id (fell back to sanitize_title)
$dropped_structural  = [];  // structural descriptors silently dropped
$no_curated_term     = [];  // real flavor notes with no matching curated slug
$unknown_flavor_strs = [];  // strings not present in either map (mapping gap)
$missing_db_terms    = [];  // curated slugs that don't exist in the DB yet

// ---------------------------------------------------------------------------
// Main loop
// ---------------------------------------------------------------------------

foreach ( $products as $p ) {
    $id = $p['id'];

    if ( in_array( $id, $skip_ids, true ) ) {
        WP_CLI::log( "SKIP  {$id} (in skip list)" );
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

    // -----------------------------------------------------------------------
    // Taxonomies
    // -----------------------------------------------------------------------

    // roaster  (brand name — use sanitize_title, brand names are already clean)
    wp_set_object_terms( $post_id, sanitize_title( $p['brand'] ), 'roaster' );

    // roast-level
    wp_set_object_terms( $post_id, sanitize_title( $p['roast_level'] ), 'roast-level' );

    // process-method
    wp_set_object_terms( $post_id, sanitize_title( $p['process_method'] ), 'process-method' );

    // brew-method  (array)
    $brew_slugs = array_map( 'sanitize_title', $p['best_brew_methods'] ?? [] );
    wp_set_object_terms( $post_id, $brew_slugs, 'brew-method' );

    // --- Origin (canonical, multi-tag) ---
    $raw_origin = $p['origin'] ?? '';
    if ( isset( $origin_map[ $raw_origin ] ) ) {
        $origin_term_ids = [];
        foreach ( $origin_map[ $raw_origin ] as $pair ) {
            [ $o_slug, $o_name ] = $pair;
            $o_term_id = cbi_get_or_create_term( $o_slug, $o_name, 'origin' );
            if ( $o_term_id ) {
                $origin_term_ids[] = $o_term_id;
            }
        }
        if ( $origin_term_ids ) {
            wp_set_object_terms( $post_id, array_unique( $origin_term_ids ), 'origin' );
        }
    } else {
        WP_CLI::warning( "  UNMAPPED origin for {$id}: \"{$raw_origin}\" — falling back to sanitize_title" );
        wp_set_object_terms( $post_id, sanitize_title( $raw_origin ), 'origin' );
        $unmapped_origins[ $raw_origin ] = $id;
    }

    // --- Flavor notes (canonical, curated only) ---
    $flavor_term_ids = [];
    foreach ( $p['flavor_notes'] ?? [] as $raw_note ) {
        $note = strtolower( trim( $raw_note ) );

        // Structural/sensory descriptor — drop silently
        if ( in_array( $note, $flavor_structural_drops, true ) ) {
            $dropped_structural[] = $note;
            continue;
        }

        // Not in the canonical map at all — mapping gap, warn
        if ( ! array_key_exists( $note, $flavor_canonical_map ) ) {
            WP_CLI::warning( "  UNKNOWN flavor string for {$id}: \"{$raw_note}\" — add to \$flavor_canonical_map" );
            $unknown_flavor_strs[] = $note;
            continue;
        }

        $curated_slug = $flavor_canonical_map[ $note ];

        // null = genuine flavor but no curated term yet
        if ( $curated_slug === null ) {
            WP_CLI::warning( "  NO CURATED TERM for \"{$raw_note}\" ({$id}) — skipping to avoid orphan" );
            $no_curated_term[] = $note;
            continue;
        }

        // Confirm the term actually exists in the DB (seeded by flavor-note-terms.php)
        $term = get_term_by( 'slug', $curated_slug, 'flavor-note' );
        if ( ! $term || is_wp_error( $term ) ) {
            WP_CLI::warning( "  MISSING DB TERM '{$curated_slug}' (flavor-note) for {$id} — run seeds first" );
            $missing_db_terms[] = $curated_slug;
            continue;
        }

        $flavor_term_ids[] = (int) $term->term_id;
    }

    if ( $flavor_term_ids ) {
        wp_set_object_terms( $post_id, array_unique( $flavor_term_ids ), 'flavor-note' );
    }

    // -----------------------------------------------------------------------
    // ACF fields
    // -----------------------------------------------------------------------

    // Sensory scores
    update_field( 'acidity',         $p['acidity'],         $post_id );
    update_field( 'body',            $p['body'],            $post_id );
    update_field( 'sweetness',       $p['sweetness'],       $post_id );
    update_field( 'bitterness',      $p['bitterness'],      $post_id );
    update_field( 'roast_intensity', $p['roast_intensity'], $post_id );

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

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------

WP_CLI::log( '' );
WP_CLI::log( "Done — Created: {$created}  |  Skipped: {$skipped}  |  Failed: {$failed}" );

if ( $unmapped_origins ) {
    WP_CLI::log( '' );
    WP_CLI::log( '--- UNMAPPED ORIGINS (fell back to sanitize_title — add entries to $origin_map) ---' );
    foreach ( $unmapped_origins as $origin_str => $product_id ) {
        WP_CLI::warning( "  \"{$origin_str}\"  (product: {$product_id})" );
    }
}

if ( $dropped_structural ) {
    WP_CLI::log( '' );
    WP_CLI::log( '--- DROPPED STRUCTURAL DESCRIPTORS (sensory/body/finish — not flavor notes, not an error) ---' );
    $counts = array_count_values( $dropped_structural );
    arsort( $counts );
    foreach ( $counts as $term => $n ) {
        WP_CLI::log( "  \"{$term}\"  ({$n}x)" );
    }
}

if ( $no_curated_term ) {
    WP_CLI::log( '' );
    WP_CLI::log( '--- FLAVOR STRINGS WITH NO CURATED TERM (real flavors, skipped to avoid orphan — consider adding to seeds) ---' );
    foreach ( array_unique( $no_curated_term ) as $term ) {
        WP_CLI::warning( "  \"{$term}\"" );
    }
}

if ( $unknown_flavor_strs ) {
    WP_CLI::log( '' );
    WP_CLI::log( '--- UNKNOWN FLAVOR STRINGS (not in $flavor_canonical_map — mapping gap, skipped) ---' );
    foreach ( array_unique( $unknown_flavor_strs ) as $term ) {
        WP_CLI::warning( "  \"{$term}\"" );
    }
}

if ( $missing_db_terms ) {
    WP_CLI::log( '' );
    WP_CLI::log( '--- MISSING DB TERMS (curated slug exists in map but not in WP DB — run seed first) ---' );
    foreach ( array_unique( $missing_db_terms ) as $slug ) {
        WP_CLI::warning( "  flavor-note: {$slug}" );
    }
}
