<?php
/**
 * Flavor note taxonomy term data.
 * Organized as: parent family terms first, then child note terms.
 * Structure: [ 'slug', 'name', 'parent_slug' (null = family), 'description', 'seo_*' ]
 */
return [

    // ──────────────────────────────────────────────
    // FAMILY: Chocolate
    // ──────────────────────────────────────────────
    [
        'taxonomy'        => 'flavor-note',
        'slug'            => 'chocolate',
        'name'            => 'Chocolate',
        'parent_slug'     => null,
        'focus_keyword'   => 'chocolate notes in coffee',
        'seo_title'       => 'Chocolate Notes in Coffee: What Causes Them & Which Beans Have Them | Coffee Bean Index',
        'seo_description' => 'Chocolate notes in coffee come from roast development and specific origins — here\'s what causes them, which roast levels produce them, and which beans we track.',
        'description'     => <<<'HTML'
<h2>What Chocolate Notes in Coffee Actually Are</h2>
<p>Chocolate notes in coffee range from dark and bitter (dark chocolate, bittersweet) to soft and creamy (milk chocolate, cocoa). They're the most common flavor descriptors in commercial coffee — and one of the most honest. The compounds that produce chocolate character in coffee (specifically pyrazines and furans from roasting) are chemically related to those in actual cacao.</p>
<p>This is not fabrication. Medium and medium-dark roasted coffees from Latin American origins — Colombia, Brazil, Latin America blends — reliably produce chocolate and caramel notes because the roasting chemistry at those temperatures develops the same compounds. The roast is doing the work.</p>

<h2>What Produces Chocolate Notes</h2>
<p><strong>Roast level:</strong> dark and medium-dark roasting is the primary driver. The Maillard reaction at 400–450°F produces melanoidins — the same browning compounds responsible for cocoa flavor in roasted cacao. Light roast rarely reads as chocolate.</p>
<p><strong>Origin:</strong> Brazilian and Colombian beans are predisposed to chocolate character due to lower altitude growing conditions and natural process (Brazil) or washed processing at medium-dark levels (Colombia). Sumatran wet-hulled beans consistently read as dark chocolate in the low-acid earthy context.</p>

<h2>Dark Chocolate vs. Milk Chocolate vs. Cocoa</h2>
<p><strong>Dark chocolate:</strong> appears in darker roasts — Peet's Major Dickason's, Kicking Horse 454, Camano Island Sumatra. Higher bitterness, lower sweetness, often paired with earthy or smoky notes.</p>
<p><strong>Milk chocolate:</strong> typical of medium roasts at lower bitterness — Lifeboost Medium Roast, Eight O'Clock Original. Creamier, softer, paired with caramel or mild citrus.</p>
<p><strong>Bittersweet chocolate:</strong> found in medium-dark espresso blends — Stumptown Hair Bender, Blue Bottle Hayes Valley. Balanced bitterness and sweetness with caramel or fruit accompaniment.</p>
<p><strong>Mild cocoa / cocoa powder:</strong> Lavazza Super Crema, Caribou Blend. Light chocolate impression without sharp bitterness — background sweetness.</p>
HTML,
    ],
    [
        'taxonomy'    => 'flavor-note',
        'slug'        => 'dark-chocolate',
        'name'        => 'Dark Chocolate',
        'parent_slug' => 'chocolate',
        'description' => '<p>Dark chocolate in coffee signals medium-dark to dark roast development. Look for it in full-bodied beans at low acidity: Peet\'s Major Dickason\'s, Kicking Horse 454 Horse Power, and Camano Island Sumatra carry this note most clearly. The bitterness is intentional — a good dark chocolate note finishes cleanly without linger. See the <a href="/flavor/chocolate/">Chocolate family guide</a> for more.</p>',
    ],
    [
        'taxonomy'    => 'flavor-note',
        'slug'        => 'milk-chocolate',
        'name'        => 'Milk Chocolate',
        'parent_slug' => 'chocolate',
        'description' => '<p>Milk chocolate in coffee is softer and creamier than dark chocolate — lower bitterness, higher sweetness. Typical of medium roast Latin American and Nicaraguan origins. Lifeboost Medium Roast and Eight O\'Clock Original carry this note well. See the <a href="/flavor/chocolate/">Chocolate family guide</a> for context.</p>',
    ],
    [
        'taxonomy'    => 'flavor-note',
        'slug'        => 'bittersweet-chocolate',
        'name'        => 'Bittersweet Chocolate',
        'parent_slug' => 'chocolate',
        'description' => '<p>Bittersweet chocolate in coffee balances roast bitterness with caramel sweetness — the note of a well-developed medium-dark espresso blend. Stumptown Hair Bender and Blue Bottle Hayes Valley Espresso carry this most clearly. See the <a href="/flavor/chocolate/">Chocolate family guide</a>.</p>',
    ],
    [
        'taxonomy'    => 'flavor-note',
        'slug'        => 'mild-cocoa',
        'name'        => 'Mild Cocoa',
        'parent_slug' => 'chocolate',
        'description' => '<p>A light, background chocolate impression without sharp bitterness. Typical of medium-roast blends and creamy espresso profiles. Lavazza Super Crema carries mild cocoa as part of its hazelnut-and-cream profile. See the <a href="/flavor/chocolate/">Chocolate family guide</a>.</p>',
    ],

    // ──────────────────────────────────────────────
    // FAMILY: Caramel & Sweet
    // ──────────────────────────────────────────────
    [
        'taxonomy'        => 'flavor-note',
        'slug'            => 'caramel-sweet',
        'name'            => 'Caramel & Sweet',
        'parent_slug'     => null,
        'focus_keyword'   => 'caramel notes in coffee',
        'seo_title'       => 'Caramel & Sweet Notes in Coffee: What Causes Them & Which Beans | Coffee Bean Index',
        'seo_description' => 'Caramel, brown sugar, toffee, and molasses notes come from sugar caramelization during roasting. Here\'s how they develop and which beans carry them most clearly.',
        'description'     => <<<'HTML'
<h2>What Caramel and Sweet Notes in Coffee Are</h2>
<p>The caramel family — caramel, brown sugar, toffee, molasses — comes from sugar caramelization during roasting. As beans hit 375–420°F, sucrose breaks down and reforms as hundreds of new flavor compounds: diacetyl (buttery caramel), furanones (caramel sweetness), pyranones (toffee depth). These are the same reactions that turn white sugar into caramel on a stovetop.</p>
<p>Medium roast is peak caramel. Light roast doesn't develop enough for caramelization. Dark roast pushes past caramel into bitter, charred compounds. Medium roast captures caramelization at its sweetest expression — it's why medium roast is described as the sweetest roast level despite having no added sugar.</p>

<h2>Caramel vs. Brown Sugar vs. Toffee vs. Molasses</h2>
<p><strong>Caramel:</strong> the lightest and brightest of the family — present in medium-roast Colombian, Illy Classico, Counter Culture Big Trouble, Stumptown Hair Bender. Sweet, clean, fades quickly.</p>
<p><strong>Brown sugar:</strong> slightly richer than caramel, with a warm molasses undertone. Present in Lavazza Super Crema and Intelligentsia Black Cat. Common in medium-dark espresso blends.</p>
<p><strong>Toffee:</strong> caramel that's been taken slightly further — drier, slightly more bitter edge. Counter Culture Big Trouble carries this clearly in its medium roast profile.</p>
<p><strong>Molasses:</strong> appears at dark roast temperatures — heavy, dark sweetness with a thick texture. Kicking Horse 454 Horse Power's profile includes this at dark roast development.</p>
HTML,
    ],
    [
        'taxonomy'    => 'flavor-note',
        'slug'        => 'caramel',
        'name'        => 'Caramel',
        'parent_slug' => 'caramel-sweet',
        'description' => '<p>Caramel is the signature sweet note of medium-roast Latin American and Colombian coffees. Clean, bright sweetness that fades without linger. Illy Classico, Counter Culture Big Trouble, Caribou Blend, and Stumptown Hair Bender all carry caramel clearly. See the <a href="/flavor/caramel-sweet/">Caramel &amp; Sweet family guide</a>.</p>',
    ],
    [
        'taxonomy'    => 'flavor-note',
        'slug'        => 'brown-sugar',
        'name'        => 'Brown Sugar',
        'parent_slug' => 'caramel-sweet',
        'description' => '<p>A warmer, richer sweet note than caramel — closer to the molasses character of raw sugar. Common in espresso blends at medium-dark roast. Lavazza Super Crema and Intelligentsia Black Cat Espresso both carry brown sugar as a primary note. See the <a href="/flavor/caramel-sweet/">Caramel &amp; Sweet family guide</a>.</p>',
    ],
    [
        'taxonomy'    => 'flavor-note',
        'slug'        => 'toffee',
        'name'        => 'Toffee',
        'parent_slug' => 'caramel-sweet',
        'description' => '<p>Toffee sits between caramel and dark chocolate — buttery sweetness with a slightly dry, bitter edge. Counter Culture Big Trouble carries toffee as its primary mid-palette note. See the <a href="/flavor/caramel-sweet/">Caramel &amp; Sweet family guide</a>.</p>',
    ],
    [
        'taxonomy'    => 'flavor-note',
        'slug'        => 'molasses',
        'name'        => 'Molasses',
        'parent_slug' => 'caramel-sweet',
        'description' => '<p>Molasses is the dark end of the caramel family — heavy, almost savory sweetness that appears in dark roast development. Kicking Horse 454 Horse Power carries molasses alongside dark chocolate and smokiness. See the <a href="/flavor/caramel-sweet/">Caramel &amp; Sweet family guide</a>.</p>',
    ],

    // ──────────────────────────────────────────────
    // FAMILY: Nutty
    // ──────────────────────────────────────────────
    [
        'taxonomy'        => 'flavor-note',
        'slug'            => 'nutty',
        'name'            => 'Nutty',
        'parent_slug'     => null,
        'focus_keyword'   => 'nutty coffee beans',
        'seo_title'       => 'Nutty Coffee: Hazelnut, Walnut & What Makes Coffee Taste Like Nuts | Coffee Bean Index',
        'seo_description' => 'Hazelnut, walnut, and nutty notes in coffee come from Maillard browning during roasting. Here\'s which origins and roasts carry nut character most clearly.',
        'description'     => <<<'HTML'
<h2>What Makes Coffee Taste Nutty</h2>
<p>Nutty notes in coffee — hazelnut, walnut, almond, peanut — come from pyrazines produced during Maillard browning. The same reaction that browns roasted nuts browns roasted coffee beans. At medium roast, the browning produces light, clean nut notes alongside caramel. At medium-dark, the nut notes shift toward walnut and take on a slight bitterness.</p>
<p>Brazilian and lower-altitude Latin American origins are most predisposed to nut notes. The beans' lower inherent acidity allows the nut character to read clearly without competition from bright acids. Colombian medium roasts often deliver caramel and mild nut alongside each other.</p>

<h2>Hazelnut vs. Walnut vs. Mild Nut</h2>
<p><strong>Hazelnut:</strong> the lightest and sweetest nut note. Associated with mild acidity and creamy body — Lavazza Super Crema carries hazelnut clearly as part of its creamy, low-acid espresso profile. It reads as sweet and smooth.</p>
<p><strong>Walnut:</strong> slightly more bitter and astringent than hazelnut. Appears at medium-dark development. Intelligentsia Black Cat Espresso includes walnut as part of its dark-chocolate-and-crema profile.</p>
<p><strong>General nutty / nuts:</strong> a mild, background nut impression without a specific nut character. Caribou Blend carries this alongside caramel and light cocoa.</p>
HTML,
    ],
    [
        'taxonomy'    => 'flavor-note',
        'slug'        => 'hazelnut',
        'name'        => 'Hazelnut',
        'parent_slug' => 'nutty',
        'description' => '<p>Hazelnut in coffee is sweet, mild, and creamy — the lightest and most approachable nut note. It appears in low-acid espresso blends with creamy body. Lavazza Super Crema carries hazelnut as its most prominent descriptor. See the <a href="/flavor/nutty/">Nutty family guide</a>.</p>',
    ],
    [
        'taxonomy'    => 'flavor-note',
        'slug'        => 'walnut',
        'name'        => 'Walnut',
        'parent_slug' => 'nutty',
        'description' => '<p>Walnut in coffee has a mild bitterness and slight astringency that sets it apart from hazelnut. It appears in medium-dark espresso blends. Intelligentsia Black Cat Espresso carries walnut alongside dark chocolate and thick crema. See the <a href="/flavor/nutty/">Nutty family guide</a>.</p>',
    ],

    // ──────────────────────────────────────────────
    // FAMILY: Fruit
    // ──────────────────────────────────────────────
    [
        'taxonomy'        => 'flavor-note',
        'slug'            => 'fruit',
        'name'            => 'Fruit',
        'parent_slug'     => null,
        'focus_keyword'   => 'fruit flavored coffee beans',
        'seo_title'       => 'Fruit Notes in Coffee: Berry, Cherry, Dried Fruit & What Causes Them | Coffee Bean Index',
        'seo_description' => 'Fruit notes in coffee come from origin character (Ethiopian washed), natural processing, or both. Here\'s what causes different fruit notes and which beans carry them.',
        'description'     => <<<'HTML'
<h2>What Fruit Notes in Coffee Actually Are</h2>
<p>Fruit notes in coffee are not flavoring or additives. They're organic compounds — esters, aldehydes, ketones — produced during cherry development, fermentation, and roasting. A strawberry note in Onyx Southern Weather is a real chemical similarity to the compounds in strawberry. It's chemistry, not marketing.</p>
<p>Two sources produce fruit notes in coffee:</p>
<p><strong>Origin character:</strong> Ethiopian heirloom varietals grown at high altitude develop intense fruit esters during slow cherry development. Washed processing preserves these esters cleanly — the bergamot and stone fruit in Atlas Ethiopia Limu read as precision fruit, not fermented fruit.</p>
<p><strong>Natural process:</strong> the fruit flesh ferments into the bean during drying, adding cherry, berry, and tropical fruit sweetness. Death Wish Coffee's dark cherry note comes from natural processing applied to Indian and Peruvian beans.</p>

<h2>Types of Fruit Notes in Our Beans</h2>
<p><strong>Stone fruit (peach, plum, apricot):</strong> Ethiopian light-medium washed — Atlas Coffee Club Ethiopia Limu. High acidity, clean finish.</p>
<p><strong>Berry / strawberry:</strong> Ethiopian light roast washed — Onyx Coffee Lab Southern Weather. Bright, almost candy-like sweetness alongside clean acidity.</p>
<p><strong>Dark cherry:</strong> natural process dark roast — Death Wish Coffee. The fruit is infused by the natural drying, reads as sweet and deep at dark roast level.</p>
<p><strong>Dried fruit:</strong> medium-dark espresso blends — Blue Bottle Hayes Valley. The fruit note is concentrated, raisin-like, paired with bittersweet chocolate.</p>
<p><strong>Mild fruit / mild citrus:</strong> medium-roast Latin American — Lifeboost, Don Francisco's, Counter Culture. A background brightness rather than a primary note.</p>
HTML,
    ],
    [
        'taxonomy'    => 'flavor-note',
        'slug'        => 'dark-cherry',
        'name'        => 'Dark Cherry',
        'parent_slug' => 'fruit',
        'description' => '<p>Dark cherry in coffee comes from natural processing — fruit sugars absorbed during drying and concentrated at dark roast development. Death Wish Coffee carries this note as its signature fruit characteristic despite being a high-bitterness dark roast. See the <a href="/flavor/fruit/">Fruit family guide</a>.</p>',
    ],
    [
        'taxonomy'    => 'flavor-note',
        'slug'        => 'dried-fruit',
        'name'        => 'Dried Fruit',
        'parent_slug' => 'fruit',
        'description' => '<p>Dried fruit (raisin, prune, dark berry) appears in dark espresso blends at medium-dark roast — the fruit note concentrates and deepens as sugars caramelize. Blue Bottle Hayes Valley Espresso carries dried fruit alongside bittersweet chocolate and caramel. See the <a href="/flavor/fruit/">Fruit family guide</a>.</p>',
    ],
    [
        'taxonomy'    => 'flavor-note',
        'slug'        => 'stone-fruit',
        'name'        => 'Stone Fruit',
        'parent_slug' => 'fruit',
        'description' => '<p>Stone fruit (peach, apricot, plum) in coffee comes from high-altitude Ethiopian washed processing. Atlas Coffee Club Ethiopia Limu carries stone fruit alongside bergamot and jasmine — the origin character reads as a complete fruit-and-floral profile. See the <a href="/flavor/fruit/">Fruit family guide</a>.</p>',
    ],
    [
        'taxonomy'    => 'flavor-note',
        'slug'        => 'strawberry',
        'name'        => 'Strawberry',
        'parent_slug' => 'fruit',
        'description' => '<p>Strawberry in coffee is the signature of high-altitude Ethiopian washed light roast. Onyx Coffee Lab Southern Weather carries strawberry alongside cream soda and bright acidity — the clearest expression of this note in our catalog. See the <a href="/flavor/fruit/">Fruit family guide</a>.</p>',
    ],

    // ──────────────────────────────────────────────
    // FAMILY: Citrus & Floral
    // ──────────────────────────────────────────────
    [
        'taxonomy'        => 'flavor-note',
        'slug'            => 'citrus-floral',
        'name'            => 'Citrus & Floral',
        'parent_slug'     => null,
        'focus_keyword'   => 'floral coffee beans',
        'seo_title'       => 'Citrus & Floral Coffee Notes: Bergamot, Jasmine & What Causes Them | Coffee Bean Index',
        'seo_description' => 'Citrus and floral notes in coffee come from high-altitude growing and washed processing — primarily Ethiopian origins. Here\'s what causes them and which beans carry them.',
        'description'     => <<<'HTML'
<h2>What Citrus and Floral Notes in Coffee Are</h2>
<p>Citrus and floral notes — bergamot, orange blossom, jasmine, citrus brightness — are the calling card of high-altitude washed coffees, particularly from Ethiopia. These are not added flavors. They're terpenes and esters (linalool, geraniol, citric acid derivatives) that develop in coffee cherries grown above 1,500 meters and are preserved by washed processing.</p>
<p>The chemistry is direct: jasmine's primary aromatic compound (linalool) appears in measurable quantities in high-grown Ethiopian washed coffees. Bergamot's citrus-floral character comes from the same terpene family. Roasting at light temperatures preserves these volatile aromatics — darker roasting burns them off.</p>

<h2>Which Beans Carry Citrus and Floral Notes</h2>
<p><strong>Atlas Coffee Club Ethiopia Limu:</strong> bergamot, jasmine, stone fruit — the clearest citrus-and-floral profile in our catalog. Light-medium roast, washed, Limu sub-region.</p>
<p><strong>Onyx Coffee Lab Southern Weather:</strong> cream soda and bright acidity with a floral undertone — Ethiopia-based blend, light roast.</p>
<p><strong>Illy Classico:</strong> orange blossom and jasmine as secondary notes in a multi-origin Arabica blend. Medium roast maintains the florals from the lighter origins in the blend.</p>
<p><strong>Stumptown Hair Bender and Don Francisco's Colombia Supremo:</strong> mild citrus as a background brightness in medium-roast Latin American profiles.</p>

<h2>How to Taste These Notes</h2>
<p>Citrus and floral notes are aromatics — they're most present on the nose. Cup the coffee (steep without pressure, like a cupping bowl) or use pour over, and smell before sipping. The jasmine and bergamot in Ethiopian coffee are detected before the liquid hits the palate. If you're tasting blind for floral notes, smell first.</p>
HTML,
    ],
    [
        'taxonomy'    => 'flavor-note',
        'slug'        => 'bergamot',
        'name'        => 'Bergamot',
        'parent_slug' => 'citrus-floral',
        'description' => '<p>Bergamot is the citrus-floral note that defines high-altitude Ethiopian washed coffee. It reads as a brighter, more floral citrus than orange or lemon — closer to Earl Grey tea bergamot. Atlas Coffee Club Ethiopia Limu carries this as its primary descriptor. See the <a href="/flavor/citrus-floral/">Citrus &amp; Floral family guide</a>.</p>',
    ],
    [
        'taxonomy'    => 'flavor-note',
        'slug'        => 'orange-blossom',
        'name'        => 'Orange Blossom',
        'parent_slug' => 'citrus-floral',
        'description' => '<p>Orange blossom is a lighter, sweeter floral note than jasmine — delicate and perfumed. It appears in Illy Classico Medium Roast as part of the brand\'s signature multi-origin Arabica profile. See the <a href="/flavor/citrus-floral/">Citrus &amp; Floral family guide</a>.</p>',
    ],
    [
        'taxonomy'    => 'flavor-note',
        'slug'        => 'jasmine',
        'name'        => 'Jasmine',
        'parent_slug' => 'citrus-floral',
        'description' => '<p>Jasmine in coffee is the most prominent floral note — intense, perfumed, distinctly non-coffee in a way that surprises first-time drinkers. It\'s most present in light-to-medium washed Ethiopian coffees. Atlas Coffee Club Ethiopia Limu and Illy Classico both carry jasmine character. See the <a href="/flavor/citrus-floral/">Citrus &amp; Floral family guide</a>.</p>',
    ],

    // ──────────────────────────────────────────────
    // FAMILY: Earthy & Smoky
    // ──────────────────────────────────────────────
    [
        'taxonomy'        => 'flavor-note',
        'slug'            => 'earthy-smoky',
        'name'            => 'Earthy & Smoky',
        'parent_slug'     => null,
        'focus_keyword'   => 'earthy smoky coffee',
        'seo_title'       => 'Earthy & Smoky Coffee Notes: What Causes Them & Which Beans | Coffee Bean Index',
        'seo_description' => 'Earthy and smoky notes in coffee come from Indonesian wet-hull processing and dark roast development. Here\'s what they mean and which beans deliver them.',
        'description'     => <<<'HTML'
<h2>What Earthy and Smoky Notes in Coffee Are</h2>
<p>Earthy and smoky notes sit at the dark, heavy end of the coffee flavor spectrum. They're the opposite of the bright, floral citrus of Ethiopian light roast. Both are legitimate flavor profiles with dedicated audiences — but they're built on completely different chemistry.</p>
<p><strong>Earthy:</strong> comes primarily from the wet-hull (Giling Basah) process used in Indonesian coffees. The partial fermentation during the Sumatran wet-hull process produces 2-methylisoborneol and other terpenoids — the same compounds that make rain-on-soil smell like it does. Camano Island Coffee Roasters Sumatra carries this note at full intensity: cedar, forest floor, dark chocolate depth.</p>
<p><strong>Smoky:</strong> comes from dark roast development pushing beyond caramelization into carbonization. Smokiness is not quite char — it's a warm, controlled combustion note. Kicking Horse 454 Horse Power and Community Coffee Signature Blend Medium-Dark carry mild smokiness as a secondary note supporting dark chocolate and molasses.</p>
<p><strong>Cedar:</strong> the specific earthy note associated with Indonesian wet-hull processing — a dry wood character that separates Sumatran coffee from generic "earthy." Camano Island Sumatra is the clearest example in our catalog.</p>

<h2>Who These Notes Are For</h2>
<p>Drinkers who find brightness and acidity unpleasant. Heavy dark roast enthusiasts. French press drinkers who want maximum weight and texture. Anyone who drinks coffee for substance rather than aromatics.</p>
<p>Not for pour-over drinkers or anyone who wants clarity in the cup. Earthy and smoky notes do not benefit from paper filtration — use French press, drip, or cold brew to preserve the heavy texture that gives these notes context.</p>
HTML,
    ],
    [
        'taxonomy'    => 'flavor-note',
        'slug'        => 'earthy',
        'name'        => 'Earthy',
        'parent_slug' => 'earthy-smoky',
        'description' => '<p>Earthy in coffee means the forest-floor, wet-soil character produced by Indonesian wet-hull processing. It\'s the defining note of Sumatran coffee. Camano Island Coffee Roasters Sumatra is the primary example in our catalog — earthy, cedar, and dark chocolate in a full-body, low-acid cup. See the <a href="/flavor/earthy-smoky/">Earthy &amp; Smoky family guide</a>.</p>',
    ],
    [
        'taxonomy'    => 'flavor-note',
        'slug'        => 'cedar',
        'name'        => 'Cedar',
        'parent_slug' => 'earthy-smoky',
        'description' => '<p>Cedar is the dry wood note that distinguishes Sumatran wet-hull coffee from generic earthiness. It reads as clean and dry rather than musty. Camano Island Coffee Roasters Sumatra carries cedar clearly alongside earthy and dark chocolate notes. See the <a href="/flavor/earthy-smoky/">Earthy &amp; Smoky family guide</a>.</p>',
    ],
    [
        'taxonomy'    => 'flavor-note',
        'slug'        => 'smoky',
        'name'        => 'Smoky',
        'parent_slug' => 'earthy-smoky',
        'description' => '<p>Smokiness in coffee comes from dark roast development — controlled carbonization that produces a warm, campfire character without actual char. Kicking Horse 454 Horse Power carries smoky as a secondary note alongside dark chocolate and molasses. See the <a href="/flavor/earthy-smoky/">Earthy &amp; Smoky family guide</a>.</p>',
    ],
    [
        'taxonomy'    => 'flavor-note',
        'slug'        => 'tobacco',
        'name'        => 'Tobacco',
        'parent_slug' => 'earthy-smoky',
        'description' => '<p>Tobacco in coffee is the dry, slightly astringent note of very dark espresso roasts. It reads as intensity rather than bitterness — present without harshness in the best expressions. Café Bustelo Espresso Style Dark Roast carries tobacco alongside intense dark chocolate and thick body. See the <a href="/flavor/earthy-smoky/">Earthy &amp; Smoky family guide</a>.</p>',
    ],

];
