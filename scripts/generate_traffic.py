"""Envoie des images du jeu de test à l'API pour alimenter les métriques et les tableaux de bord.

Avec --noise, les images sont bruitées : c'est la dérive que l'alerte
DigitClassifierPredictionSkew détecte (environ 15 minutes avec --noise 4).
"""

import argparse
import json
import time
import urllib.request

import numpy as np
from sklearn.datasets import load_digits


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument("--rate", type=float, default=5, help="requêtes par seconde")
    parser.add_argument("--noise", type=float, default=0, help="écart-type du bruit ajouté")
    parser.add_argument("--duration", type=int, default=0, help="secondes, 0 = sans fin")
    args = parser.parse_args()

    rng = np.random.default_rng()
    images = load_digits().data
    deadline = time.monotonic() + args.duration if args.duration else float("inf")

    while time.monotonic() < deadline:
        image = images[rng.integers(len(images))]
        if args.noise:
            image = np.clip(image + rng.normal(0, args.noise, image.shape), 0, 16)
        request = urllib.request.Request(
            f"{args.url}/predict",
            data=json.dumps({"pixels": image.tolist()}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request) as response:
            print(response.read().decode())
        time.sleep(1 / args.rate)


if __name__ == "__main__":
    main()
