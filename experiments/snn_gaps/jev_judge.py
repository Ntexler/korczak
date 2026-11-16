"""Jev as a judge of candidate research gaps (System One step).

Jev answers two atomic judgments per candidate pair; code makes the decision.
Evaluated against the same time-split ground truth as gaps.py (which gaps got filled after 2019).
State uses only pre-2020 graph information (each concept's name + its most common pre-2020 neighbours).

Evaluation 1 (standalone): balanced random sample of filled vs unfilled candidate gaps -> AUC of
  Jev's probability vs every other method's score on the same pairs.
Evaluation 2 (re-ranking): top-N candidates of the best graph+JEPA ranking, re-ordered with Jev -> precision@K.
"""
import json, os, sys, time, concurrent.futures as cf
import numpy as np, requests
from sklearn.metrics import roc_auc_score

URL = "https://api.typesafe.ai/v1/systemone"
HDR = {"Authorization": f"Bearer {os.environ.get('TYPESAFE_API_KEY', 'proxy-injected')}", "Content-Type": "application/json"}
N_POS = N_NEG = int(sys.argv[1]) if len(sys.argv) > 1 else 500
TOPN = int(sys.argv[2]) if len(sys.argv) > 2 else 2000
BASE = "fusion_adamic_adar+jepa_mlp"
rng = np.random.default_rng(1)

Z = np.load("gaps_arrays.npz")
G = json.load(open("gaps_graph.json"))
concepts, nbrs = G["concepts"], G["nbrs"]
ci, cj, labels = Z["ci"], Z["cj"], Z["labels"]
methods = [k[5:] for k in Z.files if k.startswith("rank_")]

# ---- all question wording lives here ----
QUESTIONS = {
    "studied_together": {
        "type": "noul",
        "instructions": "Could one social-science research paper study `concept_a.name` and `concept_b.name` together as its main topics?",
        "criteria": {
            "true": "A natural research question or study design links the two concepts",
            "false": "The concepts belong to unrelated research areas, so a paper on both would be unusual",
        },
    },
    "same_thing": {
        "type": "noul",
        "instructions": "Do `concept_a.name` and `concept_b.name` name the same idea, or is one of them a narrower form of the other?",
        "criteria": {
            "true": "They are synonyms, spelling variants, or one is a subtype of the other",
            "false": "They are two distinct ideas",
        },
    },
}


def state(i, j):
    def c(k):  # neighbours sorted by overall frequency (lower index = more frequent), pre-2020 graph only
        return {"name": concepts[k], "often_studied_with": [concepts[n] for n in sorted(nbrs[k])[:8]]}
    return {"field": "Social sciences research literature", "concept_a": c(i), "concept_b": c(j)}


def ask(i, j):
    payload = {"model": "jev-1.14.0", "state": state(i, j), "questions": QUESTIONS}
    for attempt in range(5):
        try:
            r = requests.post(URL, headers=HDR, json=payload, timeout=30)
            if r.status_code == 200:
                d = r.json()
                return (d["answers"]["studied_together"]["noul"], d["answers"]["same_thing"]["noul"],
                        d["usage"]["input_tokens"])
            if r.status_code in (429, 500, 502, 503):
                time.sleep(2 ** attempt); continue
            raise RuntimeError(f"{r.status_code} {r.text[:200]}")
        except requests.RequestException:
            time.sleep(2 ** attempt)
    raise RuntimeError("Jev request failed after retries")  # surfaced as an error, never as an answer


def run(idx):
    out = [None] * len(idx)
    with cf.ThreadPoolExecutor(8) as ex:
        futs = {ex.submit(ask, int(ci[t]), int(cj[t])): n for n, t in enumerate(idx)}
        for f in cf.as_completed(futs):
            out[futs[f]] = f.result()
    return np.array(out, dtype=np.float64)


def decision(p_together, p_same):
    """Truth table in code: a 'promising gap' is plausible and not a duplicate."""
    return (p_together >= 0.7) & (p_same < 0.3)


t0 = time.time()
# ---- Evaluation 1: balanced sample ----
pos = rng.choice(np.nonzero(labels)[0], N_POS, replace=False)
neg = rng.choice(np.nonzero(~labels)[0], N_NEG, replace=False)
idx1 = np.concatenate([pos, neg]); y1 = labels[idx1]
J1 = run(idx1)
res = {"eval1_balanced_sample": {"n": len(idx1), "AUC": {}}}
for m in methods:
    res["eval1_balanced_sample"]["AUC"][m] = round(float(roc_auc_score(y1, Z["rank_" + m][idx1])), 4)
res["eval1_balanced_sample"]["AUC"]["jev_studied_together"] = round(float(roc_auc_score(y1, J1[:, 0])), 4)
res["eval1_balanced_sample"]["AUC"]["jev_together_minus_same"] = round(float(roc_auc_score(y1, J1[:, 0] - J1[:, 1])), 4)
comb = (Z["rank_" + BASE][idx1] + J1[:, 0]) / 2
res["eval1_balanced_sample"]["AUC"]["fusion+jev"] = round(float(roc_auc_score(y1, comb)), 4)
d = decision(J1[:, 0], J1[:, 1])
res["eval1_balanced_sample"]["decision_rule"] = {
    "flagged_promising": int(d.sum()), "filled_rate_flagged": round(float(y1[d].mean()), 4),
    "filled_rate_not_flagged": round(float(y1[~d].mean()), 4)}
same_hi = J1[:, 1] >= 0.7
res["eval1_balanced_sample"]["same_thing_flagged"] = int(same_hi.sum())
res["eval1_balanced_sample"]["same_thing_examples"] = [
    [concepts[ci[t]], concepts[cj[t]], round(float(p), 2)] for t, p in zip(idx1[same_hi][:15], J1[same_hi, 1][:15])]

# ---- Evaluation 2: re-rank the top-N of the best automatic ranking ----
base = Z["rank_" + BASE]
idx2 = np.argsort(-base)[:TOPN]; y2 = labels[idx2]
J2 = run(idx2)
orders = {
    "graph+jepa (original order)": np.arange(TOPN),
    "jev only": np.argsort(-J2[:, 0]),
    "graph+jepa + jev": np.argsort(-((1 - np.arange(TOPN) / TOPN) + J2[:, 0])),
    "graph+jepa, drop jev duplicates": np.array([k for k in range(TOPN) if J2[k, 1] < 0.7]),
}
res["eval2_rerank_topN"] = {"N": TOPN, "base_rate_in_topN": round(float(y2.mean()), 4)}
for name, o in orders.items():
    res["eval2_rerank_topN"][name] = {f"P@{K}": round(float(y2[o[:K]].mean()), 4) for K in (50, 200, 500)}
# Open gaps Jev finds most promising (not filled by 2025 = candidate *current* research gaps)
open_mask = (~y2) & decision(J2[:, 0], J2[:, 1])
o = np.argsort(-J2[:, 0] * open_mask)[:25]
res["promising_open_gaps"] = [[concepts[ci[idx2[k]]], concepts[cj[idx2[k]]], round(float(J2[k, 0]), 2)] for k in o if open_mask[k]]
tokens = int(J1[:, 2].sum() + J2[:, 2].sum())
res["cost"] = {"requests": len(idx1) + TOPN, "input_tokens": tokens, "usd": round(tokens * 0.042 / 1e6, 4),
               "seconds": round(time.time() - t0, 1)}
json.dump(res, open("jev_results.json", "w"), indent=1, ensure_ascii=False)
print(json.dumps(res, indent=1, ensure_ascii=False))
