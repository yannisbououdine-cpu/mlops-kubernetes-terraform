# Runbook

Que faire quand une alerte se déclenche. Chaque alerte de [`chart/alerts/rules.yaml`](../chart/alerts/rules.yaml) renvoie à sa section.

## Avant de commencer

```bash
export KUBECONFIG=$(terraform -chdir=terraform output -raw kubeconfig_path)

kubectl get pods -n ml                     # état des pods de l'API
kubectl logs -n ml -l app.kubernetes.io/name=digit-classifier --tail=50
kubectl get events -n ml --sort-by=.lastTimestamp | tail -20
```

- Tableau de bord : Grafana → *Digit classifier*
- Alertes actives : http://127.0.0.1:9090/alerts
- Version du modèle servi : `curl http://127.0.0.1:8080/model`

## DigitClassifierDown

**Signification** : Prometheus ne parvient à collecter aucun pod de l'API depuis 2 minutes. Les utilisateurs n'ont probablement plus de service.

**Diagnostic**

```bash
kubectl get pods -n ml
kubectl describe pods -n ml -l app.kubernetes.io/name=digit-classifier
```

| Ce que vous voyez | Cause probable | Action |
|---|---|---|
| `ErrImageNeverPull` ou `ImagePullBackOff` | L'image n'est pas dans le nœud | Relancer `terraform apply` : la ressource `kind_load` recharge l'image |
| `CrashLoopBackOff` | L'API plante au démarrage, souvent un modèle introuvable | `kubectl logs -n ml <pod> --previous` |
| `OOMKilled` dans `describe` | Mémoire insuffisante | Augmenter `resources.limits.memory` dans `chart/values.yaml` |
| Pods `Running` et prêts | C'est la collecte qui échoue, pas l'API | Prometheus → *Status* → *Targets*, chercher `digit-classifier` |

**Retour arrière** : redéployer l'image précédente avec `terraform apply -var image=digit-classifier:<commit précédent>`.

## DigitClassifierHighErrorRate

**Signification** : plus de 5 % des requêtes se terminent en erreur 5xx. Les erreurs 422 (image invalide envoyée par le client) ne comptent pas : ce sont des erreurs de l'appelant, pas du service.

**Diagnostic**

```bash
kubectl logs -n ml -l app.kubernetes.io/name=digit-classifier --tail=200 | grep -B2 -A20 Traceback
```

Le tableau de bord indique depuis quand les erreurs apparaissent. Si elles commencent juste après un déploiement, comparer `model_version` dans `/model` avec la version précédente : le retour arrière est la première action, l'analyse vient après.

## DigitClassifierHighLatency

**Signification** : le 95e centile de latence de `/predict` dépasse 250 ms depuis 5 minutes. En temps normal, une prédiction prend quelques millisecondes.

**Diagnostic**

```bash
kubectl top pods -n ml   # nécessite metrics-server, absent de kind par défaut
```

Sur le tableau de bord, comparer la latence au trafic :

- **la latence monte avec le trafic** : les pods saturent leur limite CPU (500m). Ajouter des réplicas (`replicaCount`) ou, en production, un HorizontalPodAutoscaler ;
- **la latence monte sans hausse du trafic** : chercher un changement récent (nouvelle image, nœud surchargé avec `kubectl describe node`).

## DigitClassifierPredictionSkew

**Signification** : un seul chiffre représente plus de 25 % des prédictions depuis 15 minutes. Sur un trafic équilibré, chaque chiffre pèse environ 10 %. Le service répond normalement, mais les entrées ne ressemblent probablement plus aux données d'entraînement et les réponses sont sans doute fausses. La raison du choix de ce signal est expliquée dans [decisions.md](decisions.md#6-détecter-la-dérive-par-la-répartition-des-prédictions).

**Diagnostic**

1. Sur le panneau *Répartition des chiffres prédits*, repérer le chiffre dominant et l'heure du début.
2. Chercher ce qui a changé à ce moment-là côté clients : nouvelle source d'images, autre résolution, autre prétraitement, images plus sombres ou bruitées.
3. Écarter le faux positif : un client qui n'envoie légitimement qu'un seul chiffre (un test de charge par exemple) déclenche aussi l'alerte.

**Action** : ce n'est pas un incident d'infrastructure, redémarrer les pods ne changera rien. Il faut corriger le prétraitement côté client, ou réentraîner le modèle sur des données représentatives des nouvelles entrées.

**Reproduire l'alerte** : `make drift` envoie des images bruitées, l'alerte passe en *firing* en 15 minutes environ.
