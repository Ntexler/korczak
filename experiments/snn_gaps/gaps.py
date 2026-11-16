"""Gap-detection experiment on a Korczak-like concept graph (OpenAlex Social Sciences keywords).

Honest evaluation by time split:
  - Build the concept graph only from papers published <= TRAIN_END.
  - A "gap" = a pair of concepts that never co-occurred up to TRAIN_END.
  - Ground truth: which of those gaps got "filled" (co-occurred in >= MIN_FUT papers) in TRAIN_END+1..2025.
Methods compared:
  graph heuristics (preferential attachment, common neighbours, Adamic-Adar),
  plain text-embedding similarity,
  JEPA-style predictor (predict the *embedding* of a missing neighbour from the context; MLP),
  same predictor implemented as Izhikevich-style look-up tables (pairwise-comparison hash -> summed rows),
  rank fusion of graph + predictor.
"""
import itertools, json, math, os, sys, time
from collections import Counter, defaultdict
import numpy as np
import pandas as pd
import torch, torch.nn as nn, torch.nn.functional as F
from sklearn.metrics import roc_auc_score

torch.manual_seed(0); np.random.seed(0)
TRAIN_END, N_CONCEPTS, MIN_FUT = 2019, 3000, 2
OA = os.environ.get("WORKS_PKL", "data/works.pkl")
OUT = sys.argv[1] if len(sys.argv) > 1 else "gaps_results.json"

df = pd.read_pickle(OA)
df = df[(df.field == "Social Sciences") & df.year.between(1990, 2025)]
tr, fu = df[df.year <= TRAIN_END], df[df.year > TRAIN_END]
freq = Counter(k for kws in tr.kw for k in set(kws))
concepts = [k for k, c in freq.most_common(N_CONCEPTS)]
cid = {k: i for i, k in enumerate(concepts)}
N = len(concepts)


def cooc(frame):
    c = Counter()
    for kws in frame.kw:
        ids = sorted({cid[k] for k in kws if k in cid})
        c.update(itertools.combinations(ids, 2))
    return c


tr_c, fu_c = cooc(tr), cooc(fu)
A = np.zeros((N, N), dtype=np.float32)
for (i, j), w in tr_c.items():
    A[i, j] = A[j, i] = 1
deg = A.sum(1)
iu = np.triu_indices(N, 1)
cand = A[iu] == 0                                   # all non-edges = candidate gaps
pos_set = {p for p, w in fu_c.items() if w >= MIN_FUT and A[p] == 0}
labels = np.array([(i, j) in pos_set for i, j in zip(iu[0][cand], iu[1][cand])])
print(f"papers train={len(tr)} future={len(fu)} | concepts={N} train_edges={int(A.sum()/2)} "
      f"candidates={cand.sum()} filled_gaps={labels.sum()} ({labels.mean()*100:.2f}%)", flush=True)

# --- text embeddings of concept names (frozen "target encoder") ---
from sentence_transformers import SentenceTransformer
E = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2").encode(concepts, normalize_embeddings=True, batch_size=256)
E = E.astype(np.float32)
D = E.shape[1]

scores = {}
scores["preferential_attachment"] = np.outer(deg, deg)
CN = A @ A
scores["common_neighbours"] = CN
inv_log = np.where(deg > 1, 1 / np.log(np.maximum(deg, 2)), 0).astype(np.float32)
scores["adamic_adar"] = (A * inv_log) @ A
scores["embedding_similarity"] = E @ E.T

# --- JEPA-style predictor: context -> predicted embedding of a missing neighbour ---
nbrs = [np.nonzero(A[i])[0] for i in range(N)]


def context(i, drop=None):
    nb = nbrs[i] if drop is None else nbrs[i][nbrs[i] != drop]
    m = E[nb].mean(0) if len(nb) else np.zeros(D, np.float32)
    return np.concatenate([E[i], m])


train_pairs = [(i, j) for i in range(N) for j in nbrs[i] if len(nbrs[i]) >= 2]
print(f"JEPA training pairs: {len(train_pairs)}", flush=True)
Xtr = np.stack([context(i, drop=j) for i, j in train_pairs]).astype(np.float32)
Ytr = E[[j for _, j in train_pairs]]
Xall = np.stack([context(i) for i in range(N)]).astype(np.float32)


def symmetric_score(P):
    P = P / (np.linalg.norm(P, axis=1, keepdims=True) + 1e-9)
    S = P @ E.T
    return S + S.T


t0 = time.time()
mlp = nn.Sequential(nn.Linear(2 * D, 512), nn.GELU(), nn.Linear(512, D))
opt = torch.optim.AdamW(mlp.parameters(), lr=1e-3, weight_decay=1e-4)
Xt, Yt = torch.from_numpy(Xtr), torch.from_numpy(Ytr)
for ep in range(15):
    perm = torch.randperm(len(Xt))
    for b in range(0, len(Xt), 512):
        idx = perm[b:b + 512]
        loss = (1 - F.cosine_similarity(mlp(Xt[idx]), Yt[idx])).mean()
        opt.zero_grad(); loss.backward(); opt.step()
with torch.no_grad():
    P_mlp = mlp(torch.from_numpy(Xall)).numpy()
mlp_time = time.time() - t0
mlp_params = sum(p.numel() for p in mlp.parameters())
scores["jepa_predictor_mlp"] = symmetric_score(P_mlp)
print(f"MLP predictor trained in {mlp_time:.0f}s, final loss {loss.item():.3f}", flush=True)


# --- the same predictor as Izhikevich look-up tables (no matrix multiplication at inference) ---
class LUTPredictor:
    def __init__(self, n_in, n_out, nt=64, nc=10, seed=0):
        r = np.random.default_rng(seed)
        self.a = r.integers(0, n_in, (nt, nc)); self.b = r.integers(0, n_in, (nt, nc))
        self.S = np.zeros((nt, 2 ** nc, n_out), np.float32)
        self.pow = 2 ** np.arange(nc); self.nt = nt

    def index(self, X):                       # Eq. (1): concat of pairwise comparisons -> row index
        return ((X[:, self.a] > X[:, self.b]) * self.pow).sum(-1)       # (batch, nt)

    def forward(self, X):
        j = self.index(X)
        return self.S[np.arange(self.nt), j].sum(1), j                  # Eq. (3): sum of selected rows

    def step(self, X, Y, lr):
        y, j = self.forward(X)
        yn = np.linalg.norm(y, axis=1, keepdims=True) + 1e-9
        cos = (y * Y).sum(1, keepdims=True) / yn
        g = -(Y / yn - cos * y / yn ** 2)                                # d(1-cos)/dy
        for t in range(self.nt):
            np.add.at(self.S[t], j[:, t], -lr * g)
        return float((1 - cos).mean())


t0 = time.time()
lut = LUTPredictor(2 * D, D)
for ep in range(15):
    perm = np.random.permutation(len(Xtr))
    for b in range(0, len(Xtr), 512):
        idx = perm[b:b + 512]
        l = lut.step(Xtr[idx], Ytr[idx], lr=0.05)
P_lut, _ = lut.forward(Xall)
lut_time = time.time() - t0
scores["jepa_predictor_LUT"] = symmetric_score(P_lut)
print(f"LUT predictor trained in {lut_time:.0f}s, final loss {l:.3f}", flush=True)


def ranks(M):
    v = M[iu][cand]
    return pd.Series(v).rank(pct=True).values


R = {k: ranks(v) for k, v in scores.items()}
R["fusion_adamic_adar+jepa_mlp"] = (R["adamic_adar"] + R["jepa_predictor_mlp"]) / 2
R["fusion_adamic_adar+jepa_LUT"] = (R["adamic_adar"] + R["jepa_predictor_LUT"]) / 2

base_rate = labels.mean()
res = {"setup": {"papers_train": int(len(tr)), "papers_future": int(len(fu)), "concepts": N,
                 "train_edges": int(A.sum() / 2), "candidate_gaps": int(cand.sum()),
                 "filled_gaps": int(labels.sum()), "base_rate": float(base_rate),
                 "train_end": TRAIN_END, "min_future_cooc": MIN_FUT,
                 "mlp_params": int(mlp_params), "mlp_train_s": round(mlp_time, 1),
                 "lut_params": int(lut.S.size), "lut_train_s": round(lut_time, 1),
                 "lut_active_values_per_query": int(lut.nt * D + 2 * lut.a.size)},
       "methods": {}}
order = np.argsort(-np.random.rand(len(labels)))  # tie-break randomly
for k, r in R.items():
    top = np.argsort(-(r + 1e-9 * np.random.rand(len(r))))
    m = {"AUC": roc_auc_score(labels, r)}
    for K in (100, 1000, 10000):
        m[f"P@{K}"] = labels[top[:K]].mean()
        m[f"lift@{K}"] = m[f"P@{K}"] / base_rate
    res["methods"][k] = {a: round(float(b), 4) for a, b in m.items()}
    print(f"{k:32s} AUC={m['AUC']:.3f}  P@100={m['P@100']:.3f}  P@1000={m['P@1000']:.3f}  "
          f"lift@1000={m['lift@1000']:.1f}x", flush=True)

# Example predictions from the fusion method: which top gaps were filled later, which remain open
ci, cj = iu[0][cand], iu[1][cand]
top = np.argsort(-R["fusion_adamic_adar+jepa_mlp"])[:40]
res["top_predicted_gaps"] = [{"a": concepts[ci[t]], "b": concepts[cj[t]], "filled_later": bool(labels[t])} for t in top]
# "Surprising" gaps: high JEPA score but zero common neighbours (graph heuristics cannot see them)
cn_v = CN[iu][cand]
mask = cn_v == 0
idx = np.nonzero(mask)[0]
best = idx[np.argsort(-R["jepa_predictor_mlp"][idx])[:20]]
res["jepa_only_gaps"] = {"pairs_with_zero_common_neighbours": int(mask.sum()),
                         "filled_rate_overall": float(labels[mask].mean()),
                         "filled_rate_top1000_by_jepa": float(labels[idx[np.argsort(-R['jepa_predictor_mlp'][idx])[:1000]]].mean()),
                         "examples": [{"a": concepts[ci[t]], "b": concepts[cj[t]], "filled_later": bool(labels[t])} for t in best]}
json.dump(res, open(OUT, "w"), indent=1, ensure_ascii=False)
np.savez_compressed("gaps_arrays.npz", ci=ci, cj=cj, labels=labels, cn=cn_v,
    **{f"rank_{k}": v.astype(np.float32) for k, v in R.items()})
json.dump({"concepts": concepts, "nbrs": [list(map(int, n)) for n in nbrs]}, open("gaps_graph.json", "w"))
print(json.dumps(res["jepa_only_gaps"], indent=1, ensure_ascii=False)[:2500])
