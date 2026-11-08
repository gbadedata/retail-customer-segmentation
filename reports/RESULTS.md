# Results (generated)

Written by `make run`. Do not edit by hand.

## 1. Cleaning and reconciliation

| reason | description | rows | value | share of rows |
|---|---|---:|---:|---:|
| purchase | Kept: product sale to a known customer | 776,579 | 17,068,582.72 | 72.8% |
| return | Kept: cancelled product line from a known customer | 17,586 | -709,953.43 | 1.6% |
| overlap_duplicate | Row from the 2010-11 file that repeats a row already in the 2009-10 file (1-9 Dec 2010) | 22,523 | 377,488.45 | 2.1% |
| missing_customer | No customer ID, so it cannot be tied to a customer | 235,287 | 2,566,093.08 | 22.0% |
| non_product | Postage, fees, manual adjustments, bad-debt write-offs, vouchers or test lines | 3,671 | -68,262.29 | 0.3% |
| bad_price | Price of zero or less | 60 | 0.00 | 0.0% |
| bad_quantity | Zero or negative quantity on a normal invoice, or positive quantity on a cancellation | 0 | 0.00 | 0.0% |
| exact_duplicate | Identical to an earlier row in every field | 11,665 | 53,302.04 | 1.1% |

Raw rows 1,067,371; raw line value £19,287,250.57; difference after accounting £0.00 (balanced: True).
Overlap check: 22,523 rows dated 2010-12-01 to 2010-12-09 appear in both files; 22,523 match a row in the first file exactly.

## 2. Snapshots

- Fit snapshot 2010-12-01: 4,224 customers bought between 2009-12-01 and the snapshot; 48.4% ordered again by 2011-06-01. 15 customers with zero or negative net spend excluded.
- Test snapshot 2011-06-01: 4,316 customers; 57.1% ordered again by 2011-12-01. 8 excluded.
- Spend concentration at the test snapshot: top 10% of customers = 59.1% of 12-month net spend; top 20% = 73.0%.

## 3. RFM segments at the test snapshot

| rfm segment | customers | spend 12m | median spend 12m | median recency days | median orders | repeat rate next6m | next spend | share customers | share spend 12m | share next spend |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Champions | 698 | 4,061,524 | 2,419 | 12 | 7 | 91.0% | 2,386,486 | 16.2% | 52.5% | 58.2% |
| Loyal | 934 | 2,141,753 | 1,478 | 64 | 5 | 78.5% | 999,880 | 21.6% | 27.7% | 24.4% |
| Potential loyalists | 234 | 153,028 | 528 | 29 | 2 | 60.3% | 96,901 | 5.4% | 2.0% | 2.4% |
| New customers | 88 | 40,665 | 308 | 12 | 1 | 54.5% | 40,793 | 2.0% | 0.5% | 1.0% |
| Promising | 178 | 54,491 | 242 | 50 | 1 | 44.9% | 48,859 | 4.1% | 0.7% | 1.2% |
| Need attention | 177 | 122,225 | 516 | 119 | 2 | 51.4% | 59,805 | 4.1% | 1.6% | 1.5% |
| About to sleep | 271 | 88,728 | 240 | 102 | 1 | 33.6% | 46,427 | 6.3% | 1.1% | 1.1% |
| Can't lose them | 45 | 150,845 | 1,694 | 190 | 6 | 60.0% | 41,116 | 1.0% | 2.0% | 1.0% |
| At risk | 675 | 565,706 | 619 | 208 | 2 | 45.9% | 212,125 | 15.6% | 7.3% | 5.2% |
| Hibernating | 1,016 | 355,441 | 245 | 238 | 1 | 30.3% | 171,274 | 23.5% | 4.6% | 4.2% |

## 4. Choosing k (fit snapshot)

| k | inertia | silhouette | davies bouldin | calinski harabasz | ari mean | ari min | stable | chosen |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 6,665 | 0.414 | 0.937 | 3,805 | 0.969 | 0.885 | yes | no |
| 3 | 5,099 | 0.319 | 1.099 | 3,135 | 0.906 | 0.806 | yes | no |
| 4 | 4,004 | 0.340 | 0.979 | 3,046 | 0.931 | 0.873 | yes | yes |
| 5 | 3,407 | 0.325 | 1.001 | 2,869 | 0.903 | 0.621 | yes | no |
| 6 | 2,969 | 0.305 | 0.994 | 2,757 | 0.881 | 0.677 | yes | no |
| 7 | 2,695 | 0.298 | 1.005 | 2,602 | 0.781 | 0.414 | no | no |
| 8 | 2,463 | 0.291 | 1.008 | 2,496 | 0.713 | 0.379 | no | no |

Chosen k = 4 by the pre-declared rule (k >= 3, mean bootstrap ARI >= 0.8, then highest silhouette).

Profiles at the test snapshot:

| cluster | name | customers | spend 12m | median spend 12m | median recency days | median orders | repeat rate next6m | next spend | share customers | share spend 12m | share next spend |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | recent, frequent, high spend | 569 | 4,590,723 | 3,942 | 13 | 11 | 96.0% | 2,554,301 | 13.2% | 59.4% | 62.2% |
| 2 | lapsing, regular, high spend | 1,361 | 2,223,066 | 1,238 | 90 | 4 | 69.4% | 1,014,580 | 31.5% | 28.7% | 24.7% |
| 3 | recent, regular, mid spend | 398 | 262,933 | 569 | 13 | 2 | 68.1% | 195,524 | 9.2% | 3.4% | 4.8% |
| 4 | lapsed, infrequent, low spend | 1,988 | 657,684 | 290 | 203 | 1 | 35.4% | 339,261 | 46.1% | 8.5% | 8.3% |

## 5. Out-of-time validation (scored on the test snapshot's next six months)

| label | segments | repeat auc | repeat auc low | repeat auc high | spend spearman | spend spearman low | spend spearman high |
|---|---:|---:|---:|---:|---:|---:|---:|
| RFM named segments (10) | 10 | 0.758 | 0.744 | 0.773 | 0.522 | 0.497 | 0.544 |
| K-means segments (4) | 4 | 0.735 | 0.721 | 0.747 | 0.554 | 0.528 | 0.575 |
| RFM score total (3-15) | 13 | 0.780 | 0.767 | 0.792 | 0.590 | 0.567 | 0.609 |
| Spend deciles only (10) | 10 | 0.751 | 0.737 | 0.764 | 0.584 | 0.559 | 0.605 |
| Recency score only (5) | 5 | 0.722 | 0.708 | 0.736 | 0.448 | 0.421 | 0.473 |
| BG/NBD per customer (no segments) |  | 0.777 | 0.764 | 0.790 | 0.599 | 0.577 | 0.621 |

BG/NBD fitted on purchase history before 2011-06-01: r = 0.952, alpha = 12.129, a = 0.170, b = 8.170.

RFM segment repeat rates, learned at the fit snapshot vs observed at the test snapshot:

| rfm segment | customers fit | repeat rate fit | mean next spend fit | customers test | repeat rate test | mean next spend test |
|---|---:|---:|---:|---:|---:|---:|
| Champions | 520 | 85.4% | 2,341 | 698 | 91.0% | 3,419 |
| Loyal | 698 | 78.1% | 1,216 | 934 | 78.5% | 1,071 |
| Potential loyalists | 466 | 48.3% | 318 | 234 | 60.3% | 414 |
| New customers | 108 | 36.1% | 206 | 88 | 54.5% | 464 |
| Promising | 177 | 28.8% | 158 | 178 | 44.9% | 274 |
| Need attention | 299 | 46.2% | 226 | 177 | 51.4% | 338 |
| About to sleep | 261 | 28.4% | 111 | 271 | 33.6% | 171 |
| Can't lose them | 100 | 60.0% | 590 | 45 | 60.0% | 914 |
| At risk | 729 | 40.7% | 268 | 675 | 45.9% | 314 |
| Hibernating | 866 | 19.6% | 96 | 1,016 | 30.3% | 169 |

## 6. Migration, December 2010 to June 2011 (row shares)

| rfm segment | Champions | Loyal | Potential loyalists | New customers | Promising | Need attention | About to sleep | Can't lose them | At risk | Hibernating | No purchase in 12 months |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Champions | 43% | 40% | 0% | 0% | 0% | 0% | 0% | 2% | 14% | 0% | 0% |
| Loyal | 30% | 44% | 1% | 0% | 0% | 1% | 0% | 4% | 19% | 2% | 0% |
| Potential loyalists | 11% | 28% | 2% | 0% | 0% | 3% | 0% | 0% | 40% | 16% | 0% |
| New customers | 5% | 12% | 6% | 0% | 0% | 8% | 0% | 0% | 6% | 64% | 0% |
| Promising | 8% | 8% | 5% | 0% | 0% | 8% | 0% | 0% | 1% | 71% | 1% |
| Need attention | 11% | 19% | 3% | 0% | 0% | 9% | 0% | 0% | 33% | 25% | 0% |
| About to sleep | 3% | 6% | 8% | 0% | 0% | 9% | 0% | 0% | 2% | 71% | 0% |
| Can't lose them | 16% | 34% | 1% | 0% | 0% | 2% | 2% | 7% | 25% | 3% | 10% |
| At risk | 9% | 14% | 5% | 0% | 2% | 5% | 4% | 0% | 19% | 23% | 19% |
| Hibernating | 2% | 2% | 4% | 2% | 3% | 2% | 4% | 0% | 1% | 32% | 50% |
