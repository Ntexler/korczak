# SNN replication + research-gap detection + Jev judge

Three small experiments around Izhikevich, *Spiking Manifesto* (arXiv:2512.11843), JEPA-style prediction,
and TypeSafe's Jev, run to decide what (if anything) Korczak should adopt.

## 1. Does the manifesto's language-model result survive a proper evaluation?

The author's code (`izhikevich/SNN`, `main.c`) trains on `train_v2_drcat_02.csv` (Kaggle DAIGT v2: ~45k
student essays on 15 prompts, ~102 MB) and validates on random positions **inside the same file**
(only ±32 characters excluded). `snn_hw.c` keeps the model unchanged and adds:

* `proper` mode: enwik8, train on bytes [0, 90M), validate on [90M, 95M), final test on [95M, 100M)
* `leaky` mode: the author's protocol (validation positions drawn from the training text)
* Hogwild multi-threading (threads share the look-up tables), same metric as the original:
  bits of the 33rd byte given 32 bytes of context

Same model, same machine, 2 threads each, same step counts:

| steps | DAIGT, author's protocol (bpc) | enwik8, proper split (bpc) |
|---:|---:|---:|
| ~20k | 2.43 | 3.07 |
| ~60k | 2.06 | 2.76 |
| ~100k | 1.92 | 2.64 |
| ~140k | 1.86 | 2.58 |

(Interim: runs continue to 300k steps / 3 h; see `results/snn_*/curve.csv`. Final held-out test numbers
are appended to `log.txt` when they finish.)

Paper Fig. 13a (its data, its protocol) shows ~1.9 bpc at ~1e5 examples, consistent with our DAIGT run,
so the replication is faithful. On enwik8 with a held-out split the same model is ~0.7 bpc worse at
every point. The paper's Table II compares its number with 2016 LSTMs measured on enwik8/text8, which
is not a like-for-like comparison. The model does learn; the "competitive with SOTA LSTMs" claim is not
supported by this evidence.

`baseline.py` (small standard transformer with the same context and eval positions) is included but
was **not run** in this session.

## 2. Research-gap detection on a Korczak-like concept graph

Data: OpenAlex Social Sciences articles (4 snapshot partitions), keywords as concepts, top 3000.
Honest time split: graph from papers <= 2019 (34,981 papers, 93,940 edges); a "gap" is a pair that never
co-occurred; ground truth = pairs that co-occur in >= 2 papers in 2020-2025
(12,674 of 4,404,560 candidates, 0.29%).

| method | AUC | P@100 | P@1000 | lift@1000 |
|---|---:|---:|---:|---:|
| preferential attachment | 0.824 | 0.18 | 0.139 | 48x |
| common neighbours | 0.920 | 0.35 | 0.286 | 99x |
| **Adamic-Adar** | **0.923** | **0.39** | 0.299 | 104x |
| text-embedding similarity | 0.766 | 0.08 | 0.091 | 32x |
| JEPA-style predictor (MLP) | 0.828 | 0.09 | 0.070 | 24x |
| JEPA-style predictor (Izhikevich LUT) | 0.700 | 0.00 | 0.013 | 4.5x |
| Adamic-Adar + JEPA (MLP) | 0.907 | 0.39 | **0.301** | 105x |
| Adamic-Adar + JEPA (LUT) | 0.855 | 0.23 | 0.174 | 60x |

The JEPA predictor learns to predict the embedding of a missing neighbour from (concept, mean of its
neighbours). The LUT version is the same predictor built from the manifesto's pairwise-comparison
look-up tables (no matrix multiplication at inference). Similar training loss (0.548 vs 0.512),
much worse ranking.

Top JEPA-only "surprising" gaps (zero common neighbours): 0 of the top 1000 were filled; they are mostly
hierarchy/near-synonym pairs (education-teaching, jurisdiction-public law).

## 3. Jev as a judge (`jev_judge.py`)

Two atomic Noul questions per pair (decisions in code, per the TypeSafe skill): `studied_together` and
`same_thing`. State = the two concept names + up to 8 pre-2020 neighbours each.

Balanced sample (500 filled + 500 unfilled):

| scorer | AUC |
|---|---:|
| Adamic-Adar | 0.918 |
| **Jev `studied_together` (zero-shot, no training)** | **0.884** |
| JEPA MLP | 0.817 |
| text-embedding similarity | 0.751 |
| Jev `studied_together - same_thing` | 0.781 |
| Adamic-Adar fused with Jev | 0.916 |

Code rule `studied_together >= 0.7 and same_thing < 0.3`: 685 flagged, 64.8% of them filled vs 17.8% of
the rest.

Re-ranking the top 2000 of graph+JEPA: P@50 0.46 -> 0.52 after dropping pairs Jev calls duplicates
(small sample, treat as a hint); re-ordering by Jev alone was worse at the top.

`same_thing` correctly catches redundancy (Thailand/Asia, bribery/political corruption,
student assessment/student self-assessment): useful for Korczak's `entity_resolution`. Subtracting it
hurts the "co-occurs later" metric because subtype pairs do co-occur; co-occurrence is a weak proxy for a
*research gap*.

Cost: 3000 requests, 1.69M input tokens, **$0.07**, 66 s.

## Takeaways for Korczak

* Graph structure (free) is the best predictor of future connections; use it to propose candidates.
* Jev is a strong, nearly free judge without training (AUC 0.88 zero-shot) and good at duplicate
  detection; use it to filter and label candidates, then let Claude explain the survivors.
* The manifesto's LUT layers did not hold up on this task; don't build them into the product.

## Reproduce

```sh
./prepare_text_data.sh                       # enwik8 + DAIGT -> data/
gcc -O3 -march=native -pthread -o snn_hw snn_hw.c -lm
mkdir -p run_proper run_leaky
(cd run_proper && ../snn_hw proper ../data/enwik8 curve.csv 300000 11000 600 2000 10000 2)
(cd run_leaky  && ../snn_hw leaky  ../data/train_v2_drcat_02.csv curve.csv 300000 11000 600 2000 10000 2)
# args: mode data out.csv max_steps max_seconds eval_every_s n_val n_test threads

pip install pandas pyarrow torch sentence-transformers scikit-learn requests
python prepare_openalex.py                   # ~4 GB download -> data/works.pkl
python gaps.py results/gaps_results.json     # writes gaps_arrays.npz (~100 MB, not committed) + gaps_graph.json
export TYPESAFE_API_KEY=...            # Jev key
python jev_judge.py 500 2000                 # -> jev_results.json
```

`jev_judge.py` reads `TYPESAFE_API_KEY` (in the original run a network proxy injected the key).
