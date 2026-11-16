"""Small standard char-level transformer, same 32-char context and the SAME eval positions/metric as snn_hw.

Metric: NLL (bits) of byte at position 32 given the preceding 32 bytes, averaged over the
positions stored in eval_positions.txt (written by snn_hw).
usage: python baseline.py <data> <proper|leaky> <eval_positions.txt> <out.csv> <max_seconds> <threads>
"""
import math, sys, time
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

data_path, mode, pos_path, out_path = sys.argv[1:5]
max_sec, threads = int(sys.argv[5]), int(sys.argv[6])
torch.set_num_threads(threads)
torch.manual_seed(0)
CTX, D, L, H, B = 32, 256, 4, 4, 128

raw = np.fromfile(data_path, dtype=np.uint8)
if mode == "proper":
    train, valid = raw[:90_000_000], raw[90_000_000:95_000_000]
else:
    train = valid = raw[:95_000_000]
test = raw[95_000_000:100_000_000]
with open(pos_path) as f:
    nv, nt = map(int, f.readline().split())
    pos = [int(x) for x in f.read().split()]
vidx, tidx = np.array(pos[:nv]), np.array(pos[nv:nv + nt])
reserved = None
if mode == "leaky":  # same exclusion as the original code
    reserved = np.zeros(len(train), dtype=bool)
    for p in vidx:
        reserved[max(0, p - CTX):p + CTX + 1] = True


class Block(nn.Module):
    def __init__(self):
        super().__init__()
        self.ln1, self.ln2 = nn.LayerNorm(D), nn.LayerNorm(D)
        self.attn = nn.MultiheadAttention(D, H, batch_first=True)
        self.ff = nn.Sequential(nn.Linear(D, 4 * D), nn.GELU(), nn.Linear(4 * D, D))
        self.register_buffer("mask", torch.triu(torch.ones(CTX, CTX, dtype=torch.bool), 1))

    def forward(self, x):
        h = self.ln1(x)
        x = x + self.attn(h, h, h, attn_mask=self.mask[: x.size(1), : x.size(1)], need_weights=False)[0]
        return x + self.ff(self.ln2(x))


class GPT(nn.Module):
    def __init__(self):
        super().__init__()
        self.tok, self.pos = nn.Embedding(256, D), nn.Embedding(CTX, D)
        self.blocks = nn.Sequential(*[Block() for _ in range(L)])
        self.ln, self.head = nn.LayerNorm(D), nn.Linear(D, 256)

    def forward(self, x):
        h = self.tok(x) + self.pos(torch.arange(x.size(1)))
        return self.head(self.ln(self.blocks(h)))


def batch_from(arr, starts):
    idx = starts[:, None] + np.arange(CTX + 1)[None, :]
    t = torch.from_numpy(arr[idx].astype(np.int64))
    return t[:, :-1], t[:, 1:]


@torch.no_grad()
def evaluate(arr, starts):
    model.eval()
    tot = 0.0
    for i in range(0, len(starts), 1000):
        x, y = batch_from(arr, starts[i:i + 1000])
        logits = model(x)[:, -1]
        tot += F.cross_entropy(logits, y[:, -1], reduction="sum").item()
    model.train()
    return tot / len(starts) / math.log(2)


model = GPT()
nparams = sum(p.numel() for p in model.parameters())
opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=0.01)
rng = np.random.default_rng(0)
out = open(out_path, "w")
out.write(f"# params={nparams}\nstep,val_bpc,seconds,train_snippets\n")
t0, last, step = time.time(), -1e9, 0
while True:
    el = time.time() - t0
    if el - last >= 300 or el >= max_sec:
        last = el
        v = evaluate(valid, vidx)
        out.write(f"{step},{v:.4f},{int(el)},{step * B}\n"); out.flush()
        print(f"[baseline {mode}] step={step} snippets={step * B} val_bpc={v:.4f} t={int(el)}s", flush=True)
        if el >= max_sec:
            break
    lr = 1e-3 * min(1.0, (step + 1) / 500) * (0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * min(1.0, el / max_sec))))
    for g in opt.param_groups:
        g["lr"] = lr
    s = rng.integers(0, len(train) - CTX - 1, size=B)
    if reserved is not None:
        s = s[~reserved[s]]
    x, y = batch_from(train, s)
    loss = F.cross_entropy(model(x).reshape(-1, 256), y.reshape(-1))
    opt.zero_grad(set_to_none=True)
    loss.backward()
    nn.utils.clip_grad_norm_(model.parameters(), 1.0)
    opt.step()
    step += 1
te = evaluate(test, tidx)
print(f"[baseline {mode}] FINAL test bpc={te:.4f} params={nparams} snippets={step * B}", flush=True)
out.write(f"# final_test_bpc={te:.4f} snippets={step * B}\n")
