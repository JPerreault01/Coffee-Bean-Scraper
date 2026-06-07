<?php
/**
 * One-off: re-apply canonical multi-country origin tags to EXISTING bean posts.
 *
 * Run from WordPress root on the VPS:
 *   wp eval-file /opt/scrapers/retag_origins.php --allow-root
 *
 * Why this exists:
 *   create_beans.php skips beans whose slug already exists, so editing
 *   $origin_map there does NOT re-tag the ~70 beans already in the DB. This
 *   script walks every existing bean, looks up its origin string in
 *   products.json (matched by post_name === product id), maps it through the
 *   SAME multi-tag rules, and REPLACES the post's origin terms.
 *
 *   wp_set_object_terms() replaces (not appends), so stale tags like the old
 *   over-consolidated 'latin-america' / 'multi-origin-blend' are cleared as a
 *   side effect. Run the empty-term cleanup afterward (see end of output).
 *
 * Safe to re-run. Does not create, delete, or change post content — only the
 * 'origin' taxonomy assignment.
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

// Index products by id for O(1) lookup against each bean's post_name.
$products_by_id = [];
foreach ( $products as $p ) {
    if ( ! empty( $p['id'] ) ) {
        $products_by_id[ $p['id'] ] = $p;
    }
}

// ---------------------------------------------------------------------------
// Origin canonical map — MUST stay in sync with create_beans.php.
// Each value is a list of [ slug, display name ] country/region pairs.
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
// Walk every bean post (any status — drafts included) and re-tag.
// ---------------------------------------------------------------------------

$bean_posts = get_posts( [
    'post_type'   => 'bean',
    'post_status' => 'any',
    'numberposts' => -1,
    'fields'      => 'ids',
] );

$retagged   = 0;
$no_product = [];  // post_name with no matching products.json entry
$unmapped   = [];  // origin string not in $origin_map

foreach ( $bean_posts as $post_id ) {
    $slug = get_post_field( 'post_name', $post_id );

    if ( ! isset( $products_by_id[ $slug ] ) ) {
        WP_CLI::warning( "  NO products.json entry for post #{$post_id} (slug: {$slug}) — skipped" );
        $no_product[] = $slug;
        continue;
    }

    $raw_origin = $products_by_id[ $slug ]['origin'] ?? '';

    if ( ! isset( $origin_map[ $raw_origin ] ) ) {
        WP_CLI::warning( "  UNMAPPED origin \"{$raw_origin}\" for {$slug} — left unchanged" );
        $unmapped[ $raw_origin ] = $slug;
        continue;
    }

    $origin_term_ids = [];
    foreach ( $origin_map[ $raw_origin ] as $pair ) {
        [ $o_slug, $o_name ] = $pair;
        $o_term_id = cbi_get_or_create_term( $o_slug, $o_name, 'origin' );
        if ( $o_term_id ) {
            $origin_term_ids[] = $o_term_id;
        }
    }

    if ( $origin_term_ids ) {
        // Replaces all existing origin terms on this post.
        wp_set_object_terms( $post_id, array_unique( $origin_term_ids ), 'origin' );
        $slug_list = implode( ', ', array_map( function ( $pair ) { return $pair[0]; }, $origin_map[ $raw_origin ] ) );
        WP_CLI::log( "RETAGGED {$slug} → {$slug_list}" );
        $retagged++;
    }
}

// Clear WP's cached term counts so `wp term list` shows fresh numbers.
foreach ( [ 'origin' ] as $tax ) {
    $ids = get_terms( [ 'taxonomy' => $tax, 'hide_empty' => false, 'fields' => 'ids' ] );
    if ( ! is_wp_error( $ids ) && $ids ) {
        wp_update_term_count_now( $ids, $tax );
    }
}

WP_CLI::log( '' );
WP_CLI::log( "Done — Retagged: {$retagged}  |  No product match: " . count( $no_product ) . "  |  Unmapped: " . count( $unmapped ) );

if ( $unmapped ) {
    WP_CLI::log( '' );
    WP_CLI::log( '--- UNMAPPED ORIGINS (add to $origin_map in BOTH files) ---' );
    foreach ( $unmapped as $origin_str => $slug ) {
        WP_CLI::warning( "  \"{$origin_str}\"  (e.g. {$slug})" );
    }
}

if ( $no_product ) {
    WP_CLI::log( '' );
    WP_CLI::log( '--- BEANS WITH NO products.json MATCH (origin left unchanged) ---' );
    foreach ( array_unique( $no_product ) as $slug ) {
        WP_CLI::warning( "  {$slug}" );
    }
}
