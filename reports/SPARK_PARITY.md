# PySpark parity check

The PySpark engine (`src/segments/spark_engine.py`, Spark 4.3.0) and the pandas pipeline were run on the same 1,067,371 rows. **They agree on every check below.**

## Cleaning

Rows placed in a different bucket: **0** of 1,067,371. Both reconciliations balance (Spark difference: £0.00).

| Bucket | Rows (pandas) | Rows (Spark) | Value (pandas) | Value (Spark) |
|---|---:|---:|---:|---:|
| purchase | 776,579 | 776,579 | £17,068,582.72 | £17,068,582.72 |
| return | 17,586 | 17,586 | -£709,953.43 | -£709,953.43 |
| overlap_duplicate | 22,523 | 22,523 | £377,488.45 | £377,488.45 |
| missing_customer | 235,287 | 235,287 | £2,566,093.08 | £2,566,093.08 |
| non_product | 3,671 | 3,671 | -£68,262.29 | -£68,262.29 |
| bad_price | 60 | 60 | £0.00 | £0.00 |
| bad_quantity | 0 | 0 | £0.00 | £0.00 |
| exact_duplicate | 11,665 | 11,665 | £53,302.04 | £53,302.04 |

Overlap check: 22,523 rows from the second file dated 2010-12-01 to 2010-12-09, 22,523 matched to the first file in both engines.

## Snapshots and RFM

| Snapshot | Customers | Excluded (net spend <= 0) | Integer or score mismatches | Segment mismatches | Largest money or week difference |
|---|---:|---:|---:|---:|---:|
| snapshot_fit | 4,224 | 15 | 0 | 0 | 1.0e-09 |
| snapshot_test | 4,314 | 10 | 0 | 0 | 8.7e-10 |

The two engines add money up in a different order, so totals can differ around the ninth decimal place. Nothing differs at the penny, and net spend is compared in whole pennies in both.

## The README's headline figures, recomputed from the Spark output

- 4,314 customers at the June 2011 snapshot.
- Champions and Loyal: 37.8% of customers, 82.5% of next-period spend.
- Champions alone: 16.2% of customers, 58.2% of next spend, 91% reordered.

## Run time

pandas: 4.4 s. Spark in local mode on the same machine: 39.9 s. At about a million rows pandas is the faster tool; the Spark engine is here so the same logic can run on a cluster when the data outgrows one machine.
