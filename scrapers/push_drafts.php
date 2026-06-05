<?php
/**
 * Parse draft markdown files and push content into ACF fields on bean posts.
 *
 * Run from WordPress root on the VPS:
 *   wp eval-file /opt/scrapers/push_drafts.php --allow-root
 *
 * Reads all /opt/drafts/*.md files, parses sections, finds the matching
 * bean post by slug, and updates ACF fields. Safe to re-run — overwrites
 * fields each time, so re-running after editing a draft updates the post.
 */

$drafts_dir = '/opt/drafts';

$files = glob( $drafts_dir . '/*.md' );
if ( empty( $files ) ) {
    WP_CLI::error( "No .md files found in {$drafts_dir}" );
    exit;
}

$updated = 0;
$skipped = 0;
$failed  = 0;

foreach ( $files as $file ) {
    $filename = basename( $file );

    // Extract product_id — strip the trailing -YYYY-MM-DD.md
    if ( ! preg_match( '/^(.+)-\d{4}-\d{2}-\d{2}\.md$/', $filename, $m ) ) {
        WP_CLI::warning( "SKIP  {$filename} — can't parse product_id from filename" );
        $skipped++;
        continue;
    }
    $product_id = $m[1];

    // Find the bean post
    $post = get_page_by_path( $product_id, OBJECT, 'bean' );
    if ( ! $post ) {
        WP_CLI::warning( "SKIP  {$product_id} — no bean post found with this slug" );
        $skipped++;
        continue;
    }

    $content = file_get_contents( $file );
    if ( ! $content ) {
        WP_CLI::warning( "SKIP  {$product_id} — could not read file" );
        $skipped++;
        continue;
    }

    // --- Parse verdict ---
    $verdict = '';
    if ( preg_match( '/\*\*One-line verdict\*\*:\s*(.+)/m', $content, $match ) ) {
        $verdict = trim( $match[1] );
    }

    // --- Parse rating (extract first number before /10) ---
    $rating = '';
    if ( preg_match( '/###\s*Rating:\s*([\d.]+)\s*\/\s*10/m', $content, $match ) ) {
        $rating = floatval( $match[1] );
    }

    // --- Parse price/oz from spec table (take first number if range like $0.78–$0.82) ---
    $price_per_oz = '';
    if ( preg_match( '/\|\s*Price\/oz\s*\|\s*\$?([\d.]+)/m', $content, $match ) ) {
        $price_per_oz = floatval( $match[1] );
    }

    // --- Parse tasting notes (bullets under ### Tasting notes) ---
    $tasting_notes = '';
    if ( preg_match( '/###\s*Tasting notes?\s*\n(.*?)(?=\n###|\z)/si', $content, $match ) ) {
        $lines = explode( "\n", trim( $match[1] ) );
        $notes = [];
        foreach ( $lines as $line ) {
            $line = trim( $line );
            if ( strpos( $line, '-' ) === 0 ) {
                $notes[] = ltrim( $line, '- ' );
            }
        }
        $tasting_notes = implode( "\n", $notes );
    }

    // --- Parse who it's for ---
    $whos_for = '';
    if ( preg_match( '/###\s*Who it\'s for\s*\n(.*?)(?=\n###|\z)/si', $content, $match ) ) {
        $whos_for = trim( $match[1] );
    }

    // --- Parse who should skip it ---
    $whos_not_for = '';
    if ( preg_match( '/###\s*Who should skip it\s*\n(.*?)(?=\n###|\z)/si', $content, $match ) ) {
        $whos_not_for = trim( $match[1] );
    }

    // --- Parse price analysis ---
    $price_analysis = '';
    if ( preg_match( '/###\s*Price analysis\s*\n(.*?)(?=\n###|\z)/si', $content, $match ) ) {
        // Strip affiliate disclosure line if it crept in
        $pa = trim( $match[1] );
        $pa = preg_replace( '/\*\[?Affiliate disclosure.*$/si', '', $pa );
        $price_analysis = trim( $pa );
    }

    // --- Parse RankMath meta from the <!--META ... --> header ---
    $meta_title = '';
    $meta_desc  = '';
    if ( preg_match( '/<!--META\s*(.*?)-->/si', $content, $match ) ) {
        $meta_block = $match[1];
        if ( preg_match( '/meta_title:\s*(.+)/i', $meta_block, $mt ) ) {
            $meta_title = trim( $mt[1] );
        }
        if ( preg_match( '/meta_description:\s*(.+)/i', $meta_block, $md ) ) {
            $meta_desc = trim( $md[1] );
        }
    }

    // --- Parse "Explore further" internal links → HTML for post_content ---
    $body_html = '';
    if ( preg_match( '/###\s*Explore further\s*\n(.*?)(?=\n###|\n---|\z)/si', $content, $match ) ) {
        $links_md = trim( $match[1] );
        // Convert [text](/url/) → <a href="/url/">text</a>
        $links_html = preg_replace( '/\[([^\]]+)\]\(([^)]+)\)/', '<a href="$2">$1</a>', $links_md );
        if ( $links_html ) {
            $body_html = '<p>' . trim( $links_html ) . '</p>';
        }
    }

    // --- Validate we got the minimum fields ---
    if ( empty( $verdict ) || empty( $rating ) ) {
        WP_CLI::warning( "SKIP  {$product_id} — draft looks incomplete (missing verdict or rating). Is it a clarifying-question file?" );
        $skipped++;
        continue;
    }

    // --- Push to ACF ---
    update_field( 'verdict',        $verdict,        $post->ID );
    update_field( 'rating',         $rating,         $post->ID );
    update_field( 'tasting_notes',  $tasting_notes,  $post->ID );
    update_field( 'whos_for',       $whos_for,       $post->ID );
    update_field( 'whos_not_for',   $whos_not_for,   $post->ID );
    update_field( 'price_analysis', $price_analysis, $post->ID );

    if ( $price_per_oz ) {
        update_field( 'price_per_oz', $price_per_oz, $post->ID );
    }

    // --- RankMath meta (per-post overrides the CPT title template) ---
    if ( $meta_title ) {
        update_post_meta( $post->ID, 'rank_math_title', $meta_title );
    }
    if ( $meta_desc ) {
        update_post_meta( $post->ID, 'rank_math_description', $meta_desc );
    }

    // --- Post body: internal links render under "Full review" in single-bean.php ---
    $post_update = [ 'ID' => $post->ID, 'post_status' => 'draft' ];
    if ( $body_html ) {
        $post_update['post_content'] = $body_html;
    }
    wp_update_post( $post_update );

    $meta_note = $meta_title ? ' + meta' : '';
    $body_note = $body_html ? ' + internal links' : '';
    WP_CLI::success( "UPDATED {$product_id} (post #{$post->ID}) — verdict, rating {$rating}/10, " . count( explode( "\n", $tasting_notes ) ) . " tasting notes{$meta_note}{$body_note}" );
    $updated++;
}

WP_CLI::log( "" );
WP_CLI::log( "Done — Updated: {$updated}  |  Skipped: {$skipped}  |  Failed: {$failed}" );
WP_CLI::log( "" );
WP_CLI::log( "Review drafts at: " . admin_url( 'edit.php?post_type=bean&post_status=draft' ) );
