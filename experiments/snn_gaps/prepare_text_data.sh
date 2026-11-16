#!/bin/sh
# enwik8 + the author's training file (DAIGT v2, rebuilt from a HuggingFace mirror of the Kaggle dataset)
set -e; mkdir -p data; cd data
[ -f enwik8 ] || { curl -sSLO http://mattmahoney.net/dc/enwik8.zip && unzip -q enwik8.zip; }
[ -f train_v2_drcat_02.csv ] || { curl -sSL -o daigt.parquet https://huggingface.co/datasets/Yunij/kaggle-comp-daigt/resolve/main/data/train-00000-of-00001.parquet
  python3 -c "import pandas as pd; pd.read_parquet('daigt.parquet', columns=['text','label','prompt_name','source','RDizzl3_seven']).to_csv('train_v2_drcat_02.csv', index=False)"; }
