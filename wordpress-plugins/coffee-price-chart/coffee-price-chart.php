<?php
/**
 * Plugin Name: Coffee Price Chart
 * Plugin URI:  https://github.com/JPerreault01/Coffee-Bean-Scraper
 * Description: Renders a Chart.js price history chart for tracked coffee beans. Usage: [coffee_price_chart product_id="lavazza-super-crema"]
 * Version:     2.0.0
 * Author:      JPerreault01
 * License:     GPL2
 *
 * File: wordpress-plugins/coffee-price-chart/coffee-price-chart.php
 * Deploy to: /var/www/coffeebeans/wp-content/plugins/coffee-price-chart/coffee-price-chart.php
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

define( 'CPC_DB_PATH',       '/opt/data/prices.db' );
define( 'CPC_DAYS',          90 );
define( 'CPC_DEAL_THRESHOLD', 5.0 ); // % below avg to flag as deal

// ---------------------------------------------------------------------------
// Shortcode registration
// ---------------------------------------------------------------------------

add_shortcode( 'coffee_price_chart', 'cpc_render_shortcode' );

function cpc_render_shortcode( $atts ): string {
    static $styles_done = false;

    $atts       = shortcode_atts( [ 'product_id' => '' ], $atts, 'coffee_price_chart' );
    $product_id = sanitize_text_field( $atts['product_id'] );

    if ( empty( $product_id ) ) {
        return '<p class="cpc-no-data">coffee_price_chart: product_id is required.</p>';
    }

    $rows = cpc_fetch_price_history( $product_id, CPC_DAYS );

    if ( empty( $rows ) ) {
        return '<p class="cpc-no-data">Price history coming soon &mdash; check back after the next daily update.</p>';
    }

    // ---------------------------------------------------------------------------
    // Compute stats
    // ---------------------------------------------------------------------------

    $prices_arr  = array_map( fn( $r ) => (float) $r['price'], $rows );
    $current     = end( $prices_arr );
    $min_price   = min( $prices_arr );
    $max_price   = max( $prices_arr );
    $avg_price   = array_sum( $prices_arr ) / count( $prices_arr );
    $deal_pct    = $avg_price > 0 ? ( ( $avg_price - $current ) / $avg_price * 100 ) : 0;
    $is_deal     = $deal_pct  >=  CPC_DEAL_THRESHOLD;
    $high_pct    = $avg_price > 0 ? ( ( $current - $avg_price ) / $avg_price * 100 ) : 0;
    $is_high     = $high_pct >= CPC_DEAL_THRESHOLD;

    // ---------------------------------------------------------------------------
    // Build JS arrays
    // ---------------------------------------------------------------------------

    $chart_id    = 'cpc-' . esc_attr( $product_id ) . '-' . wp_rand( 1000, 9999 );
    $js_labels   = [];
    $js_prices   = [];
    $js_per_oz   = [];

    foreach ( $rows as $row ) {
        $js_labels[]  = date( 'M j', strtotime( $row['checked_at'] ) );
        $js_prices[]  = (float) $row['price'];
        $js_per_oz[]  = $row['price_per_oz'] !== null ? (float) $row['price_per_oz'] : null;
    }

    $labels_json  = wp_json_encode( $js_labels );
    $prices_json  = wp_json_encode( $js_prices );
    $per_oz_json  = wp_json_encode( $js_per_oz );
    $avg_json     = wp_json_encode( round( $avg_price, 2 ) );
    $current_json = wp_json_encode( round( $current, 2 ) );
    $day_count    = count( $rows );

    ob_start();

    // Styles — injected once per page, scoped to .cpc-wrapper
    if ( ! $styles_done ) {
        $styles_done = true;
        ?>
        <style>
        .cpc-wrapper { max-width: 100%; }

        /* Badge */
        .cpc-badge {
            display: inline-flex; align-items: center; gap: var(--space-2, .5rem);
            border-radius: 4px; padding: var(--space-2, .5rem) var(--space-3, .75rem);
            font-family: var(--font-mono, monospace); font-size: var(--text-xs, .75rem);
            margin-bottom: var(--space-4, 1rem);
            background: var(--cbi-bg-2, #f2ece3);
            border: 1px solid var(--cbi-border, #d4c9bb);
            color: var(--cbi-text-muted, #5c5048);
        }
        .cpc-badge--deal {
            background: rgba(45, 106, 45, 0.09);
            border-color: rgba(45, 106, 45, 0.28);
            color: var(--cbi-positive, #2d6a2d);
            font-weight: 500;
        }
        .cpc-badge--high {
            background: var(--cbi-accent-bg, #fdf1ee);
            border-color: rgba(158, 43, 14, 0.28);
            color: var(--cbi-accent, #9e2b0e);
        }

        /* Stats strip */
        .cpc-stats {
            display: grid; grid-template-columns: repeat(4, 1fr);
            gap: var(--space-3, .75rem); margin-bottom: var(--space-5, 1.25rem);
        }
        @media (max-width: 520px) { .cpc-stats { grid-template-columns: repeat(2, 1fr); } }
        .cpc-stat {
            background: var(--cbi-surface, #ede8df);
            border: 1px solid var(--cbi-border, #d4c9bb);
            border-radius: 6px;
            padding: var(--space-3, .75rem) var(--space-4, 1rem);
            text-align: center;
        }
        .cpc-stat__label {
            font-family: var(--font-mono, monospace);
            font-size: var(--text-xs, .75rem);
            color: var(--cbi-text-dim, #73655b);
            text-transform: uppercase; letter-spacing: .05em;
            margin-bottom: var(--space-1, .25rem);
        }
        .cpc-stat__value {
            font-family: var(--font-mono, monospace);
            font-size: var(--text-lg, 1.125rem); font-weight: 500;
            color: var(--cbi-text, #1c1410);
            font-variant-numeric: tabular-nums;
        }
        .cpc-stat--current .cpc-stat__value { color: var(--cbi-accent, #9e2b0e); }
        .cpc-stat--deal    .cpc-stat__value { color: var(--cbi-positive, #2d6a2d); }

        /* Chart canvas container */
        .cpc-chart-area {
            position: relative; height: 280px;
            margin-bottom: var(--space-5, 1.25rem);
        }
        .cpc-chart-area canvas { position: absolute; inset: 0; }

        /* History table (inside <details>) */
        .cpc-details summary {
            font-family: var(--font-mono, monospace);
            font-size: var(--text-xs, .75rem);
            color: var(--cbi-text-dim, #73655b);
            cursor: pointer; padding: var(--space-2, .5rem) 0;
            list-style: none; display: inline-flex; align-items: center; gap: var(--space-2, .5rem);
        }
        .cpc-details summary::marker,
        .cpc-details summary::-webkit-details-marker { display: none; }
        .cpc-details summary:hover { color: var(--cbi-accent, #9e2b0e); }
        .cpc-details[open] summary .cpc-details__arrow { transform: rotate(90deg); }
        .cpc-details__arrow { display: inline-block; transition: transform .15s; }
        .cpc-table-wrap { margin-top: var(--space-3, .75rem); overflow-x: auto; }
        .cpc-table {
            width: 100%; border-collapse: collapse;
            font-size: var(--text-sm, .875rem);
            font-family: var(--font-mono, monospace);
        }
        .cpc-table thead th {
            padding: var(--space-2, .5rem) var(--space-3, .75rem);
            text-align: left; border-bottom: 2px solid var(--cbi-border, #d4c9bb);
            background: var(--cbi-bg-2, #f2ece3);
            color: var(--cbi-text-dim, #73655b); font-weight: 500;
            font-size: var(--text-xs, .75rem); text-transform: uppercase; letter-spacing: .05em;
        }
        .cpc-table thead th:not(:first-child) { text-align: right; }
        .cpc-table tbody td {
            padding: var(--space-2, .5rem) var(--space-3, .75rem);
            border-bottom: 1px solid var(--cbi-border-light, #e2d8cc);
            color: var(--cbi-text-muted, #5c5048);
        }
        .cpc-table tbody td:not(:first-child) { text-align: right; font-variant-numeric: tabular-nums; }
        .cpc-table tbody tr:hover td { background: var(--cbi-bg-2, #f2ece3); }

        .cpc-no-data {
            color: var(--cbi-text-dim, #73655b); font-family: var(--font-mono, monospace);
            font-size: var(--text-sm, .875rem); padding: var(--space-4, 1rem);
            background: var(--cbi-bg-2, #f2ece3); border-radius: 4px;
        }
        </style>
        <?php
    }

    // ---------------------------------------------------------------------------
    // Deal / high-price badge
    // ---------------------------------------------------------------------------
    $badge = '';
    if ( $is_deal ) {
        $badge = sprintf(
            '<div class="cpc-badge cpc-badge--deal">&#9660;&nbsp; %.0f%% below %d-day average &mdash; historically low</div>',
            $deal_pct, CPC_DAYS
        );
    } elseif ( $is_high ) {
        $badge = sprintf(
            '<div class="cpc-badge cpc-badge--high">&#9650;&nbsp; %.0f%% above %d-day average</div>',
            $high_pct, CPC_DAYS
        );
    }
    ?>

    <div class="cpc-wrapper">

        <?php echo $badge; ?>

        <!-- Stats strip -->
        <div class="cpc-stats">
            <div class="cpc-stat<?php echo $is_deal ? ' cpc-stat--deal' : ' cpc-stat--current'; ?>">
                <div class="cpc-stat__label">Current</div>
                <div class="cpc-stat__value">$<?php echo number_format( $current, 2 ); ?></div>
            </div>
            <div class="cpc-stat">
                <div class="cpc-stat__label"><?php echo esc_html( CPC_DAYS ); ?>d Low</div>
                <div class="cpc-stat__value">$<?php echo number_format( $min_price, 2 ); ?></div>
            </div>
            <div class="cpc-stat">
                <div class="cpc-stat__label"><?php echo esc_html( CPC_DAYS ); ?>d High</div>
                <div class="cpc-stat__value">$<?php echo number_format( $max_price, 2 ); ?></div>
            </div>
            <div class="cpc-stat">
                <div class="cpc-stat__label"><?php echo esc_html( CPC_DAYS ); ?>d Avg</div>
                <div class="cpc-stat__value">$<?php echo number_format( $avg_price, 2 ); ?></div>
            </div>
        </div>

        <!-- Chart -->
        <div class="cpc-chart-area">
            <canvas id="<?php echo esc_attr( $chart_id ); ?>"
                    aria-label="Price history chart for <?php echo esc_attr( $product_id ); ?>"
                    role="img">
            </canvas>
        </div>

        <!-- Collapsible price history table -->
        <details class="cpc-details">
            <summary>
                <span class="cpc-details__arrow">&#9658;</span>
                Show price history (<?php echo esc_html( $day_count ); ?> days)
            </summary>
            <div class="cpc-table-wrap">
                <table class="cpc-table">
                    <thead>
                        <tr>
                            <th>Date</th>
                            <th>Price</th>
                            <th>Per oz</th>
                        </tr>
                    </thead>
                    <tbody>
                        <?php foreach ( array_reverse( $rows ) as $row ) : ?>
                        <tr>
                            <td><?php echo esc_html( date( 'M j, Y', strtotime( $row['checked_at'] ) ) ); ?></td>
                            <td>$<?php echo esc_html( number_format( (float) $row['price'], 2 ) ); ?></td>
                            <td>
                                <?php echo $row['price_per_oz'] !== null
                                    ? '$' . esc_html( number_format( (float) $row['price_per_oz'], 3 ) )
                                    : '&mdash;'; ?>
                            </td>
                        </tr>
                        <?php endforeach; ?>
                    </tbody>
                </table>
            </div>
        </details>

    </div>

    <script>
    (function() {
        function cpcInit() {
            var ctx = document.getElementById(<?php echo wp_json_encode( $chart_id ); ?>);
            if ( ! ctx || typeof Chart === 'undefined' ) {
                setTimeout( cpcInit, 200 );
                return;
            }

            var s        = getComputedStyle( document.documentElement );
            var accent   = s.getPropertyValue('--cbi-accent').trim()      || '#9e2b0e';
            var muted    = s.getPropertyValue('--cbi-text-muted').trim()   || '#5c5048';
            var dim      = s.getPropertyValue('--cbi-text-dim').trim()     || '#73655b';
            var border   = s.getPropertyValue('--cbi-border').trim()       || '#d4c9bb';
            var fontMono = s.getPropertyValue('--font-mono').trim()        || 'monospace';

            var labels    = <?php echo $labels_json; ?>;
            var prices    = <?php echo $prices_json; ?>;
            var perOz     = <?php echo $per_oz_json; ?>;
            var avgPrice  = <?php echo $avg_json; ?>;
            var pointR    = prices.length > 30 ? 0 : 3;

            new Chart( ctx.getContext('2d'), {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: 'Price',
                            data: prices,
                            borderColor: accent,
                            backgroundColor: 'rgba(158, 43, 14, 0.07)',
                            borderWidth: 2,
                            pointRadius: pointR,
                            pointHoverRadius: 5,
                            tension: 0.3,
                            fill: true,
                            yAxisID: 'yPrice',
                        },
                        {
                            label: 'Per oz',
                            data: perOz,
                            borderColor: muted,
                            backgroundColor: 'transparent',
                            borderWidth: 1.5,
                            borderDash: [5, 4],
                            pointRadius: 0,
                            pointHoverRadius: 4,
                            tension: 0.3,
                            fill: false,
                            yAxisID: 'yPerOz',
                            spanGaps: true,
                        },
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: 'index', intersect: false },
                    animation: {
                        duration: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 500
                    },
                    plugins: {
                        legend: {
                            position: 'top',
                            labels: {
                                font: { family: fontMono, size: 11 },
                                color: dim,
                                boxWidth: 20,
                                padding: 14,
                            }
                        },
                        annotation: {
                            annotations: {
                                avgLine: {
                                    type: 'line',
                                    yMin: avgPrice,
                                    yMax: avgPrice,
                                    yScaleID: 'yPrice',
                                    borderColor: 'rgba(92, 80, 72, 0.40)',
                                    borderWidth: 1,
                                    borderDash: [4, 4],
                                    label: {
                                        display: true,
                                        content: 'Avg $' + avgPrice.toFixed(2),
                                        position: 'start',
                                        backgroundColor: 'rgba(92,80,72,0.70)',
                                        color: '#fff',
                                        font: { size: 10, family: fontMono },
                                        padding: { x: 6, y: 3 },
                                    }
                                }
                            }
                        },
                        tooltip: {
                            backgroundColor: 'rgba(28,20,16,0.90)',
                            titleFont: { family: fontMono, size: 11 },
                            bodyFont:  { family: fontMono, size: 11 },
                            padding: 10,
                            callbacks: {
                                label: function( ctx ) {
                                    var val = ctx.parsed.y;
                                    if ( val === null || val === undefined ) return null;
                                    var suffix = ctx.datasetIndex === 0 ? '/bag' : '/oz';
                                    var dec    = ctx.datasetIndex === 0 ? 2 : 3;
                                    return ' ' + ctx.dataset.label + ': $' + val.toFixed( dec ) + suffix;
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            ticks: {
                                maxTicksLimit: 10,
                                font: { family: fontMono, size: 10 },
                                color: dim,
                            },
                            grid: { color: 'rgba(212, 201, 187, 0.45)' }
                        },
                        yPrice: {
                            type: 'linear',
                            position: 'left',
                            title: {
                                display: true,
                                text: 'Price ($)',
                                font: { family: fontMono, size: 10 },
                                color: dim,
                            },
                            ticks: {
                                callback: function(v) { return '$' + v.toFixed(2); },
                                font: { family: fontMono, size: 10 },
                                color: dim,
                            },
                            grid: { color: 'rgba(212, 201, 187, 0.45)' }
                        },
                        yPerOz: {
                            type: 'linear',
                            position: 'right',
                            title: {
                                display: true,
                                text: 'Per oz ($)',
                                font: { family: fontMono, size: 10 },
                                color: dim,
                            },
                            ticks: {
                                callback: function(v) { return '$' + v.toFixed(3); },
                                font: { family: fontMono, size: 10 },
                                color: dim,
                            },
                            grid: { drawOnChartArea: false }
                        }
                    }
                }
            });
        }

        if ( typeof Chart !== 'undefined' ) {
            cpcInit();
        } else {
            window.addEventListener( 'load', cpcInit );
        }
    })();
    </script>

    <?php
    cpc_enqueue_chartjs();
    return ob_get_clean();
}

// ---------------------------------------------------------------------------
// Enqueue Chart.js (deferred, once per page)
// ---------------------------------------------------------------------------

function cpc_enqueue_chartjs(): void {
    if ( ! wp_script_is( 'chartjs', 'enqueued' ) ) {
        wp_enqueue_script(
            'chartjs',
            'https://cdn.jsdelivr.net/npm/chart.js@4.4.2/dist/chart.umd.min.js',
            [],
            '4.4.2',
            true
        );
        wp_enqueue_script(
            'chartjs-annotation',
            'https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@3.0.1/dist/chartjs-plugin-annotation.min.js',
            [ 'chartjs' ],
            '3.0.1',
            true
        );
    }
}

// ---------------------------------------------------------------------------
// Database query
// ---------------------------------------------------------------------------

function cpc_fetch_price_history( string $product_id, int $days ): array {
    if ( ! file_exists( CPC_DB_PATH ) ) {
        error_log( 'CPC plugin: SQLite DB not found at ' . CPC_DB_PATH );
        return [];
    }

    try {
        $pdo = new PDO( 'sqlite:' . CPC_DB_PATH );
        $pdo->setAttribute( PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION );

        $stmt = $pdo->prepare( "
            SELECT
                date(checked_at)   AS checked_at,
                AVG(price)         AS price,
                AVG(price_per_oz)  AS price_per_oz
            FROM price_history
            WHERE product_id = :pid
              AND checked_at >= date('now', :offset)
            GROUP BY date(checked_at)
            ORDER BY date(checked_at) ASC
        " );

        $stmt->execute( [
            ':pid'    => $product_id,
            ':offset' => '-' . $days . ' days',
        ] );

        return $stmt->fetchAll( PDO::FETCH_ASSOC );
    } catch ( PDOException $e ) {
        error_log( 'CPC plugin PDO error: ' . $e->getMessage() );
        return [];
    }
}
