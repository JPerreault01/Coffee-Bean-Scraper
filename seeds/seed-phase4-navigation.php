<?php
/**
 * Phase 4 Seed Script — Primary Navigation Menu
 *
 * Run via WP-CLI:
 *   sudo -u www-data wp --path=/var/www/coffeebeans eval-file /path/to/seeds/seed-phase4-navigation.php
 *
 * Idempotent: checks for existing menu by name, clears and rebuilds items.
 * NOTE: After running, verify in Appearance → Menus that "Primary Navigation"
 *       is assigned to the "Primary Menu" location. The script attempts auto-
 *       assignment but GeneratePress location keys vary by version.
 */

$menu_name = 'Primary Navigation';

// Find or create the menu
$menu_id = 0;
$menus   = wp_get_nav_menus();
foreach ( $menus as $m ) {
    if ( $m->name === $menu_name ) {
        $menu_id = $m->term_id;
        break;
    }
}

if ( ! $menu_id ) {
    $result = wp_create_nav_menu( $menu_name );
    if ( is_wp_error( $result ) ) {
        WP_CLI::error( "Could not create menu: " . $result->get_error_message() );
        exit;
    }
    $menu_id = $result;
    WP_CLI::log( "Created menu: $menu_name (ID $menu_id)" );
} else {
    // Clear existing items for a clean rebuild
    $existing_items = wp_get_nav_menu_items( $menu_id );
    if ( $existing_items ) {
        foreach ( $existing_items as $item ) {
            wp_delete_post( $item->ID, true );
        }
    }
    WP_CLI::log( "Rebuilding menu: $menu_name (ID $menu_id)" );
}

// ── Helper to add a menu item ──────────────────────────────────────────────────
function cbi_add_menu_item( $menu_id, $title, $url, $parent_id = 0 ) {
    return wp_update_nav_menu_item( $menu_id, 0, [
        'menu-item-title'     => $title,
        'menu-item-url'       => $url,
        'menu-item-status'    => 'publish',
        'menu-item-type'      => 'custom',
        'menu-item-parent-id' => $parent_id,
    ] );
}

// ── Build menu structure ───────────────────────────────────────────────────────

// Beans
$beans = cbi_add_menu_item( $menu_id, 'Beans', home_url( '/beans/' ) );

// Flavors
$flavors = cbi_add_menu_item( $menu_id, 'Flavors', home_url( '/flavor/' ) );
cbi_add_menu_item( $menu_id, 'Chocolate', home_url( '/flavor/chocolate/' ), $flavors );
cbi_add_menu_item( $menu_id, 'Caramel & Sweet', home_url( '/flavor/caramel-sweet/' ), $flavors );
cbi_add_menu_item( $menu_id, 'Fruit', home_url( '/flavor/fruit/' ), $flavors );
cbi_add_menu_item( $menu_id, 'Citrus & Floral', home_url( '/flavor/citrus-floral/' ), $flavors );
cbi_add_menu_item( $menu_id, 'Earthy & Smoky', home_url( '/flavor/earthy-smoky/' ), $flavors );
cbi_add_menu_item( $menu_id, 'Nutty', home_url( '/flavor/nutty/' ), $flavors );

// Origins
$origins = cbi_add_menu_item( $menu_id, 'Origins', home_url( '/origin/' ) );
cbi_add_menu_item( $menu_id, 'Ethiopia', home_url( '/origin/ethiopia/' ), $origins );
cbi_add_menu_item( $menu_id, 'Colombia', home_url( '/origin/colombia/' ), $origins );
cbi_add_menu_item( $menu_id, 'Sumatra', home_url( '/origin/sumatra/' ), $origins );
cbi_add_menu_item( $menu_id, 'Brazil', home_url( '/origin/brazil/' ), $origins );
cbi_add_menu_item( $menu_id, 'Nicaragua', home_url( '/origin/nicaragua/' ), $origins );
cbi_add_menu_item( $menu_id, 'Latin America', home_url( '/origin/latin-america/' ), $origins );

// Roasts
$roasts = cbi_add_menu_item( $menu_id, 'Roasts', home_url( '/roast-level/' ) );
cbi_add_menu_item( $menu_id, 'Light', home_url( '/roast-level/light/' ), $roasts );
cbi_add_menu_item( $menu_id, 'Medium', home_url( '/roast-level/medium/' ), $roasts );
cbi_add_menu_item( $menu_id, 'Medium-Dark', home_url( '/roast-level/medium-dark/' ), $roasts );
cbi_add_menu_item( $menu_id, 'Dark', home_url( '/roast-level/dark/' ), $roasts );

// Brew Methods
// NOTE: the brew-method taxonomy rewrite base is '/brew/', NOT '/brew-method/'.
// These URLs must match the live archive base or the menu links 404.
$brew = cbi_add_menu_item( $menu_id, 'Brew Methods', home_url( '/brew/' ) );
cbi_add_menu_item( $menu_id, 'Espresso', home_url( '/brew/espresso/' ), $brew );
cbi_add_menu_item( $menu_id, 'Pour Over', home_url( '/brew/pour-over/' ), $brew );
cbi_add_menu_item( $menu_id, 'French Press', home_url( '/brew/french-press/' ), $brew );
cbi_add_menu_item( $menu_id, 'Moka Pot', home_url( '/brew/moka-pot/' ), $brew );
cbi_add_menu_item( $menu_id, 'Drip / Auto', home_url( '/brew/drip/' ), $brew );
cbi_add_menu_item( $menu_id, 'Cold Brew', home_url( '/brew/cold-brew/' ), $brew );
cbi_add_menu_item( $menu_id, 'AeroPress', home_url( '/brew/aeropress/' ), $brew );

// Rankings
$rankings = cbi_add_menu_item( $menu_id, 'Rankings', home_url( '/rankings/' ) );
cbi_add_menu_item( $menu_id, 'Best Espresso Under $20', home_url( '/best-espresso-beans-under-20/' ), $rankings );
cbi_add_menu_item( $menu_id, 'Best Dark Roast', home_url( '/best-dark-roast-coffee-beans/' ), $rankings );

// Learn
$learn = cbi_add_menu_item( $menu_id, 'Learn', home_url( '/learn/' ) );
cbi_add_menu_item( $menu_id, 'Origin Guides', home_url( '/origin/' ), $learn );
cbi_add_menu_item( $menu_id, 'Brew Guides', home_url( '/brew/' ), $learn );
cbi_add_menu_item( $menu_id, 'Roast Guides', home_url( '/roast-level/' ), $learn );
cbi_add_menu_item( $menu_id, 'Process Methods', home_url( '/process-method/' ), $learn );

// Price Tracker (placeholder)
cbi_add_menu_item( $menu_id, 'Price Tracker', home_url( '/price-tracker/' ) );

// ── Assign to theme locations ──────────────────────────────────────────────────
$locations = get_theme_mod( 'nav_menu_locations' );
if ( ! is_array( $locations ) ) {
    $locations = [];
}

// Try common GeneratePress location keys
foreach ( [ 'primary', 'primary-menu', 'main-nav', 'main-menu' ] as $location ) {
    $locations[ $location ] = $menu_id;
}
set_theme_mod( 'nav_menu_locations', $locations );

WP_CLI::success( "Phase 4 complete. Menu '$menu_name' built with " . count( wp_get_nav_menu_items( $menu_id ) ) . " items." );
WP_CLI::log( "ACTION REQUIRED: Go to Appearance → Menus → Primary Navigation → Menu Settings and check 'Primary Menu', then Save." );
