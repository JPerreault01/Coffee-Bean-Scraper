<?php
/**
 * Bulk-create bean CPT posts from products.json
 *
 * Run from WordPress root on the VPS:
 *   wp eval-file /opt/scrapers/create_beans.php --allow-root
 *
 * - Skips lavazza-super-crema (already created)
 * - Skips any bean whose slug already exists (safe to re-run)
 * - Sets all ACF fields, taxonomy terms, and affiliate URLs
 * - Posts created as 'draft' — publish manually after adding review copy
 *
 * Origin and flavor-note taxonomies use canonical curated terms rather than
 * raw sanitize_title() on freeform strings. Unmapped/dropped strings are
 * reported in the summary at the end.
 */

$products_file = '/opt/scrapers/products.json';

if ( ! file_exists( $products_file ) ) {
    WP_CLI::error( "products.json not found at {$products_file}" );
    exit;
}

$products = json_decode( file_get_contents( $products_file ), true );
if ( ! $products ) {
    WP_CLI::error( 'Failed to parse products.json — check file is valid JSON.' );
    exit;
}

// ---------------------------------------------------------------------------
// Origin canonical map
// Keys: exact "origin" strings from products.json
// Values: list of [ slug, display name ] canonical country/region pairs.
//
// A bean's origin resolves to MULTIPLE country tags so it surfaces under each
// country's filter and archive. Single-origin beans get one entry; blends get
// one entry per named country plus a ['blend','Blend'] marker so "show me only
// blends" stays possible. Where a source only names a region (e.g. "Latin
// America") with no countries, the regional term is kept alongside the marker.
// ---------------------------------------------------------------------------

$origin_map = [
    // ---- Single-country / no-data fallback ----
    'Colombia'                  => [ ['colombia',          'Colombia']          ],
    'Sumatra'                   => [ ['sumatra',           'Sumatra']           ],
    'Nicaragua (single origin)' => [ ['nicaragua',         'Nicaragua']         ],
    'Nicaragua'                 => [ ['nicaragua',         'Nicaragua']         ],
    'India'                     => [ ['india',             'India']             ],
    'Burundi'                   => [ ['burundi',           'Burundi']           ],
    'Tanzania, Oldeani'         => [ ['tanzania',          'Tanzania']          ],
    'Bolivia, Caranavi'         => [ ['bolivia',           'Bolivia']           ],
    'Ecuador, Hacienda La Papaya' => [ ['ecuador',         'Ecuador']           ],
    ''                          => [ ['blend',             'Blend']             ], // no origin data

    // ---- Ethiopia variants ----
    'Limu, Ethiopia'                            => [ ['ethiopia', 'Ethiopia'] ],
    'Yirgacheffe, Ethiopia'                     => [ ['ethiopia', 'Ethiopia'] ],
    'Guji, Ethiopia'                            => [ ['ethiopia', 'Ethiopia'] ],
    'Guji, Ethiopia, Hambela'                   => [ ['ethiopia', 'Ethiopia'] ],
    'Guji, Ethiopia, Oromia, Oromia (snnp)'    => [ ['ethiopia', 'Ethiopia'] ],
    'Ethiopia, Arbegona'                        => [ ['ethiopia', 'Ethiopia'] ],
    'Ethiopia, Bench Maji'                      => [ ['ethiopia', 'Ethiopia'] ],
    'Ethiopia, Bensa'                           => [ ['ethiopia', 'Ethiopia'] ],
    'Ethiopia, Bensa, Sidama, Ware'             => [ ['ethiopia', 'Ethiopia'] ],
    'Ethiopia, Danse Sayisa'                    => [ ['ethiopia', 'Ethiopia'] ],
    'Ethiopia, Gedeb'                           => [ ['ethiopia', 'Ethiopia'] ],
    'Ethiopia, Gedeo Zone'                      => [ ['ethiopia', 'Ethiopia'] ],
    'Ethiopia, Guji Uraga'                      => [ ['ethiopia', 'Ethiopia'] ],
    'Ethiopia, Sidama'                          => [ ['ethiopia', 'Ethiopia'] ],
    'Ethiopia, Worka Chelichele'                => [ ['ethiopia', 'Ethiopia'] ],
    'Ethiopia, Yirgacheffe'                     => [ ['ethiopia', 'Ethiopia'] ],
    'Ethiopia, Yirgacheffe, Gedeb'              => [ ['ethiopia', 'Ethiopia'] ],
    'Ethiopia, Yirgacheffe, Gedeb, Worka Chelichele' => [ ['ethiopia', 'Ethiopia'] ],

    // ---- Colombia variants ----
    'Colombia, Calarca'   => [ ['colombia', 'Colombia'] ],
    'Colombia, Caldas'    => [ ['colombia', 'Colombia'] ],
    'Colombia, Huila'     => [ ['colombia', 'Colombia'] ],
    'Colombia, Pitalito'  => [ ['colombia', 'Colombia'] ],
    'Colombia, Planadas'  => [ ['colombia', 'Colombia'] ],
    'Colombia, Quindío'   => [ ['colombia', 'Colombia'] ],
    'Colombia, Risaralda' => [ ['colombia', 'Colombia'] ],

    // ---- Kenya variants ----
    'Kenya, Kiambu'      => [ ['kenya', 'Kenya'] ],
    'Kenya, Kirinyaga'   => [ ['kenya', 'Kenya'] ],
    'Kenya, Nyeri'       => [ ['kenya', 'Kenya'] ],
    'Kenya, Nyeri, Tetu' => [ ['kenya', 'Kenya'] ],

    // ---- Costa Rica variants ----
    'Tarrazu, Costa Rica'                        => [ ['costa-rica', 'Costa Rica'] ],
    'Costa Rica, Brunca-chirripó'                => [ ['costa-rica', 'Costa Rica'] ],
    'Costa Rica, Central Valley'                 => [ ['costa-rica', 'Costa Rica'] ],
    'Costa Rica, Finca La Candelilla'            => [ ['costa-rica', 'Costa Rica'] ],
    'Costa Rica, Sabanilla De Alajuela, Naranjo' => [ ['costa-rica', 'Costa Rica'] ],
    'Costa Rica, Santa Barbara De Heredia'       => [ ['costa-rica', 'Costa Rica'] ],
    'Costa Rica, West Valley'                    => [ ['costa-rica', 'Costa Rica'] ],
    'Costa Rica, West Valley Zarcero'            => [ ['costa-rica', 'Costa Rica'] ],

    // ---- Panama variants ----
    'Panama, Bambito'     => [ ['panama', 'Panama'] ],
    'Panama, Boquete'     => [ ['panama', 'Panama'] ],
    'Panama, Santa Clara' => [ ['panama', 'Panama'] ],
    'Jaramillo, Panama'   => [ ['panama', 'Panama'] ],

    // ---- Brazil variants ----
    'Minas Gerais, Brazil'           => [ ['brazil', 'Brazil'] ],
    'Brazil, Carmo De Minas'         => [ ['brazil', 'Brazil'] ],
    'Brazil, Matas De Minas'         => [ ['brazil', 'Brazil'] ],
    'Brazil, Paraná, Norte Pioneiro' => [ ['brazil', 'Brazil'] ],

    // ---- El Salvador ----
    'El Salvador, Apaneca Ilamatepec' => [ ['el-salvador', 'El Salvador'] ],
    'El Salvador, Chalatenango'       => [ ['el-salvador', 'El Salvador'] ],

    // ---- Guatemala ----
    'Guatemala, Antigua'       => [ ['guatemala', 'Guatemala'] ],
    'Guatemala, Huehuetenango' => [ ['guatemala', 'Guatemala'] ],

    // ---- Indonesia variants ----
    'Indonesia, Aceh'    => [ ['indonesia', 'Indonesia'] ],
    'Indonesia, Sumatra' => [ ['indonesia', 'Indonesia'] ],

    // ---- India variants ----
    'India, Western Ghats' => [ ['india', 'India'] ],

    // ---- Burundi variants ----
    'Kayanza, Burundi' => [ ['burundi', 'Burundi'] ],

    // ---- Papua New Guinea ----
    'Papua New Guinea, Chimbu Province' => [ ['papua-new-guinea', 'Papua New Guinea'] ],

    // ---- Hawaii / United States ----
    'Kona, Hawaii'                             => [ ['hawaii', 'Hawaii'] ],
    'South Kona, United States, Hōlualoa'      => [ ['hawaii', 'Hawaii'] ],
    'United States'                            => [ ['hawaii', 'Hawaii'] ],
    'United States, Hawaii'                    => [ ['hawaii', 'Hawaii'] ],
    "United States, Ka'u"                      => [ ['hawaii', 'Hawaii'] ],
    'United States, Kona'                      => [ ['hawaii', 'Hawaii'] ],
    'United States, Kona Coffee Belt (hawaii)' => [ ['hawaii', 'Hawaii'] ],
    "United States, Kona District, Hawai'i"    => [ ['hawaii', 'Hawaii'] ],
    'United States, Kona, Hawaii, Big Island'  => [ ['hawaii', 'Hawaii'] ],
    'Chiapas, Mexico'                          => [ ['mexico',  'Mexico'] ],

    // ---- Multi-country blends ----
    'Latin America blend'             => [ ['latin-america', 'Latin America'], ['blend', 'Blend'] ],
    'Central and South America blend' => [ ['latin-america', 'Latin America'], ['blend', 'Blend'] ],
    'Central America, South America, Sumatra blend' => [
        ['central-america', 'Central America'], ['south-america', 'South America'],
        ['sumatra', 'Sumatra'], ['blend', 'Blend'],
    ],
    'Colombia, Brazil, Honduras blend'  => [ ['colombia', 'Colombia'], ['brazil', 'Brazil'], ['honduras', 'Honduras'], ['blend', 'Blend'] ],
    'Colombia, Central America blend'   => [ ['colombia', 'Colombia'], ['central-america', 'Central America'], ['blend', 'Blend'] ],
    'Brazil, Colombia, Indonesia blend' => [ ['brazil', 'Brazil'], ['colombia', 'Colombia'], ['indonesia', 'Indonesia'], ['blend', 'Blend'] ],
    'Brazil, Colombia, Carmo De Minas'  => [ ['brazil', 'Brazil'], ['colombia', 'Colombia'], ['blend', 'Blend'] ],
    'Brazil, Cerrado, Guatemala, Indonesia, Huehuetenango, Sumatra' => [
        ['brazil', 'Brazil'], ['guatemala', 'Guatemala'], ['indonesia', 'Indonesia'], ['blend', 'Blend'],
    ],
    'Brazil, Ethiopia, Bensa, Mantiqueira De Minas, Yirgacheffe' => [
        ['brazil', 'Brazil'], ['ethiopia', 'Ethiopia'], ['blend', 'Blend'],
    ],
    'Brazil, Indonesia, India, Idukki, Sumatra, Cerrado Minero' => [
        ['brazil', 'Brazil'], ['indonesia', 'Indonesia'], ['india', 'India'], ['blend', 'Blend'],
    ],
    'Brazil, Tarrazú, Costa Rica, Cerrado Mineiro, Guatemala, Huehuetenango' => [
        ['brazil', 'Brazil'], ['costa-rica', 'Costa Rica'], ['guatemala', 'Guatemala'], ['blend', 'Blend'],
    ],
    '9-country Arabica blend'                         => [ ['blend', 'Blend'] ],
    'Latin America, Indonesia blend'                  => [ ['latin-america', 'Latin America'], ['indonesia', 'Indonesia'], ['blend', 'Blend'] ],
    'Latin America, East Africa blend'                => [ ['latin-america', 'Latin America'], ['east-africa', 'East Africa'], ['blend', 'Blend'] ],
    'India, Peru blend'                               => [ ['india', 'India'], ['peru', 'Peru'], ['blend', 'Blend'] ],
    'Indonesia, Central America, South America blend' => [ ['indonesia', 'Indonesia'], ['central-america', 'Central America'], ['south-america', 'South America'], ['blend', 'Blend'] ],
    'Ethiopia, Colombia blend'                        => [ ['ethiopia', 'Ethiopia'], ['colombia', 'Colombia'], ['blend', 'Blend'] ],
    'Ethiopia, Latin America blend'                   => [ ['ethiopia', 'Ethiopia'], ['latin-america', 'Latin America'], ['blend', 'Blend'] ],
    'Indonesia, South America blend'                  => [ ['indonesia', 'Indonesia'], ['south-america', 'South America'], ['blend', 'Blend'] ],
    'Nyamasheke, Rwanda, Guatemala, Peña Blanca' => [ ['rwanda', 'Rwanda'], ['guatemala', 'Guatemala'], ['blend', 'Blend'] ],
    'Nyamasheke, Rwanda, Kayanza, Burundi'       => [ ['rwanda', 'Rwanda'], ['burundi', 'Burundi'], ['blend', 'Blend'] ],

    // ---- 69-bean specialty batch (2026-06) ----
    'Brazil, Colombia'                                  => [ ['brazil', 'Brazil'], ['colombia', 'Colombia'], ['blend', 'Blend'] ],
    'Brazil, Colombia, Cerrado Mineiro, Pitalito, La Plata' => [ ['brazil', 'Brazil'], ['colombia', 'Colombia'], ['blend', 'Blend'] ],
    'Brazil, Sul De Minas'                              => [ ['brazil', 'Brazil'] ],
    'Colombia, Acevedo'                                 => [ ['colombia', 'Colombia'] ],
    'Colombia, Cauca, Sotará'                           => [ ['colombia', 'Colombia'] ],
    'Colombia, El Diviso Estate'                        => [ ['colombia', 'Colombia'] ],
    'Colombia, Ethiopia'                                => [ ['colombia', 'Colombia'], ['ethiopia', 'Ethiopia'], ['blend', 'Blend'] ],
    'Colombia, Nariño'                                  => [ ['colombia', 'Colombia'] ],
    'Colombia, Northern Huila'                          => [ ['colombia', 'Colombia'] ],
    'Colombia, Risaralda, Marsella'                     => [ ['colombia', 'Colombia'] ],
    'Colombia, Santa Monica'                            => [ ['colombia', 'Colombia'] ],
    'Colombia, Sierra Nevada De Santa Marta'            => [ ['colombia', 'Colombia'] ],
    'Costa Rica'                                        => [ ['costa-rica', 'Costa Rica'] ],
    'Costa Rica, Los Santos'                            => [ ['costa-rica', 'Costa Rica'] ],
    'Costa Rica, Turrialba Volcano'                     => [ ['costa-rica', 'Costa Rica'] ],
    'Dominican Republic, Cibao'                         => [ ['dominican-republic', 'Dominican Republic'] ],
    'El Salvador, La Primavera'                         => [ ['el-salvador', 'El Salvador'] ],
    'El Salvador, Santa Ana'                            => [ ['el-salvador', 'El Salvador'] ],
    'Ethiopia'                                          => [ ['ethiopia', 'Ethiopia'] ],
    'Ethiopia, Amaro, Amaro Gayo'                       => [ ['ethiopia', 'Ethiopia'] ],
    'Ethiopia, Bombe'                                   => [ ['ethiopia', 'Ethiopia'] ],
    'Ethiopia, Chelbesa, Gedeo'                         => [ ['ethiopia', 'Ethiopia'] ],
    'Ethiopia, Danbi Uddo'                              => [ ['ethiopia', 'Ethiopia'] ],
    'Ethiopia, Sidama - Bensa'                          => [ ['ethiopia', 'Ethiopia'] ],
    'Ethiopia, Sidama, Arbegona'                        => [ ['ethiopia', 'Ethiopia'] ],
    'Ethiopia, Uraga'                                   => [ ['ethiopia', 'Ethiopia'] ],
    'Ethiopia, Yirgacheffe (idido)'                     => [ ['ethiopia', 'Ethiopia'] ],
    'Guatemala, Fraijanes'                              => [ ['guatemala', 'Guatemala'] ],
    'Guatemala, Huehuetenango, Chimaltenango'           => [ ['guatemala', 'Guatemala'] ],
    'Guatemala, Jalapa'                                 => [ ['guatemala', 'Guatemala'] ],
    'Guji, Ethiopia, Shakiso, Oromia'                   => [ ['ethiopia', 'Ethiopia'] ],
    'Indonesia, Takengon (aceh)'                        => [ ['indonesia', 'Indonesia'] ],
    'Kenya, Embu'                                       => [ ['kenya', 'Kenya'] ],
    'Kenya, Nyeri, Mexico, Muranga, Oaxaca'             => [ ['kenya', 'Kenya'], ['mexico', 'Mexico'], ['blend', 'Blend'] ],
    'Malaysia'                                          => [ ['malaysia', 'Malaysia'] ],
    'Malaysia, Simpang Renggam'                         => [ ['malaysia', 'Malaysia'] ],
    'Nyamasheke, Rwanda'                                => [ ['rwanda', 'Rwanda'] ],
    'Panama, El Velo, Quiel'                            => [ ['panama', 'Panama'] ],
    'Rwanda, Ecuador, Western Province, Rutsiro District, Sumaco Archidona' => [ ['rwanda', 'Rwanda'], ['ecuador', 'Ecuador'], ['blend', 'Blend'] ],
    'Rwanda, Gatsibo'                                   => [ ['rwanda', 'Rwanda'] ],
    'Rwanda, Maraba'                                    => [ ['rwanda', 'Rwanda'] ],
    'South Kona, United States'                         => [ ['hawaii', 'Hawaii'] ],
    'Tarrazú, Costa Rica'                               => [ ['costa-rica', 'Costa Rica'] ],
    'Tolima, Colombia'                                  => [ ['colombia', 'Colombia'] ],
    'Tolima, Colombia, Ethiopia, Limu'                  => [ ['colombia', 'Colombia'], ['ethiopia', 'Ethiopia'], ['blend', 'Blend'] ],
    "United States, Ka'ū (hawai'i Island, Hawaii), Maragogipe" => [ ['hawaii', 'Hawaii'] ],
    'Vietnam, Quảng Trị, Quang Chi'                     => [ ['vietnam', 'Vietnam'] ],
];

// ---------------------------------------------------------------------------
// Origin continent hierarchy
// Newly-created origin country terms are nested under a continent parent so the
// front-end tree (page-explore.php, taxonomy-bean-archive.php) stays correct
// going forward. The migration script back-fills any existing flat terms.
// keep in sync with set_origin_continents.php
// ---------------------------------------------------------------------------

$continent_parents = [
    'africa'        => 'Africa',
    'asia'          => 'Asia',
    'north-america' => 'North America',
    'south-america' => 'South America',
    'oceania'       => 'Oceania',
    'europe'        => 'Europe',
];

// keep in sync with set_origin_continents.php
$country_to_continent = [
    // Africa
    'ethiopia'           => 'africa',
    'kenya'              => 'africa',
    'burundi'            => 'africa',
    'tanzania'           => 'africa',
    'rwanda'             => 'africa',
    'uganda'             => 'africa',
    // Asia
    'sumatra'            => 'asia',
    'indonesia'          => 'asia',
    'india'              => 'asia',
    'papua-new-guinea'   => 'asia',
    'vietnam'            => 'asia',
    'timor'              => 'asia',
    // North America
    'mexico'             => 'north-america',
    'guatemala'          => 'north-america',
    'costa-rica'         => 'north-america',
    'honduras'           => 'north-america',
    'nicaragua'          => 'north-america',
    'el-salvador'        => 'north-america',
    'panama'             => 'north-america',
    'hawaii'             => 'north-america',
    'jamaica'            => 'north-america',
    'dominican-republic' => 'north-america',
    'central-america'    => 'north-america',
    'united-states'      => 'north-america',
    // South America
    'colombia'           => 'south-america',
    'brazil'             => 'south-america',
    'peru'               => 'south-america',
    'bolivia'            => 'south-america',
    'ecuador'            => 'south-america',
    'south-america'      => 'south-america', // region term IS the continent
];
// Structural markers (blend, latin-america, multi-origin-blend) are intentionally
// absent from the map above so they stay top-level (parent 0).

// ---------------------------------------------------------------------------
// Flavor-note canonical map
// Keys: exact lowercase strings from products.json "flavor_notes" arrays
// Values:
//   string  = curated flavor-note slug (must already exist from seed data)
//   null    = genuine flavor with no curated term — warn + skip
//   false   = structural/sensory descriptor, not a flavor — drop silently
//
// Structural descriptors (bold, smooth, full body, etc.) are already captured
// by ACF sensory bars (acidity, body, sweetness, bitterness, roast_intensity).
// Creating flavor-note taxonomy terms for them pollutes the flavor hierarchy.
// ---------------------------------------------------------------------------

$flavor_structural_drops = [
    // Body/texture
    'bold', 'smooth', 'mild', 'intense', 'silky',
    'full body', 'medium body', 'thick body', 'smooth body', 'creamy body', 'thick crema', 'light body',
    // Acidity/bitterness
    'low acid', 'low acidity', 'low bitterness', 'bright acidity', 'citric acid',
    // Finish/balance/descriptive
    'balanced', 'clean', 'clean finish', 'lingering finish',
    'boozy', 'funky', 'herb-like', 'mineral', 'sour aromatics', 'sugary/sweet', 'sweetness', 'tea-like',
    // 69-bean specialty batch (2026-06) — texture/acidity/sweetness descriptors, not flavors
    'cream', 'creamy', 'juicy', 'round body', 'malic acidity', 'winey acidity',
    'sugary sweetness', 'stevia', 'wine-like peppery finish',
];

$flavor_canonical_map = [
    // Chocolate family (slugs from seeds/data/flavor-note-terms.php)
    'dark chocolate'       => 'dark-chocolate',
    'milk chocolate'       => 'milk-chocolate',
    'bittersweet chocolate' => 'bittersweet-chocolate',
    'mild cocoa'           => 'mild-cocoa',
    'light cocoa'          => 'mild-cocoa',
    'mild chocolate'       => 'mild-cocoa',
    'light chocolate'      => 'mild-cocoa',
    'chocolate'            => 'chocolate',       // parent family term

    // Caramel & Sweet family
    'caramel'              => 'caramel',
    'light caramel'        => 'caramel',
    'brown sugar'          => 'brown-sugar',
    'toffee'               => 'toffee',
    'molasses'             => 'molasses',

    // Nutty family
    'hazelnut'             => 'hazelnut',
    'walnut'               => 'walnut',
    'nuts'                 => 'nutty',           // parent family term
    'nutty'                => 'nutty',           // parent family term

    // Fruit family
    'dark cherry'          => 'dark-cherry',
    'dried fruit'          => 'dried-fruit',
    'stone fruit'          => 'stone-fruit',
    'strawberry'           => 'strawberry',
    'mild fruit'           => 'fruit',           // parent family term

    // Citrus & Floral family
    'bergamot'             => 'bergamot',
    'orange blossom'       => 'orange-blossom',
    'jasmine'              => 'jasmine',
    'citrus'               => 'citrus-floral',   // no child slug for generic citrus; use parent
    'mild citrus'          => 'citrus-floral',

    // Earthy & Smoky family
    'earthy'               => 'earthy',
    'cedar'                => 'cedar',
    'smoky'                => 'smoky',
    'mild smokiness'       => 'smoky',
    'tobacco'              => 'tobacco',

    // Genuine flavors with no curated term — warn + skip
    'cream soda'           => null,

    // Additional flavor strings from bulk import (2026-06)
    'spice'          => 'spice',
    'raisin'         => 'dried-fruit',
    'sweet citrus'   => 'citrus-floral',
    'graham cracker' => 'caramel',
    'cocoa'          => 'chocolate',
    'toasted nut'    => 'nutty',
    'toasted almond' => 'nutty',
    'red fruit'      => 'red-fruit',
    'berry'          => 'red-fruit',
    'honey'          => 'caramel',
    'blueberry'      => 'blueberry',
    'floral'         => 'floral',
    'charred'        => 'smoky',
    'toasted malt'   => 'nutty',
    'soft cocoa'     => 'chocolate',
    'chicory'        => 'earthy',
    'marshmallow'    => 'caramel',
    'raspberry'      => 'red-fruit',
    'cherry'         => 'red-fruit',
    'plum'           => 'dried-fruit',
    'sweet'          => 'caramel',
    'bright'         => false,
    'light body'     => false,

    // Additional flavors from 100-bean catalog expansion (2026-06)

    // Berries
    'blackberry'       => 'red-fruit',
    'blackcurrant'     => 'red-fruit',
    'boysenberry'      => 'red-fruit',
    'cranberry'        => 'red-fruit',
    'grape'            => 'red-fruit',
    'grape candy'      => 'red-fruit',
    'grape soda'       => 'red-fruit',
    'black grape'      => 'red-fruit',
    'pomegranate'      => 'red-fruit',
    'raspberries'      => 'red-fruit',
    'yellow berries'   => 'red-fruit',
    'yellow berry'     => 'red-fruit',
    'strawberries'     => 'strawberry',
    'strawberry papaya' => 'strawberry',
    'strawberry yogurt' => 'strawberry',
    'dried strawberry' => 'dried-fruit',
    'blueberry candy'  => 'blueberry',

    // Cherries
    'black cherry'     => 'dark-cherry',
    'dried cherry'     => 'dark-cherry',
    'red cherry'       => 'dark-cherry',
    'white cherry'     => 'dark-cherry',
    'cherry liqueur'   => 'dark-cherry',
    'maraschino'       => 'dark-cherry',

    // Stone fruit
    'apricot'          => 'stone-fruit',
    'apricot liqueur'  => 'stone-fruit',
    'dried apricot'    => 'dried-fruit',
    'nectarine'        => 'stone-fruit',
    'peach'            => 'stone-fruit',
    'purple plum'      => 'dried-fruit',

    // Tree fruit / tropical
    'apple'            => 'fruit',
    'baked apple'      => 'fruit',
    'crisp apple'      => 'fruit',
    'fuji apple'       => 'fruit',
    'green apple'      => 'fruit',
    'pear'             => 'fruit',
    'yellow pear'      => 'fruit',
    'pineapple'        => 'fruit',
    'pineapple juice'  => 'fruit',
    'canned pineapple' => 'fruit',
    'watermelon candy' => 'fruit',
    'honeydew melon'   => 'fruit',
    'orchard fruit'    => 'fruit',
    'dried fig'        => 'dried-fruit',
    'dried currants'   => 'dried-fruit',
    'dried fruits'     => 'dried-fruit',

    // Citrus
    'blood orange'     => 'citrus-floral',
    'citrus fruit'     => 'citrus-floral',
    'citrus brightness' => 'citrus-floral',
    'grapefruit'       => 'citrus-floral',
    'white grapefruit' => 'citrus-floral',
    'lemon'            => 'citrus-floral',
    'lemon candy'      => 'citrus-floral',
    'lemon cream'      => 'citrus-floral',
    'lemon sponge'     => 'citrus-floral',
    'lemon verbena'    => 'citrus-floral',
    'sweet lemon'      => 'citrus-floral',
    'lime'             => 'citrus-floral',
    'mandarin peel'    => 'citrus-floral',
    'meyer lemon'      => 'citrus-floral',
    'orange'           => 'citrus-floral',
    'orange peel'      => 'citrus-floral',
    'orange zest'      => 'citrus-floral',
    'pink lemonade'    => 'citrus-floral',
    'preserved lemon'  => 'citrus-floral',
    'yuzu'             => 'citrus-floral',

    // Floral
    'coffee blossom'   => 'floral',
    'dried florals'    => 'floral',
    'floral notes'     => 'floral',
    'gardenia'         => 'floral',
    'hibiscus'         => 'floral',
    'jasmine honey'    => 'jasmine',
    'linden blossom'   => 'floral',
    'marigold'         => 'floral',
    'parma violet'     => 'floral',
    'pink rose'        => 'floral',
    'plumeria'         => 'floral',
    'poppy'            => 'floral',
    'rose'             => 'floral',
    'rosehip'          => 'floral',
    'subtle florals'   => 'floral',
    'white florals'    => 'floral',
    'white flower syrup' => 'floral',

    // Chocolate
    'cocoa nibs'       => 'chocolate',
    'cocoa powder'     => 'chocolate',
    'dark cocoa'       => 'chocolate',
    'liquor chocolate' => 'chocolate',
    'mint choc'        => 'chocolate',

    // Caramel & sweet
    'barley malt syrup'   => 'caramel',
    'burnt sugar'         => 'caramel',
    'butter cookie'       => 'caramel',
    'caramelized'         => 'caramel',
    'cookie'              => 'caramel',
    'dulce de leche'      => 'caramel',
    'fruit toffee'        => 'toffee',
    'malt'                => 'caramel',
    'maltose'             => 'caramel',
    'maple syrup'         => 'caramel',
    'raw honey'           => 'caramel',
    'toasted marshmallow' => 'caramel',
    'turbinado sugar'     => 'brown-sugar',
    'vanilla'             => 'caramel',

    // Nutty
    'almond'           => 'nutty',
    'peanuts'          => 'nutty',
    'pistachio'        => 'nutty',
    'praline nut'      => 'nutty',
    'roasted hazelnut' => 'hazelnut',

    // Spice
    'baking spices'    => 'spice',
    'brown spice'      => 'spice',
    'cinnamon'         => 'spice',
    'ginger'           => 'spice',
    'nutmeg'           => 'spice',
    'peppercorn'       => 'spice',
    'pink peppercorn'  => 'spice',
    'spices'           => 'spice',
    'woody spices'     => 'spice',

    // Earthy / smoky
    'pipe tobacco'     => 'tobacco',
    'woody'            => 'earthy',

    // Genuine flavors with no curated term — skip to avoid orphan taxonomy entries
    'berry milk tea'   => null,
    'black tea'        => null,
    'buah bidara'      => null,
    'calpis'           => null,
    'ceylon'           => null,
    'coffee ice cream' => null,
    'elephant heart plum' => null,
    'haskap'           => null,
    'hawthorn'         => null,
    'lychee jelly'     => null,
    'mango cream'      => null,
    'mint'             => null,
    'oolong'           => null,
    'sangria'          => null,
    'sherbet'          => null,
    'shiraz'           => null,
    'shiso plum'       => null,
    'soursop'          => null,
    'spearmint'        => null,
    'tamarind'         => null,
    'tomato'           => null,
    'whipped cream'    => null,

    // Additional flavors from 69-bean specialty batch (2026-06)
    'almonds'             => 'nutty',
    'amaretto'            => 'nutty',
    'roasted nut'         => 'nutty',
    'toasted nuts'        => 'nutty',
    'toast'               => 'nutty',
    'nutty/cocoa'         => 'nutty',
    'baker\'s chocolate'  => 'dark-chocolate',
    'cacao nibs'          => 'chocolate',
    'cocoa bitters'       => 'chocolate',
    'sweet chocolate'     => 'chocolate',
    'fondue'              => 'chocolate',
    'barley'              => 'caramel',
    'brown butter'        => 'caramel',
    'butterscotch'        => 'caramel',
    'cookies'             => 'caramel',
    'shortbread'          => 'caramel',
    'tonka bean'          => 'caramel',
    'wild honey'          => 'caramel',
    'bonfire toffee'      => 'toffee',
    'panela'              => 'brown-sugar',
    'ananas'              => 'fruit',
    'cherimoya'           => 'fruit',
    'cooked apple'        => 'fruit',
    'jackfruit'           => 'fruit',
    'lychee'              => 'fruit',
    'mango'               => 'fruit',
    'passion fruit'       => 'fruit',
    'water apple'         => 'fruit',
    'green grape'         => 'red-fruit',
    'red currant'         => 'red-fruit',
    'white grape juice'   => 'red-fruit',
    'sour cherry'         => 'dark-cherry',
    'sweet cherry'        => 'dark-cherry',
    'aromatic woods'      => 'cedar',
    'dried banana'        => 'dried-fruit',
    'dried date'          => 'dried-fruit',
    'dried tropical fruit' => 'dried-fruit',
    'golden raisin'       => 'dried-fruit',
    'prune'               => 'dried-fruit',
    'shiro plum'          => 'dried-fruit',
    'yellow plum'         => 'dried-fruit',
    'kumquat'             => 'citrus-floral',
    'orange citrus'       => 'citrus-floral',
    'pomelo'              => 'citrus-floral',
    'sweet orange'        => 'citrus-floral',
    'chamomile'           => 'floral',
    'dark rose'           => 'floral',
    'floral aromatics'    => 'floral',
    'honeysuckle'         => 'floral',
    'lily'                => 'floral',
    'lotus'               => 'floral',
    'sakura'              => 'floral',
    'violet'              => 'floral',
    'crystallized ginger' => 'spice',
    'gingersnap'          => 'spice',
    'spicy'               => 'spice',
    // Genuine flavors with no curated term — warn + skip
    'bubblegum'           => null,
    'champagne candy'     => null,
    'dried tomato'        => null,
    'rice pudding'        => null,
];

// ---------------------------------------------------------------------------
// Helper: ensure a term with the given slug and display name exists in a
// taxonomy, then return its term_id. Creates it if absent.
// ---------------------------------------------------------------------------

function cbi_get_or_create_term( $slug, $name, $taxonomy ) {
    $term = get_term_by( 'slug', $slug, $taxonomy );
    if ( $term && ! is_wp_error( $term ) ) {
        return (int) $term->term_id;
    }
    $result = wp_insert_term( $name, $taxonomy, [ 'slug' => $slug ] );
    if ( is_wp_error( $result ) ) {
        WP_CLI::warning( "  Could not create term '{$name}' ({$slug}) in {$taxonomy}: " . $result->get_error_message() );
        return null;
    }
    return (int) $result['term_id'];
}

// ---------------------------------------------------------------------------
// Helper: if an origin term is a known country, ensure it sits under the right
// continent parent (creating the parent if needed). Unknown slugs and the
// structural markers (blend, latin-america) are left at the top level.
// Mirrors set_origin_continents.php so newly-created beans nest correctly.
// ---------------------------------------------------------------------------

function cbi_ensure_origin_parent( $term_id, $slug, array $country_to_continent, array $continent_parents ) {
    if ( ! isset( $country_to_continent[ $slug ] ) ) {
        return; // not a known country — leave top-level
    }
    $continent_slug = $country_to_continent[ $slug ];
    if ( $slug === $continent_slug ) {
        return; // term IS the continent (e.g. south-america) — stays top-level
    }
    if ( ! isset( $continent_parents[ $continent_slug ] ) ) {
        return; // no display name for this continent — defensive
    }
    $parent_id = cbi_get_or_create_term( $continent_slug, $continent_parents[ $continent_slug ], 'origin' );
    if ( ! $parent_id ) {
        return;
    }
    $term = get_term( $term_id, 'origin' );
    if ( $term && ! is_wp_error( $term ) && (int) $term->parent !== (int) $parent_id ) {
        wp_update_term( $term_id, 'origin', [ 'parent' => (int) $parent_id ] );
    }
}

// ---------------------------------------------------------------------------
// Already created — skip these
// ---------------------------------------------------------------------------

$skip_ids = [ 'lavazza-super-crema' ];

// Counters and summary accumulators
$created  = 0;
$skipped  = 0;
$failed   = 0;

$unmapped_origins    = [];  // origin string => product id (fell back to sanitize_title)
$dropped_structural  = [];  // structural descriptors silently dropped
$no_curated_term     = [];  // real flavor notes with no matching curated slug
$unknown_flavor_strs = [];  // strings not present in either map (mapping gap)
$missing_db_terms    = [];  // curated slugs that don't exist in the DB yet

// ---------------------------------------------------------------------------
// Main loop
// ---------------------------------------------------------------------------

foreach ( $products as $p ) {
    $id = $p['id'];

    if ( in_array( $id, $skip_ids, true ) ) {
        WP_CLI::log( "SKIP  {$id} (in skip list)" );
        $skipped++;
        continue;
    }

    // Check if slug already exists as a bean post
    $existing = get_page_by_path( $id, OBJECT, 'bean' );
    if ( $existing ) {
        WP_CLI::log( "SKIP  {$id} — already exists as post #{$existing->ID}" );
        $skipped++;
        continue;
    }

    // --- Create the post ---
    $post_id = wp_insert_post( [
        'post_type'   => 'bean',
        'post_title'  => $p['name'],
        'post_name'   => $id,
        'post_status' => 'draft',
    ], true );

    if ( is_wp_error( $post_id ) ) {
        WP_CLI::warning( "FAILED {$id} — " . $post_id->get_error_message() );
        $failed++;
        continue;
    }

    // -----------------------------------------------------------------------
    // Taxonomies
    // -----------------------------------------------------------------------

    // roaster  (brand name — use sanitize_title, brand names are already clean)
    wp_set_object_terms( $post_id, sanitize_title( $p['brand'] ), 'roaster' );

    // roast-level
    wp_set_object_terms( $post_id, sanitize_title( $p['roast_level'] ), 'roast-level' );

    // process-method
    wp_set_object_terms( $post_id, sanitize_title( $p['process_method'] ), 'process-method' );

    // brew-method  (array)
    $brew_slugs = array_map( 'sanitize_title', $p['best_brew_methods'] ?? [] );
    wp_set_object_terms( $post_id, $brew_slugs, 'brew-method' );

    // --- Origin (canonical, multi-tag) ---
    $raw_origin = $p['origin'] ?? '';
    if ( isset( $origin_map[ $raw_origin ] ) ) {
        $origin_term_ids = [];
        foreach ( $origin_map[ $raw_origin ] as $pair ) {
            [ $o_slug, $o_name ] = $pair;
            $o_term_id = cbi_get_or_create_term( $o_slug, $o_name, 'origin' );
            if ( $o_term_id ) {
                // Nest known countries under their continent parent (no-op for
                // structural markers and already-parented terms).
                cbi_ensure_origin_parent( $o_term_id, $o_slug, $country_to_continent, $continent_parents );
                $origin_term_ids[] = $o_term_id;
            }
        }
        if ( $origin_term_ids ) {
            wp_set_object_terms( $post_id, array_unique( $origin_term_ids ), 'origin' );
        }
    } else {
        WP_CLI::warning( "  UNMAPPED origin for {$id}: \"{$raw_origin}\" — falling back to sanitize_title" );
        wp_set_object_terms( $post_id, sanitize_title( $raw_origin ), 'origin' );
        $unmapped_origins[ $raw_origin ] = $id;
    }

    // --- Flavor notes (canonical, curated only) ---
    $flavor_term_ids = [];
    foreach ( $p['flavor_notes'] ?? [] as $raw_note ) {
        $note = strtolower( trim( $raw_note ) );

        // Structural/sensory descriptor — drop silently
        if ( in_array( $note, $flavor_structural_drops, true ) ) {
            $dropped_structural[] = $note;
            continue;
        }

        // Not in the canonical map at all — mapping gap, warn
        if ( ! array_key_exists( $note, $flavor_canonical_map ) ) {
            WP_CLI::warning( "  UNKNOWN flavor string for {$id}: \"{$raw_note}\" — add to \$flavor_canonical_map" );
            $unknown_flavor_strs[] = $note;
            continue;
        }

        $curated_slug = $flavor_canonical_map[ $note ];

        // null = genuine flavor but no curated term yet
        if ( $curated_slug === null ) {
            WP_CLI::warning( "  NO CURATED TERM for \"{$raw_note}\" ({$id}) — skipping to avoid orphan" );
            $no_curated_term[] = $note;
            continue;
        }

        // Confirm the term actually exists in the DB (seeded by flavor-note-terms.php)
        $term = get_term_by( 'slug', $curated_slug, 'flavor-note' );
        if ( ! $term || is_wp_error( $term ) ) {
            WP_CLI::warning( "  MISSING DB TERM '{$curated_slug}' (flavor-note) for {$id} — run seeds first" );
            $missing_db_terms[] = $curated_slug;
            continue;
        }

        $flavor_term_ids[] = (int) $term->term_id;
    }

    if ( $flavor_term_ids ) {
        wp_set_object_terms( $post_id, array_unique( $flavor_term_ids ), 'flavor-note' );
    }

    // -----------------------------------------------------------------------
    // ACF fields
    // -----------------------------------------------------------------------

    // Sensory scores
    update_field( 'acidity',         $p['acidity'],         $post_id );
    update_field( 'body',            $p['body'],            $post_id );
    update_field( 'sweetness',       $p['sweetness'],       $post_id );
    update_field( 'bitterness',      $p['bitterness'],      $post_id );
    update_field( 'roast_intensity', $p['roast_intensity'], $post_id );

    // Specs
    update_field( 'weight_oz',  $p['weight_oz'], $post_id );
    update_field( 'product_id', $id,             $post_id );

    if ( ! empty( $p['amazon_asin'] ) ) {
        update_field( 'amazon_asin', $p['amazon_asin'], $post_id );
    }

    if ( ! empty( $p['roaster_url'] ) ) {
        update_field( 'roaster_url', $p['roaster_url'], $post_id );
    }

    // Build affiliate URL: Amazon affiliate takes priority, else roaster URL
    $asin = $p['amazon_asin'] ?? '';
    $tag  = $p['affiliate_tag'] ?? '';

    if ( $asin && $tag ) {
        update_field( 'amazon_affiliate_url', "https://www.amazon.com/dp/{$asin}?tag={$tag}", $post_id );
    } elseif ( ! empty( $p['roaster_url'] ) ) {
        update_field( 'amazon_affiliate_url', $p['roaster_url'], $post_id );
    }

    WP_CLI::success( "CREATED {$id} → post #{$post_id}" );
    $created++;
}

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------

WP_CLI::log( '' );
WP_CLI::log( "Done — Created: {$created}  |  Skipped: {$skipped}  |  Failed: {$failed}" );

if ( $unmapped_origins ) {
    WP_CLI::log( '' );
    WP_CLI::log( '--- UNMAPPED ORIGINS (fell back to sanitize_title — add entries to $origin_map) ---' );
    foreach ( $unmapped_origins as $origin_str => $product_id ) {
        WP_CLI::warning( "  \"{$origin_str}\"  (product: {$product_id})" );
    }
}

if ( $dropped_structural ) {
    WP_CLI::log( '' );
    WP_CLI::log( '--- DROPPED STRUCTURAL DESCRIPTORS (sensory/body/finish — not flavor notes, not an error) ---' );
    $counts = array_count_values( $dropped_structural );
    arsort( $counts );
    foreach ( $counts as $term => $n ) {
        WP_CLI::log( "  \"{$term}\"  ({$n}x)" );
    }
}

if ( $no_curated_term ) {
    WP_CLI::log( '' );
    WP_CLI::log( '--- FLAVOR STRINGS WITH NO CURATED TERM (real flavors, skipped to avoid orphan — consider adding to seeds) ---' );
    foreach ( array_unique( $no_curated_term ) as $term ) {
        WP_CLI::warning( "  \"{$term}\"" );
    }
}

if ( $unknown_flavor_strs ) {
    WP_CLI::log( '' );
    WP_CLI::log( '--- UNKNOWN FLAVOR STRINGS (not in $flavor_canonical_map — mapping gap, skipped) ---' );
    foreach ( array_unique( $unknown_flavor_strs ) as $term ) {
        WP_CLI::warning( "  \"{$term}\"" );
    }
}

if ( $missing_db_terms ) {
    WP_CLI::log( '' );
    WP_CLI::log( '--- MISSING DB TERMS (curated slug exists in map but not in WP DB — run seed first) ---' );
    foreach ( array_unique( $missing_db_terms ) as $slug ) {
        WP_CLI::warning( "  flavor-note: {$slug}" );
    }
}
