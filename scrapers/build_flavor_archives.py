#!/usr/bin/env python3
"""
Build deploy-ready flavor-note taxonomy archive descriptions + FAQPage schema.

Two tiers:
  - FAMILY pages (parent terms): pillar/hub, ~500-650 words.
  - NOTE pages (child terms): tighter, ~250-400 words.

For every term this emits TWO files into drafts/flavor/ (gitignored):
  - <slug>.html         kses-safe HTML, NO H1, FAQ as the theme's .cbi-faq accordion.
  - <slug>.schema.json  standalone FAQPage JSON-LD object.

The FAQ question/answer strings are the SINGLE SOURCE for both the accordion and the
schema, so acceptedAnswer.text is byte-for-byte identical to the rendered <p> answer.

Bean links use the live permalink base /beans/<slug>/ and ONLY reference published
beans actually tagged at the relevant flavor-note term (verified over SSH). Family
"which beans" sections may aggregate beans tagged at child notes of that family.

Rules enforced:
  - No <h1>. No <script>/<style>. Only h2/h3/p/ul/li/a/strong.
  - No em dash or en dash anywhere (asserted).
  - Answer/question text contains no & < > so HTML and JSON strings match exactly.

Usage:  python scrapers/build_flavor_archives.py
"""
import json
import os
import re

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "drafts", "flavor")

# --- Published bean registry: slug -> display title (verified live) -----------
BEANS = {
    "speckled-ax-ethiopia-suke-quto-honey": "Speckled Ax Ethiopia Suke Quto Honey",
    "san-francisco-bay-fog-chaser": "San Francisco Bay Coffee Fog Chaser",
    "starbucks-veranda-blonde": "Starbucks Veranda Blend Blonde Roast",
    "starbucks-french-roast": "Starbucks French Roast",
    "starbucks-pike-place": "Starbucks Pike Place Roast",
    "stone-street-cold-brew": "Stone Street Cold Brew Reserve Dark Roast",
    "triple-five-coffee-roasters-tanzania-geisha": "Triple Five Coffee Roasters Tanzania Geisha",
    "studio-caffeine-omni-ethiopia-yirgacheffe-winey-natural": "Studio Caffeine OMNI Ethiopia Yirgacheffe Winey Natural",
    "studio-caffeine-kenya-nyeri-othaya-fcs-gura-factory-aa-top": "Studio Caffeine Kenya Nyeri Othaya FCS Gura Factory AA Top",
    "studio-caffeine-ethiopia-sidama-oromia-twakok-g1-washed": "Studio Caffeine Ethiopia Sidama Oromia Twakok G1 Washed",
    "vibrant-coffee-roasters-ethiopia-bensa-mirado": "Vibrant Coffee Roasters Ethiopia Bensa Mirado",
    "volcanica-coffee-brazil-estate-coffee": "Volcanica Coffee Brazil Estate Coffee",
    "volcanica-coffee-colombia-la-divisa-coffee": "Volcanica Coffee Colombia La Divisa Coffee",
    "volcanica-coffee-ethiopian-yirgacheffe-decaf-coffee": "Volcanica Coffee Ethiopian Yirgacheffe Decaf Coffee",
    "verve-sermon": "Verve Coffee The Sermon",
    "triple-five-coffee-roasters-colombia-pink-bourbon": "Triple Five Coffee Roasters Colombia Pink Bourbon",
    "volcanica-coffee-colombian-supremo-coffee": "Volcanica Coffee Colombian Supremo Coffee",
    "volcanica-coffee-ethiopian-yirgacheffe-coffee": "Volcanica Coffee Ethiopian Yirgacheffe Coffee",
    "volcanica-coffee-costa-rica-geisha-coffee": "Volcanica Coffee Costa Rica Geisha Coffee",
    "tattle-tale-french-roast": "Peet's Coffee French Roast",
    "stumptown-coffee-roasters-founder-s-blend": "Stumptown Coffee Roasters Founder's Blend",
    "verve-streetlevel": "Verve Coffee Streetlevel",
    "wes-ngopi-ethiopia-banko-taratu-washed": "Wes Ngopi Ethiopia Banko Taratu Washed",
    "volcanica-coffee-indian-monsoon-malabar-aa-coffee": "Volcanica Coffee Indian Monsoon Malabar AA Coffee",
    "volcanica-coffee-guatemala-huehuetenango-coffee": "Volcanica Coffee Guatemala Huehuetenango Coffee",
    "volcanica-coffee-guatemala-antigua-coffee": "Volcanica Coffee Guatemala Antigua Coffee",
    "wonderstate-house-blend": "Wonderstate Coffee House Blend",
    "tandem-time-and-temperature": "Tandem Coffee Time and Temperature",
    "volcanica-costa-rica-tarrazu": "Volcanica Costa Rica Tarrazu",
    "volcanica-sumatra-mandheling": "Volcanica Sumatra Mandheling",
    "volcanica-ethiopian-yirgacheffe": "Volcanica Ethiopian Yirgacheffe",
    "stumptown-hair-bender": "Stumptown Hair Bender",
    "wes-ngopi-kenya-rungeto-kii-aa": "Wes Ngopi Kenya Rungeto Kii AA",
    "zab-cafe-ethiopia-hambela": "Zab Cafe Ethiopia Hambela",
    "wes-ngopi-ethiopia-danche-natural": "Wes Ngopi Ethiopia Danche Natural",
    "volcanica-coffee-hawaiian-kona-extra-fancy-coffee": "Volcanica Coffee Hawaiian Kona Extra Fancy Coffee",
    "volcanica-coffee-magma-espresso-blend": "Volcanica Coffee Magma Espresso Blend",
    "volcanica-coffee-sumatra-mandheling-coffee": "Volcanica Coffee Sumatra Mandheling Coffee",
    "volcanica-coffee-kona-peaberry-coffee": "Volcanica Coffee Kona Peaberry Coffee",
    "lavazza-super-crema": "Lavazza Super Crema",
}


# --- link + block helpers -----------------------------------------------------
def bean(slug):
    title = BEANS[slug]
    return f'<a href="/beans/{slug}/">{title}</a>'


def flav(slug, label):
    return f'<a href="/flavor/{slug}/">{label}</a>'


def origin(slug, label):
    return f'<a href="/origin/{slug}/">{label}</a>'


def p(text):
    return f"<p>{text}</p>"


def h2(text):
    return f"<h2>{text}</h2>"


def ul(items):
    lis = "".join(f"<li>{it}</li>" for it in items)
    return f"<ul>{lis}</ul>"


def faq_block(faqs):
    """Render the .cbi-faq accordion. Answers must contain no & < >."""
    parts = [h2("Common questions"), '<div class="cbi-faq">']
    for q, a in faqs:
        parts.append(
            '<details class="cbi-faq__item">'
            f'<summary class="cbi-faq__question">{q}</summary>'
            f'<div class="cbi-faq__answer"><p>{a}</p></div>'
            "</details>"
        )
    parts.append("</div>")
    return "".join(parts)


def schema(faqs):
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": q,
                "acceptedAnswer": {"@type": "Answer", "text": a},
            }
            for q, a in faqs
        ],
    }


# =============================================================================
# CONTENT
# Each entry: slug -> dict(blocks=[html...], faqs=[(q,a)...])
# blocks already exclude the FAQ; faq_block() is appended at render time.
# =============================================================================
TERMS = {}


def term(slug, blocks, faqs):
    TERMS[slug] = {"blocks": blocks, "faqs": faqs}


# ---------------------------------------------------------------- CHOCOLATE ---
term(
    "chocolate",
    [
        p("Chocolate notes in coffee are the most common flavor descriptor in the cup, and one of the most honest. They run from dark and bitter to soft and creamy, and they are not marketing. The compounds that read as chocolate (pyrazines, furans, and melanoidins built during roasting) are chemically related to the ones in roasted cacao. The roast is doing the work."),
        h2("Why coffee tastes like chocolate"),
        p("Two things drive chocolate character. The first is roast development. The Maillard reaction and sugar browning between first and second crack build the same brown, bittersweet compounds that give roasted cacao its flavor. Light roasts rarely read as chocolate because they stop before those compounds dominate. The second is origin. Lower-altitude Latin American beans, especially from " + origin("brazil", "Brazil") + " and " + origin("colombia", "Colombia") + ", carry a natural cocoa lean, and " + origin("sumatra", "Sumatra") + " wet-hulled beans push it toward dark, earthy chocolate."),
        h2("The notes in this family"),
        p("This family splits into four notes by roast level and intensity. " + flav("dark-chocolate", "Dark chocolate") + " sits at the bitter, low-acid end of darker roasts. " + flav("milk-chocolate", "Milk chocolate") + " is softer and sweeter, typical of medium roasts. " + flav("bittersweet-chocolate", "Bittersweet chocolate") + " balances roast bitterness against caramel sweetness in medium-dark espresso. " + flav("mild-cocoa", "Mild cocoa") + " is the light, background chocolate impression in creamy blends."),
        h2("Which beans carry chocolate notes"),
        p("Across the catalog, chocolate is the workhorse. Clear examples worth tasting for it:"),
        ul([
            bean("volcanica-coffee-magma-espresso-blend") + " leans into chocolate as the spine of an espresso blend.",
            bean("stumptown-coffee-roasters-founder-s-blend") + " pairs chocolate with caramel in a balanced medium.",
            bean("wonderstate-house-blend") + " carries chocolate alongside brown sugar and a nutty edge.",
            bean("starbucks-pike-place") + " shows the soft cocoa end of a mainstream medium roast.",
        ]),
        p("For the bitter, oily end of the spectrum, the " + flav("earthy-smoky", "Earthy and Smoky family") + " is the natural next stop, since dark chocolate and smoke travel together in heavy roasts."),
        h2("How to get the most chocolate from the cup"),
        p("Chocolate notes reward body. Brew methods that keep oils and weight in the cup, French press, moka pot, espresso, and full-immersion drip, push the cocoa character forward. Paper-filtered pour over strips some of that body and can thin the chocolate to a lighter cocoa impression. For the deepest dark chocolate, brew a dark roast as French press or espresso. For softer milk chocolate and cocoa, a medium roast through drip or moka pot keeps the sweetness in balance. Tasting black is the only honest test, since milk and sugar simply rebuild the chocolate flavor you were trying to judge."),
    ],
    [
        ("What gives coffee a chocolate flavor?", "Roasting. As beans move from first crack toward second crack, the Maillard reaction and sugar browning build melanoidins, pyrazines, and furans. Those are the same families of compounds that make roasted cacao taste like chocolate. Medium and medium-dark roasts develop them most. Lower-altitude Latin American beans from Brazil and Colombia start with a natural cocoa lean that the roast then amplifies."),
        ("Is chocolate coffee actually flavored with chocolate?", "No. A coffee described with chocolate notes has no cocoa added. The flavor is a real chemical resemblance created during roasting, not a flavoring. Flavored mocha coffee is a separate product where chocolate is physically added. If a bag lists only coffee as the ingredient, any chocolate you taste is roast chemistry."),
        ("Which roast level is best for chocolate notes?", "Medium to medium-dark. That window develops the brown, bittersweet compounds without burning them into ash. Push too dark and chocolate slides into char and smoke. Stay too light and you get acidity and fruit instead. For clean cocoa with sweetness, a medium roast from Colombia or Brazil is the reliable pick."),
    ],
)

term(
    "dark-chocolate",
    [
        p("Dark chocolate flavor in coffee signals heavy roast development at low acidity. It is bitter without being sour, deep rather than bright, and in a good cup it finishes clean instead of lingering. Look for it in full-bodied dark roasts and Sumatran beans."),
        p("The note comes from roasting taken into or near second crack, where bittersweet melanoidins dominate and most origin acidity has burned off. It is the defining chocolate note of " + origin("sumatra", "Sumatran") + " wet-hulled coffee and of dark Latin American roasts."),
        h2("Beans with a dark chocolate note"),
        ul([
            bean("volcanica-sumatra-mandheling") + " carries dark chocolate alongside cedar and earth.",
            bean("stone-street-cold-brew") + " builds its cold brew profile on dark chocolate and body.",
            bean("verve-sermon") + " pairs dark chocolate with caramel in an espresso roast.",
            bean("lavazza-super-crema") + " shows a softer dark chocolate under its crema.",
        ]),
        p("Dark chocolate belongs to the " + flav("chocolate", "Chocolate family") + ". For the smoky, earthy company it usually keeps, see " + flav("smoky", "smoky") + "."),
    ],
    [
        ("What causes a dark chocolate taste in coffee?", "A long, hot roast. Taking beans into or near second crack builds bittersweet melanoidins and burns off most of the bright acidity, leaving a deep, low-acid bitterness that reads as dark chocolate. Origin helps too, since Sumatran wet-hulled beans and dark Latin American roasts lean that way naturally."),
        ("Is a dark chocolate note the same as bitterness?", "No. Bitterness is one dimension of it, but a good dark chocolate note has sweetness and depth underneath and finishes clean. Flat, harsh bitterness usually means over-extraction or a scorched roast, not a true dark chocolate character. Grind coarser and cool your water if the cup turns sharp."),
    ],
)

term(
    "milk-chocolate",
    [
        p("Milk chocolate flavor in coffee is softer and sweeter than dark chocolate. Lower bitterness, more sugar, a creamy rather than a sharp edge. It is the chocolate note of well-developed medium roasts where the roast has built cocoa character without driving it toward char."),
        p("It shows up when caramelized sugars sit alongside the cocoa compounds instead of being overrun by them. That balance is a medium-roast signature, often in Latin American beans with naturally low acidity."),
        h2("Beans with a milk chocolate note"),
        ul([
            bean("verve-streetlevel") + " carries milk chocolate with brown sugar and red fruit in an approachable medium.",
        ]),
        p("Only one bean in the current catalog is tagged specifically for milk chocolate. For more of this softer profile, browse the wider " + flav("chocolate", "Chocolate family") + ", where medium-roast cocoa shows up across several blends, or the " + flav("caramel-sweet", "Caramel and Sweet family") + " that usually rides with it."),
    ],
    [
        ("What makes coffee taste like milk chocolate instead of dark chocolate?", "Roast balance. Milk chocolate appears when caramelized sugars stay in play next to the cocoa compounds, which happens at a medium roast. Dark chocolate appears when the roast goes further, the sugars burn down, and bitterness takes over. Same family, different roast development."),
        ("Is milk chocolate coffee sweet?", "Sweeter than most, but not sugary. The sweetness is perceived, built from caramelized bean sugars rather than anything added. It reads as soft and rounded, which is why milk chocolate notes pair so often with caramel and brown sugar in the same cup."),
    ],
)

term(
    "bittersweet-chocolate",
    [
        p("Bittersweet chocolate flavor in coffee is the balance point between roast bitterness and caramel sweetness. It is the chocolate note of a well-built medium-dark espresso, where the roast is deep enough for cocoa bitterness but stops short of the flat char of a true dark roast."),
        p("This note lives in espresso blends for a reason. Espresso concentrates everything, so a roaster aims for the bittersweet middle where chocolate has depth and a sweet backbone at the same time."),
        h2("Beans with a bittersweet chocolate note"),
        ul([
            bean("stumptown-hair-bender") + " carries bittersweet chocolate with caramel and a touch of citrus.",
        ]),
        p("One bean in the catalog is tagged specifically for bittersweet chocolate. For the broader range, see the " + flav("chocolate", "Chocolate family") + ", and for the sweetness that defines this note, the " + flav("caramel-sweet", "Caramel and Sweet family") + "."),
    ],
    [
        ("What is a bittersweet chocolate note in coffee?", "It is chocolate character with roughly equal bitterness and sweetness, the way bittersweet baking chocolate tastes against milk chocolate. In coffee it comes from a medium-dark roast that develops cocoa depth while keeping caramelized sugar in the cup. It is most common in espresso blends."),
        ("Why is bittersweet chocolate common in espresso?", "Espresso concentrates flavor, so roasters target the bittersweet middle on purpose. Too light and the shot turns sour, too dark and it turns to ash. The bittersweet window gives an espresso chocolate depth with enough sweetness to stay balanced under pressure."),
    ],
)

term(
    "mild-cocoa",
    [
        p("Mild cocoa flavor in coffee is the light, background chocolate impression in a balanced cup. No sharp bitterness, no heavy roast weight, just a soft cocoa-powder sweetness sitting under the other notes. It is the gentlest member of the chocolate family."),
        p("It comes from medium roasting that develops just enough browning for cocoa character without pushing into the bitter, dark-chocolate range. Smooth, low-intensity blends and creamy espresso profiles carry it most often."),
        h2("Where mild cocoa shows up"),
        p("No bean in the current catalog is tagged specifically for mild cocoa, so there is no single review to point at yet. In practice it appears as a secondary note across smooth medium roasts. The closest tasting experiences sit in the broader " + flav("chocolate", "Chocolate family") + ", especially the softer " + flav("milk-chocolate", "milk chocolate") + " profiles, and in creamy blends that also carry " + flav("caramel-sweet", "caramel and sweet notes") + "."),
    ],
    [
        ("What is mild cocoa in coffee?", "A light cocoa-powder impression rather than a rich chocolate hit. It is soft, lightly sweet, and sits in the background of a balanced medium roast. It comes from modest roast browning that builds cocoa character without the bitterness of a darker roast."),
        ("How is mild cocoa different from dark chocolate in coffee?", "Intensity and roast level. Mild cocoa is faint and sweet from a medium roast. Dark chocolate is deep and bitter from a darker roast taken near second crack. They are the two ends of the same chocolate family."),
    ],
)

# ---------------------------------------------------------------- CARAMEL -----
term(
    "caramel-sweet",
    [
        p("Caramel notes in coffee come from sugar caramelization during roasting, not from anything added to the bean. As coffee passes through first crack, its natural sugars break down and rebuild into hundreds of new compounds: diacetyl for buttery caramel, furanones for caramel sweetness, pyranones for toffee depth. These are the same reactions that turn white sugar into caramel on a stovetop."),
        h2("Why medium roast is the sweetest"),
        p("Medium roast is peak caramel. Light roast stops before the sugars fully caramelize, so it reads as bright and acidic instead of sweet. Dark roast pushes past caramel into bitter, charred compounds. Medium roast catches caramelization at its sweetest expression, which is why a good medium is described as the sweetest roast level even with no sugar added."),
        h2("The notes in this family"),
        p("The family runs from light to heavy. " + flav("caramel", "Caramel") + " is the bright, clean center. " + flav("brown-sugar", "Brown sugar") + " is warmer, with a molasses undertone. " + flav("toffee", "Toffee") + " is caramel taken a step further, drier with a slight bitter edge. " + flav("molasses", "Molasses") + " is the dark end, heavy and almost savory, appearing at darker roast levels."),
        h2("Which beans carry caramel and sweet notes"),
        ul([
            bean("san-francisco-bay-fog-chaser") + " pairs caramel with chocolate in an easy medium-dark.",
            bean("volcanica-coffee-colombian-supremo-coffee") + " shows clean caramel over a " + origin("colombia", "Colombian") + " base.",
            bean("tandem-time-and-temperature") + " carries brown sugar alongside chocolate and cherry.",
            bean("volcanica-coffee-kona-peaberry-coffee") + " leans on brown sugar from a " + origin("hawaii", "Hawaiian") + " peaberry.",
        ]),
        p("Caramel and chocolate are constant companions, so the " + flav("chocolate", "Chocolate family") + " is the obvious sibling to explore next."),
        h2("How to taste caramel and sweet notes"),
        p("Sweetness in coffee is fragile. Over-extraction buries it under bitterness, so the caramel a roaster promises can vanish in a badly brewed cup. Grind a touch coarser, keep your water near 200°F, and stop the brew before it runs long and bitter. Medium roasts show these notes best, and drip, pour over, or a balanced espresso all carry them well. Taste black to judge the sweetness honestly, since added sugar masks the exact note you are trying to find and leaves you paying for a flavor you never taste."),
    ],
    [
        ("What causes caramel flavor in coffee?", "Sugar caramelization during roasting. As beans hit and pass first crack, their natural sugars break down and reform into buttery, sweet compounds like diacetyl and furanones. It is the same chemistry as melting sugar into caramel on a stove. No sweetener is added to the bean."),
        ("Why does medium roast coffee taste sweeter than dark roast?", "Because caramelization peaks in the medium range. Light roast stops before the sugars fully caramelize, and dark roast burns past caramel into bitter, charred compounds. Medium roast captures the sugars at their sweetest point, which is why it reads as the sweetest roast level despite having no added sugar."),
        ("What is the difference between caramel and toffee notes in coffee?", "Degree. Caramel is the brighter, cleaner sweet note that fades fast. Toffee is caramel taken slightly further, drier and a little more bitter, closer to the edge of dark chocolate. Both come from the same caramelization process at slightly different roast development."),
    ],
)

term(
    "caramel",
    [
        p("Caramel flavor in coffee is the bright, clean center of the sweet family. It is sweet without being heavy, and in a good cup it fades cleanly rather than sticking around. It is the signature note of medium-roast Latin American coffee."),
        p("Caramel comes from sugar caramelization at medium roast, the point where the bean sugars have broken down into sweet compounds but have not yet burned toward bitterness. " + origin("colombia", "Colombian") + " and other Latin American mediums carry it most reliably."),
        h2("Beans with a caramel note"),
        ul([
            bean("volcanica-coffee-colombian-supremo-coffee") + " shows clean caramel over a washed Colombian base.",
            bean("stumptown-coffee-roasters-founder-s-blend") + " pairs caramel with chocolate in a balanced medium.",
            bean("san-francisco-bay-fog-chaser") + " carries caramel alongside chocolate.",
            bean("verve-sermon") + " sets caramel against dark chocolate in an espresso roast.",
        ]),
        p("Caramel is part of the " + flav("caramel-sweet", "Caramel and Sweet family") + ". For its richer cousin, see " + flav("brown-sugar", "brown sugar") + "."),
    ],
    [
        ("What gives coffee a caramel taste?", "Sugar caramelization during a medium roast. The bean sugars break down and rebuild into sweet, buttery compounds. It is real roast chemistry, not added flavoring. Latin American beans at medium roast carry it most clearly."),
        ("Is caramel coffee sweet enough to skip sugar?", "Many people find it is. The sweetness is built into the roast, so a clean caramel-forward medium can taste sweet black. It will not be sugary like a dessert, but the perceived sweetness is enough that adding sugar often buries the note you paid for."),
    ],
)

term(
    "brown-sugar",
    [
        p("Brown sugar flavor in coffee is a warmer, richer sweet note than caramel, with a molasses undertone running through it. It carries more depth and a heavier sweetness, which is why it shows up so often in espresso blends and medium-dark roasts."),
        p("The note comes from caramelization that develops a little further than clean caramel, picking up the darker, molasses-leaning compounds without tipping into bitterness."),
        h2("Beans with a brown sugar note"),
        ul([
            bean("verve-streetlevel") + " pairs brown sugar with milk chocolate and red fruit.",
            bean("triple-five-coffee-roasters-colombia-pink-bourbon") + " carries brown sugar with floral and spice.",
            bean("volcanica-costa-rica-tarrazu") + " shows brown sugar over a clean " + origin("costa-rica", "Costa Rican") + " base.",
            bean("wonderstate-house-blend") + " sets brown sugar against chocolate and nut.",
        ]),
        p("Brown sugar belongs to the " + flav("caramel-sweet", "Caramel and Sweet family") + ". Its lighter sibling is " + flav("caramel", "caramel") + ", and its dark end is " + flav("molasses", "molasses") + "."),
    ],
    [
        ("What is the difference between brown sugar and caramel notes in coffee?", "Depth. Caramel is the brighter, cleaner sweet note that fades fast. Brown sugar is warmer and heavier, with a molasses undertone underneath. Both come from caramelization, but brown sugar develops a step further toward the darker, richer end."),
        ("Why do espresso blends often taste of brown sugar?", "Because espresso concentrates the cup and rewards a deeper, richer sweetness. Roasters develop the sugars far enough to pick up that molasses-leaning brown sugar depth, which holds up under espresso pressure better than a lighter, more delicate caramel."),
    ],
)

term(
    "toffee",
    [
        p("Toffee flavor in coffee sits between caramel and dark chocolate. It is buttery and sweet like caramel, but drier, with a slight bitter edge that points toward the roast. Think of caramel cooked a shade longer, right before it turns."),
        p("The note comes from caramelization taken a step past clean caramel, where the sugars develop a drier, deeper character without crossing into char. It reads best in medium and medium-dark roasts."),
        h2("Where toffee shows up"),
        p("No bean in the current catalog is tagged specifically for toffee, so there is no single review to link yet. In practice it sits next to caramel in many medium roasts. The nearest tasting experiences are in the " + flav("caramel-sweet", "Caramel and Sweet family") + ", especially beans carrying " + flav("caramel", "caramel") + " and " + flav("brown-sugar", "brown sugar") + ", which bracket toffee on either side."),
    ],
    [
        ("What does a toffee note taste like in coffee?", "Buttery and sweet like caramel, but drier and with a faint bitter edge. It is caramel cooked one step further, sitting right on the line toward dark chocolate. It usually appears in medium and medium-dark roasts."),
        ("Is toffee the same as caramel in coffee?", "They are close, both from sugar caramelization, but toffee is the drier, slightly more bitter version. Caramel is brighter and cleaner. If a sweet note has a buttery depth with a hint of bitterness on the back, that is toffee rather than caramel."),
    ],
)

term(
    "molasses",
    [
        p("Molasses flavor in coffee is the dark end of the sweet family. Heavy, thick, almost savory, it appears when caramelization runs into the darker roast range and the sugars take on a deep, syrupy character. It is sweetness with weight behind it."),
        p("The note develops at darker roast levels where the bean sugars push past caramel and brown sugar into their heaviest expression. It often rides with dark chocolate and a touch of smoke."),
        h2("Beans with a molasses note"),
        ul([
            bean("triple-five-coffee-roasters-tanzania-geisha") + " carries molasses with stone fruit and florals.",
            bean("volcanica-coffee-guatemala-huehuetenango-coffee") + " shows molasses alongside nut and spice.",
        ]),
        p("Molasses anchors the dark corner of the " + flav("caramel-sweet", "Caramel and Sweet family") + ". For the chocolate and smoke it travels with, see the " + flav("earthy-smoky", "Earthy and Smoky family") + "."),
    ],
    [
        ("What causes a molasses note in coffee?", "Caramelization pushed into the darker roast range. The bean sugars develop past caramel and brown sugar into a heavy, syrupy, almost savory sweetness. It is the deepest sweet note before the roast turns fully bitter."),
        ("Is molasses in coffee bitter or sweet?", "Both, leaning sweet with weight. It carries real sweetness, but it is dark and heavy rather than bright, and it often sits next to dark chocolate and a little smoke. That combination is why molasses reads as rich rather than simply sugary."),
    ],
)

# ---------------------------------------------------------------- NUTTY -------
term(
    "nutty",
    [
        p("Nutty coffee beans get their hazelnut, walnut, and almond character from pyrazines produced during Maillard browning. The same reaction that browns a roasting nut browns a roasting coffee bean, and it builds the same toasted, nutty compounds. No nuts are involved and none are added."),
        h2("Why coffee tastes nutty"),
        p("Nut notes are a medium-roast signature. At medium roast, browning produces light, clean nut character alongside caramel. Take the roast a little further and the nut notes shift toward walnut and pick up a slight bitterness. Lower-altitude " + origin("brazil", "Brazilian") + " and Latin American beans carry nut character most clearly because their naturally low acidity lets the toasted notes read without bright fruit competing."),
        h2("The notes in this family"),
        p("The family runs lightest to heaviest. " + flav("hazelnut", "Hazelnut") + " is the sweetest and softest nut note, tied to creamy, low-acid coffee. " + flav("walnut", "Walnut") + " is more bitter and astringent, appearing at medium-dark development."),
        h2("Which beans carry nutty notes"),
        ul([
            bean("volcanica-coffee-brazil-estate-coffee") + " shows clean nut character from a Brazilian base.",
            bean("wonderstate-house-blend") + " carries a nutty edge with chocolate and brown sugar.",
            bean("volcanica-coffee-guatemala-huehuetenango-coffee") + " pairs nut with molasses and spice.",
            bean("starbucks-veranda-blonde") + " shows a toasted, nutty lightness in a blonde roast.",
        ]),
        p("Nut and caramel develop together, so the " + flav("caramel-sweet", "Caramel and Sweet family") + " is the natural sibling. Both lean on the same medium-roast chemistry."),
        h2("How to taste nutty notes"),
        p("Nut character is subtle and sits in the mid-palate, so it is easy to lose. Keep the roast medium, brew clean, and avoid scalding water that drags out bitterness and covers the toasted notes. Drip and pour over both show nut character clearly. Tasting black helps, since milk and sugar smother the light, dry nuttiness that defines this family."),
        p("Nutty coffees make reliable everyday drinkers. They are low in acidity, forgiving to brew, and pleasant across a wide range of methods, which is why so many breakfast and house blends lean nutty rather than bright or fruity."),
    ],
    [
        ("What makes coffee taste nutty?", "Maillard browning during roasting. It produces pyrazines, the same toasted compounds that make roasted nuts taste like nuts. Medium roast develops them best. Lower-altitude Brazilian and Latin American beans show nut character most clearly because their low acidity does not bury it."),
        ("Does nutty coffee contain nuts?", "No. The flavor is roast chemistry, not an ingredient. A coffee described as nutty has no nuts in it and is generally safe from a nut-allergy standpoint, though anyone with a serious allergy should still check that a roaster does not also process flavored products on shared equipment."),
        ("What roast level brings out nutty flavors?", "Medium roast. It develops clean, sweet nut notes alongside caramel. Go a bit darker and the character shifts toward walnut with more bitterness. Go lighter and acidity and fruit take over before the nut compounds fully form."),
    ],
)

term(
    "hazelnut",
    [
        p("Hazelnut flavor in coffee is the sweetest and softest nut note, the most approachable member of the nutty family. It reads as smooth and lightly sweet, and it pairs naturally with creamy body and low acidity. This is real roast character, not the synthetic hazelnut of flavored coffee."),
        p("It develops at medium roast in low-acid beans, where Maillard browning builds a gentle, sweet nut note rather than the more bitter walnut character of a darker roast."),
        h2("Beans with a hazelnut note"),
        ul([
            bean("lavazza-super-crema") + " carries hazelnut as its most prominent descriptor, under a creamy espresso crema.",
        ]),
        p("One bean in the catalog is tagged specifically for hazelnut. For the wider range of toasted notes, see the " + flav("nutty", "Nutty family") + ", and note how hazelnut rides with the " + flav("caramel-sweet", "caramel and sweet notes") + " in the same cup."),
    ],
    [
        ("Is hazelnut coffee flavored or natural?", "Both exist. Synthetic hazelnut flavoring is sprayed onto some coffees and tastes sweet and obvious. A natural hazelnut note, like the one in a low-acid espresso bean, comes from roast browning and is subtler. If the bag lists only coffee, the hazelnut you taste is roast chemistry."),
        ("What kind of coffee has a natural hazelnut flavor?", "Smooth, low-acid medium roasts, often espresso blends with creamy body. The combination of gentle roast browning and low acidity lets the soft, sweet hazelnut note read clearly instead of being overrun by brightness or bitterness."),
    ],
)

term(
    "walnut",
    [
        p("Walnut flavor in coffee is the more bitter, more astringent member of the nutty family. Where hazelnut is soft and sweet, walnut has a dry, slightly tannic edge that sets it apart. It appears at medium-dark roast development."),
        p("The note comes from roast browning pushed a step past the sweet hazelnut range, where the toasted compounds gain a drier, more bitter character. It often sits in espresso blends with dark chocolate."),
        h2("Where walnut shows up"),
        p("No bean in the current catalog is tagged specifically for walnut, so there is no single review to point at yet. In practice it appears as a secondary note in darker medium roasts and espresso blends. The closest tasting experiences are in the " + flav("nutty", "Nutty family") + ", especially its sweeter sibling " + flav("hazelnut", "hazelnut") + ", and in the " + flav("chocolate", "Chocolate family") + " where walnut and dark chocolate often share a cup."),
    ],
    [
        ("What does a walnut note taste like in coffee?", "Dry and slightly bitter, with a faint astringent edge. It is the more serious end of the nutty family, the opposite of soft, sweet hazelnut. It shows up at medium-dark roast levels, often next to dark chocolate."),
        ("Why is walnut more bitter than hazelnut in coffee?", "Roast development. Walnut appears when browning is pushed a step past the sweet hazelnut range, so the toasted compounds gain a drier, more tannic character. Same family, deeper roast, more bitterness."),
    ],
)

# ---------------------------------------------------------------- FRUIT -------
term(
    "fruit",
    [
        p("Fruit notes in coffee are not flavoring or additives. They are organic compounds, esters, aldehydes, and acids, produced during cherry development, fermentation, and roasting. A strawberry note in a washed Ethiopian is a genuine chemical resemblance to the compounds in strawberry. It is chemistry, not marketing."),
        h2("Where fruit notes come from"),
        p("Two sources drive fruit character. The first is origin. High-altitude " + origin("ethiopia", "Ethiopian") + " and " + origin("kenya", "Kenyan") + " beans develop intense fruit esters during slow cherry ripening, and washed processing preserves them as clean, precise fruit. The second is natural processing, where the fruit flesh ferments into the bean during drying and adds cherry, berry, and tropical sweetness. Light roasting keeps these volatile notes intact; dark roasting burns them off."),
        h2("The notes in this family"),
        p("The family spans bright to deep. " + flav("stone-fruit", "Stone fruit") + " covers peach, apricot, and plum from washed high-altitude beans. " + flav("strawberry", "Strawberry") + " is the candy-bright berry note of light Ethiopian roasts. " + flav("dark-cherry", "Dark cherry") + " comes from natural processing and reads sweet and deep. " + flav("dried-fruit", "Dried fruit") + " is the concentrated raisin note of darker espresso blends."),
        h2("Which beans carry fruit notes"),
        ul([
            bean("studio-caffeine-ethiopia-sidama-oromia-twakok-g1-washed") + " shows clean washed fruit and stone fruit.",
            bean("wes-ngopi-kenya-rungeto-kii-aa") + " carries bright Kenyan fruit and red fruit.",
            bean("volcanica-coffee-costa-rica-geisha-coffee") + " leans on delicate fruit from a geisha lot.",
            bean("studio-caffeine-omni-ethiopia-yirgacheffe-winey-natural") + " shows natural-process cherry and strawberry.",
        ]),
        p("Fruit and florals travel together in high-grown coffee, so the " + flav("citrus-floral", "Citrus and Floral family") + " is the natural next stop."),
        h2("How to taste fruit notes"),
        p("Fruit is volatile, so freshness and brew method decide whether you taste it at all. Buy light-roasted and recent, and brew as pour over or another filter method that keeps the cup clean and bright. Let the coffee cool slightly before judging it, since the fruit esters read more clearly below scalding temperature. Dark roasts and heavy immersion brewing bury fruit under body, so they are the wrong tools for this family."),
    ],
    [
        ("Why does some coffee taste like fruit?", "Two reasons. High-altitude origins like Ethiopia and Kenya build real fruit esters in the bean during slow ripening, and natural processing ferments fruit sugars into the bean during drying. Both create genuine fruit compounds. Light roasting preserves them; dark roasting destroys them."),
        ("Is fruity coffee flavored?", "No. A fruity single-origin has nothing added. The berry or stone-fruit notes are chemical compounds from the cherry and the process. Flavored fruit coffee is a separate product where flavoring is sprayed on. If the bag lists only coffee, the fruit is real origin character."),
        ("What roast level is best for fruit notes?", "Light to light-medium. Fruit compounds are volatile and burn off with heat, so a light roast preserves them while a dark roast replaces them with chocolate and smoke. If you want the fruit a roaster advertises, buy it light and brew it as filter or pour over."),
    ],
)

term(
    "dark-cherry",
    [
        p("Dark cherry flavor in coffee comes from natural processing, where fruit sugars are absorbed into the bean during drying and then concentrated by the roast. It reads sweet and deep, a darker fruit than bright berry, and it can survive into medium and darker roasts where most fruit notes would burn away."),
        p("The note is a signature of natural-process coffee. Leaving the cherry on the bean during drying ferments dark, sweet fruit character directly into it."),
        h2("Beans with a dark cherry note"),
        ul([
            bean("studio-caffeine-omni-ethiopia-yirgacheffe-winey-natural") + " carries dark cherry from a winey natural process, with strawberry and red fruit.",
        ]),
        p("One bean in the catalog is tagged specifically for dark cherry. For the broader range, see the " + flav("fruit", "Fruit family") + ", especially the natural-process " + flav("strawberry", "strawberry") + " and " + flav("dried-fruit", "dried fruit") + " notes that share its origin."),
    ],
    [
        ("What causes a dark cherry flavor in coffee?", "Natural processing. When the coffee cherry is left on the bean to dry, its sugars ferment into the bean and create deep, sweet, dark-fruit compounds. The roast then concentrates them. It is why natural-process coffees so often read with cherry and berry depth."),
        ("Can dark cherry survive a medium or dark roast?", "Yes, better than most fruit notes. Because natural processing drives the fruit deep into the bean, dark cherry holds up further into the roast than delicate berry or stone fruit, which burn off quickly. That is why it can appear even in bolder cups."),
    ],
)

term(
    "dried-fruit",
    [
        p("Dried fruit flavor in coffee means raisin, prune, and dark berry, the concentrated sweet-fruit note of medium-dark espresso blends. As sugars caramelize and the fruit character deepens, the result reads like dried fruit rather than fresh, with more weight and less brightness."),
        p("The note appears where fruit-leaning origins meet a darker roast. The fresh fruit concentrates and sweetens into its dried form, often alongside bittersweet chocolate."),
        h2("Beans with a dried fruit note"),
        ul([
            bean("volcanica-coffee-brazil-estate-coffee") + " carries dried fruit with chocolate and nut.",
            bean("volcanica-coffee-sumatra-mandheling-coffee") + " shows dried fruit against brown sugar.",
        ]),
        p("Dried fruit belongs to the " + flav("fruit", "Fruit family") + ". For the chocolate it usually pairs with in espresso, see the " + flav("chocolate", "Chocolate family") + "."),
    ],
    [
        ("What is a dried fruit note in coffee?", "Raisin, prune, or dark berry character, deeper and sweeter than fresh fruit. It shows up in medium-dark roasts where fruit-leaning beans are taken far enough for the fruit to concentrate and the sugars to caramelize. It often rides with bittersweet chocolate."),
        ("Why does dried fruit appear in darker roasts when most fruit notes disappear?", "Because the darker roast concentrates rather than preserves. Bright, delicate fruit burns off, but the residual fruit character deepens into its dried, raisin-like form as sugars caramelize. So the fruit you taste in a dark espresso reads dried, not fresh."),
    ],
)

term(
    "stone-fruit",
    [
        p("Stone fruit flavor in coffee covers peach, apricot, and plum, the juicy, sweet-tart fruit of high-altitude washed beans. It reads clean and bright with real structure, the kind of fruit note that comes from origin rather than process."),
        p("The note develops in high-grown " + origin("ethiopia", "Ethiopian") + " and " + origin("kenya", "Kenyan") + " coffee, where slow cherry ripening builds fruit esters and washed processing preserves them cleanly. Light roasting keeps them intact."),
        h2("Beans with a stone fruit note"),
        ul([
            bean("triple-five-coffee-roasters-tanzania-geisha") + " carries stone fruit with molasses and florals.",
            bean("studio-caffeine-ethiopia-sidama-oromia-twakok-g1-washed") + " shows clean washed stone fruit.",
            bean("vibrant-coffee-roasters-ethiopia-bensa-mirado") + " pairs stone fruit with jasmine and red fruit.",
            bean("wes-ngopi-ethiopia-banko-taratu-washed") + " sets stone fruit against caramel and florals.",
        ]),
        p("Stone fruit belongs to the " + flav("fruit", "Fruit family") + ", and in high-grown coffee it almost always shares the cup with " + flav("citrus-floral", "citrus and floral notes") + "."),
    ],
    [
        ("What causes stone fruit notes in coffee?", "High-altitude growing and washed processing. Slow cherry ripening at elevation builds peach, apricot, and plum esters in the bean, and washed processing preserves them cleanly. A light roast keeps them intact. Ethiopian and Kenyan washed coffees are the classic source."),
        ("How do I brew coffee to taste stone fruit?", "Use a filter method like pour over and keep the coffee fresh and lightly roasted. Paper filtration keeps the cup clean so the bright fruit reads. Avoid dark roasts and heavy immersion brewing, which bury or burn off the delicate stone-fruit character."),
    ],
)

term(
    "strawberry",
    [
        p("Strawberry flavor in coffee is the candy-bright berry note of high-altitude Ethiopian light roasts. It is almost sweet enough to read as flavored, but it is pure origin and process character, a real ester resemblance to the fruit. This is one of the most striking notes a single-origin can produce."),
        p("It appears in light-roasted, high-grown beans, especially natural and winey processed " + origin("ethiopia", "Ethiopian") + " lots where fermentation amplifies the berry character. The light roast is essential, since the note burns off with heat."),
        h2("Beans with a strawberry note"),
        ul([
            bean("studio-caffeine-omni-ethiopia-yirgacheffe-winey-natural") + " carries strawberry from a winey natural process, with dark cherry.",
            bean("wes-ngopi-ethiopia-danche-natural") + " shows natural-process strawberry with jasmine and florals.",
        ]),
        p("Strawberry belongs to the " + flav("fruit", "Fruit family") + ". For the florals that often run alongside it in Ethiopian coffee, see the " + flav("citrus-floral", "Citrus and Floral family") + "."),
    ],
    [
        ("Why does some Ethiopian coffee taste like strawberry?", "High-altitude growing builds intense fruit esters, and natural or winey processing amplifies the berry character during drying. A light roast preserves it. The result is a real chemical resemblance to strawberry, not added flavoring. It is one of the signature notes of Ethiopian coffee."),
        ("Is strawberry coffee a flavored coffee?", "Not when it is a single-origin Ethiopian. The strawberry note there is genuine origin and process character with nothing added. There are separately flavored strawberry coffees on the market, but a natural-process light-roast Ethiopian gets the note from chemistry alone."),
    ],
)

# ---------------------------------------------------------------- CITRUS ------
term(
    "citrus-floral",
    [
        p("Floral coffee beans, and the citrus brightness that runs with them, are the calling card of high-altitude washed coffee, above all from " + origin("ethiopia", "Ethiopia") + ". Bergamot, orange blossom, jasmine, and clean citrus are not added flavors. They are terpenes and acids, linalool, geraniol, and citric acid among them, that develop in cherries grown above 1,500 meters and are preserved by washed processing."),
        h2("Why coffee tastes floral and citrusy"),
        p("The chemistry is direct. Jasmine's main aromatic compound, linalool, appears in measurable amounts in high-grown washed Ethiopian coffee. Bergamot's citrus-floral character comes from the same terpene family. Light roasting preserves these volatile aromatics, while darker roasting burns them off. That is why floral coffee is almost always a light or light-medium roast."),
        h2("The notes in this family"),
        p("The family runs from citrus to perfume. " + flav("bergamot", "Bergamot") + " is the bright, Earl Grey citrus-floral note. " + flav("orange-blossom", "Orange blossom") + " is lighter and sweeter, delicate and perfumed. " + flav("jasmine", "Jasmine") + " is the most intense floral, distinctly non-coffee in a way that surprises first-time drinkers."),
        h2("Which beans carry citrus and floral notes"),
        ul([
            bean("volcanica-coffee-guatemala-antigua-coffee") + " carries jasmine and red fruit over an " + origin("guatemala", "Antigua") + " base.",
            bean("vibrant-coffee-roasters-ethiopia-bensa-mirado") + " shows jasmine with stone fruit and red fruit.",
            bean("volcanica-ethiopian-yirgacheffe") + " leans into clean citrus-floral character.",
            bean("studio-caffeine-kenya-nyeri-othaya-fcs-gura-factory-aa-top") + " pairs citrus-floral brightness with red fruit.",
        ]),
        p("Florals and fruit develop together at altitude, so the " + flav("fruit", "Fruit family") + " is the natural sibling family to explore next."),
        h2("Citrus versus floral in the cup"),
        p("The two halves of this family separate on the palate. Citrus is an acidity you taste, bright, clean, and structural, the backbone that makes a high-grown coffee feel alive. Floral is an aromatic you smell, perfumed and delicate, registering in the nose before the sip. A great Ethiopian washed lot delivers both at once, citrus structure underneath and floral aromatics on top. Brew it light and clean, and smell the cup before you drink to catch the florals before they fade."),
    ],
    [
        ("What makes coffee taste floral?", "High-altitude growing and washed processing. Cherries grown above 1,500 meters build aromatic terpenes like linalool, the same compound behind jasmine, and washed processing preserves them. A light roast keeps them intact. Ethiopian washed coffee is the classic source of floral character."),
        ("Why are floral coffees almost always light roast?", "Because the aromatic compounds are volatile and burn off with heat. A light roast preserves the jasmine, bergamot, and orange blossom notes, while a medium or dark roast replaces them with chocolate and smoke. To taste florals, the roast has to stay light."),
        ("How do I taste floral and citrus notes in coffee?", "Smell first. These notes are aromatics, strongest on the nose, so cup the coffee or brew it as pour over and smell before you sip. The jasmine and bergamot in Ethiopian coffee register in the aroma before the liquid even reaches your palate."),
    ],
)

term(
    "bergamot",
    [
        p("Bergamot flavor in coffee is the bright, floral citrus note that defines high-altitude Ethiopian washed coffee. It reads as a more floral, more perfumed citrus than orange or lemon, closest to the bergamot in Earl Grey tea. It is one of the clearest signs of a clean, high-grown washed lot."),
        p("The note comes from aromatic terpenes built during slow cherry ripening at elevation and preserved by washed processing and a light roast. Push the roast darker and it disappears."),
        h2("Where bergamot shows up"),
        p("No bean in the current catalog is tagged specifically for bergamot, so there is no single review to point at yet. In practice it appears in light, high-grown washed coffees alongside other florals. The closest tasting experiences are in the " + flav("citrus-floral", "Citrus and Floral family") + ", especially beans carrying " + flav("jasmine", "jasmine") + ", and across high-grown " + origin("ethiopia", "Ethiopian") + " lots."),
    ],
    [
        ("What does bergamot taste like in coffee?", "Bright, floral citrus, more perfumed than orange or lemon, very close to the bergamot note in Earl Grey tea. It is a clean, high-toned aromatic that shows up in light-roasted, high-altitude washed coffee, especially from Ethiopia."),
        ("Why does bergamot only show up in light roasts?", "Because it is a volatile aromatic compound that heat destroys. A light roast preserves it, while a medium or dark roast burns it off and replaces it with chocolate and roast character. Bergamot is a marker of a lightly roasted, high-grown washed coffee."),
    ],
)

term(
    "orange-blossom",
    [
        p("Orange blossom flavor in coffee is a lighter, sweeter floral note than jasmine, delicate and perfumed rather than intense. It sits between citrus and floral, the soft, sweet aromatic of a clean high-grown washed coffee."),
        p("Like the rest of this family, it comes from aromatic compounds built at altitude and preserved by washed processing and a light roast. It is subtle, easily lost to a heavier roast or a muddy brew."),
        h2("Where orange blossom shows up"),
        p("No bean in the current catalog is tagged specifically for orange blossom, so there is no single review to link yet. In practice it appears as a delicate secondary note in light, high-grown washed coffees. The nearest tasting experiences are in the " + flav("citrus-floral", "Citrus and Floral family") + ", especially beans carrying " + flav("jasmine", "jasmine") + " and " + flav("bergamot", "bergamot") + ", which sit on either side of it."),
    ],
    [
        ("What does orange blossom taste like in coffee?", "A soft, sweet, perfumed floral note, lighter than jasmine and gentler than bright citrus. It is delicate and sits between citrus and floral, the kind of aromatic you find in a clean, lightly roasted, high-grown washed coffee."),
        ("How do I keep delicate notes like orange blossom in the cup?", "Buy light-roasted and fresh, and brew clean. Use pour over or another filter method, keep your water just off the boil, and smell before you sip. Delicate florals are easily lost to a dark roast, stale beans, or a heavy immersion brew."),
    ],
)

term(
    "jasmine",
    [
        p("Jasmine flavor in coffee is the most intense floral note, perfumed and distinctly non-coffee in a way that surprises first-time drinkers. It is the clearest expression of the citrus-floral family, and a reliable sign of a clean, high-grown washed or natural light roast."),
        p("Its main aromatic compound, linalool, develops in high-altitude cherries and is preserved by careful processing and a light roast. It is strongest on the nose, registering in the aroma before the first sip."),
        h2("Beans with a jasmine note"),
        ul([
            bean("vibrant-coffee-roasters-ethiopia-bensa-mirado") + " carries jasmine with stone fruit and red fruit.",
            bean("volcanica-coffee-guatemala-antigua-coffee") + " shows jasmine over an Antigua base.",
            bean("wes-ngopi-ethiopia-danche-natural") + " pairs jasmine with strawberry and florals.",
            bean("wes-ngopi-ethiopia-banko-taratu-washed") + " sets jasmine against caramel and stone fruit.",
        ]),
        p("Jasmine belongs to the " + flav("citrus-floral", "Citrus and Floral family") + ", and in high-grown coffee it almost always shares the cup with " + flav("fruit", "fruit notes") + "."),
    ],
    [
        ("What gives coffee a jasmine flavor?", "Linalool, an aromatic terpene that is also the main compound in jasmine flowers. It develops in high-altitude coffee cherries and is preserved by careful processing and a light roast. High-grown Ethiopian coffee is the most common source of a clear jasmine note."),
        ("Why does jasmine coffee smell stronger than it tastes?", "Because jasmine is an aromatic, strongest on the nose. Much of what you perceive as flavor is actually aroma, so the note registers in the smell of the cup before the liquid reaches your palate. Smell before you sip to catch it fully."),
    ],
)

# ---------------------------------------------------------------- EARTHY ------
term(
    "earthy-smoky",
    [
        p("Earthy and smoky coffee sits at the dark, heavy end of the flavor spectrum, the opposite of bright Ethiopian florals. Both profiles are legitimate, with dedicated audiences, but they come from completely different sources. Earthy comes from process. Smoky comes from roast."),
        h2("Where these notes come from"),
        p("Earthy character comes mainly from the wet-hull process used in " + origin("indonesia", "Indonesian") + " and " + origin("sumatra", "Sumatran") + " coffee, and from the monsoon process used for Indian Malabar. Partial fermentation during drying produces the terpenoid compounds that make these cups taste of forest floor and cedar. Smoky character comes from dark roasting pushed past caramelization into controlled carbonization. It is a warm combustion note, not quite char."),
        h2("The notes in this family"),
        p("The family runs from soil to fire. " + flav("earthy", "Earthy") + " is the wet-soil, forest-floor base. " + flav("cedar", "Cedar") + " is the dry wood note specific to wet-hull processing. " + flav("smoky", "Smoky") + " is the dark-roast combustion note. " + flav("tobacco", "Tobacco") + " is the dry, leafy intensity of very dark espresso roasts."),
        h2("Which beans carry earthy and smoky notes"),
        ul([
            bean("volcanica-coffee-indian-monsoon-malabar-aa-coffee") + " carries earthy, smoky, and tobacco character in one cup.",
            bean("volcanica-sumatra-mandheling") + " shows wet-hull earth with cedar and dark chocolate.",
            bean("starbucks-french-roast") + " is a clean example of dark-roast smoke.",
            bean("tattle-tale-french-roast") + " pushes smoky character to the front.",
        ]),
        h2("Who these notes are for"),
        p("Drinkers who find brightness and acidity unpleasant, dark roast enthusiasts, and French press drinkers who want maximum weight. Not for pour-over drinkers chasing clarity. These notes keep their context in heavy brewing, so use French press, drip, or cold brew rather than paper filtration. For the dark chocolate and molasses that ride with them, see the " + flav("chocolate", "Chocolate family") + "."),
        h2("Earthy versus smoky at a glance"),
        p("Earthy is process, smoky is roast. An earthy cup can be almost any roast level and still taste of soil and wood, because the character is built in during wet-hull or monsoon drying. A smoky cup is dark by definition, since the smoke comes from the roast itself. A coffee like a dark Sumatran can carry both at once: earth from the process, smoke from the roast. Knowing which is which tells you whether to chase a different origin or simply a different roast level."),
    ],
    [
        ("What causes earthy and smoky flavors in coffee?", "Two different things. Earthy comes from wet-hull and monsoon processing, where partial fermentation during drying builds forest-floor and cedar compounds. Smoky comes from dark roasting taken past caramelization into controlled carbonization. One is process, the other is roast."),
        ("Are earthy and smoky coffees lower in acidity?", "Yes. Both profiles come from processes and roast levels that strip out bright acidity, so the cups read low-acid, heavy, and full-bodied. That is why acid-sensitive drinkers and French press fans often gravitate toward Sumatran and dark-roast coffees."),
        ("How should I brew earthy and smoky coffee?", "Use a method that keeps body and weight, like French press, drip, or cold brew. Paper filtration strips the heavy texture that gives these notes their context, leaving them thin and hollow. Immersion brewing preserves the substance these profiles are built on."),
    ],
)

term(
    "earthy",
    [
        p("Earthy flavor in coffee is the forest-floor, wet-soil character produced by wet-hull and monsoon processing. It is the defining note of " + origin("sumatra", "Sumatran") + " coffee and Indian Malabar, a low-acid, heavy profile built on substance rather than brightness."),
        p("The note comes from partial fermentation during drying, which produces terpenoid compounds that read as damp soil and forest floor. It is process character, not roast, though it usually appears in darker cups."),
        h2("Beans with an earthy note"),
        ul([
            bean("volcanica-coffee-indian-monsoon-malabar-aa-coffee") + " carries earthy character with smoke and tobacco.",
            bean("volcanica-sumatra-mandheling") + " shows wet-hull earth with cedar and dark chocolate.",
        ]),
        p("Earthy anchors the " + flav("earthy-smoky", "Earthy and Smoky family") + ". Its dry-wood relative is " + flav("cedar", "cedar") + ", which comes from the same wet-hull process."),
    ],
    [
        ("What makes coffee taste earthy?", "Wet-hull processing, used in Sumatra, and monsoon processing, used for Indian Malabar. Partial fermentation during drying produces terpenoid compounds that read as wet soil and forest floor. It is a process note, not a roast note, and it gives a low-acid, heavy cup."),
        ("Is an earthy taste in coffee a defect?", "Not in this context. Intentional earthiness from wet-hull Sumatran coffee is a sought-after profile with a clear audience. It only becomes a defect when it reads as moldy or musty from poor storage. Clean earthiness is dry and savory, not sour or off."),
    ],
)

term(
    "cedar",
    [
        p("Cedar flavor in coffee is the dry wood note that separates true Sumatran character from generic earthiness. It reads clean and dry rather than musty, a sharp aromatic edge on top of the heavier earthy base. It is one of the clearest markers of wet-hull processing."),
        p("The note comes from the same partial fermentation that builds earthiness, but it expresses as dry cedar wood rather than damp soil. It sits naturally with dark chocolate in " + origin("sumatra", "Sumatran") + " coffee."),
        h2("Beans with a cedar note"),
        ul([
            bean("volcanica-sumatra-mandheling") + " carries cedar clearly alongside earthy and dark chocolate notes.",
        ]),
        p("One bean in the catalog is tagged specifically for cedar. For the wider profile, see the " + flav("earthy-smoky", "Earthy and Smoky family") + ", especially its base note " + flav("earthy", "earthy") + ", which shares the same wet-hull origin."),
    ],
    [
        ("What does a cedar note taste like in coffee?", "Dry aromatic wood, clean rather than musty. It sits on top of the heavier earthy base in Sumatran coffee and gives it a sharper, drier edge. It is a marker of wet-hull processing and usually appears next to dark chocolate."),
        ("How is cedar different from earthy in coffee?", "Cedar is the dry-wood version, earthy is the wet-soil version. They come from the same wet-hull process but express differently: cedar reads clean and dry, earthy reads damp and savory. A good Sumatran often shows both at once."),
    ],
)

term(
    "smoky",
    [
        p("Smoky flavor in coffee comes from dark roast development, controlled carbonization that produces a warm, campfire character without actual char. It is the fire end of the earthy and smoky family, a roast note rather than an origin note."),
        p("The note appears when roasting pushes past caramelization into the early stages of carbonization. Done well it is warm and controlled; pushed too far it turns to flat, ashy char."),
        h2("Beans with a smoky note"),
        ul([
            bean("starbucks-french-roast") + " is a clean, mainstream example of dark-roast smoke.",
            bean("tattle-tale-french-roast") + " pushes smoky character to the front of the cup.",
            bean("volcanica-coffee-indian-monsoon-malabar-aa-coffee") + " carries smoke alongside earth and tobacco.",
        ]),
        p("Smoky belongs to the " + flav("earthy-smoky", "Earthy and Smoky family") + ". For the dark chocolate and molasses that round out a smoky cup, see the " + flav("chocolate", "Chocolate family") + "."),
    ],
    [
        ("What causes a smoky flavor in coffee?", "Dark roasting. When the roast pushes past caramelization into controlled carbonization, it builds a warm, campfire-like smoke note. It is a roast characteristic, not an origin one, which is why French roast and other very dark coffees taste smoky regardless of where the beans came from."),
        ("Is smoky coffee burnt?", "Not necessarily. Controlled smoke is a warm, intentional note from a well-managed dark roast. Burnt is the failure mode: flat, ashy, and bitter from a roast taken too far. The difference is whether the cup has warmth and depth or just harshness."),
    ],
)

term(
    "tobacco",
    [
        p("Tobacco flavor in coffee is the dry, leafy intensity of very dark espresso roasts. It reads as intensity rather than simple bitterness, present without harshness in the best examples. It is the most concentrated note in the earthy and smoky family."),
        p("The note develops at the darkest end of roasting, where the cup gains a dry, slightly astringent, leafy character that sits alongside dark chocolate and smoke. It is a hallmark of bold espresso and monsoon-processed coffee."),
        h2("Beans with a tobacco note"),
        ul([
            bean("volcanica-coffee-indian-monsoon-malabar-aa-coffee") + " carries tobacco alongside earthy and smoky character.",
        ]),
        p("One bean in the catalog is tagged specifically for tobacco. For the broader heavy profile, see the " + flav("earthy-smoky", "Earthy and Smoky family") + ", especially " + flav("smoky", "smoky") + ", which sits right next to it."),
    ],
    [
        ("What does a tobacco note taste like in coffee?", "Dry, leafy, and intense, more about concentration than sharp bitterness. In a good cup it reads as depth and weight rather than harshness. It shows up at the darkest roast levels and in monsoon-processed coffee, usually next to dark chocolate and smoke."),
        ("Is a tobacco note in coffee a bad thing?", "No, in the right context it is a sought-after marker of a bold, very dark roast. It signals intensity and weight rather than a defect. It only reads as unpleasant if the roast tips into flat, ashy char, which is a roasting failure rather than the tobacco note itself."),
    ],
)


# =============================================================================
# RENDER
# =============================================================================
DASH_RE = re.compile(r"[–—]")


def render_html(entry):
    html = "".join(entry["blocks"]) + faq_block(entry["faqs"])
    return html


def main():
    out = os.path.abspath(OUT_DIR)
    os.makedirs(out, exist_ok=True)
    expected = 27
    written = 0
    for slug, entry in TERMS.items():
        html = render_html(entry)
        # Guards
        if DASH_RE.search(html):
            raise SystemExit(f"DASH found in HTML for {slug}")
        sch = schema(entry["faqs"])
        sch_json = json.dumps(sch, ensure_ascii=False, indent=2)
        if DASH_RE.search(sch_json):
            raise SystemExit(f"DASH found in schema for {slug}")
        for bad in ("<script", "<style", "<h1"):
            if bad in html.lower():
                raise SystemExit(f"Illegal tag {bad} in {slug}")
        # Byte-for-byte FAQ parity check: each answer must appear verbatim in HTML
        for q, a in entry["faqs"]:
            if f"<p>{a}</p>" not in html:
                raise SystemExit(f"FAQ answer not found verbatim in HTML for {slug}: {q}")
        with open(os.path.join(out, f"{slug}.html"), "w", encoding="utf-8") as f:
            f.write(html)
        with open(os.path.join(out, f"{slug}.schema.json"), "w", encoding="utf-8") as f:
            f.write(sch_json)
        written += 1
    print(f"Wrote {written} terms x 2 files to {out}")
    if written != expected:
        print(f"WARNING: expected {expected} terms, wrote {written}")


if __name__ == "__main__":
    main()
