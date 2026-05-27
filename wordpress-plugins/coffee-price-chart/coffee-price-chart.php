<?php
/**
 * Plugin Name: Coffee Price Chart
 * Plugin URI:  https://github.com/JPerreault01/Coffee-Bean-Scraper
 * Description: Renders a Chart.js price history chart for tracked coffee beans. Usage: [coffee_price_chart product_id="lavazza-super-crema"]
 * Version:     1.0.0
 * Author:      JPerreault01
 * License:     GPL2
 *
 * File: wordpress-plugins/coffee-price-chart/coffee-price-chart.php
 * Deploy to: /var/www/coffeebeans/wp-content/plugins/coffee-price-chart/coffee-price-chart.php
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

define( 'CPC_DB_PATH', '/opt/data/prices.db' );
define( 'CPC_DAYS',    90 );

// ---------------------------------------------------------------------------
// Shortcode registration
// ---------------------------------------------------------------------------

add_shortcode( 'coffee_price_chart', 'cpc_render_shortcode' );

function cpc_render_shortcode( $atts ): string {
    $atts = shortcode_atts( [ 'product_id' => '' ], $atts, 'coffee_price_chart' );
    $product_id = sanitize_text_field( $atts['product_id'] );

    if ( empty( $product_id ) ) {
        return '<p class="cpc-error">coffee_price_chart: product_id is required.</p>';
    }

    $rows = cpc_fetch_price_history( $product_id, CPC_DAYS );

    if ( empty( $rows ) ) {
        return '<p class="cpc-error">No price history found for product: ' . esc_html( $product_id ) . '</p>';
    }

    $chart_id  = 'cpc-' . esc_attr( $product_id ) . '-' . wp_rand( 1000, 9999 );
    $labels    = [];
    $prices    = [];
    $per_oz    = [];

    foreach ( $rows as $row ) {
        $labels[]  = esc_js( date( 'M j', strtotime( $row['checked_at'] ) ) );
        $prices[]  = (float) $row['price'];
        $per_oz[]  = $row['price_per_oz'] !== null ? (float) $row['price_per_oz'] : 'null';
    }

    $current_price = end( $prices );
    $labels_json   = wp_json_encode( $labels );
    $prices_json   = wp_json_encode( $prices );
    $per_oz_json   = wp_json_encode( $per_oz );

    ob_start();
    ?>
    <div class="cpc-wrapper" style="max-width:100%;overflow-x:auto;">
        <canvas id="<?php echo esc_attr( $chart_id ); ?>"
                style="width:100%;height:320px;display:block;"
                aria-label="Price history chart for <?php echo esc_attr( $product_id ); ?>"
                role="img">
        </canvas>
    </div>

    <div class="cpc-table-wrapper" style="margin-top:1.5em;overflow-x:auto;">
        <table class="cpc-table" style="width:100%;border-collapse:collapse;font-size:.9em;">
            <thead>
                <tr style="background:#f5f5f5;">
                    <th style="padding:8px 12px;text-align:left;border-bottom:2px solid #ddd;">Date</th>
                    <th style="padding:8px 12px;text-align:right;border-bottom:2px solid #ddd;">Price</th>
                    <th style="padding:8px 12px;text-align:right;border-bottom:2px solid #ddd;">Price / oz</th>
                </tr>
            </thead>
            <tbody>
                <?php foreach ( array_reverse( $rows ) as $row ) : ?>
                <tr style="border-bottom:1px solid #eee;">
                    <td style="padding:6px 12px;"><?php echo esc_html( date( 'M j, Y', strtotime( $row['checked_at'] ) ) ); ?></td>
                    <td style="padding:6px 12px;text-align:right;">$<?php echo esc_html( number_format( $row['price'], 2 ) ); ?></td>
                    <td style="padding:6px 12px;text-align:right;">
                        <?php echo $row['price_per_oz'] !== null
                            ? '$' . esc_html( number_format( $row['price_per_oz'], 3 ) )
                            : '—'; ?>
                    </td>
                </tr>
                <?php endforeach; ?>
            </tbody>
        </table>
    </div>

    <script>
    (function() {
        function cpcInitChart() {
            var ctx = document.getElementById(<?php echo wp_json_encode( $chart_id ); ?>);
            if (!ctx || typeof Chart === 'undefined') {
                setTimeout(cpcInitChart, 200);
                return;
            }

            var labels    = <?php echo $labels_json; ?>;
            var prices    = <?php echo $prices_json; ?>;
            var perOz     = <?php echo $per_oz_json; ?>;
            var currPrice = <?php echo json_encode( $current_price ); ?>;

            new Chart(ctx.getContext('2d'), {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: 'Price ($)',
                            data: prices,
                            borderColor: '#c0392b',
                            backgroundColor: 'rgba(192,57,43,0.08)',
                            borderWidth: 2,
                            pointRadius: 3,
                            tension: 0.3,
                            fill: true,
                            yAxisID: 'yPrice',
                        },
                        {
                            label: 'Price / oz ($)',
                            data: perOz,
                            borderColor: '#2980b9',
                            backgroundColor: 'transparent',
                            borderWidth: 2,
                            borderDash: [6, 4],
                            pointRadius: 2,
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
                    plugins: {
                        legend: { position: 'top' },
                        annotation: {
                            annotations: {
                                currentPrice: {
                                    type: 'line',
                                    yMin: currPrice,
                                    yMax: currPrice,
                                    yScaleID: 'yPrice',
                                    borderColor: 'rgba(192,57,43,0.5)',
                                    borderWidth: 1,
                                    borderDash: [4, 4],
                                    label: {
                                        display: true,
                                        content: 'Current: $' + currPrice.toFixed(2),
                                        position: 'end',
                                        backgroundColor: 'rgba(192,57,43,0.7)',
                                        color: '#fff',
                                        font: { size: 11 },
                                    }
                                }
                            }
                        },
                        tooltip: {
                            callbacks: {
                                label: function(ctx) {
                                    var val = ctx.parsed.y;
                                    if (val === null) return null;
                                    return ctx.dataset.label + ': $' + val.toFixed(ctx.datasetIndex === 0 ? 2 : 3);
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            ticks: { maxTicksLimit: 12 },
                            grid:  { display: false }
                        },
                        yPrice: {
                            type: 'linear',
                            position: 'left',
                            title: { display: true, text: 'Price ($)' },
                            ticks: { callback: v => '$' + v.toFixed(2) }
                        },
                        yPerOz: {
                            type: 'linear',
                            position: 'right',
                            title: { display: true, text: 'Per oz ($)' },
                            ticks: { callback: v => '$' + v.toFixed(3) },
                            grid: { drawOnChartArea: false }
                        }
                    }
                }
            });
        }
        cpcInitChart();
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
