# UC-04 data facts — 2026-09-06-data-facts-425-customers-population

Ran on: `substrate.db` (sha256 b6d82a0dc5a4…), 425 linked customers, 18213 products
Population: 192403 users / 1689188 reviews from the pinned dump
When: 2026-09-06, 20 s
Model calls: none

## facts

    customers_linked = 425                               (contacts with an Amazon reviewer, i.e. with purchases; the arena's population)
    customers_prospects = 75                             (contacts without a reviewer: no purchases, out of leave-one-out by construction)
    groups = {'A': 300, 'B': 50, 'C': 75}                (stratum sizes A / B / C)
    catalogue_products = 18213                           (products in the shop catalogue = the ranking universe)
    catalogue_czech_titles = 16067                       (products with a Czech title (the Czech branch reads it))
    interactions = 45526                                 (purchases in the histories (hidden items excluded))
    density_percent = 0.588                              (share of the customer x product matrix that is filled)
    products_bought = 18116                              (products bought by at least one customer in the histories)
    products_single_buyer = 10355                        (of those, bought by exactly one customer)
    median_buyers_per_bought_product = 1.0               (median number of customers per bought product)
    hidden_bought_by_0_others = 108                      (hidden items nobody else bought: unreachable for any behavioural method)
    hidden_bought_by_1_other = 77                        (hidden items bought by one other customer)
    hidden_bought_by_2_to_4_others = 98                  (hidden items bought by two to four other customers)
    hidden_bought_by_5_plus_others = 142                 (hidden items bought by five or more other customers)
    last_day_ties = 88                                   (customers with two or more reviews on their final day (tie broken by review id))
    history_products_median = 94                         (median purchases per customer in the history)
    history_products_min = 11                            (shortest history)
    history_products_max = 430                           (longest history)
    history_title_words_median = 1061                    (median words if every bought title is written out (a prompt's history block))
    history_title_words_max = 4665                       (longest such history in words)
    review_words_per_customer_median = 29469             (median words of English review text per customer)
    review_words_per_customer_max = 203047               (most review text a single customer wrote)
    czech_history_texts_empty = 3181                     (history reviews with no Czech text in the Czech branch (dropped by the May translation run))
    random_floor_full_top10 = 0.00055                    (hit rate of guessing under the full protocol at top 10)
    random_floor_sampled_top10 = 0.099                   (hit rate of guessing under the sampled protocol (100 negatives) at top 10)
    population_users = 192403                            (reviewers in the public Amazon Electronics 5-core dump)
    population_items = 63001                             (products in the dump)
    population_reviews = 1689188                         (reviews in the dump)
    hidden_bought_by_0_others_in_population = 0          (our hidden items nobody in the population bought)
    hidden_bought_by_1_to_4_others_in_population = 26    (our hidden items bought by one to four other reviewers in the population)
    hidden_bought_by_5_plus_others_in_population = 399   (our hidden items bought by five or more other reviewers in the population)
    sanity_users = 2000                                  (random ordinary reviewers (not ours, >= 5 reviews) scored with the population ALS, their chronologically last review hidden, as in the arena)
    sanity_hits_top10 = 50                               (of them, hidden interaction in the ALS top 10 over the full population catalogue)
    sanity_hr10_percent = 2.5                            (the population model's hit rate on ordinary reviewers, the yardstick for the shop's heavy buyers)
    sanity_seconds = 7.5                                 (training + scoring time of the sanity check)

The matrix is 0.588 % dense, 108 of 425 hidden items were bought by nobody else, so single-digit hit counts against the whole catalogue are a property of the data, not of any method.
