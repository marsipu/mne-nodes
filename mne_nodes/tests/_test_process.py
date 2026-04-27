"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import time
import tqdm
import traceback

print("Test1")
for _ in tqdm.tqdm(range(20), desc="Progress"):
    time.sleep(0.05)
try:
    raise RuntimeError("Test-Error")
except RuntimeError:
    traceback.print_exc()
print("Test2")
