# Journal de construction

Ce document retrace la construction du projet, étape par étape, dans l'ordre où elle a eu lieu. Pour chaque étape : ce qui a été fait, pourquoi, comment le vérifier soi-même, et les questions qu'on peut vous poser en entretien.

Il sert à deux choses : comprendre chaque ligne du dépôt, et pouvoir raconter le projet comme une suite de décisions plutôt que comme une liste d'outils.

**Sommaire**

0. [Cadrer le projet](#étape-0--cadrer-le-projet)
1. [Relever les versions actuelles des outils](#étape-1--relever-les-versions-actuelles-des-outils)
2. [Entraîner le modèle avec un seuil de qualité](#étape-2--entraîner-le-modèle-avec-un-seuil-de-qualité)
3. [Écrire l'API d'inférence](#étape-3--écrire-lapi-dinférence)
4. [Tester l'API et l'entraînement](#étape-4--tester-lapi-et-lentraînement)
5. [Mesurer avant de choisir une alerte](#étape-5--mesurer-avant-de-choisir-une-alerte)
6. [Construire l'image Docker](#étape-6--construire-limage-docker)
7. [Écrire le chart Helm](#étape-7--écrire-le-chart-helm)
8. [Décrire l'infrastructure avec Terraform](#étape-8--décrire-linfrastructure-avec-terraform)
9. [Automatiser avec GitHub Actions](#étape-9--automatiser-avec-github-actions)
10. [Documenter](#étape-10--documenter)
11. [Vérifier sur la vraie CI](#étape-11--vérifier-sur-la-vraie-ci)

---

## Étape 0 : cadrer le projet

**Objectif** : un projet qui montre en entretien qu'on sait mener un modèle d'IA jusqu'à la production et l'y surveiller.

**Décisions prises avant d'écrire du code**

| Question | Choix | Raison |
|---|---|---|
| Modèle ou agent IA ? | Un modèle classique (scikit-learn) | Pas de clé d'API payante, reproductible par n'importe quel recruteur, déployable à chaque commit |
| Quel Kubernetes ? | kind, créé par Terraform | Gratuit, et la CI peut faire un vrai déploiement au lieu d'un simple `plan` |
| Quelle supervision ? | Prometheus et Grafana (kube-prometheus-stack) | Le standard du marché sur Kubernetes |
| Quelle CI ? | GitHub Actions | Le dépôt est sur GitHub, et c'est gratuit pour un dépôt public |

Le détail de chaque choix et de ce qu'il coûte est dans [decisions.md](decisions.md).

**En entretien**

- *« Pourquoi un modèle aussi simple ? »* Le sujet est la chaîne autour du modèle. Un modèle qui s'entraîne en une seconde permet de déployer réellement à chaque commit. La structure resterait la même pour un modèle lourd ; ce qui changerait est décrit dans decisions.md, section 1.
- *« Pourquoi pas AWS ou GCP ? »* Pour pouvoir tout tester gratuitement à chaque commit. Le README liste ce qui changerait pour passer sur EKS ou GKE.

---

## Étape 1 : relever les versions actuelles des outils

**Ce qui a été fait** : avant d'écrire la moindre ligne, j'ai relevé la dernière version publiée de chaque outil directement sur leurs dépôts Git, plutôt que de m'appuyer sur ma mémoire :

```bash
# Derniers tags d'une action GitHub, avec le SHA du commit correspondant
git ls-remote --tags https://github.com/actions/checkout | tail -3
```

| Outil | Version retenue |
|---|---|
| Terraform | 1.17.2 |
| Provider kind (`tehcyx/kind`) | 0.13.0 |
| Provider Helm (`hashicorp/helm`) | 3.3.0 |
| kube-prometheus-stack | 93.2.2 |
| Kubernetes (image des nœuds kind 0.33.0) | 1.37.0 |
| Python | 3.13 |

J'ai aussi lu la documentation et le code source des deux providers Terraform à ces versions précises. Exemple concret : le provider Helm est passé en version 3 avec une syntaxe différente (`set = [ { ... } ]` au lieu de blocs `set { ... }`, `kubernetes = { ... }` au lieu d'un bloc). Un exemple trouvé en ligne en version 2 aurait échoué.

**Pourquoi** : les outils DevOps changent vite. Un champ inventé ou obsolète fait échouer un déploiement de façon déroutante.

**Ce que j'ai appris en route** : en cherchant la version de `trivy-action`, je suis tombé sur l'attaque de mars 2026 (CVE-2026-33634) : des attaquants ont déplacé presque tous les tags de cette action vers un code qui volait les secrets des pipelines. C'est la raison pour laquelle chaque action du workflow est épinglée par son SHA (étape 9).

**En entretien**

- *« Comment choisissez-vous vos versions ? »* La dernière version stable, figée explicitement, puis mise à jour par Dependabot à travers la CI. Jamais `latest`.

---

## Étape 2 : entraîner le modèle avec un seuil de qualité

**Fichier** : [`app/train.py`](../app/train.py)

**Ce qui a été fait**

- Jeu de données : 1 797 images de chiffres manuscrits en 8×8 pixels, en niveaux de gris de 0 à 16, embarqué dans scikit-learn. Aucun téléchargement, donc entraînement reproductible.
- Découpage : 80 % pour l'entraînement, 20 % pour le test, stratifié (chaque chiffre est représenté dans les mêmes proportions des deux côtés), graine fixe.
- Modèle : normalisation (`StandardScaler`) puis régression logistique, dans un `Pipeline` pour que la normalisation soit enregistrée avec le modèle.
- **Seuil de qualité** : si l'exactitude sur le jeu de test est inférieure à 95 %, le script s'arrête en erreur et **n'écrit aucun fichier**.
- Le script écrit deux fichiers : le modèle (`model.joblib`) et ses métadonnées (`metadata.json` : version, exactitude, version de scikit-learn).

**Résultat mesuré** : 97,22 % d'exactitude.

**Vérifier soi-même**

```bash
cd app
pip install -r requirements-dev.txt
python train.py --output-dir /tmp/model --model-version local
```

**En entretien**

- *« À quoi sert le seuil de qualité ? »* C'est un garde-fou automatique : un modèle dégradé (données corrompues, changement de dépendance) ne peut pas être déployé, puisque l'image ne se construit même pas.
- *« Pourquoi enregistrer la version de scikit-learn ? »* Un modèle sérialisé avec joblib n'est garanti que pour la version qui l'a produit. L'information permet de diagnostiquer un problème de chargement.

---

## Étape 3 : écrire l'API d'inférence

**Fichier** : [`app/main.py`](../app/main.py)

**Ce qui a été fait** : une API FastAPI avec quatre routes.

| Route | Rôle |
|---|---|
| `POST /predict` | Reçoit 64 pixels, renvoie le chiffre, la confiance et la version du modèle |
| `GET /model` | Renvoie les métadonnées du modèle servi |
| `GET /healthz` | Répond si le processus est vivant ; utilisée par les sondes Kubernetes |
| `GET /metrics` | Métriques au format Prometheus |

Points importants :

1. **Validation des entrées** : le schéma Pydantic exige exactement 64 valeurs entre 0 et 16. Toute autre entrée reçoit une erreur 422 avant d'atteindre le modèle.
2. **Échec rapide au démarrage** : le modèle est chargé au démarrage (`lifespan`). S'il est absent, l'API refuse de démarrer. Kubernetes voit alors un pod en échec au lieu d'un pod « prêt » qui répondrait en erreur.
3. **Deux familles de métriques** :
   - techniques : nombre de requêtes par route et par code, durée des requêtes ;
   - métier : chiffres prédits, confiance du modèle, exactitude du modèle servi.
4. **Cardinalité maîtrisée** : le label `path` contient le *modèle* de route (`/predict`), jamais l'URL réelle. Une URL inconnue est comptée sous `unmatched`. Sans cela, quelqu'un qui appelle `/a1`, `/a2`, `/a3`… créerait une série Prometheus par URL et pourrait saturer sa mémoire.

**Problème rencontré et corrigé** : la première version exposait les métriques avec `app.mount("/metrics", ...)`. En lançant le vrai serveur et en l'appelant avec `curl`, j'ai constaté que `/metrics` répondait **307** (redirection vers `/metrics/`) au lieu de 200 :

```
INFO:     127.0.0.1:49362 - "GET /metrics HTTP/1.1" 307 Temporary Redirect
```

Les tests passaient pourtant, parce que le client de test suit les redirections automatiquement. J'ai remplacé le montage par une route normale et réglé le client de test pour **ne plus suivre les redirections**, afin que ce type de problème fasse échouer les tests à l'avenir.

**Vérifier soi-même**

```bash
cd app
MODEL_DIR=/tmp/model uvicorn main:create_app --factory --port 8000 &
curl -X POST localhost:8000/predict -H 'Content-Type: application/json' -d @../examples/digit-5.json
# {"digit":5,"confidence":0.918,"model_version":"local"}
curl -s localhost:8000/metrics | grep model_predictions_total
```

**En entretien**

- *« Quelle différence entre sonde de vivacité et sonde de disponibilité ? »* La sonde de disponibilité (*readiness*) retire le pod du Service tant qu'il ne répond pas : il ne reçoit pas de trafic. La sonde de vivacité (*liveness*) redémarre le conteneur s'il ne répond plus.
- *« Qu'est-ce que la cardinalité dans Prometheus ? »* Le nombre de séries distinctes : chaque combinaison de labels est une série en mémoire. Un label à valeurs illimitées (URL, identifiant d'utilisateur) fait exploser la mémoire.

---

## Étape 4 : tester l'API et l'entraînement

**Fichiers** : [`app/tests/`](../app/tests)

**Ce qui a été fait** : 14 tests pytest.

| Test | Ce qu'il garantit |
|---|---|
| `test_train_writes_model_and_metadata` | L'entraînement produit un modèle utilisable au-dessus du seuil |
| `test_training_is_reproducible` | Deux entraînements donnent exactement la même exactitude |
| `test_quality_gate_stops_the_build` | Avec un seuil inatteignable, le script échoue **et n'écrit aucun modèle** |
| `test_predict_recognises_a_known_digit` | L'API reconnaît une image du jeu de données |
| `test_predict_rejects_invalid_input` (×5) | Image trop courte, trop longue, hors échelle, valeur négative, texte : toutes rejetées en 422 |
| `test_metrics_expose_predictions_and_http_traffic` | Les métriques métier et techniques sont bien exposées |
| `test_unknown_path_does_not_create_a_label_per_url` | La protection contre la cardinalité fonctionne |
| `test_startup_fails_without_model` | Sans modèle, l'API refuse de démarrer |

Le linter `ruff` vérifie le style et quelques règles de sécurité (famille `S`, issue de Bandit).

**Vérifier soi-même** : `make test`

**En entretien**

- *« Comment testez-vous un modèle ? »* À deux niveaux : la qualité du modèle (seuil d'exactitude, reproductibilité) et le service qui l'expose (validation des entrées, métriques, comportement au démarrage).

---

## Étape 5 : mesurer avant de choisir une alerte

C'est l'étape qui distingue le projet d'un tutoriel.

**Le problème** : en production, on ne connaît pas la bonne réponse au moment où le modèle prédit. Impossible de mesurer l'exactitude en direct. Il faut un signal indirect qui se dégrade quand les données d'entrée ne ressemblent plus à celles de l'entraînement : c'est la **dérive des données**.

**L'hypothèse courante** : surveiller la confiance du modèle. Si elle baisse, le modèle doute, donc les entrées ont changé.

**La vérification** : j'ai ajouté un bruit croissant aux images de test et mesuré trois indicateurs.

| Entrées | Exactitude | Confiance moyenne | Part du chiffre le plus prédit |
|---|---|---|---|
| Intactes | 97,2 % | 95,1 % | 11 % |
| Bruit σ = 2 | 75,8 % | 90,7 % | 30 % |
| Bruit σ = 4 | 45,6 % | 91,1 % | 52 % |
| Bruit σ = 8 | 21,4 % | 93,8 % | 63 % |

**Conclusion** : l'hypothèse est fausse pour ce modèle. Quand l'exactitude tombe à 21 %, la confiance reste à 94 %. Une alerte sur la confiance ne se serait jamais déclenchée. En revanche, le modèle se replie sur une ou deux classes : c'est ce signal que l'alerte `DigitClassifierPredictionSkew` surveille (un chiffre au-dessus de 25 % des prédictions, contre environ 10 % en temps normal).

**En entretien**

- *« Comment détectez-vous la dérive ? »* Racontez cette étape : l'hypothèse naturelle, la mesure qui l'a contredite, le signal retenu, et ses limites (il suppose un trafic équilibré entre les chiffres, voir decisions.md section 6).
- C'est aussi la meilleure réponse à *« Parlez-moi d'une fois où vous avez remis en question une idée reçue. »*

---

## Étape 6 : construire l'image Docker

**Fichier** : [`app/Dockerfile`](../app/Dockerfile)

**Ce qui a été fait** : un build en deux étapes.

1. **Étape `builder`** : installe les dépendances dans un environnement virtuel, puis **entraîne le modèle**. Si le seuil de qualité n'est pas atteint, `train.py` échoue et la construction de l'image s'arrête.
2. **Étape finale** : repart d'une image Python propre et ne copie que l'environnement virtuel, le modèle et `main.py`. Le code d'entraînement n'est pas dans l'image servie.

Autres points :

- `USER 10001` : le conteneur ne tourne pas en root.
- `MODEL_VERSION` est obligatoire (`${MODEL_VERSION:?...}`) : la CI y passe le SHA court du commit, ce qui relie chaque prédiction au commit qui a produit le modèle.
- Le `.dockerignore` fonctionne en liste blanche (`*` puis exceptions) : rien d'autre que les trois fichiers utiles n'entre dans le contexte de build, ni secret ni fichier local oublié.

**En entretien**

- *« Pourquoi un build multi-étapes ? »* Image plus petite, surface d'attaque réduite : ni outils de build ni code d'entraînement en production.
- *« Pourquoi entraîner pendant le build ? »* L'image devient l'unique artefact versionné (code, dépendances et modèle ensemble). Pour un modèle lourd, je séparerais l'entraînement et utiliserais un registre de modèles (decisions.md section 4).

---

## Étape 7 : écrire le chart Helm

**Dossier** : [`chart/`](../chart)

**Ce qui a été fait** : un chart qui contient l'API **et sa supervision**.

| Fichier | Ressource Kubernetes | Rôle |
|---|---|---|
| `deployment.yaml` | Deployment | 2 réplicas de l'API |
| `service.yaml` | Service (NodePort) | Adresse stable devant les pods |
| `servicemonitor.yaml` | ServiceMonitor | Dit à Prometheus de collecter `/metrics` toutes les 15 s |
| `prometheusrule.yaml` | PrometheusRule | Les 4 alertes, lues depuis `alerts/rules.yaml` |
| `dashboard.yaml` | ConfigMap | Le tableau de bord Grafana, chargé automatiquement grâce au label `grafana_dashboard: "1"` |

**Durcissement du Deployment**

| Réglage | Effet |
|---|---|
| `runAsNonRoot`, `runAsUser: 10001` | Kubernetes refuse de lancer le conteneur en root |
| `readOnlyRootFilesystem: true` | Le système de fichiers est en lecture seule ; seul `/tmp` est inscriptible |
| `capabilities.drop: ["ALL"]` | Retire tous les privilèges Linux |
| `allowPrivilegeEscalation: false` | Interdit à un processus de gagner des droits |
| `seccompProfile: RuntimeDefault` | Filtre les appels système dangereux |
| `automountServiceAccountToken: false` | L'API n'a pas besoin de parler à Kubernetes, elle n'en reçoit pas les identifiants |
| `maxUnavailable: 0`, `maxSurge: 1` | Mise à jour sans coupure : un nouveau pod doit être prêt avant qu'un ancien soit retiré |
| `resources.requests` et `limits` | Réserve et plafond de CPU et mémoire |

**Détail technique** : les annotations des alertes utilisent la syntaxe `{{ $value }}` de Prometheus, la même que celle des gabarits Helm. Pour éviter que Helm ne tente de les interpréter, les règles sont dans un fichier à part, inséré tel quel avec `.Files.Get`.

**En entretien**

- *« Pourquoi mettre les alertes dans le chart de l'application ? »* L'équipe qui change l'API change ses alertes dans la même pull request. La supervision évolue avec le code.

---

## Étape 8 : décrire l'infrastructure avec Terraform

**Dossier** : [`terraform/`](../terraform)

**Ce qui a été fait** : un seul `terraform apply` monte tout l'environnement.

| Fichier | Contenu |
|---|---|
| `versions.tf` | Versions de Terraform et des providers, figées ; configuration des providers |
| `variables.tf` | Image à déployer (avec validation : un tag précis obligatoire, `latest` refusé), nom du cluster, versions, ports |
| `cluster.tf` | Le cluster kind et le chargement de l'image dans son nœud |
| `monitoring.tf` | kube-prometheus-stack, avec un mot de passe Grafana généré |
| `app.tf` | Le chart de l'API |
| `outputs.tf` | Les URL, le mot de passe Grafana (marqué sensible) et le chemin du kubeconfig |
| `values/monitoring.yaml` | Réglages de kube-prometheus-stack |

**Ordre de création** : Terraform le déduit des références entre ressources. Il crée le cluster, charge l'image, installe la supervision, puis l'API. L'API dépend explicitement (`depends_on`) de la supervision, car elle utilise les types `ServiceMonitor` et `PrometheusRule` que celle-ci installe.

**Deux réglages de la supervision méritent une explication**

1. `serviceMonitorSelectorNilUsesHelmValues: false` : par défaut, Prometheus n'écoute que les ServiceMonitor créés par sa propre release Helm. Sans ce réglage, il ignorerait celui de l'API.
2. Désactivation de la surveillance de `etcd`, du scheduler, du controller-manager et de kube-proxy : dans kind, ces composants n'écoutent que sur `127.0.0.1` et sont injoignables. Les laisser activés déclencherait de fausses alertes dès l'installation.

**Aucun secret dans le dépôt** : le mot de passe de Grafana est généré par Terraform (`random_password`), passé par `set_sensitive` et récupéré avec `terraform output -raw grafana_admin_password`.

**Vérifier soi-même**

```bash
make up                                  # build, puis terraform init et apply
terraform -chdir=terraform output        # les adresses
make smoke                               # test de bout en bout
make down                                # tout détruire
```

**En entretien**

- *« Qu'est-ce que le state Terraform ? »* Le fichier où Terraform enregistre ce qu'il a créé, pour calculer la différence avec le code. Ici il est local ; en équipe il serait distant et verrouillé (S3 et DynamoDB, par exemple) pour éviter deux `apply` simultanés.
- *« Quelle limite voyez-vous dans votre configuration ? »* Le provider Helm est configuré avec les identifiants d'un cluster créé dans la même configuration, ce que HashiCorp déconseille. Acceptable pour un environnement éphémère ; en production je séparerais infrastructure et applications (decisions.md section 3). Citer soi-même une limite de son travail fait bonne impression.

---

## Étape 9 : automatiser avec GitHub Actions

**Fichier** : [`.github/workflows/ci.yml`](../.github/workflows/ci.yml)

**Ce qui a été fait** : trois jobs. Les deux premiers tournent en parallèle ; le troisième n'est lancé que s'ils réussissent.

```
app ────────┐
            ├──► e2e (déploiement réel sur kind)
infra ──────┘
```

| Job | Étapes |
|---|---|
| `app` | Installe les dépendances, `ruff`, `pytest` |
| `infra` | `hadolint` (Dockerfile), `actionlint` (workflows), `helm lint`, `terraform fmt` et `validate`, scan Trivy de l'IaC |
| `e2e` | Build de l'image (donc entraînement et seuil de qualité), scan Trivy de l'image, `terraform plan` puis `apply`, test de fumée, diagnostic en cas d'échec, publication sur GHCR (sur `main` uniquement), `terraform destroy` dans tous les cas |

**Pratiques de sécurité appliquées**

| Pratique | Où |
|---|---|
| Actions épinglées par SHA de commit | Chaque `uses:` (voir étape 1 pour la raison) |
| Droits minimaux | `permissions: contents: read` par défaut ; seul `e2e` peut publier un paquet |
| Jeton Git non conservé | `persist-credentials: false` sur chaque checkout |
| Pas d'injection de script | Les valeurs variables passent par des variables d'environnement (`$IMAGE`), jamais par `${{ }}` dans un script |
| Nettoyage garanti | `terraform destroy` avec `if: always()` |

**Le test de fumée** ([`scripts/smoke-test.sh`](../scripts/smoke-test.sh)) vérifie six choses, en réessayant pendant 5 minutes au plus :

1. l'API reconnaît le 5 de `examples/digit-5.json` ;
2. l'API rejette une image invalide en 422 ;
3. Prometheus collecte les 2 pods ;
4. Prometheus a enregistré les prédictions ;
5. les 4 règles d'alerte sont chargées ;
6. Grafana a provisionné le tableau de bord.

**Dependabot** ([`.github/dependabot.yml`](../.github/dependabot.yml)) propose chaque semaine une pull request par dépendance à mettre à jour ; la CI la valide de bout en bout.

**En entretien**

- *« Que se passe-t-il entre un `git push` et la production ? »* Déroulez les trois jobs. Insistez sur le fait que le déploiement est réellement exécuté et vérifié, pas seulement planifié.
- *« Pourquoi épingler par SHA plutôt que par tag ? »* Un tag peut être déplacé ; un SHA désigne un contenu immuable. Citez l'attaque contre trivy-action.

---

## Étape 10 : documenter

**Fichiers** : [`README.md`](../README.md), [`decisions.md`](decisions.md), [`runbook.md`](runbook.md) et ce journal.

| Document | Lecteur | Question à laquelle il répond |
|---|---|---|
| README | Recruteur, nouvel arrivant | Qu'est-ce que c'est, comment le lancer, qu'est-ce que ça montre ? |
| decisions.md | Relecteur technique | Pourquoi ces choix, et que coûtent-ils ? |
| runbook.md | Personne d'astreinte | Une alerte sonne : que faire ? |
| Ce journal | Vous, avant l'entretien | Comment le projet a été construit, et comment le raconter |

Chaque alerte contient un lien `runbook` vers sa section : la personne alertée tombe directement sur la procédure.

---

## Étape 11 : vérifier sur la vraie CI

Ce qui pouvait être vérifié avant d'envoyer le code l'a été : les 14 tests, le lint Python, la syntaxe YAML et HCL, et l'API lancée réellement et appelée avec `curl`. Docker, Terraform, Helm et kind n'étaient pas disponibles dans l'environnement de construction : la première vérification réelle du déploiement est la CI.

Les résultats de chaque exécution, y compris les échecs et leur correction, sont consignés ci-dessous avec leur preuve.

<!-- journal-ci -->

### Exécution 1 : le job Infrastructure échoue sur `helm lint`

**Symptôme** : le job `API` passe (lint et 14 tests). Le job `Infrastructure` s'arrête à l'étape *Lint du chart Helm* :

```
[ERROR] templates/: parse error at (digit-classifier/templates/prometheusrule.yaml:2): unexpected <.> in operand
```

**Cause prouvée** : la ligne 2 de `prometheusrule.yaml` est un **commentaire** YAML qui contenait le texte `{{ ... }}`. Helm traite le fichier comme un gabarit Go *avant* de le lire comme du YAML : pour lui, un `#` n'a aucune signification, et `{{ ... }}` est une instruction à exécuter. Une recherche (`grep -n "#.*{{" chart/templates/*`) confirme que c'est la seule occurrence.

**Correction** : reformuler le commentaire sans accolades.

**Leçon** : dans un chart Helm, les commentaires YAML ne protègent rien. Pour commenter une syntaxe de gabarit, utiliser un commentaire Helm `{{/* ... */}}`, ou ne pas écrire les accolades. C'est exactement le piège que le fichier `alerts/rules.yaml` contourne pour les vraies règles d'alerte (étape 7) : le commentaire qui l'expliquait est tombé dedans.

**Pourquoi la CI ne démarrait pas au début** : les deux premières exécutions, déclenchées par les `git push`, sont restées en file d'attente sans aucun job, et les mises à jour Dependabot ont échoué au démarrage. L'exécution lancée à la main avec *Run workflow* (déclencheur `workflow_dispatch`) a démarré normalement. La cause côté GitHub n'est pas établie ; l'hypothèse la plus probable est une restriction temporaire sur un compte récent.
