<?php
/**
 * Plugin Name: Coffee Bean Profile
 * Plugin URI:  https://github.com/JPerreault01/Coffee-Bean-Scraper
 * Description: Renders a full flavor profile card for a tracked coffee bean — radar chart, specs, flavor notes, and similar bean recommendations. Usage: [coffee_bean_profile product_id="lavazza-super-crema"]
 * Version:     1.0.0
 * Author:      JPerreault01
 * License:     GPL2
 *
 * File: wordpress-plugins/coffee-bean-profile/coffee-bean-profile.php
 * Deploy to: /var/www/coffeebeans/wp-content/plugins/coffee-bean-profile/coffee-bean-profile.php
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

define( 'CBP_DB_PATH',        '/opt/data/prices.db' );
define( 'CBP_SIMILAR_COUNT',  3 );

// ---------------------------------------------------------------------------
// Shortcode
// ---------------------------------------------------------------------------

add_shortcode( 'coffee_bean_profile', 'cbp_render_shortcode' );

function cbp_render_shortcode( $atts ): string {
    $atts = shortcode_atts( [ 'product_id' => '' ], $atts, 'coffee_bean_profile' );
    $product_id = sanitize_text_field( $atts['product_id'] );

    if ( empty( $product_id ) ) {
        return '<p class="cbp-error">coffee_bean_profile: product_id is required.</p>';
    }

    $product = cbp_get_product( $product_id );
    if ( ! $product ) {
        return '<p class="cbp-error">No profile found for: ' . esc_html( $product_id ) . '. Run sync_products.py to populate the database.</p>';
    }

    $similar  = cbp_get_similar( $product_id, $product, CBP_SIMILAR_COUNT );
    $price    = cbp_get_current_price( $product_id );

    cbp_enqueue_assets();

    $chart_id = 'cbp-radar-' . esc_attr( $product_id ) . '-' . wp_rand( 1000, 9999 );

    $flavor_data = wp_json_encode( [
        (int) $product['acidity'],
        (int) $product['body'],
        (int) $product['sweetness'],
        (int) $product['bitterness'],
        (int) $product['roast_intensity'],
    ] );

    $brew_methods  = cbp_decode_json_array( $product['best_brew_methods'] );
    $flavor_notes  = cbp_decode_json_array( $product['flavor_notes'] );
    $affiliate_url = cbp_build_affiliate_url( $product );

    ob_start();
    cbp_render_styles();
    ?>

<div class="cbp-card" id="cbp-<?php echo esc_attr( $product_id ); ?>">

    <!-- ── Header ───────────────────────────────────────────── -->
    <div class="cbp-header">
        <div class="cbp-header-meta">
            <span class="cbp-roast-badge cbp-roast-<?php echo esc_attr( strtolower( str_replace( [ ' ', '-' ], '', $product['roast_level'] ?? '' ) ) ); ?>">
                <?php echo esc_html( $product['roast_level'] ?? '' ); ?>
            </span>
            <?php if ( $product['brand'] ) : ?>
            <span class="cbp-brand"><?php echo esc_html( $product['brand'] ); ?></span>
            <?php endif; ?>
        </div>
        <h2 class="cbp-product-name"><?php echo esc_html( $product['name'] ); ?></h2>
        <?php if ( $product['origin'] ) : ?>
        <p class="cbp-origin">
            <svg class="cbp-icon" viewBox="0 0 16 16" aria-hidden="true"><path d="M8 0a8 8 0 1 0 0 16A8 8 0 0 0 8 0zm0 14.5A6.5 6.5 0 1 1 8 1.5a6.5 6.5 0 0 1 0 13zm.75-9.25v3.5l3 1.75-.5.87-3.5-2V5.25h1z" fill="currentColor"/></svg>
            <?php echo esc_html( $product['origin'] ); ?>
        </p>
        <?php endif; ?>
    </div>

    <!-- ── Body: chart + specs ──────────────────────────────── -->
    <div class="cbp-body">

        <!-- Radar chart -->
        <div class="cbp-chart-wrap">
            <div class="cbp-chart-inner">
                <canvas id="<?php echo esc_attr( $chart_id ); ?>"
                        aria-label="Flavor profile radar chart for <?php echo esc_attr( $product['name'] ); ?>"
                        role="img"></canvas>
            </div>
            <?php if ( $price !== null ) : ?>
            <div class="cbp-price-pill">
                <span class="cbp-price-label">Current price</span>
                <span class="cbp-price-value">$<?php echo esc_html( number_format( $price, 2 ) ); ?></span>
            </div>
            <?php endif; ?>
        </div>

        <!-- Specs -->
        <div class="cbp-specs-wrap">

            <!-- Flavor dimension bars -->
            <div class="cbp-dims" aria-label="Flavor dimensions">
                <?php
                $dims = [
                    'Acidity'        => (int) $product['acidity'],
                    'Body'           => (int) $product['body'],
                    'Sweetness'      => (int) $product['sweetness'],
                    'Bitterness'     => (int) $product['bitterness'],
                    'Roast Intensity' => (int) $product['roast_intensity'],
                ];
                foreach ( $dims as $label => $val ) :
                    $pct = ( $val / 5 ) * 100;
                    ?>
                <div class="cbp-dim-row">
                    <span class="cbp-dim-label"><?php echo esc_html( $label ); ?></span>
                    <div class="cbp-dim-track" role="meter" aria-valuenow="<?php echo esc_attr( $val ); ?>" aria-valuemin="0" aria-valuemax="5">
                        <div class="cbp-dim-fill" style="width:<?php echo esc_attr( $pct ); ?>%"></div>
                    </div>
                    <span class="cbp-dim-val"><?php echo esc_html( $val ); ?>/5</span>
                </div>
                <?php endforeach; ?>
            </div>

            <!-- Spec table -->
            <table class="cbp-spec-table" aria-label="Product specifications">
                <tbody>
                    <?php if ( $product['process_method'] ) : ?>
                    <tr>
                        <th scope="row">Process</th>
                        <td><?php echo esc_html( $product['process_method'] ); ?></td>
                    </tr>
                    <?php endif; ?>
                    <?php if ( $product['weight_oz'] ) : ?>
                    <tr>
                        <th scope="row">Weight</th>
                        <td><?php echo esc_html( $product['weight_oz'] ); ?> oz</td>
                    </tr>
                    <?php endif; ?>
                    <?php if ( $price !== null && $product['weight_oz'] ) : ?>
                    <tr>
                        <th scope="row">Price / oz</th>
                        <td>$<?php echo esc_html( number_format( $price / $product['weight_oz'], 3 ) ); ?></td>
                    </tr>
                    <?php endif; ?>
                    <?php if ( ! empty( $brew_methods ) ) : ?>
                    <tr>
                        <th scope="row">Best for</th>
                        <td><?php echo esc_html( implode( ', ', $brew_methods ) ); ?></td>
                    </tr>
                    <?php endif; ?>
                </tbody>
            </table>

            <!-- Flavor note tags -->
            <?php if ( ! empty( $flavor_notes ) ) : ?>
            <div class="cbp-tags" aria-label="Flavor notes">
                <?php foreach ( $flavor_notes as $note ) : ?>
                <span class="cbp-tag"><?php echo esc_html( $note ); ?></span>
                <?php endforeach; ?>
            </div>
            <?php endif; ?>

            <!-- CTA -->
            <?php if ( $affiliate_url ) : ?>
            <a href="<?php echo esc_url( $affiliate_url ); ?>"
               class="cbp-cta"
               target="_blank"
               rel="nofollow sponsored noopener noreferrer">
                Check Price →
            </a>
            <?php endif; ?>

        </div>
    </div>

    <!-- ── Similar beans ────────────────────────────────────── -->
    <?php if ( ! empty( $similar ) ) : ?>
    <div class="cbp-similar">
        <h3 class="cbp-similar-heading">Similar beans</h3>
        <div class="cbp-similar-grid">
            <?php foreach ( $similar as $sim ) :
                $sim_brew  = cbp_decode_json_array( $sim['best_brew_methods'] );
                $sim_notes = cbp_decode_json_array( $sim['flavor_notes'] );
                $sim_url   = cbp_build_affiliate_url( $sim );
                $sim_dims  = [
                    (int) $sim['acidity'],
                    (int) $sim['body'],
                    (int) $sim['sweetness'],
                    (int) $sim['bitterness'],
                    (int) $sim['roast_intensity'],
                ];
                $sim_chart_id = 'cbp-sim-' . esc_attr( $sim['id'] ) . '-' . wp_rand( 1000, 9999 );
                ?>
            <div class="cbp-sim-card">
                <div class="cbp-sim-chart-wrap">
                    <canvas id="<?php echo esc_attr( $sim_chart_id ); ?>"
                            aria-label="Flavor radar for <?php echo esc_attr( $sim['name'] ); ?>"
                            role="img"></canvas>
                </div>
                <div class="cbp-sim-info">
                    <span class="cbp-sim-roast"><?php echo esc_html( $sim['roast_level'] ?? '' ); ?></span>
                    <p class="cbp-sim-name"><?php echo esc_html( $sim['name'] ); ?></p>
                    <?php if ( ! empty( $sim_notes ) ) : ?>
                    <p class="cbp-sim-notes"><?php echo esc_html( implode( ' · ', array_slice( $sim_notes, 0, 3 ) ) ); ?></p>
                    <?php endif; ?>
                    <?php if ( $sim_url ) : ?>
                    <a href="<?php echo esc_url( $sim_url ); ?>"
                       class="cbp-sim-link"
                       target="_blank"
                       rel="nofollow sponsored noopener noreferrer">View →</a>
                    <?php endif; ?>
                </div>
                <script>
                (function() {
                    function initSim_<?php echo esc_js( str_replace( '-', '_', $sim_chart_id ) ); ?>() {
                        var c = document.getElementById(<?php echo wp_json_encode( $sim_chart_id ); ?>);
                        if ( !c || typeof Chart === 'undefined' ) { setTimeout(initSim_<?php echo esc_js( str_replace( '-', '_', $sim_chart_id ) ); ?>, 200); return; }
                        new Chart(c.getContext('2d'), <?php echo cbp_radar_config( $sim_dims, $sim['name'], true ); ?>);
                    }
                    initSim_<?php echo esc_js( str_replace( '-', '_', $sim_chart_id ) ); ?>();
                })();
                </script>
            </div>
            <?php endforeach; ?>
        </div>
    </div>
    <?php endif; ?>

    <p class="cbp-disclosure">This profile card contains affiliate links. We may earn commissions from qualifying purchases.</p>

</div><!-- .cbp-card -->

<script>
(function() {
    function cbpInitRadar() {
        var c = document.getElementById(<?php echo wp_json_encode( $chart_id ); ?>);
        if ( !c || typeof Chart === 'undefined' ) { setTimeout(cbpInitRadar, 200); return; }
        new Chart(c.getContext('2d'), <?php echo cbp_radar_config( array_values( $dims ), $product['name'], false ); ?>);
    }
    cbpInitRadar();
})();
</script>

    <?php
    return ob_get_clean();
}

// ---------------------------------------------------------------------------
// Chart config builder
// ---------------------------------------------------------------------------

function cbp_radar_config( array $data, string $label, bool $mini ): string {
    $labels = wp_json_encode( [ 'Acidity', 'Body', 'Sweetness', 'Bitterness', 'Roast' ] );
    $data_json = wp_json_encode( $data );
    $label_json = wp_json_encode( $label );

    $font_size   = $mini ? 9 : 11;
    $point_radius = $mini ? 2 : 3;

    return '{
        type: "radar",
        data: {
            labels: ' . $labels . ',
            datasets: [{
                label: ' . $label_json . ',
                data: ' . $data_json . ',
                borderColor: "rgba(200, 112, 42, 0.9)",
                backgroundColor: "rgba(200, 112, 42, 0.15)",
                borderWidth: ' . ( $mini ? 1.5 : 2 ) . ',
                pointBackgroundColor: "rgba(200, 112, 42, 1)",
                pointRadius: ' . $point_radius . ',
                pointHoverRadius: ' . ( $point_radius + 2 ) . '
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { display: false },
                tooltip: { enabled: ' . ( $mini ? 'false' : 'true' ) . ' }
            },
            scales: {
                r: {
                    min: 0,
                    max: 5,
                    ticks: {
                        stepSize: 1,
                        display: ' . ( $mini ? 'false' : 'true' ) . ',
                        font: { size: ' . $font_size . ' },
                        color: "#8a7060",
                        backdropColor: "transparent"
                    },
                    grid: { color: "rgba(138,112,96,0.25)" },
                    angleLines: { color: "rgba(138,112,96,0.3)" },
                    pointLabels: {
                        font: { size: ' . $font_size . ' },
                        color: "#5c4033"
                    }
                }
            }
        }
    }';
}

// ---------------------------------------------------------------------------
// Styles (output once per page)
// ---------------------------------------------------------------------------

function cbp_render_styles(): void {
    static $rendered = false;
    if ( $rendered ) return;
    $rendered = true;
    ?>
<style>
.cbp-card {
    --cbp-bg:        #faf7f4;
    --cbp-surface:   #fff;
    --cbp-border:    #e8ddd5;
    --cbp-accent:    #c8702a;
    --cbp-accent-dk: #a35520;
    --cbp-text:      #2d1f0e;
    --cbp-muted:     #7a6050;
    --cbp-tag-bg:    #f2ebe4;
    --cbp-radius:    10px;
    font-family: Georgia, 'Times New Roman', serif;
    background: var(--cbp-bg);
    border: 1px solid var(--cbp-border);
    border-radius: var(--cbp-radius);
    overflow: hidden;
    margin: 2em 0;
    box-shadow: 0 2px 12px rgba(45,31,14,.08);
}
.cbp-header {
    background: var(--cbp-surface);
    padding: 1.5em 1.75em 1.25em;
    border-bottom: 1px solid var(--cbp-border);
}
.cbp-header-meta {
    display: flex;
    align-items: center;
    gap: .6em;
    margin-bottom: .5em;
    flex-wrap: wrap;
}
.cbp-roast-badge {
    display: inline-block;
    font-family: 'Helvetica Neue', Arial, sans-serif;
    font-size: .68em;
    font-weight: 700;
    letter-spacing: .08em;
    text-transform: uppercase;
    padding: .2em .6em;
    border-radius: 3px;
    background: var(--cbp-accent);
    color: #fff;
}
.cbp-roast-badge.cbp-roast-light          { background: #c5a35c; }
.cbp-roast-badge.cbp-roast-lightmedium    { background: #b8863a; }
.cbp-roast-badge.cbp-roast-medium         { background: #c8702a; }
.cbp-roast-badge.cbp-roast-mediumdark     { background: #8b4513; }
.cbp-roast-badge.cbp-roast-dark           { background: #4a2008; }
.cbp-brand {
    font-family: 'Helvetica Neue', Arial, sans-serif;
    font-size: .75em;
    color: var(--cbp-muted);
    letter-spacing: .03em;
}
.cbp-product-name {
    font-size: 1.45em;
    font-weight: normal;
    color: var(--cbp-text);
    margin: 0 0 .3em;
    line-height: 1.2;
}
.cbp-origin {
    display: flex;
    align-items: center;
    gap: .35em;
    font-family: 'Helvetica Neue', Arial, sans-serif;
    font-size: .82em;
    color: var(--cbp-muted);
    margin: 0;
}
.cbp-icon {
    width: 12px;
    height: 12px;
    flex-shrink: 0;
    opacity: .7;
}
.cbp-body {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0;
}
@media (max-width: 640px) {
    .cbp-body { grid-template-columns: 1fr; }
}
.cbp-chart-wrap {
    background: #1e1108;
    padding: 1.5em 1.25em 1em;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 1em;
}
.cbp-chart-inner {
    width: 100%;
    max-width: 260px;
}
.cbp-chart-inner canvas {
    display: block;
    width: 100% !important;
    height: auto !important;
}
.cbp-price-pill {
    display: flex;
    flex-direction: column;
    align-items: center;
    background: rgba(200,112,42,.15);
    border: 1px solid rgba(200,112,42,.35);
    border-radius: 6px;
    padding: .5em 1.2em;
}
.cbp-price-label {
    font-family: 'Helvetica Neue', Arial, sans-serif;
    font-size: .68em;
    letter-spacing: .07em;
    text-transform: uppercase;
    color: rgba(245,237,227,.55);
}
.cbp-price-value {
    font-size: 1.3em;
    font-weight: 700;
    color: #f5ede3;
    letter-spacing: .02em;
}
.cbp-specs-wrap {
    padding: 1.5em 1.75em;
    display: flex;
    flex-direction: column;
    gap: 1.25em;
}
.cbp-dims { display: flex; flex-direction: column; gap: .5em; }
.cbp-dim-row {
    display: grid;
    grid-template-columns: 100px 1fr 36px;
    align-items: center;
    gap: .5em;
}
.cbp-dim-label {
    font-family: 'Helvetica Neue', Arial, sans-serif;
    font-size: .76em;
    color: var(--cbp-muted);
    letter-spacing: .02em;
}
.cbp-dim-track {
    height: 6px;
    background: #e8ddd5;
    border-radius: 3px;
    overflow: hidden;
}
.cbp-dim-fill {
    height: 100%;
    background: linear-gradient(90deg, #c8702a, #e8962a);
    border-radius: 3px;
    transition: width .4s ease;
}
.cbp-dim-val {
    font-family: 'Helvetica Neue', Arial, sans-serif;
    font-size: .72em;
    color: var(--cbp-muted);
    text-align: right;
}
.cbp-spec-table {
    width: 100%;
    border-collapse: collapse;
    font-size: .85em;
}
.cbp-spec-table th,
.cbp-spec-table td {
    padding: .45em .25em;
    border-bottom: 1px solid var(--cbp-border);
    text-align: left;
    vertical-align: top;
}
.cbp-spec-table th {
    font-family: 'Helvetica Neue', Arial, sans-serif;
    font-weight: 600;
    color: var(--cbp-muted);
    width: 90px;
    font-size: .9em;
}
.cbp-spec-table td { color: var(--cbp-text); }
.cbp-spec-table tr:last-child th,
.cbp-spec-table tr:last-child td { border-bottom: none; }
.cbp-tags {
    display: flex;
    flex-wrap: wrap;
    gap: .4em;
}
.cbp-tag {
    display: inline-block;
    font-family: 'Helvetica Neue', Arial, sans-serif;
    font-size: .75em;
    background: var(--cbp-tag-bg);
    color: var(--cbp-accent-dk);
    padding: .25em .65em;
    border-radius: 20px;
    border: 1px solid #ddd0c5;
    letter-spacing: .02em;
}
.cbp-cta {
    display: inline-block;
    background: var(--cbp-accent);
    color: #fff !important;
    text-decoration: none !important;
    font-family: 'Helvetica Neue', Arial, sans-serif;
    font-size: .85em;
    font-weight: 600;
    letter-spacing: .04em;
    padding: .65em 1.4em;
    border-radius: 5px;
    transition: background .2s;
    align-self: flex-start;
}
.cbp-cta:hover { background: var(--cbp-accent-dk); }
/* Similar beans */
.cbp-similar {
    border-top: 1px solid var(--cbp-border);
    padding: 1.5em 1.75em;
    background: var(--cbp-surface);
}
.cbp-similar-heading {
    font-size: .8em;
    font-family: 'Helvetica Neue', Arial, sans-serif;
    font-weight: 700;
    letter-spacing: .1em;
    text-transform: uppercase;
    color: var(--cbp-muted);
    margin: 0 0 1em;
}
.cbp-similar-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1em;
}
@media (max-width: 640px) {
    .cbp-similar-grid { grid-template-columns: 1fr; }
}
.cbp-sim-card {
    border: 1px solid var(--cbp-border);
    border-radius: 8px;
    overflow: hidden;
    background: var(--cbp-bg);
}
.cbp-sim-chart-wrap {
    background: #1e1108;
    padding: .75em;
}
.cbp-sim-chart-wrap canvas {
    display: block;
    width: 100% !important;
    height: auto !important;
    max-height: 120px;
}
.cbp-sim-info {
    padding: .75em 1em;
    display: flex;
    flex-direction: column;
    gap: .3em;
}
.cbp-sim-roast {
    font-family: 'Helvetica Neue', Arial, sans-serif;
    font-size: .65em;
    font-weight: 700;
    letter-spacing: .08em;
    text-transform: uppercase;
    color: var(--cbp-accent);
}
.cbp-sim-name {
    font-size: .9em;
    color: var(--cbp-text);
    margin: 0;
    line-height: 1.3;
}
.cbp-sim-notes {
    font-family: 'Helvetica Neue', Arial, sans-serif;
    font-size: .75em;
    color: var(--cbp-muted);
    margin: 0;
}
.cbp-sim-link {
    font-family: 'Helvetica Neue', Arial, sans-serif;
    font-size: .78em;
    font-weight: 600;
    color: var(--cbp-accent) !important;
    text-decoration: none !important;
    margin-top: .25em;
}
.cbp-sim-link:hover { color: var(--cbp-accent-dk) !important; }
.cbp-disclosure {
    font-family: 'Helvetica Neue', Arial, sans-serif;
    font-size: .72em;
    color: #aaa;
    padding: .6em 1.75em;
    margin: 0;
    border-top: 1px solid var(--cbp-border);
    background: var(--cbp-surface);
}
.cbp-error {
    font-family: 'Helvetica Neue', Arial, sans-serif;
    color: #c0392b;
    background: #fdf0ef;
    border: 1px solid #f5c6c4;
    border-radius: 5px;
    padding: .75em 1em;
    font-size: .9em;
}
</style>
    <?php
}

// ---------------------------------------------------------------------------
// Asset enqueueing (Chart.js — shared handle with coffee-price-chart plugin)
// ---------------------------------------------------------------------------

function cbp_enqueue_assets(): void {
    if ( ! wp_script_is( 'chartjs', 'enqueued' ) ) {
        wp_enqueue_script(
            'chartjs',
            'https://cdn.jsdelivr.net/npm/chart.js@4.4.2/dist/chart.umd.min.js',
            [],
            '4.4.2',
            true
        );
    }
}

// ---------------------------------------------------------------------------
// Database queries
// ---------------------------------------------------------------------------

function cbp_get_db(): ?PDO {
    if ( ! file_exists( CBP_DB_PATH ) ) {
        error_log( 'CBP plugin: SQLite DB not found at ' . CBP_DB_PATH );
        return null;
    }
    try {
        $pdo = new PDO( 'sqlite:' . CBP_DB_PATH );
        $pdo->setAttribute( PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION );
        $pdo->setAttribute( PDO::ATTR_DEFAULT_FETCH_MODE, PDO::FETCH_ASSOC );
        return $pdo;
    } catch ( PDOException $e ) {
        error_log( 'CBP plugin PDO error: ' . $e->getMessage() );
        return null;
    }
}

function cbp_get_product( string $product_id ): ?array {
    $pdo = cbp_get_db();
    if ( ! $pdo ) return null;
    try {
        $stmt = $pdo->prepare(
            'SELECT * FROM products WHERE id = ? LIMIT 1'
        );
        $stmt->execute( [ $product_id ] );
        $row = $stmt->fetch();
        return $row ?: null;
    } catch ( PDOException $e ) {
        error_log( 'CBP cbp_get_product error: ' . $e->getMessage() );
        return null;
    }
}

function cbp_get_similar( string $product_id, array $product, int $limit ): array {
    $pdo = cbp_get_db();
    if ( ! $pdo ) return [];
    try {
        $rows = $pdo->query(
            'SELECT * FROM products WHERE id != ' . $pdo->quote( $product_id ) .
            ' AND acidity IS NOT NULL AND body IS NOT NULL'
        )->fetchAll();
    } catch ( PDOException $e ) {
        error_log( 'CBP cbp_get_similar error: ' . $e->getMessage() );
        return [];
    }

    if ( empty( $rows ) ) return [];

    $a = (int) $product['acidity'];
    $b = (int) $product['body'];
    $s = (int) $product['sweetness'];
    $bi = (int) $product['bitterness'];
    $ri = (int) $product['roast_intensity'];

    // Euclidean distance across 5 flavor dimensions
    $distances = [];
    foreach ( $rows as $row ) {
        $dist = sqrt(
            pow( $a  - (int) $row['acidity'], 2 ) +
            pow( $b  - (int) $row['body'], 2 ) +
            pow( $s  - (int) $row['sweetness'], 2 ) +
            pow( $bi - (int) $row['bitterness'], 2 ) +
            pow( $ri - (int) $row['roast_intensity'], 2 )
        );
        $distances[] = [ 'dist' => $dist, 'row' => $row ];
    }

    usort( $distances, fn( $x, $y ) => $x['dist'] <=> $y['dist'] );

    return array_map(
        fn( $d ) => $d['row'],
        array_slice( $distances, 0, $limit )
    );
}

function cbp_get_current_price( string $product_id ): ?float {
    $pdo = cbp_get_db();
    if ( ! $pdo ) return null;
    try {
        $stmt = $pdo->prepare(
            'SELECT price FROM price_history WHERE product_id = ? ORDER BY checked_at DESC LIMIT 1'
        );
        $stmt->execute( [ $product_id ] );
        $row = $stmt->fetch();
        return $row ? (float) $row['price'] : null;
    } catch ( PDOException $e ) {
        return null;
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function cbp_decode_json_array( ?string $json ): array {
    if ( ! $json ) return [];
    $decoded = json_decode( $json, true );
    return is_array( $decoded ) ? $decoded : [];
}

function cbp_build_affiliate_url( array $product ): string {
    $asin = $product['amazon_asin'] ?? '';
    $tag  = $product['affiliate_tag'] ?? '';
    if ( $asin && $tag ) {
        return "https://www.amazon.com/dp/{$asin}?tag={$tag}";
    }
    if ( $product['roaster_url'] ?? '' ) {
        $url = $product['roaster_url'];
        if ( $tag ) {
            $sep = strpos( $url, '?' ) !== false ? '&' : '?';
            return "{$url}{$sep}ref={$tag}";
        }
        return $url;
    }
    return '';
}
