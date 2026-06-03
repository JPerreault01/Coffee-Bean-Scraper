<?php
/**
 * Link Audit Script — orphan and broken internal link checker
 *
 * Run via WP-CLI:
 *   sudo -u www-data wp --path=/var/www/coffeebeans eval-file /path/to/seeds/audit-links.php
 *   # or redirect to file:
 *   sudo -u www-data wp --path=/var/www/coffeebeans eval-file /path/to/seeds/audit-links.php > /tmp/audit.txt
 *
 * Checks:
 *   1. Published bean pages with no inbound internal links from any other published page/post
 *   2. Taxonomy terms that have guide content (description) but no link pointing to their archive URL
 *   3. Broken internal links on published pages (href targets that return 404)
 */

WP_CLI::log( "=== Coffee Bean Index — Internal Link Audit ===" );
WP_CLI::log( "Started: " . date( 'Y-m-d H:i:s' ) );
WP_CLI::log( "" );

// ─────────────────────────────────────────────────────────────────────────────
// 1. Bean pages with no inbound internal links
// ─────────────────────────────────────────────────────────────────────────────
WP_CLI::log( "--- Check 1: Bean pages with no inbound internal links ---" );

$bean_posts = get_posts( [
    'post_type'      => 'bean',
    'post_status'    => 'publish',
    'posts_per_page' => -1,
] );

if ( empty( $bean_posts ) ) {
    WP_CLI::log( "  No published bean pages found." );
} else {
    // Build list of all internal content (pages + posts) to search for links
    $all_content_posts = get_posts( [
        'post_type'      => [ 'page', 'post', 'bean' ],
        'post_status'    => 'publish',
        'posts_per_page' => -1,
        'fields'         => 'ids',
    ] );

    // Get all published content as a concatenated string to search
    $all_content = '';
    foreach ( $all_content_posts as $pid ) {
        $all_content .= get_post_field( 'post_content', $pid ) . "\n";
    }
    // Also include term descriptions
    $all_taxonomies = [ 'origin', 'roast-level', 'process-method', 'brew-method', 'flavor-note', 'roaster' ];
    foreach ( $all_taxonomies as $tax ) {
        $terms = get_terms( [ 'taxonomy' => $tax, 'hide_empty' => false ] );
        foreach ( $terms as $term ) {
            $all_content .= $term->description . "\n";
        }
    }

    $orphan_beans = [];
    foreach ( $bean_posts as $bean ) {
        $url       = get_permalink( $bean->ID );
        $path      = parse_url( $url, PHP_URL_PATH );
        $slug      = $bean->post_name;
        // Check for the slug in any href attribute in all content
        if ( strpos( $all_content, $slug ) === false && strpos( $all_content, $path ) === false ) {
            $orphan_beans[] = [
                'title' => $bean->post_title,
                'url'   => $url,
                'slug'  => $slug,
            ];
        }
    }

    if ( empty( $orphan_beans ) ) {
        WP_CLI::log( "  ✓ All published bean pages have at least one inbound reference." );
    } else {
        WP_CLI::warning( "  " . count( $orphan_beans ) . " orphan bean page(s) found:" );
        foreach ( $orphan_beans as $b ) {
            WP_CLI::log( "    - {$b['title']} → {$b['url']}" );
        }
        WP_CLI::log( "  Fix: add a link to each orphan from a relevant guide or roundup." );
    }
}

WP_CLI::log( "" );

// ─────────────────────────────────────────────────────────────────────────────
// 2. Taxonomy terms with guide content but no inbound links
// ─────────────────────────────────────────────────────────────────────────────
WP_CLI::log( "--- Check 2: Taxonomy guide terms with no inbound links ---" );

$all_taxonomies = [ 'origin', 'roast-level', 'process-method', 'brew-method', 'flavor-note' ];
$orphan_terms   = [];

// Rebuild all content for link search (same as above — scoped function for clarity)
$all_content_for_terms = '';
$all_content_posts_for_terms = get_posts( [
    'post_type'      => [ 'page', 'post', 'bean' ],
    'post_status'    => 'publish',
    'posts_per_page' => -1,
    'fields'         => 'ids',
] );
foreach ( $all_content_posts_for_terms as $pid ) {
    $all_content_for_terms .= get_post_field( 'post_content', $pid ) . "\n";
}

foreach ( $all_taxonomies as $tax ) {
    $terms = get_terms( [
        'taxonomy'   => $tax,
        'hide_empty' => false,
        'number'     => 0,
    ] );
    foreach ( $terms as $term ) {
        if ( empty( $term->description ) ) {
            continue; // No guide content — skip, it's expected to be empty
        }
        $term_url  = get_term_link( $term );
        if ( is_wp_error( $term_url ) ) {
            continue;
        }
        $term_path = parse_url( $term_url, PHP_URL_PATH );
        if ( strpos( $all_content_for_terms, $term_path ) === false
             && strpos( $all_content_for_terms, $term->slug ) === false ) {
            $orphan_terms[] = [
                'taxonomy' => $tax,
                'name'     => $term->name,
                'url'      => $term_url,
            ];
        }
    }
}

if ( empty( $orphan_terms ) ) {
    WP_CLI::log( "  ✓ All guide terms have at least one inbound reference." );
} else {
    WP_CLI::warning( "  " . count( $orphan_terms ) . " guide term(s) with no inbound link:" );
    foreach ( $orphan_terms as $t ) {
        WP_CLI::log( "    - [{$t['taxonomy']}] {$t['name']} → {$t['url']}" );
    }
    WP_CLI::log( "  Fix: add a link to each term from the Learn hub page or a relevant guide." );
}

WP_CLI::log( "" );

// ─────────────────────────────────────────────────────────────────────────────
// 3. Broken internal links on published pages/posts
// ─────────────────────────────────────────────────────────────────────────────
WP_CLI::log( "--- Check 3: Broken internal links (href targets returning 404) ---" );

$posts_to_check = get_posts( [
    'post_type'      => [ 'page', 'post', 'bean' ],
    'post_status'    => 'publish',
    'posts_per_page' => -1,
] );

$broken_links = [];
$home         = home_url();

foreach ( $posts_to_check as $post ) {
    $content = get_post_field( 'post_content', $post->ID );
    if ( empty( $content ) ) {
        continue;
    }

    // Find all internal href values
    preg_match_all( '/href=["\'](' . preg_quote( $home, '/' ) . '[^"\']+)["\']/', $content, $matches );
    preg_match_all( '/href=["\'](\\/[^"\']+)["\']/', $content, $rel_matches );

    $hrefs = array_merge( $matches[1] ?? [], array_map( fn( $p ) => $home . $p, $rel_matches[1] ?? [] ) );

    foreach ( $hrefs as $href ) {
        // Skip anchors, query strings only
        if ( strpos( $href, '#' ) !== false ) {
            continue;
        }
        // Use wp_remote_head for a lightweight check
        $response = wp_remote_head( $href, [ 'timeout' => 5, 'redirection' => 5 ] );
        if ( is_wp_error( $response ) ) {
            continue; // Network error — skip
        }
        $code = wp_remote_retrieve_response_code( $response );
        if ( $code === 404 ) {
            $broken_links[] = [
                'source_title' => get_the_title( $post->ID ),
                'source_url'   => get_permalink( $post->ID ),
                'broken_href'  => $href,
            ];
        }
    }
}

if ( empty( $broken_links ) ) {
    WP_CLI::log( "  ✓ No broken internal links found." );
} else {
    WP_CLI::warning( "  " . count( $broken_links ) . " broken internal link(s) found:" );
    foreach ( $broken_links as $bl ) {
        WP_CLI::log( "    - Page: {$bl['source_title']} ({$bl['source_url']})" );
        WP_CLI::log( "      → Broken href: {$bl['broken_href']}" );
    }
    WP_CLI::log( "  Fix: update or remove each broken link from its source page." );
}

WP_CLI::log( "" );
WP_CLI::log( "=== Audit complete ===" );
