"""Script de telechargement du dataset PaySim depuis Hugging Face."""

import urllib.request
import sys
import time
from pathlib import Path

URL = "https://huggingface.co/datasets/purulalwani/Synthetic-Financial-Datasets-For-Fraud-Detection/resolve/main/financial_txns.parquet"
OUTPUT_FILE = Path(__file__).resolve().parent / "paysim.parquet"

def progress_hook(block_num, block_size, total_size):
    downloaded = block_num * block_size
    if total_size > 0:
        percent = min(100.0, downloaded * 100.0 / total_size)
        mb_down = downloaded / (1024 * 1024)
        mb_total = total_size / (1024 * 1024)
        sys.stdout.write(f"\rTelechargement : {mb_down:.1f} / {mb_total:.1f} Mo ({percent:.1f}%)")
        sys.stdout.flush()

if __name__ == "__main__":
    print(f"Demarrage du telechargement de PaySim depuis :\n{URL}")
    print(f"Destination : {OUTPUT_FILE}")
    start = time.time()
    
    opener = urllib.request.build_opener()
    opener.addheaders = [('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)')]
    urllib.request.install_opener(opener)
    
    urllib.request.urlretrieve(URL, OUTPUT_FILE, reporthook=progress_hook)
    
    elapsed = time.time() - start
    print(f"\n[OK] Telechargement termine en {elapsed:.1f} secondes !")
    print(f"Taille du fichier : {OUTPUT_FILE.stat().st_size / (1024 * 1024):.2f} Mo")
