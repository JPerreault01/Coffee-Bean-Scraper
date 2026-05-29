<?php
/**
 * Plugin Name: Coffee Flavor Explorer
 * Plugin URI:  https://github.com/JPerreault01/Coffee-Bean-Scraper
 * Description: Filterable coffee bean grid and per-product radar chart shortcodes. [flavor_explorer] and [coffee_profile id="product-id"]
 * Version:     1.0.0
 * Author:      JPerreault01
 * License:     GPL2
 *
 * File: wordpress-plugins/coffee-flavor-explorer/coffee-flavor-explorer.php
 * Deploy to: /var/www/coffeebeans/wp-content/plugins/coffee-flavor-explorer/coffee-flavor-explorer.php
 */

defined( 'ABSPATH' ) || exit;

function cfe_flavors_url() {
    return wp_upload_dir()['baseurl'] . '/coffee-data/flavors.json';
}

function cfe_enqueue_assets() {
    wp_enqueue_script(
        'cfe-chartjs',
        'https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js',
        [],
        '4.4.1',
        true
    );
    wp_enqueue_style(
        'cfe-styles',
        plugins_url( 'flavor-explorer.css', __FILE__ ),
        [],
        '1.0.0'
    );
    wp_enqueue_script(
        'cfe-script',
        plugins_url( 'flavor-explorer.js', __FILE__ ),
        [ 'cfe-chartjs' ],
        '1.0.0',
        true
    );
}

function cfe_flavor_explorer_shortcode( $atts ) {
    cfe_enqueue_assets();
    $url = esc_url( cfe_flavors_url() );
    return '<div id="coffee-flavor-explorer" data-flavors-url="' . $url . '"></div>';
}
add_shortcode( 'flavor_explorer', 'cfe_flavor_explorer_shortcode' );

function cfe_coffee_profile_shortcode( $atts ) {
    $atts       = shortcode_atts( [ 'id' => '' ], $atts, 'coffee_profile' );
    $product_id = sanitize_text_field( $atts['id'] );
    if ( ! $product_id ) {
        return '';
    }
    cfe_enqueue_assets();
    $url = esc_url( cfe_flavors_url() );
    return '<div class="coffee-radar-chart" data-product-id="' . esc_attr( $product_id ) . '" data-flavors-url="' . $url . '"></div>';
}
add_shortcode( 'coffee_profile', 'cfe_coffee_profile_shortcode' );
