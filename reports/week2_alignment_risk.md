# Week 2 — Cross-Class Alignment Risk Check

## Method

Semi-automated one-to-one greedy matching of paragraphs across entity classes
sharing a subject family, using token Jaccard ≥ 0.45.
This is a **risk measurement**, not gold alignment. Spot-check recommended.

- Subjects used: ['Know Your Customer', 'Prudential Norms on Capital Adequacy', 'Miscellaneous']
- Pair comparisons: 9
- Mean one-to-one alignment rate: **0.9225**
- <60% fallback trigger: **False**

## Pair details

- Know Your Customer | Commercial Banks vs Small Finance Banks: 98/101 = 0.9703
- Know Your Customer | Commercial Banks vs Payments Banks: 98/101 = 0.9703
- Know Your Customer | Small Finance Banks vs Payments Banks: 103/108 = 0.9537
- Prudential Norms on Capital Adequacy | Commercial Banks vs Small Finance Banks: 289/329 = 0.8784
- Prudential Norms on Capital Adequacy | Commercial Banks vs Payments Banks: 103/131 = 0.7863
- Prudential Norms on Capital Adequacy | Small Finance Banks vs Payments Banks: 116/131 = 0.8855
- Miscellaneous | Commercial Banks vs Small Finance Banks: 163/168 = 0.9702
- Miscellaneous | Commercial Banks vs Payments Banks: 156/168 = 0.9286
- Miscellaneous | Small Finance Banks vs Payments Banks: 163/170 = 0.9588
