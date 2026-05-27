<?php
/**
 * Plugin Name: Coffee Price Chart
 * Plugin URI: https://github.com/JPerreault01/Coffee-Bean-Scraper
 * Description: Displays a Chart.js price history chart for coffee products via shortcode. Usage: [coffee_price_chart product_id="lavazza-super-crema"]
 * Version: 1.0.0
 * Author: Coffee Beans Review Site
 * License: GPL2
 *
 * wordpress-plugins/coffee-price-chart/coffee-price-chart.php
 */

defined('ABSPATH') || exit;

define('CPCHART_DB_PATH', '/opt/data/prices.db');
define('CPCHART_HISTORY_DAYS', 90);

// ---------------------------------------------------------------------------
// Enqueue Chart.js (once per page, only when shortcode is present)
// ---------------------------------------------------------------------------

add_action('wp_enqueue_scripts', 'cpchart_register_scripts');

function cpchart_register_scripts() {
    wp_register_script(
        'chartjs',
        'https://cdn.jsdelivr.net/npm/chart.js@4.4.2/dist/chart.umd.min.js',
        [],
        '4.4.2',
        true
    );
    wp_register_script(
        'chartjs-annotation',
        'https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@3.0.1/dist/chartjs-plugin-annotation.min.js',
        ['chartjs'],
        '3.0.1',
        true
    );
}

// ---------------------------------------------------------------------------
// Data fetch from SQLite
// ---------------------------------------------------------------------------

function cpchart_get_price_data(string $product_id): array {
    if (!file_exists(CPCHART_DB_PATH)) {
        return [];
    }

    try {
        $db = new PDO('sqlite:' . CPCHART_DB_PATH);
        $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);

        $cutoff = date('Y-m-d', strtotime('-' . CPCHART_HISTORY_DAYS . ' days'));

        $stmt = $db->prepare("
            SELECT
                date(checked_at) AS day,
                AVG(price) AS avg_price,
                AVG(price_per_oz) AS avg_ppo,
                MIN(price) AS min_price
            FROM price_history
            WHERE product_id = :pid
              AND date(checked_at) >= :cutoff
            GROUP BY date(checked_at)
            ORDER BY day ASC
        ");
        $stmt->execute([':pid' => $product_id, ':cutoff' => $cutoff]);
        return $stmt->fetchAll(PDO::FETCH_ASSOC);

    } catch (PDOException $e) {
        error_log('CoffePriceChart DB error: ' . $e->getMessage());
        return [];
    }
}

// ---------------------------------------------------------------------------
// Shortcode
// ---------------------------------------------------------------------------

add_shortcode('coffee_price_chart', 'cpchart_render_shortcode');

function cpchart_render_shortcode(array $atts): string {
    $atts = shortcode_atts(['product_id' => ''], $atts);
    $product_id = sanitize_text_field($atts['product_id']);

    if (empty($product_id)) {
        return '<p class="cpchart-error">coffee_price_chart: product_id is required.</p>';
    }

    $rows = cpchart_get_price_data($product_id);

    if (empty($rows)) {
        return '<p class="cpchart-notice">No price history available yet for this product.</p>';
    }

    // Enqueue scripts now that we know the shortcode is used
    wp_enqueue_script('chartjs');
    wp_enqueue_script('chartjs-annotation');

    $labels       = [];
    $prices       = [];
    $prices_ppo   = [];
    $table_rows   = '';
    $current_price = null;

    foreach ($rows as $row) {
        $labels[]     = esc_js($row['day']);
        $price        = round((float) $row['avg_price'], 2);
        $ppo          = $row['avg_ppo'] !== null ? round((float) $row['avg_ppo'], 3) : null;
        $prices[]     = $price;
        $prices_ppo[] = $ppo;
        $current_price = $price;

        $ppo_cell = $ppo !== null ? '$' . number_format($ppo, 3) : '—';
        $table_rows .= sprintf(
            '<tr><td>%s</td><td>$%s</td><td>%s</td></tr>',
            esc_html($row['day']),
            esc_html(number_format($price, 2)),
            esc_html($ppo_cell)
        );
    }

    $chart_id     = 'cpchart_' . esc_attr($product_id) . '_' . wp_rand(1000, 9999);
    $labels_json  = json_encode($labels);
    $prices_json  = json_encode($prices);
    $ppo_json     = json_encode($prices_ppo);
    $current_price_val = $current_price !== null ? (float) $current_price : 0;

    ob_start();
    ?>
    <div class="cpchart-wrapper" style="width:100%;max-width:900px;margin:24px auto;">
        <canvas id="<?php echo esc_attr($chart_id); ?>" style="width:100%;height:380px;"></canvas>

        <h4 style="margin:24px 0 8px;font-size:15px;">Price History</h4>
        <div style="overflow-x:auto;">
            <table class="cpchart-table" style="width:100%;border-collapse:collapse;font-size:13px;">
                <thead>
                    <tr style="background:#f5f5f5;">
                        <th style="padding:8px 12px;text-align:left;border-bottom:1px solid #ddd;">Date</th>
                        <th style="padding:8px 12px;text-align:left;border-bottom:1px solid #ddd;">Price</th>
                        <th style="padding:8px 12px;text-align:left;border-bottom:1px solid #ddd;">Price / oz</th>
                    </tr>
                </thead>
                <tbody>
                    <?php echo $table_rows; ?>
                </tbody>
            </table>
        </div>
    </div>

    <script>
    (function() {
        function initChart_<?php echo esc_js($chart_id); ?>() {
            var ctx = document.getElementById(<?php echo json_encode($chart_id); ?>);
            if (!ctx) return;

            var labels      = <?php echo $labels_json; ?>;
            var prices      = <?php echo $prices_json; ?>;
            var ppoData     = <?php echo $ppo_json; ?>;
            var currentPrice = <?php echo json_encode($current_price_val); ?>;

            new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: 'Price ($)',
                            data: prices,
                            borderColor: '#c8681e',
                            backgroundColor: 'rgba(200,104,30,0.08)',
                            borderWidth: 2,
                            pointRadius: 3,
                            fill: true,
                            tension: 0.3,
                            yAxisID: 'yPrice'
                        },
                        {
                            label: 'Price / oz ($)',
                            data: ppoData,
                            borderColor: '#2c7bb6',
                            backgroundColor: 'transparent',
                            borderWidth: 1.5,
                            borderDash: [6, 3],
                            pointRadius: 2,
                            fill: false,
                            tension: 0.3,
                            yAxisID: 'yPPO'
                        }
                    ]
                },
                options: {
                    responsive: true,
                    interaction: { mode: 'index', intersect: false },
                    plugins: {
                        legend: { position: 'top' },
                        tooltip: {
                            callbacks: {
                                label: function(ctx) {
                                    if (ctx.parsed.y === null) return null;
                                    return ctx.dataset.label + ': $' + ctx.parsed.y.toFixed(2);
                                }
                            }
                        },
                        annotation: {
                            annotations: {
                                currentLine: {
                                    type: 'line',
                                    yMin: currentPrice,
                                    yMax: currentPrice,
                                    yScaleID: 'yPrice',
                                    borderColor: 'rgba(200,104,30,0.5)',
                                    borderWidth: 1,
                                    borderDash: [4, 4],
                                    label: {
                                        content: 'Current: $' + currentPrice.toFixed(2),
                                        enabled: true,
                                        position: 'end',
                                        backgroundColor: 'rgba(200,104,30,0.8)',
                                        font: { size: 11 }
                                    }
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            ticks: {
                                maxTicksLimit: 12,
                                font: { size: 11 }
                            },
                            grid: { display: false }
                        },
                        yPrice: {
                            type: 'linear',
                            position: 'left',
                            title: { display: true, text: 'Price ($)', font: { size: 11 } },
                            ticks: {
                                callback: function(v) { return '$' + v.toFixed(2); },
                                font: { size: 11 }
                            }
                        },
                        yPPO: {
                            type: 'linear',
                            position: 'right',
                            title: { display: true, text: 'Price / oz ($)', font: { size: 11 } },
                            ticks: {
                                callback: function(v) { return '$' + v.toFixed(3); },
                                font: { size: 11 }
                            },
                            grid: { drawOnChartArea: false }
                        }
                    }
                }
            });
        }

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', initChart_<?php echo esc_js($chart_id); ?>);
        } else {
            initChart_<?php echo esc_js($chart_id); ?>();
        }
    })();
    </script>
    <?php
    return ob_get_clean();
}
