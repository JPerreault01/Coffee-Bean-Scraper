<?php
/**
 * Phase 5 Seed Script — Homepage + Utility Pages
 *
 * Run via WP-CLI:
 *   sudo -u www-data wp --path=/var/www/coffeebeans eval-file /path/to/seeds/seed-phase5-homepage.php
 *
 * Idempotent: matches on post_name (slug), updates if exists.
 * Creates: Home, Rankings hub, About, Editorial Standards, Affiliate Disclosure.
 * Sets Home as the static front page.
 */

// ── Helper: upsert a page by slug ─────────────────────────────────────────────
function cbi_seed_page( array $args ) {
    $slug   = $args['post_name'];
    $exists = get_page_by_path( $slug, OBJECT, 'page' );

    $post_data = [
        'post_title'   => $args['post_title'],
        'post_name'    => $slug,
        'post_content' => $args['post_content'] ?? '',
        'post_status'  => $args['post_status'] ?? 'publish',
        'post_type'    => 'page',
        'post_author'  => 1,
    ];

    if ( $exists ) {
        $post_data['ID'] = $exists->ID;
        $post_id         = wp_update_post( $post_data, true );
        if ( is_wp_error( $post_id ) ) {
            WP_CLI::warning( "Could not update page '$slug': " . $post_id->get_error_message() );
            return null;
        }
        WP_CLI::log( "Updated page: $slug (ID $post_id)" );
    } else {
        $post_id = wp_insert_post( $post_data, true );
        if ( is_wp_error( $post_id ) ) {
            WP_CLI::warning( "Could not create page '$slug': " . $post_id->get_error_message() );
            return null;
        }
        WP_CLI::log( "Created page: $slug (ID $post_id)" );
    }

    // RankMath SEO
    if ( ! empty( $args['seo_title'] ) ) {
        update_post_meta( $post_id, 'rank_math_title', $args['seo_title'] );
    }
    if ( ! empty( $args['seo_description'] ) ) {
        update_post_meta( $post_id, 'rank_math_description', $args['seo_description'] );
    }
    if ( ! empty( $args['focus_keyword'] ) ) {
        update_post_meta( $post_id, 'rank_math_focus_keyword', $args['focus_keyword'] );
    }
    // Page template
    if ( ! empty( $args['page_template'] ) ) {
        update_post_meta( $post_id, '_wp_page_template', $args['page_template'] );
    }

    return $post_id;
}

WP_CLI::log( "\n=== Phase 5: Homepage + Utility Pages ===" );

// ── Homepage ──────────────────────────────────────────────────────────────────
$home_content = <<<'HTML'
<!-- Homepage content is rendered by front-page.php template. This text is a fallback. -->
<p>Coffee Bean Index tracks prices, publishes reviews, and explains coffee — so you can find the right bean and buy it at the right price.</p>

<p><strong>Browse by what you care about:</strong></p>
<ul>
  <li><a href="/beans/">All beans</a> — every product we track, with prices updated daily</li>
  <li><a href="/flavor/chocolate/">Chocolate notes</a> · <a href="/flavor/caramel-sweet/">Caramel</a> · <a href="/flavor/fruit/">Fruit</a> · <a href="/flavor/earthy-smoky/">Earthy</a></li>
  <li><a href="/origin/ethiopia/">Ethiopian coffee</a> · <a href="/origin/colombia/">Colombian</a> · <a href="/origin/sumatra/">Sumatran</a></li>
  <li><a href="/brew-method/espresso/">Espresso</a> · <a href="/brew-method/pour-over/">Pour over</a> · <a href="/brew-method/french-press/">French press</a></li>
</ul>
HTML;

$home_id = cbi_seed_page( [
    'post_title'      => 'Home',
    'post_name'       => 'home',
    'post_status'     => 'publish',
    'post_content'    => $home_content,
    'page_template'   => 'front-page.php',
    'seo_title'       => 'Coffee Bean Index — Price Tracker, Reviews & Flavor Guides',
    'seo_description' => 'Track coffee bean prices, read analytical reviews, and find the right bean for your brew method. Updated daily from Amazon and direct roasters.',
    'focus_keyword'   => 'coffee bean reviews',
] );

// ── Rankings hub ──────────────────────────────────────────────────────────────
$rankings_content = <<<'HTML'
<p>Coffee ranked by value, flavor quality, and brew method suitability — not by affiliate rate or brand recognition.</p>

<h2>Espresso</h2>
<ul>
  <li><a href="/best-espresso-beans-under-20/">Best Espresso Beans Under $20</a> — five beans that pull clean shots without a $2,000 machine</li>
</ul>

<h2>Dark Roast</h2>
<ul>
  <li><a href="/best-dark-roast-coffee-beans/">Best Dark Roast Coffee Beans</a> — ranked by clean finish over raw intensity</li>
</ul>

<h2>Related Guides</h2>
<ul>
  <li><a href="/brew-method/espresso/">Espresso Brewing Guide</a></li>
  <li><a href="/roast-level/dark/">Dark Roast Guide</a></li>
  <li><a href="/roast-level/medium-dark/">Medium-Dark Roast Guide</a></li>
</ul>
HTML;

cbi_seed_page( [
    'post_title'      => 'Rankings',
    'post_name'       => 'rankings',
    'post_status'     => 'publish',
    'post_content'    => $rankings_content,
    'seo_title'       => 'Coffee Rankings — Best Beans by Category | Coffee Bean Index',
    'seo_description' => 'Coffee beans ranked by category — espresso, dark roast, value, and more. Honest rankings based on flavor quality and value, not commission rate.',
    'focus_keyword'   => 'best coffee beans ranked',
] );

// ── About ─────────────────────────────────────────────────────────────────────
$about_content = <<<'HTML'
<p>This page contains affiliate links. We may earn commissions from qualifying purchases.</p>

<p>Coffee Bean Index tracks prices on coffee beans sold through Amazon and direct roasters, publishes analytical reviews, and maintains origin, brew method, and flavor guides.</p>

<h2>How Reviews Work</h2>
<p>Reviews are generated using structured product data, public tasting notes, roast information, and editorial evaluation criteria. Unless explicitly marked as personal reviews, content should be understood as analytical commentary rather than firsthand consumption experience.</p>

<p>The review voice applies the site's standing preferences as the critical lens: clean finishes over lingering bitterness, forgiving brew profiles over finicky ones, value over brand premium, bright defined flavors over muddy complexity.</p>

<h2>How Prices Are Tracked</h2>
<p>Prices are pulled daily from Amazon via the Product Advertising API and directly from roaster websites where available. Price history is stored and displayed on each bean's page. The "Price Analysis" section of each review compares the current price to the 30-day average.</p>

<h2>Affiliate Disclosure</h2>
<p>Some content on this site is generated or assisted by AI systems using structured product and review data.</p>
<p>This site participates in the Amazon Associates program and other affiliate programs. We earn commissions from qualifying purchases at no extra cost to you. Commission rates do not affect rankings or recommendations.</p>

<p>See the <a href="/affiliate-disclosure/">full affiliate disclosure</a> and <a href="/editorial-standards/">editorial standards</a>.</p>
HTML;

cbi_seed_page( [
    'post_title'   => 'About',
    'post_name'    => 'about',
    'post_status'  => 'publish',
    'post_content' => $about_content,
] );

// ── Editorial Standards ────────────────────────────────────────────────────────
$editorial_content = <<<'HTML'
<p>This page contains affiliate links. We may earn commissions from qualifying purchases.</p>

<h2>Review Voice</h2>
<p>All reviews on Coffee Bean Index use an analytical voice by default. The coffee is the subject. Reviews describe what the coffee is and does — not what a taster found or what buyers report.</p>

<p>First-person consumption claims ("I tasted," "I brewed") appear only on reviews explicitly marked as personal reviews by the site author. Crowd attribution ("buyers say," "reviewers report") is never used.</p>

<h2>AI-Assisted Content</h2>
<p>Some content on this site is generated or assisted by AI systems using structured product and review data.</p>

<p>Reviews are generated using structured product data, public tasting notes, roast information, and editorial evaluation criteria. Unless explicitly marked as personal reviews, content should be understood as analytical commentary rather than firsthand consumption experience.</p>

<h2>Ranking Criteria</h2>
<p>Rankings use the site's standing preferences as the critical lens:</p>
<ul>
  <li>Clean finishes over lingering bitterness</li>
  <li>Forgiving brew profiles over finicky ones</li>
  <li>Value-driven pricing over brand premiums</li>
  <li>Bright, defined flavors over muddy complexity</li>
  <li>Espresso that works without a $2,000 machine is worth more than espresso that doesn't</li>
</ul>
<p>Affiliate commission rates do not affect rankings or recommendations.</p>

<h2>Price Data</h2>
<p>Prices are updated daily from Amazon and direct roaster sites. Historical price data is stored and displayed on bean pages. The "Price Analysis" section of each review references 30-day average pricing from the price history database.</p>
HTML;

cbi_seed_page( [
    'post_title'   => 'Editorial Standards',
    'post_name'    => 'editorial-standards',
    'post_status'  => 'publish',
    'post_content' => $editorial_content,
] );

// ── Affiliate Disclosure ───────────────────────────────────────────────────────
$disclosure_content = <<<'HTML'
<h2>Affiliate Disclosure</h2>
<p>Coffee Bean Index participates in affiliate advertising programs designed to provide a means for the site to earn advertising fees by advertising and linking to partner retailers.</p>

<p>This site is a participant in the Amazon Services LLC Associates Program, an affiliate advertising program designed to provide a means for sites to earn advertising fees by advertising and linking to Amazon.com.</p>

<p>We also participate in affiliate programs with Stumptown Coffee, Trade Coffee, Blue Bottle Coffee, Death Wish Coffee, and other roasters. These relationships are noted on relevant pages.</p>

<h2>How Affiliate Links Work</h2>
<p>When you click an affiliate link and make a qualifying purchase, we earn a small commission — typically 4–15% of the sale price, depending on the program. This commission comes from the retailer, not from you. Your purchase price is the same whether you use an affiliate link or not.</p>

<h2>How Affiliate Relationships Affect Content</h2>
<p>They don't affect rankings or recommendations. Commission rates vary by program — a brand with a 15% commission rate does not receive preferential placement over a brand with a 4% rate. Rankings are based on the editorial criteria described in our <a href="/editorial-standards/">Editorial Standards</a>.</p>

<p>We only link to products we've reviewed analytically. We don't create pages specifically to capture affiliate revenue from products we haven't evaluated against our standards.</p>

<h2>Questions</h2>
<p>If you have questions about our affiliate relationships or content practices, use the contact form on the <a href="/about/">About page</a>.</p>
HTML;

cbi_seed_page( [
    'post_title'   => 'Affiliate Disclosure',
    'post_name'    => 'affiliate-disclosure',
    'post_status'  => 'publish',
    'post_content' => $disclosure_content,
] );

// ── Learn hub ─────────────────────────────────────────────────────────────────
$learn_content = <<<'HTML'
<p>Coffee education — origin guides, brew method guides, roast level explanations, and process method breakdowns. Everything you need to understand what's in your cup and why it tastes the way it does.</p>

<h2>Origin Guides</h2>
<ul>
  <li><a href="/origin/ethiopia/">Ethiopian Coffee</a> — high acidity, floral aromatics, the origin that defines specialty coffee</li>
  <li><a href="/origin/colombia/">Colombian Coffee</a> — caramel sweetness, forgiving profile, the daily driver</li>
  <li><a href="/origin/sumatra/">Sumatra Coffee</a> — earthy, full-body, low-acid — and why it tastes that way</li>
  <li><a href="/origin/brazil/">Brazilian Coffee</a> — chocolate, nuts, and why it's the backbone of espresso blends</li>
  <li><a href="/origin/nicaragua/">Nicaraguan Coffee</a> — smooth, low-acid, and more interesting than it gets credit for</li>
  <li><a href="/origin/latin-america/">Latin American Blends Explained</a></li>
  <li><a href="/origin/india/">Indian Coffee</a> — Robusta, Monsoon Malabar, and why Death Wish uses it</li>
</ul>

<h2>Brew Method Guides</h2>
<ul>
  <li><a href="/brew-method/espresso/">Espresso</a> — what makes a great espresso bean and how extraction works</li>
  <li><a href="/brew-method/pour-over/">Pour Over</a> — the method for light roast and single origins</li>
  <li><a href="/brew-method/french-press/">French Press</a> — full immersion, full body, and how to fix a muddy cup</li>
  <li><a href="/brew-method/moka-pot/">Moka Pot</a> — concentrated without an espresso machine</li>
  <li><a href="/brew-method/drip/">Drip / Auto</a> — the most common method and how to do it right</li>
  <li><a href="/brew-method/cold-brew/">Cold Brew</a> — no acidity, heavy body, steep time and ratio</li>
  <li><a href="/brew-method/aeropress/">AeroPress</a> — the most versatile brewer available</li>
  <li><a href="/brew-method/chemex/">Chemex</a> — the cleanest cup, and why it demands light roast</li>
</ul>

<h2>Roast Level Guides</h2>
<ul>
  <li><a href="/roast-level/light/">Light Roast</a> — high acidity, origin character, who it's for</li>
  <li><a href="/roast-level/medium/">Medium Roast</a> — the sweet spot and why it dominates</li>
  <li><a href="/roast-level/medium-dark/">Medium-Dark Roast</a> — espresso territory, low acid, full body</li>
  <li><a href="/roast-level/dark/">Dark Roast</a> — zero acidity, maximum weight, honest evaluation</li>
</ul>

<h2>Process Method Guides</h2>
<ul>
  <li><a href="/process-method/washed/">Washed Process</a> — why it produces the cleanest cups</li>
  <li><a href="/process-method/natural/">Natural Process</a> — fruit fermented into the bean and why it's complex</li>
  <li><a href="/process-method/honey/">Honey Process</a> — between washed and natural</li>
  <li><a href="/process-method/wet-hulled/">Wet-Hulled (Giling Basah)</a> — why Sumatra tastes earthy</li>
</ul>
HTML;

cbi_seed_page( [
    'post_title'      => 'Learn',
    'post_name'       => 'learn',
    'post_status'     => 'publish',
    'post_content'    => $learn_content,
    'seo_title'       => 'Coffee Education: Origin, Brew & Roast Guides | Coffee Bean Index',
    'seo_description' => 'Origin guides, brew method guides, roast level breakdowns, and process method explanations — everything you need to understand your coffee.',
    'focus_keyword'   => 'coffee origin guide',
] );

// ── Price Tracker (placeholder) ───────────────────────────────────────────────
cbi_seed_page( [
    'post_title'   => 'Price Tracker',
    'post_name'    => 'price-tracker',
    'post_status'  => 'publish',
    'post_content' => '<p>Price tracking is built into each bean page — visit any <a href="/beans/">bean review</a> to see its 30-day price history and current price.</p><p>Set up email alerts on the <a href="/about/">About page</a> to get notified when a tracked bean drops below your target price.</p>',
] );

// ── Set static front page ─────────────────────────────────────────────────────
if ( $home_id ) {
    update_option( 'show_on_front', 'page' );
    update_option( 'page_on_front', $home_id );
    WP_CLI::log( "Set static front page to 'Home' (ID $home_id)" );
}

WP_CLI::success( "\nPhase 5 complete. Verify at / (homepage), /rankings/, /about/, /editorial-standards/, /affiliate-disclosure/, /learn/" );
WP_CLI::log( "Check Settings → Reading to confirm 'Your homepage displays: A static page → Home'" );
