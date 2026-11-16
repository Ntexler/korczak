"""Download 4 OpenAlex works partitions (public S3 snapshot, ~4 GB) and extract year/field/keywords -> data/works.pkl."""
import os, subprocess, pyarrow.parquet as pq, pandas as pd
PARTS = ["updated_date=2026-09-30/part_0000", "updated_date=2026-10-09/part_0004",
         "updated_date=2026-10-09/part_0002", "updated_date=2026-10-08/part_0013"]
os.makedirs("data", exist_ok=True)
rows = []
for p in PARTS:
    f = "data/" + p.replace("/", "_").replace("=", "_") + ".parquet"
    if not os.path.exists(f):
        subprocess.run(["curl", "-sS", "-o", f, f"https://openalex.s3.amazonaws.com/data/parquet/works/{p}.parquet"], check=True)
    for b in pq.ParquetFile(f).iter_batches(batch_size=50000, columns=["publication_year", "primary_topic", "keywords", "type"]):
        for r in b.to_pylist():
            pt, kw = r["primary_topic"], r["keywords"]
            if pt and kw and r["type"] == "article":
                rows.append((r["publication_year"], pt["field"]["display_name"], pt["subfield"]["display_name"],
                             pt["display_name"], [k["display_name"] for k in kw]))
pd.DataFrame(rows, columns=["year", "field", "subfield", "topic", "kw"]).to_pickle("data/works.pkl")
print(len(rows), "works")
