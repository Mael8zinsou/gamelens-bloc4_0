"""Configuration commune des tests.

Rend les modules d'ingestion importables sans installer le projet comme paquet :
la CI execute pytest depuis la racine du depot.
"""

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "ingestion"))
