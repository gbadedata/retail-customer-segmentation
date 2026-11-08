# Data quality log (generated)

What was found in the raw files, what it would have done to the analysis, and how it is handled.

## DQ01 [high] The two yearly files overlap

- **Finding:** 22,523 rows dated 2010-12-01 to 2010-12-09 appear in both files; all 22,523 are exact copies of rows in the first file.
- **Impact if ignored:** Stacking the files double-counts £377,488 of sales in the busiest pre-Christmas week.
- **Handling:** Rows from the second file inside the first file's date range are quarantined.

## DQ02 [high] Dates are day-first

- **Finding:** InvoiceDate is written dd/mm/yyyy hh:mm (01/12/2009 is 1 December).
- **Impact if ignored:** Month-first parsing silently swaps day and month for days 1-12 and fails on the rest.
- **Handling:** Parsed with an explicit format; the contract fails the run on any unparsed date.

## DQ03 [high] No customer ID on a fifth of rows

- **Finding:** 235,287 rows (22.0%) carry no customer ID, worth £2,566,093 (13.3% of raw line value).
- **Impact if ignored:** These sales cannot be segmented; segment revenue shares describe identified customers only.
- **Handling:** Quarantined and reported; not imputed.

## DQ04 [medium] Non-product lines mixed with sales

- **Finding:** 3,671 lines are postage, fees, manual adjustments, bad-debt write-offs, vouchers or test products (codes such as POST, DOT, M, AMAZONFEE, B).
- **Impact if ignored:** They distort spend, especially single large adjustments.
- **Handling:** Listed explicitly in config.py and quarantined.

## DQ05 [medium] Exact duplicate lines

- **Finding:** 11,665 rows repeat an earlier row in every field.
- **Impact if ignored:** Keeping them adds £53,302 of probably double-keyed sales.
- **Handling:** First copy kept, the rest quarantined. This is a judgement: a customer could genuinely order the same line twice on one invoice.

## DQ06 [low] Returns recorded as cancellation invoices

- **Finding:** Cancellations ('C' invoices) from known customers equal 4.2% of purchase value.
- **Impact if ignored:** Ignoring them overstates customer value; dropping them as noise loses a behaviour signal.
- **Handling:** Kept as returns and netted off each customer's spend in the same window.

## DQ07 [low] Inconsistent ID format and file encoding

- **Finding:** Customer IDs are '13085.0' in one file and '13085' in the other; the second file starts with a byte-order mark.
- **Impact if ignored:** A naive join treats the same customer as two, and the first column name is corrupted.
- **Handling:** IDs normalised to 5-digit strings and checked by the contract; files read as utf-8-sig.

## DQ08 [low] Zero or negative net spend

- **Finding:** 15 customers at the fit snapshot and 8 at the test snapshot returned as much as they bought.
- **Impact if ignored:** They cannot be scored on spend.
- **Handling:** Excluded from that snapshot's segmentation and counted here.

## DQ09 [pass] Every raw row is accounted for

- **Finding:** 1,067,371 rows and £19,287,250.57 of line value reconcile to purchases + returns + quarantine with a difference of £0.00.
- **Impact if ignored:** None.
- **Handling:** Asserted in the pipeline and in the tests.
