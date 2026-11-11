# Choix techniques

Chaque décision est présentée avec les alternatives envisagées et ce qu'elle coûte. Un choix sans contrepartie n'a pas été réfléchi.

## 1. Un modèle classique plutôt qu'un agent ou un LLM

**Choix** : un classifieur scikit-learn (régression logistique) entraîné sur le jeu de chiffres manuscrits embarqué dans scikit-learn.

**Pourquoi** : le projet porte sur la chaîne de déploiement, pas sur le modèle. Ce modèle s'entraîne en une seconde, pèse quelques kilo-octets, tient dans 256 Mio de mémoire et ne dépend d'aucune clé d'API payante. N'importe qui peut cloner le dépôt et tout reproduire, et la CI peut le déployer à chaque commit.

**Contrepartie** : un vrai LLM poserait des questions absentes ici : GPU, images de plusieurs gigaoctets, démarrage lent, coût par requête. La structure (image versionnée, chart, supervision, seuil de qualité) reste la même. Pour un LLM, on remplacerait l'API par un serveur comme vLLM, on ajouterait un pool de nœuds GPU et on suivrait des métriques propres aux LLM : délai avant le premier token, tokens par seconde, coût.

## 2. kind plutôt qu'un Kubernetes managé

**Choix** : un cluster kind créé par Terraform, en local comme en CI.

**Pourquoi** : c'est gratuit, ça se crée en une minute et ça se détruit sans laisser de ressource facturée. Surtout, la CI peut faire un **vrai** déploiement à chaque commit, au lieu de se contenter d'un `terraform plan`.

**Contrepartie** : kind ne montre ni le réseau cloud (VPC, sous-réseaux), ni l'IAM, ni les load balancers. Le tableau « Passer du poste local au cloud » du README liste ce qui changerait.

## 3. Une seule configuration Terraform pour le cluster et ce qu'il contient

**Choix** : `terraform/` crée le cluster et y installe les releases Helm. Le provider Helm reçoit les identifiants du cluster créé dans la même configuration.

**Pourquoi** : une seule commande monte ou détruit tout l'environnement, ce qui convient à un environnement éphémère de démonstration et de CI.

**Contrepartie** : HashiCorp déconseille de configurer un provider avec les attributs d'une ressource du même état. Si le cluster devait être remplacé, Terraform planifierait les releases Helm avec des identifiants inconnus. En production, je séparerais deux configurations : l'infrastructure (réseau, cluster) d'un côté, les applications de l'autre, ces dernières de préférence déployées par Argo CD.

## 4. Entraîner le modèle pendant la construction de l'image

**Choix** : le `Dockerfile` entraîne le modèle dans une première étape et ne copie que le résultat dans l'image finale. `train.py` refuse de produire un modèle dont l'exactitude passe sous 95 % : la construction échoue et rien n'est déployé.

**Pourquoi** : l'image est l'unique artefact déployable. Code, dépendances et modèle sont versionnés ensemble, et le tag de l'image ainsi que l'endpoint `/model` renvoient au commit qui les a produits. L'entraînement est déterministe (graine fixe) : le même commit donne le même modèle, ce que vérifie un test.

**Contrepartie** : cette approche ne fonctionne que pour un modèle qui s'entraîne en quelques secondes. Pour un modèle plus lourd, l'entraînement deviendrait un job séparé, le modèle serait stocké dans un registre de modèles (MLflow par exemple) avec ses métriques, et l'API chargerait une version précise au démarrage.

## 5. Le chart de l'API apporte sa propre supervision

**Choix** : le ServiceMonitor, les règles d'alerte et le tableau de bord Grafana font partie du chart de l'API, pas de la configuration de la supervision.

**Pourquoi** : l'équipe qui modifie l'API modifie ses alertes dans la même pull request. Les règles et le tableau de bord sont des fichiers à part ([`chart/alerts/rules.yaml`](../chart/alerts/rules.yaml) et [`chart/dashboards/`](../chart/dashboards)), lisibles et modifiables sans passer par la syntaxe des gabarits Helm.

**Contrepartie** : le chart dépend des types de ressources installés par kube-prometheus-stack. Terraform l'installe donc en premier (`depends_on`).

## 6. Détecter la dérive par la répartition des prédictions

En production, on ne connaît pas la bonne réponse au moment de la prédiction : l'exactitude réelle n'est pas mesurable en direct. Il faut un signal indirect qui se dégrade quand les entrées ne ressemblent plus aux données d'entraînement.

L'idée la plus courante est de surveiller la confiance du modèle. Je l'ai **mesurée** avant de la retenir, en ajoutant un bruit gaussien d'écart-type σ aux images du jeu de test :

| Entrées | Exactitude | Confiance moyenne | Part du chiffre le plus prédit |
|---|---|---|---|
| Jeu de test intact | 97,2 % | 95,1 % | 11 % |
| Bruit σ = 2 | 75,8 % | 90,7 % | 30 % |
| Bruit σ = 4 | 45,6 % | 91,1 % | 52 % |
| Bruit σ = 8 | 21,4 % | 93,8 % | 63 % |

**Résultat** : quand l'exactitude s'effondre, la confiance ne baisse presque pas, elle remonte même. Une alerte sur la confiance ne se serait jamais déclenchée. En revanche, le modèle se replie sur une ou deux classes : la part du chiffre le plus prédit passe de 11 % à plus de 50 %.

**Choix** : l'alerte `DigitClassifierPredictionSkew` se déclenche quand un seul chiffre dépasse 25 % des prédictions pendant 15 minutes, avec au moins 0,2 requête par seconde pour ne pas réagir sur trois requêtes. La confiance reste affichée sur le tableau de bord, avec un avertissement.

**Contrepartie** : ce signal suppose un trafic à peu près équilibré entre les chiffres. Si les usages réels étaient déséquilibrés, il faudrait comparer la répartition observée à une répartition de référence, par exemple avec la divergence de Jensen-Shannon. Il ne voit pas non plus une dérive qui laisserait la répartition intacte. C'est un premier filet, pas une mesure de qualité.

## 7. Épingler les actions par SHA et figer toutes les versions

**Choix** : chaque action GitHub est référencée par le SHA de son commit, avec la version en commentaire. Les providers Terraform, le chart kube-prometheus-stack, l'image des nœuds kind (par condensat) et les dépendances Python sont figés à une version précise. Dependabot propose les mises à jour et la CI les valide.

**Pourquoi** : un tag Git peut être déplacé. En mars 2026, des attaquants ont réécrit la quasi-totalité des tags de `aquasecurity/trivy-action` pour qu'ils pointent vers un code qui volait les secrets des pipelines (CVE-2026-33634). Les workflows épinglés par SHA n'étaient pas touchés. Figer les versions rend aussi chaque build reproductible : un échec s'explique par un changement du dépôt, pas par une mise à jour silencieuse.

**Contrepartie** : il faut maintenir ces versions. C'est le rôle de Dependabot.

## 8. Des ports NodePort plutôt qu'un Ingress

**Choix** : l'API, Grafana et Prometheus sont exposés en NodePort, reliés à des ports de la machine hôte en écoute sur `127.0.0.1` uniquement.

**Pourquoi** : c'est le moyen le plus simple d'atteindre les services depuis l'hôte avec kind, sans contrôleur supplémentaire à installer. L'écoute sur `127.0.0.1` évite d'exposer Grafana ou Prometheus au réseau local.

**Contrepartie** : il n'y a ni TLS ni nom de domaine. En production : un Ingress ou une Gateway API, avec des certificats gérés par cert-manager.
