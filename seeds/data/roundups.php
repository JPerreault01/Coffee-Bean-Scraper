<?php
/**
 * Roundup post data.
 * Posts created as DRAFT — publish only when all referenced bean pages are live.
 *
 * Required bean pages before publishing:
 *   best-espresso-beans-under-20: lavazza, illy, cafe-don-pablo, cafe-bustelo, kicking-horse
 *   best-dark-roast-coffee-beans: peets, camano-island, kicking-horse, death-wish, community-coffee, cafe-bustelo
 */
return [

    [
        'post_title'     => 'Best Espresso Beans Under $20',
        'post_name'      => 'best-espresso-beans-under-20',
        'post_status'    => 'draft',
        'post_type'      => 'post',
        'post_category'  => ['roundups'],
        'page_template'  => 'template-roundup.php',
        'focus_keyword'  => 'best espresso beans under $20',
        'seo_title'      => 'Best Espresso Beans Under $20 (2024) — Ranked | Coffee Bean Index',
        'seo_description'=> 'Five espresso beans under $20 that pull clean shots without a $2,000 machine. Ranked by value, flavor, and how forgiving they are for home setups.',
        'post_content'   => <<<'HTML'
<p class="roundup-intro">This page contains affiliate links. We may earn commissions from qualifying purchases.</p>

<p>Good espresso under $20 requires a specific profile: medium-dark roast, low acidity, enough body for crema, and a blend ratio that doesn't punish a slightly-off grind. These five beans hit that target. None require a dialed-in setup to pull correctly. All are available on Amazon with tracked pricing.</p>

<p>Ranking is based on the site's standing preferences: forgiving brew profiles over finicky ones, value over brand premium, clean finishes over lingering bitterness, and espresso that works without a $2,000 machine.</p>

<hr/>

<h2>#1 — Lavazza Super Crema</h2>
<p><strong>Why it ranks first:</strong> 35.2 oz at under $16 is a price-per-oz calculation that nothing else at this level beats. The hazelnut-and-brown-sugar profile pulls consistently across a wide grind range. Crema production is excellent from the Brazilian and Indonesian components in the blend. Medium roast keeps it approachable for any setup.</p>
<p><strong>Who it's for:</strong> Espresso and moka pot users who want a reliable daily bean without obsessing over parameters.</p>
<p><strong>Who should skip it:</strong> Drinkers who want dark roast intensity in the shot. Lavazza Super Crema is mild — it's not going to challenge you.</p>
<p><em>→ <a href="/beans/lavazza-super-crema/">Full Lavazza Super Crema Review</a></em></p>

<hr/>

<h2>#2 — Café Don Pablo Gourmet Signature Blend</h2>
<p><strong>Why it ranks second:</strong> The Colombia-Brazil-Honduras blend at medium-dark roast delivers exactly what a home espresso setup needs: low acidity, balanced chocolate and caramel, and body that survives the pressure of a basic machine. 16 oz at typically $13–16.</p>
<p><strong>Who it's for:</strong> Drip and espresso users who want medium-dark character without paying for a premium roaster.</p>
<p><strong>Who should skip it:</strong> Light roast drinkers. The medium-dark development covers the origin's brighter notes.</p>
<p><em>→ <a href="/beans/cafe-don-pablo-gourmet/">Full Café Don Pablo Review</a></em></p>

<hr/>

<h2>#3 — Café Bustelo Espresso Style Dark Roast</h2>
<p><strong>Why it ranks third:</strong> The lowest price in the category — often $9–12 for 16 oz — and a dark roast intensity that holds up in milk drinks. Not the most nuanced shot, but the tobacco-and-dark-chocolate profile is exactly what Cuban espresso is supposed to taste like.</p>
<p><strong>Who it's for:</strong> Moka pot users. Anyone who drinks cortados or lattes and wants the espresso to cut through. Budget daily driver.</p>
<p><strong>Who should skip it:</strong> Drinkers who want clean, nuanced shots. Café Bustelo is built for intensity, not complexity.</p>
<p><em>→ <a href="/beans/cafe-bustelo-espresso/">Full Café Bustelo Review</a></em></p>

<hr/>

<h2>#4 — Kicking Horse 454 Horse Power Dark Roast</h2>
<p><strong>Why it ranks fourth:</strong> The dark chocolate and molasses profile at dark roast makes this a strong espresso choice for drinkers who want intensity. 16 oz at $14–18 — it can drift over $20 depending on current pricing. Check the price tracker before buying.</p>
<p><strong>Who it's for:</strong> Dark roast espresso drinkers. Anyone who needs the shot to stand up to steamed milk.</p>
<p><strong>Who should skip it:</strong> Budget shoppers — if price has gone above $20, move to Café Don Pablo. Anyone who wants a medium roast.</p>
<p><em>→ <a href="/beans/kicking-horse-454-horse-power/">Full Kicking Horse Review</a></em></p>

<hr/>

<h2>#5 — Illy Classico Medium Roast</h2>
<p><strong>Why it ranks fifth:</strong> Illy's 9-country Arabica blend delivers the highest complexity in this roundup — caramel, orange blossom, jasmine, and chocolate in one shot. The 8.8 oz bag typically runs $14–16, making the price-per-oz the highest in the list. It's worth it for the occasional special cup; it's not the daily value pick.</p>
<p><strong>Who it's for:</strong> Espresso drinkers who want something interesting for a smaller bag. The medium roast suits drip and French press equally well.</p>
<p><strong>Who should skip it:</strong> Anyone who wants the best price-per-oz. The per-ounce cost is nearly 2× Lavazza Super Crema for a different (not objectively better) profile.</p>
<p><em>→ <a href="/beans/illy-classico-medium/">Full Illy Classico Review</a></em></p>

<hr/>

<h2>How We Rank</h2>
<p>Rankings use the site's standing preferences as the critical lens: forgiving brew profiles over finicky ones, value over brand premium, clean finishes over lingering bitterness. Affiliate commission rates do not affect placement — Illy and Lavazza have different commission structures; rank reflects value to the buyer.</p>

<h2>Frequently Asked Questions</h2>
<dl>
  <dt><strong>Do I need an espresso machine to use these beans?</strong></dt>
  <dd>No. All five work in a moka pot, which produces a similar concentrated brew at 1–2 bars of pressure. A moka pot costs $25–40 and is one of the best investments for espresso-style coffee on a budget. A real espresso machine adds crema and more control over the shot, but the flavor profile is achievable in a moka pot.</dd>
  <dt><strong>How do I know if a bean is over $20?</strong></dt>
  <dd>Use the price tracker on each bean's page. Prices are updated daily from Amazon. If Kicking Horse is over $20 today, Café Don Pablo at current pricing is your better bet in this roundup.</dd>
</dl>
HTML,
    ],

    [
        'post_title'     => 'Best Dark Roast Coffee Beans',
        'post_name'      => 'best-dark-roast-coffee-beans',
        'post_status'    => 'draft',
        'post_type'      => 'post',
        'post_category'  => ['roundups'],
        'page_template'  => 'template-roundup.php',
        'focus_keyword'  => 'best dark roast coffee beans',
        'seo_title'      => 'Best Dark Roast Coffee Beans (2024) — Ranked by Flavor | Coffee Bean Index',
        'seo_description'=> 'Six dark roast coffees ranked by flavor quality, value, and brew method suitability. Clean finishes and forgiving profiles ranked above raw intensity.',
        'post_content'   => <<<'HTML'
<p class="roundup-intro">This page contains affiliate links. We may earn commissions from qualifying purchases.</p>

<p>Dark roast is polarizing because the range within "dark roast" is enormous. A well-developed dark roast produces dark chocolate, molasses, and clean bitterness. A poorly developed one produces char, ash, and harsh bitterness that lingers. These six span the full range — ranked by the site's preference for clean finishes over raw intensity, forgiving profiles over finicky ones, and value over brand premium.</p>

<hr/>

<h2>#1 — Peet's Coffee Major Dickason's Blend</h2>
<p><strong>Why it ranks first:</strong> 32 oz of dark roast at consistently strong value. The Latin America and Indonesia blend produces dark chocolate and earthy complexity at full body and near-zero acidity. The finish is clean for a dark roast — it doesn't linger with char. This is the standard against which other full-dark blends are measured.</p>
<p><strong>Who it's for:</strong> Daily dark roast drinkers. French press. Anyone who drinks coffee for weight and substance rather than brightness or complexity.</p>
<p><strong>Who should skip it:</strong> Drinkers who want specific origin character. The blend smooths out individuality. Anyone who finds Peet's too intense — go to Community Coffee instead.</p>
<p><em>→ <a href="/beans/peets-major-dickasons/">Full Peet's Major Dickason's Review</a></em></p>

<hr/>

<h2>#2 — Camano Island Coffee Roasters Sumatra</h2>
<p><strong>Why it ranks second:</strong> The wet-hull Sumatran profile is distinctive in a category that can blur together. Earthy and cedar character give it a dimension that straight dark roasts don't have. French press is the ideal brew — the full body comes through without paper filtration stripping it.</p>
<p><strong>Who it's for:</strong> French press drinkers who want the heaviest possible cup. Drinkers who find standard dark roast one-dimensional.</p>
<p><strong>Who should skip it:</strong> Anyone who doesn't like earthy notes — the Sumatran wet-hull character is defining, not background. Pour-over users lose the body through paper filtration.</p>
<p><em>→ <a href="/beans/camano-island-sumatra/">Full Camano Island Sumatra Review</a></em></p>

<hr/>

<h2>#3 — Kicking Horse Coffee 454 Horse Power</h2>
<p><strong>Why it ranks third:</strong> The dark chocolate and molasses profile at dark roast is clean — no char, no harsh linger. The Indonesia-Central-South America blend is calibrated for consistent dark roast character. Works in French press, drip, and as a base for moka pot espresso.</p>
<p><strong>Who it's for:</strong> Dark roast drinkers who want reliability across brew methods.</p>
<p><strong>Who should skip it:</strong> Anyone seeking origin complexity. Kicking Horse 454 is built to taste like great dark roast, not like a specific place.</p>
<p><em>→ <a href="/beans/kicking-horse-454-horse-power/">Full Kicking Horse Review</a></em></p>

<hr/>

<h2>#4 — Community Coffee Signature Blend Medium-Dark Roast</h2>
<p><strong>Why it ranks fourth:</strong> 32 oz at the lowest price-per-oz in this roundup. The medium-dark roast hits the accessible end of the dark spectrum — full body, low acidity, bold chocolate, without the intensity that alienates casual dark roast drinkers. Best value in the category.</p>
<p><strong>Who it's for:</strong> Budget buyers. Office coffee. Anyone transitioning from medium to dark roast who doesn't want to go all the way.</p>
<p><strong>Who should skip it:</strong> Drinkers who specifically want full dark roast intensity. Community Coffee's medium-dark reads as full dark to medium-roast drinkers but falls short for committed dark roast enthusiasts.</p>
<p><em>→ <a href="/beans/community-coffee-medium-dark/">Full Community Coffee Review</a></em></p>

<hr/>

<h2>#5 — Death Wish Coffee Whole Bean</h2>
<p><strong>Why it ranks fifth:</strong> Unique and valid in a specific niche — the natural process India-Peru blend produces dark cherry and chocolate at high-caffeine levels that nothing else in this roundup delivers. It's not for everyone. The high bitterness (5/5) makes it a commitment.</p>
<p><strong>Who it's for:</strong> High-caffeine seekers specifically. Drinkers who want an unusual dark roast experience. French press at 1:12 ratio for maximum intensity.</p>
<p><strong>Who should skip it:</strong> Anyone who doesn't need or want extreme caffeine. The intensity is a feature for the right audience and a flaw for everyone else.</p>
<p><em>→ <a href="/beans/death-wish-coffee/">Full Death Wish Coffee Review</a></em></p>

<hr/>

<h2>#6 — Café Bustelo Espresso Style Dark Roast</h2>
<p><strong>Why it ranks sixth:</strong> Café Bustelo is the right tool for moka pot and espresso — it's not primarily a drip dark roast. The tobacco-and-dark-chocolate profile is very dark and very intense. In a French press or drip machine, the bitterness dominates without the crema production that softens it in espresso contexts.</p>
<p><strong>Who it's for:</strong> Moka pot users who want budget dark roast espresso. Anyone who drinks cortados or lattes.</p>
<p><strong>Who should skip it:</strong> Drip and French press drinkers who want a nuanced dark roast. Go to Peet's or Kicking Horse instead.</p>
<p><em>→ <a href="/beans/cafe-bustelo-espresso/">Full Café Bustelo Review</a></em></p>

<hr/>

<h2>How We Rank</h2>
<p>Clean finishes rank above raw intensity. A dark roast that finishes without char and doesn't linger ranks higher than one that hits harder but leaves bitterness on the palate for minutes. Value and forgiving brew profiles inform every position. Affiliate rates do not.</p>

<h2>Frequently Asked Questions</h2>
<dl>
  <dt><strong>What's the best dark roast for French press?</strong></dt>
  <dd>Peet's Major Dickason's or Camano Island Sumatra. Both are built for immersion brewing — the full body reads clearly through metal mesh without paper filtration stripping it. Camano Island if you want earthy complexity; Peet's if you want a clean, consistent dark roast.</dd>
  <dt><strong>Is dark roast bad for espresso?</strong></dt>
  <dd>No — but very dark roast (bitterness 5/5 with high intensity) amplifies bitterness under espresso pressure. Kicking Horse, Café Don Pablo, and Lavazza at medium-dark are often better espresso choices than maximum-dark roasts like Café Bustelo or Death Wish. Dark roast works in espresso; the darkest roasts work best in moka pot where pressure is lower.</dd>
</dl>
HTML,
    ],

];
