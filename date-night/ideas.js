/* =====================================================================
   DATE IDEAS — edit this file to add your own!
   =====================================================================

   HOW TO ADD AN IDEA
   1. Copy one of the blocks below, from the opening {  to the closing },
   2. Paste it right before the  ];  at the very bottom of this file.
   3. Change the words inside the quotes. Keep the commas at the ends of lines.
   4. Give it a new "id" (any unique word-with-dashes, e.g. "our-taco-spot").

   WHAT EACH FIELD MEANS
   id        A unique name. No spaces. Never reuse one.
   title     Short name shown in big letters.
   desc      One sentence about it.
   tier      "in"   = Stay in, but upgraded
             "ease" = Ease out (movies + food, just not at home)
             "send" = Full send (stuff we'd never normally do)
   budget    0 = Free, 1 = $ (under ~$30), 2 = $$ (~$30–80), 3 = $$$ ($80+)
   energy    "lazy", "chill", or "active"
   time      "short" (a couple hours), "half" (half day), "full" (full day)
   when      "day", "night", or "any"
   area      Neighborhood shown on the card (e.g. "Mount Pleasant")
   cost      What it'll roughly cost, in words (e.g. "~$20")
   duration  How long, in words (e.g. "~2 hrs")

   OPTIONAL FIELDS (leave them out if they don't apply)
   place     What to search in Maps for directions, e.g. "Shem Creek Park, Mount Pleasant, SC"
   verify    true  = a real business/venue. The app reminds you to check hours first.
   age21     true  = 21+ (bars, breweries, etc.)
   months    Only show during these months (1 = Jan ... 12 = Dec), e.g. [10, 11, 12]
             In-season ideas also get picked more often.
   ===================================================================== */

window.DATE_IDEAS = [

  /* ---------------- STAY IN, BUT UPGRADED ---------------- */
  {
    id: "charleston-on-screen",
    title: "Charleston-on-screen movie night",
    desc: "Watch something filmed around here (The Notebook, Outer Banks) and try to spot the locations. Boiled peanuts mandatory.",
    tier: "in", budget: 0, energy: "lazy", time: "short", when: "night",
    area: "Home", cost: "Free", duration: "~2.5 hrs"
  },
  {
    id: "shrimp-and-grits",
    title: "Cook shrimp & grits together",
    desc: "Grab local shrimp and make the Lowcountry classic yourselves instead of ordering in.",
    tier: "in", budget: 1, energy: "chill", time: "short", when: "night",
    area: "Home", cost: "~$25 groceries", duration: "~1.5 hrs"
  },
  {
    id: "pizza-from-scratch",
    title: "Build-each-other pizzas",
    desc: "Store-bought dough, a pile of toppings, and you each design a pizza for the other. Loser does dishes.",
    tier: "in", budget: 1, energy: "chill", time: "short", when: "night",
    area: "Home", cost: "~$20", duration: "~1.5 hrs"
  },
  {
    id: "food-passport",
    title: "Movie + food passport",
    desc: "Pick a random country, cook one dish from there, and watch a movie set there.",
    tier: "in", budget: 1, energy: "chill", time: "half", when: "night",
    area: "Home", cost: "~$25", duration: "~3–4 hrs"
  },
  {
    id: "spooky-double-feature",
    title: "Spooky double feature + pumpkins",
    desc: "Carve pumpkins during movie one, roast the seeds during movie two.",
    tier: "in", budget: 1, energy: "chill", time: "half", when: "night",
    area: "Home", cost: "~$15", duration: "~4 hrs", months: [9, 10]
  },
  {
    id: "cocoa-bar",
    title: "Hot cocoa bar + holiday movie",
    desc: "Marshmallows, peppermint, whipped cream, blankets. Pick the cheesiest holiday movie you can find.",
    tier: "in", budget: 1, energy: "lazy", time: "short", when: "night",
    area: "Home", cost: "~$12", duration: "~2 hrs", months: [11, 12, 1]
  },
  {
    id: "fondue-night",
    title: "Fondue night",
    desc: "One pot of cheese, one pot of chocolate, dip absolutely everything.",
    tier: "in", budget: 2, energy: "chill", time: "short", when: "night",
    area: "Home", cost: "~$35", duration: "~2 hrs", months: [10, 11, 12, 1, 2]
  },
  {
    id: "restaurant-at-home",
    title: "Fancy restaurant at home",
    desc: "Dress up, write a menu, cook three courses, candles on. Phones go in a bowl.",
    tier: "in", budget: 2, energy: "chill", time: "half", when: "night",
    area: "Home", cost: "~$40", duration: "~3 hrs"
  },
  {
    id: "sushi-night",
    title: "Roll your own sushi",
    desc: "Rolling mats are cheap and ugly rolls taste exactly the same.",
    tier: "in", budget: 2, energy: "chill", time: "short", when: "night",
    area: "Home", cost: "~$35", duration: "~2 hrs"
  },
  {
    id: "paint-each-other",
    title: "Paint-each-other portraits",
    desc: "Cheap canvases, a 30-minute timer, then the big reveal. Frame the worst one.",
    tier: "in", budget: 1, energy: "lazy", time: "short", when: "any",
    area: "Home", cost: "~$20", duration: "~1.5 hrs"
  },
  {
    id: "bake-off",
    title: "Bake Off night",
    desc: "Watch a Great British Bake Off episode, then attempt the technical challenge.",
    tier: "in", budget: 1, energy: "chill", time: "short", when: "night",
    area: "Home", cost: "~$15", duration: "~2.5 hrs"
  },
  {
    id: "breakfast-for-dinner",
    title: "Pajama breakfast-for-dinner",
    desc: "Pancakes, bacon, and the comfiest pajamas you own.",
    tier: "in", budget: 1, energy: "lazy", time: "short", when: "night",
    area: "Home", cost: "~$15", duration: "~1.5 hrs"
  },
  {
    id: "blind-wine-board",
    title: "Blind wine tasting + snack board",
    desc: "Each of you secretly buys a $12 bottle. Build a board, taste blind, guess which is whose.",
    tier: "in", budget: 2, energy: "lazy", time: "short", when: "night",
    area: "Home", cost: "~$40", duration: "~2 hrs", age21: true
  },
  {
    id: "home-cocktail-class",
    title: "Home cocktail class",
    desc: "Learn two classics from YouTube, then invent and name your own house drink.",
    tier: "in", budget: 2, energy: "chill", time: "short", when: "night",
    area: "Home", cost: "~$40", duration: "~2 hrs", age21: true
  },
  {
    id: "game-tournament",
    title: "Living-room picnic + game tournament",
    desc: "Blanket on the floor, snacks everywhere, best of five at any card or board game.",
    tier: "in", budget: 0, energy: "lazy", time: "short", when: "night",
    area: "Home", cost: "Free", duration: "~2 hrs"
  },
  {
    id: "recreate-first-date",
    title: "Recreate your first date (at home)",
    desc: "Same food, same outfits if you can, same awkward small talk.",
    tier: "in", budget: 1, energy: "lazy", time: "short", when: "night",
    area: "Home", cost: "~$20", duration: "~2 hrs"
  },
  {
    id: "blanket-stargazing",
    title: "Blanket stargazing",
    desc: "Cool nights mean clearer skies. Hot drinks, a stargazing app, and find one planet.",
    tier: "in", budget: 0, energy: "lazy", time: "short", when: "night",
    area: "Home (backyard or balcony)", cost: "Free", duration: "~1 hr", months: [10, 11, 12, 1, 2, 3]
  },
  {
    id: "puzzle-playlist",
    title: "Puzzle + playlist swap",
    desc: "Do a 500-piece puzzle while playing 10-song playlists you each made about the other.",
    tier: "in", budget: 1, energy: "lazy", time: "short", when: "any",
    area: "Home", cost: "~$15", duration: "~2 hrs"
  },

  /* ---------------- EASE OUT ---------------- */
  {
    id: "drive-in",
    title: "Drive-in double feature",
    desc: "Highway 21 Drive-In: pile blankets in the car, bring snacks from home. Road trip included.",
    tier: "ease", budget: 2, energy: "lazy", time: "half", when: "night",
    area: "Beaufort (road trip, ~1.5 hrs)", cost: "~$10–20 each + gas", duration: "~5–6 hrs",
    place: "Highway 21 Drive-In, Beaufort, SC", verify: true
  },
  {
    id: "pitt-street-sunset",
    title: "Takeout picnic at Pitt Street Bridge",
    desc: "Grab takeout and a blanket and watch the sun set over the marsh in the Old Village.",
    tier: "ease", budget: 1, energy: "lazy", time: "short", when: "night",
    area: "Mount Pleasant (Old Village)", cost: "~$25 takeout", duration: "~1.5 hrs",
    place: "Pitt Street Bridge, Mount Pleasant, SC"
  },
  {
    id: "shem-creek-boardwalk",
    title: "Shem Creek boardwalk + dinner on a deck",
    desc: "Walk the boardwalk looking for dolphins and shrimp boats, then eat outside on the water.",
    tier: "ease", budget: 2, energy: "chill", time: "short", when: "any",
    area: "Mount Pleasant", cost: "~$50", duration: "~2 hrs",
    place: "Shem Creek Park, Mount Pleasant, SC"
  },
  {
    id: "terrace-theater",
    title: "Indie movie at The Terrace",
    desc: "James Island's cozy little movie theater, and they serve beer and wine.",
    tier: "ease", budget: 2, energy: "lazy", time: "short", when: "night",
    area: "James Island", cost: "~$30", duration: "~2.5 hrs",
    place: "The Terrace Theater, James Island, SC", verify: true
  },
  {
    id: "big-screen-movie",
    title: "Big-screen movie night out",
    desc: "Your usual movie night, but with a giant screen and somebody else's popcorn.",
    tier: "ease", budget: 2, energy: "lazy", time: "short", when: "night",
    area: "Mount Pleasant", cost: "~$35", duration: "~2.5 hrs",
    place: "Regal Palmetto Grande, Mount Pleasant, SC", verify: true
  },
  {
    id: "poes-sunset",
    title: "Burgers at Poe's + beach sunset",
    desc: "Burgers on Sullivan's Island, then walk a block to the beach for sunset.",
    tier: "ease", budget: 2, energy: "lazy", time: "short", when: "night",
    area: "Sullivan's Island", cost: "~$45", duration: "~2 hrs",
    place: "Poe's Tavern, Sullivan's Island, SC", verify: true
  },
  {
    id: "waterfront-park-night",
    title: "Pineapple Fountain night walk",
    desc: "Get takeout downtown, then wander Waterfront Park and the Battery after dark.",
    tier: "ease", budget: 1, energy: "chill", time: "short", when: "night",
    area: "Downtown", cost: "~$25 takeout", duration: "~2 hrs",
    place: "Waterfront Park, Charleston, SC"
  },
  {
    id: "kaminskys",
    title: "Late-night dessert at Kaminsky's",
    desc: "Split two slices of cake on Market Street. Dessert counts as dinner tonight.",
    tier: "ease", budget: 1, energy: "lazy", time: "short", when: "night",
    area: "Downtown", cost: "~$25", duration: "~1 hr",
    place: "Kaminsky's Dessert Cafe, Charleston, SC", verify: true
  },
  {
    id: "pages-brunch",
    title: "Brunch at Page's Okra Grill",
    desc: "A Mount Pleasant brunch staple. Go early because there's usually a wait.",
    tier: "ease", budget: 2, energy: "lazy", time: "short", when: "day",
    area: "Mount Pleasant", cost: "~$40", duration: "~1.5 hrs",
    place: "Page's Okra Grill, Mount Pleasant, SC", verify: true
  },
  {
    id: "bookstore-date",
    title: "Bookstore date on King Street",
    desc: "Buxton Books: each of you picks a book for the other (under $20), then go get coffee.",
    tier: "ease", budget: 2, energy: "chill", time: "short", when: "day",
    area: "Downtown", cost: "~$45", duration: "~2 hrs",
    place: "Buxton Books, Charleston, SC", verify: true
  },
  {
    id: "festival-of-lights",
    title: "Holiday Festival of Lights",
    desc: "Drive through millions of lights at James Island County Park with cocoa in the cupholders.",
    tier: "ease", budget: 1, energy: "lazy", time: "short", when: "night",
    area: "James Island", cost: "~$20–25 per car", duration: "~1.5 hrs",
    place: "James Island County Park, Charleston, SC", verify: true, months: [11, 12, 1]
  },
  {
    id: "farmers-market",
    title: "Saturday farmers market",
    desc: "Marion Square: breakfast from a vendor, then buy ingredients and cook dinner together later.",
    tier: "ease", budget: 1, energy: "chill", time: "short", when: "day",
    area: "Downtown", cost: "~$30", duration: "~2 hrs",
    place: "Marion Square, Charleston, SC", verify: true, months: [4, 5, 6, 7, 8, 9, 10, 11]
  },
  {
    id: "night-market",
    title: "City Market night market",
    desc: "Friday and Saturday evenings: local makers, snacks, and people-watching.",
    tier: "ease", budget: 1, energy: "chill", time: "short", when: "night",
    area: "Downtown", cost: "~$20", duration: "~1.5 hrs",
    place: "Charleston City Market, Charleston, SC", verify: true, months: [3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
  },
  {
    id: "westbrook",
    title: "Westbrook Brewing taproom",
    desc: "A big Mount Pleasant brewery with room to hang out. Bring a card game.",
    tier: "ease", budget: 1, energy: "lazy", time: "short", when: "any",
    area: "Mount Pleasant", cost: "~$25", duration: "~2 hrs",
    place: "Westbrook Brewing Co, Mount Pleasant, SC", verify: true, age21: true
  },
  {
    id: "two-blokes",
    title: "Pints at Two Blokes",
    desc: "A low-key Mount Pleasant brewery, about five minutes from the couch.",
    tier: "ease", budget: 1, energy: "lazy", time: "short", when: "night",
    area: "Mount Pleasant", cost: "~$25", duration: "~1.5 hrs",
    place: "Two Blokes Brewing, Mount Pleasant, SC", verify: true, age21: true
  },
  {
    id: "revelry-rooftop",
    title: "Revelry rooftop at sunset",
    desc: "A downtown brewery with a rooftop, perfect for sunset.",
    tier: "ease", budget: 1, energy: "chill", time: "short", when: "night",
    area: "Downtown", cost: "~$25", duration: "~2 hrs",
    place: "Revelry Brewing Co, Charleston, SC", verify: true, age21: true
  },
  {
    id: "low-tide-angel-oak",
    title: "Angel Oak + Low Tide Brewing",
    desc: "See the giant Angel Oak, then grab a pint at Low Tide on Johns Island.",
    tier: "ease", budget: 1, energy: "chill", time: "half", when: "day",
    area: "Johns Island", cost: "~$25", duration: "~3–4 hrs",
    place: "Low Tide Brewing, Johns Island, SC", verify: true, age21: true
  },
  {
    id: "park-circle",
    title: "Park Circle dinner stroll",
    desc: "Pick an East Montague Ave restaurant you've never tried, then walk around the circle.",
    tier: "ease", budget: 2, energy: "chill", time: "short", when: "night",
    area: "Park Circle (N. Charleston)", cost: "~$50", duration: "~2 hrs",
    place: "East Montague Avenue, North Charleston, SC"
  },
  {
    id: "palmetto-islands",
    title: "Picnic at Palmetto Islands park",
    desc: "Marsh boardwalks and an observation tower, right in Mount Pleasant.",
    tier: "ease", budget: 0, energy: "chill", time: "short", when: "day",
    area: "Mount Pleasant", cost: "~$2 each entry", duration: "~2 hrs",
    place: "Palmetto Islands County Park, Mount Pleasant, SC", verify: true
  },
  {
    id: "bowens-oysters",
    title: "Oyster roast at Bowens Island",
    desc: "Shovels of oysters and sunset over the marsh. Cooler months are oyster season.",
    tier: "ease", budget: 2, energy: "chill", time: "short", when: "night",
    area: "James Island", cost: "~$50", duration: "~2 hrs",
    place: "Bowens Island Restaurant, Charleston, SC", verify: true, months: [10, 11, 12, 1, 2, 3]
  },
  {
    id: "golden-hour-photos",
    title: "Golden-hour photo walk",
    desc: "Rainbow Row, the Battery, and the little alleys. Take one really good photo of each other.",
    tier: "ease", budget: 0, energy: "chill", time: "short", when: "day",
    area: "Downtown", cost: "Free", duration: "~1.5 hrs",
    place: "Rainbow Row, Charleston, SC"
  },
  {
    id: "mp-pier-sunset",
    title: "Mount Pleasant Pier swings at sunset",
    desc: "Swing benches under the Ravenel Bridge, takeout in your laps.",
    tier: "ease", budget: 0, energy: "lazy", time: "short", when: "night",
    area: "Mount Pleasant", cost: "Free (+ takeout)", duration: "~1 hr",
    place: "Mount Pleasant Pier, Mount Pleasant, SC", verify: true
  },
  {
    id: "thrift-challenge",
    title: "$20 thrift outfit challenge",
    desc: "Each of you gets $20 to build an outfit for the other. Wear them out to dinner.",
    tier: "ease", budget: 1, energy: "chill", time: "half", when: "day",
    area: "Mount Pleasant", cost: "~$40", duration: "~3 hrs",
    place: "thrift store, Mount Pleasant, SC"
  },
  {
    id: "brewery-trivia",
    title: "Brewery trivia night",
    desc: "Lots of local spots run weekly trivia. A ridiculous team name is required.",
    tier: "ease", budget: 1, energy: "chill", time: "short", when: "night",
    area: "Mount Pleasant", cost: "~$25", duration: "~2 hrs",
    place: "trivia night, Mount Pleasant, SC", verify: true, age21: true
  },
  {
    id: "vendue-rooftop",
    title: "Rooftop drinks at The Vendue",
    desc: "A downtown rooftop bar with harbor views. Dress up a little.",
    tier: "ease", budget: 2, energy: "lazy", time: "short", when: "night",
    area: "Downtown", cost: "~$45", duration: "~1.5 hrs",
    place: "The Rooftop at The Vendue, Charleston, SC", verify: true, age21: true
  },
  {
    id: "morris-lighthouse",
    title: "Morris Island Lighthouse walk",
    desc: "At the north end of Folly, an easy walk to see the lighthouse standing out in the ocean.",
    tier: "ease", budget: 0, energy: "chill", time: "short", when: "day",
    area: "Folly Beach", cost: "Free", duration: "~1.5 hrs",
    place: "Lighthouse Inlet Heritage Preserve, Folly Beach, SC"
  },
  {
    id: "folly-afternoon",
    title: "Lazy Folly Beach afternoon",
    desc: "Wander Center Street, eat somewhere with a deck, then end up on the sand.",
    tier: "ease", budget: 2, energy: "lazy", time: "half", when: "day",
    area: "Folly Beach", cost: "~$50", duration: "~4 hrs",
    place: "Center Street, Folly Beach, SC"
  },
  {
    id: "hampton-park",
    title: "Hampton Park picnic",
    desc: "Sandwiches, a blanket, and a slow loop around one of downtown's prettiest parks.",
    tier: "ease", budget: 0, energy: "lazy", time: "short", when: "day",
    area: "Downtown", cost: "Free (+ food)", duration: "~2 hrs",
    place: "Hampton Park, Charleston, SC"
  },
  {
    id: "the-alley",
    title: "Bowling + arcade at The Alley",
    desc: "Downtown bowling, arcade games, and food. Loser buys dessert.",
    tier: "ease", budget: 2, energy: "chill", time: "short", when: "night",
    area: "Downtown", cost: "~$50", duration: "~2 hrs",
    place: "The Alley, Charleston, SC", verify: true
  },
  {
    id: "riverdogs",
    title: "RiverDogs baseball game",
    desc: "Cheap seats, hot dogs, and between-inning chaos at The Joe.",
    tier: "ease", budget: 1, energy: "lazy", time: "short", when: "night",
    area: "Downtown (The Joe)", cost: "~$30", duration: "~3 hrs",
    place: "Joseph P. Riley Jr. Park, Charleston, SC", verify: true, months: [4, 5, 6, 7, 8, 9]
  },

  /* ---------------- FULL SEND ---------------- */
  {
    id: "dolphin-kayak",
    title: "Dolphin kayak tour from Shem Creek",
    desc: "A guided paddle through the creek and marsh. Good odds of seeing dolphins up close.",
    tier: "send", budget: 2, energy: "active", time: "half", when: "day",
    area: "Mount Pleasant", cost: "~$50–65 each", duration: "~2.5 hrs",
    place: "Nature Adventures Outfitters, Mount Pleasant, SC", verify: true
  },
  {
    id: "ravenel-walk",
    title: "Walk the Ravenel Bridge",
    desc: "About 2.5 miles each way from Mount Pleasant. Reward yourselves with food downtown.",
    tier: "send", budget: 0, energy: "active", time: "half", when: "any",
    area: "Mount Pleasant → Downtown", cost: "Free", duration: "~2.5–3 hrs",
    place: "Mount Pleasant Memorial Waterfront Park, Mount Pleasant, SC"
  },
  {
    id: "sunset-sail",
    title: "Sunset sail on the harbor",
    desc: "A schooner cruise around Charleston Harbor as the sun goes down.",
    tier: "send", budget: 3, energy: "chill", time: "short", when: "night",
    area: "Downtown", cost: "~$45+ each", duration: "~2 hrs",
    place: "Schooner Pride, Charleston, SC", verify: true
  },
  {
    id: "ghost-tour",
    title: "Downtown ghost tour",
    desc: "Charleston is extremely haunted, allegedly. Hold hands for safety.",
    tier: "send", budget: 2, energy: "chill", time: "short", when: "night",
    area: "Downtown", cost: "~$30 each", duration: "~1.5 hrs",
    place: "Bulldog Tours, Charleston, SC", verify: true
  },
  {
    id: "fort-sumter",
    title: "Ferry to Fort Sumter",
    desc: "A boat ride across the harbor to the fort where the Civil War started.",
    tier: "send", budget: 2, energy: "chill", time: "half", when: "day",
    area: "Mount Pleasant (Patriots Point)", cost: "~$35 each", duration: "~2.5 hrs",
    place: "Fort Sumter Tours, Patriots Point, Mount Pleasant, SC", verify: true
  },
  {
    id: "uss-yorktown",
    title: "Explore the USS Yorktown",
    desc: "Climb around a real aircraft carrier at Patriots Point. Way more fun than it sounds.",
    tier: "send", budget: 2, energy: "active", time: "half", when: "day",
    area: "Mount Pleasant", cost: "~$30 each", duration: "~3 hrs",
    place: "Patriots Point Naval & Maritime Museum, Mount Pleasant, SC", verify: true
  },
  {
    id: "pumpkin-patch",
    title: "Boone Hall pumpkin patch",
    desc: "Hayride, corn maze, and you each pick the weirdest pumpkin you can find.",
    tier: "send", budget: 2, energy: "active", time: "half", when: "day",
    area: "Mount Pleasant", cost: "~$40", duration: "~3 hrs",
    place: "Boone Hall Pumpkin Patch, Mount Pleasant, SC", verify: true, months: [9, 10]
  },
  {
    id: "oyster-festival",
    title: "Lowcountry Oyster Festival",
    desc: "A giant January oyster party. Wear clothes you don't care about.",
    tier: "send", budget: 2, energy: "chill", time: "half", when: "day",
    area: "Mount Pleasant", cost: "~$60+", duration: "~4 hrs",
    place: "Boone Hall Plantation, Mount Pleasant, SC", verify: true, months: [1]
  },
  {
    id: "stingrays-hockey",
    title: "Stingrays hockey game",
    desc: "Loud, cheap, and a freezing ice rink in the South. Yell along with everyone else.",
    tier: "send", budget: 2, energy: "chill", time: "short", when: "night",
    area: "North Charleston", cost: "~$25 each", duration: "~2.5 hrs",
    place: "North Charleston Coliseum, North Charleston, SC", verify: true, months: [10, 11, 12, 1, 2, 3, 4]
  },
  {
    id: "ice-skating",
    title: "Go ice skating",
    desc: "Hold hands, fall down, get hot chocolate after.",
    tier: "send", budget: 2, energy: "active", time: "short", when: "any",
    area: "North Charleston", cost: "~$15 each", duration: "~1.5 hrs",
    place: "Carolina Ice Palace, North Charleston, SC", verify: true, months: [11, 12, 1, 2]
  },
  {
    id: "tea-garden",
    title: "Charleston Tea Garden trip",
    desc: "A working tea plantation on Wadmalaw Island. Free tastings and rows of tea bushes.",
    tier: "send", budget: 1, energy: "chill", time: "half", when: "day",
    area: "Wadmalaw Island", cost: "~$20", duration: "~4 hrs",
    place: "Charleston Tea Garden, Wadmalaw Island, SC", verify: true
  },
  {
    id: "angel-oak",
    title: "Visit the Angel Oak",
    desc: "A massive, centuries-old live oak on Johns Island. Free, and genuinely wow.",
    tier: "ease", budget: 0, energy: "lazy", time: "short", when: "day",
    area: "Johns Island", cost: "Free", duration: "~1.5 hrs",
    place: "Angel Oak Tree, Johns Island, SC", verify: true
  },
  {
    id: "cypress-gardens",
    title: "Paddle Cypress Gardens",
    desc: "Paddle a boat through black-water swamp and cypress trees. Spooky-pretty.",
    tier: "send", budget: 2, energy: "active", time: "half", when: "day",
    area: "Moncks Corner", cost: "~$20 each", duration: "~4 hrs",
    place: "Cypress Gardens, Moncks Corner, SC", verify: true
  },
  {
    id: "hunting-island",
    title: "Hunting Island road trip",
    desc: "Climb the lighthouse and walk the wild boneyard beach. Lunch in Beaufort on the way.",
    tier: "send", budget: 1, energy: "active", time: "full", when: "day",
    area: "Hunting Island (road trip, ~2 hrs)", cost: "~$30 + gas", duration: "All day",
    place: "Hunting Island State Park, SC", verify: true
  },
  {
    id: "savannah-day-trip",
    title: "Day trip to Savannah",
    desc: "Two hours south: wander the squares and River Street and eat too many pralines.",
    tier: "send", budget: 3, energy: "chill", time: "full", when: "day",
    area: "Savannah (road trip, ~2 hrs)", cost: "~$100+", duration: "All day",
    place: "Forsyth Park, Savannah, GA"
  },
  {
    id: "theatre-99",
    title: "Improv at Theatre 99",
    desc: "Charleston's improv comedy theater. You'll laugh harder than at any Netflix special.",
    tier: "send", budget: 2, energy: "lazy", time: "short", when: "night",
    area: "Downtown", cost: "~$20–30 each", duration: "~1.5 hrs",
    place: "Theatre 99, Charleston, SC", verify: true
  },
  {
    id: "pour-house",
    title: "Live music at the Pour House",
    desc: "A James Island music venue. Check the deck for smaller (sometimes free) shows.",
    tier: "send", budget: 1, energy: "chill", time: "short", when: "night",
    area: "James Island", cost: "Free–$25", duration: "~2.5 hrs",
    place: "The Charleston Pour House, Charleston, SC", verify: true
  },
  {
    id: "royal-american",
    title: "Live band at The Royal American",
    desc: "A divey, fun live-music bar on Morrison Drive. Go see a band you've never heard of.",
    tier: "send", budget: 1, energy: "chill", time: "short", when: "night",
    area: "Downtown (NoMo)", cost: "~$25", duration: "~2.5 hrs",
    place: "The Royal American, Charleston, SC", verify: true, age21: true
  },
  {
    id: "gin-joint",
    title: "Fancy cocktails at The Gin Joint",
    desc: "A dim, cozy cocktail bar. Order a bartender's choice and trust the process.",
    tier: "send", budget: 3, energy: "lazy", time: "short", when: "night",
    area: "Downtown", cost: "~$60–90", duration: "~1.5 hrs",
    place: "The Gin Joint, Charleston, SC", verify: true, age21: true
  },
  {
    id: "firefly-distillery",
    title: "Firefly Distillery tasting",
    desc: "The home of sweet tea vodka, in North Charleston. Taste a flight and pick a favorite.",
    tier: "send", budget: 1, energy: "chill", time: "short", when: "day",
    area: "North Charleston", cost: "~$15 each", duration: "~1.5 hrs",
    place: "Firefly Distillery, North Charleston, SC", verify: true, age21: true
  },
  {
    id: "iop-sunrise",
    title: "Sunrise on Isle of Palms",
    desc: "Set an alarm, bring coffee and a blanket, watch the sun come up over the ocean. Breakfast after.",
    tier: "send", budget: 0, energy: "active", time: "short", when: "day",
    area: "Isle of Palms", cost: "Free (+ breakfast)", duration: "~2 hrs",
    place: "Isle of Palms County Park, Isle of Palms, SC"
  },
  {
    id: "beach-horseback",
    title: "Horseback ride on the beach",
    desc: "A guided ride along the sand at Seabrook Island. The main-character date.",
    tier: "send", budget: 3, energy: "active", time: "half", when: "day",
    area: "Seabrook Island", cost: "~$100+ each", duration: "~3 hrs",
    place: "Seabrook Island Equestrian Center, Seabrook Island, SC", verify: true
  },
  {
    id: "escape-room",
    title: "Escape room",
    desc: "Find out how well you actually work together under pressure.",
    tier: "send", budget: 2, energy: "active", time: "short", when: "night",
    area: "Mount Pleasant", cost: "~$30–40 each", duration: "~1.5 hrs",
    place: "escape room, Mount Pleasant, SC", verify: true
  },
  {
    id: "dance-class",
    title: "One-night dance class",
    desc: "Salsa, swing, whatever's on tonight. Nobody's good at the start.",
    tier: "send", budget: 2, energy: "active", time: "short", when: "night",
    area: "Charleston area", cost: "~$20–40 each", duration: "~1.5 hrs",
    place: "dance lessons, Charleston, SC", verify: true
  },
  {
    id: "pottery-class",
    title: "Pottery class",
    desc: "Make a pair of lopsided mugs together. Use them forever.",
    tier: "send", budget: 3, energy: "chill", time: "short", when: "any",
    area: "Charleston area", cost: "~$50+ each", duration: "~2 hrs",
    place: "pottery class, Charleston, SC", verify: true
  },
  {
    id: "beach-cruisers",
    title: "Beach cruiser bike ride",
    desc: "Rent bikes and ride the hard sand at low tide on Isle of Palms.",
    tier: "send", budget: 2, energy: "active", time: "half", when: "day",
    area: "Isle of Palms", cost: "~$25 each", duration: "~3 hrs",
    place: "bike rental, Isle of Palms, SC", verify: true
  },
  {
    id: "fort-moultrie",
    title: "Fort Moultrie + Breach Inlet",
    desc: "Explore the old fort on Sullivan's, then watch for dolphins at Breach Inlet.",
    tier: "send", budget: 0, energy: "chill", time: "short", when: "day",
    area: "Sullivan's Island", cost: "Free–$10", duration: "~2 hrs",
    place: "Fort Moultrie, Sullivan's Island, SC", verify: true
  },
  {
    id: "paddleboard",
    title: "Paddleboard lesson",
    desc: "Rent boards or take a quick lesson on the calm water behind Folly.",
    tier: "send", budget: 2, energy: "active", time: "half", when: "day",
    area: "Folly Beach", cost: "~$40+ each", duration: "~3 hrs",
    place: "paddleboard rental, Folly Beach, SC", verify: true
  },
  {
    id: "music-hall-show",
    title: "Concert at Charleston Music Hall",
    desc: "Pick a show you'd never normally go to and get dressed up for it.",
    tier: "send", budget: 3, energy: "chill", time: "short", when: "night",
    area: "Downtown", cost: "~$40–80 each", duration: "~3 hrs",
    place: "Charleston Music Hall, Charleston, SC", verify: true
  },
  {
    id: "home-spa-day",
    title: "Lazy at-home spa day",
    desc: "Face masks, a long bath, smoothies, robes, and a movie marathon to finish.",
    tier: "in", budget: 1, energy: "lazy", time: "full", when: "any",
    area: "Home", cost: "~$25", duration: "All day"
  },
  {
    id: "sullivans-beach-day",
    title: "Full beach day at Sullivan's",
    desc: "Chairs, a cooler, a book each, and stay until the sun goes down.",
    tier: "ease", budget: 1, energy: "lazy", time: "full", when: "day",
    area: "Sullivan's Island", cost: "~$20 snacks", duration: "All day",
    place: "Sullivan's Island Beach, Sullivan's Island, SC", months: [4, 5, 6, 7, 8, 9, 10]
  },
  {
    id: "edisto-day-trip",
    title: "Edisto Beach day trip",
    desc: "A sleepy, old-school beach town about an hour away. Hunt for shells and fossils.",
    tier: "send", budget: 1, energy: "chill", time: "full", when: "day",
    area: "Edisto Beach (road trip, ~1 hr)", cost: "~$30 + gas", duration: "All day",
    place: "Edisto Beach State Park, SC", verify: true
  },
  {
    id: "kiawah-day",
    title: "Kiawah beach + Freshfields Village",
    desc: "Beachwalker Park in the morning, then lunch and a wander around Freshfields.",
    tier: "send", budget: 2, energy: "chill", time: "full", when: "day",
    area: "Kiawah Island", cost: "~$60", duration: "~6 hrs",
    place: "Beachwalker Park, Kiawah Island, SC", verify: true
  }

  // ← Add your own ideas above this line (remember the comma after the previous } ).
];
