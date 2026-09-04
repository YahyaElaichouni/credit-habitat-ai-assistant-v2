# Priorité 1 — champs, provenance et confirmation

Base : `5e065f3b445229ebe5f8d295dd19f7ade9fdd3f6`, branche `main` consultée le 3 septembre 2026.
Modifications préparées localement uniquement. Aucun push, commit distant ou pull request.

## Modifications

- Type `attestation_salaire`, avec employeur, salaire net et date d'embauche.
- Champs `charge_mensuelle_credits` et `revenus_complementaires` sur les relevés.
- Provenance de chaque champ enveloppé : document (identifiant fichier côté serveur), SHA-256,
  page et citation OCR. Le numéro de page est conservé même après une page vide.
- La citation du modèle est recherchée dans la page qu'il indique. Une citation absente,
  inventée ou attribuée à une autre page ne devient pas une provenance vérifiée.
- Formulaire déclaratif métier à la place de la zone JSON. Une entrée vide ne vaut pas zéro.
- Contrôles serveur des confirmations : montants finis, dates valides/non futures selon le champ,
  champs obligatoires non vides, utilisateur renseigné, vérification humaine explicite.
- Confirmation par document, correction typée, réouverture d'un champ et export des seules
  valeurs confirmées. Les anciennes confirmations non structurées doivent être refaites.
- Audit des valeurs originales/finales et de la provenance ; une panne de journalisation
  bloque la confirmation ou sa révocation. Le chemin documentaire est identique dans les événements.
- CSV UTF-8 BOM avec valeur finale, valeur extraite initiale, statut, utilisateur, date et provenance.
  Les contenus pouvant être interprétés comme formules sont neutralisés.
- Une charge déclarée à zéro et extraite non nulle est signalée.
- La précision fictive de 94 % est remplacée par « Non mesurée ».

La compétence Streamlit a guidé la séparation de la logique métier et de l'interface,
la validation serveur des widgets et la gestion des clés propres à chaque document.

## Utilisation du patch

Dans votre dépôt d'origine, après avoir préservé vos modifications locales :

```powershell
git apply --check CHEMIN_VERS_PRIORITE_1.patch
git apply CHEMIN_VERS_PRIORITE_1.patch
```

Le patch est destiné à la base ci-dessus. Si la vérification échoue, ne forcez pas
l'application : comparez les changements depuis cette base.

L'archive contient une copie des sources corrigées, les trois PDF documentaires,
le logo et l'index existants. Le fichier de session `.pkl` du dépôt n'a pas été
recopié ; aucune session ni base SQLite de test n'est livrée. Le patch ne supprime
aucun fichier de session dans votre dépôt d'origine.

## Vérifications automatisées

Résultat de cette livraison : **42 tests réussis**. Compilation Python vérifiée.
Le patch a été contrôlé avec `git apply --check`, puis appliqué sur une copie
propre de la base ; les sources Python obtenues correspondent aux sources testées.

Dans l'environnement du projet, installer pytest en plus des dépendances d'exécution :

```powershell
python -m pip install pytest
python -m pytest tests/test_priority1.py tests/test_review_ui.py -q
```

Tests exécutés avec Python 3.12, Pydantic 2.13.4, Streamlit 1.61.1,
Ollama client 0.6.2 et LangGraph 1.2.11. Les tests comprennent : types et dates,
provenance correcte/fausse/manquante, page vide, confirmations, panne d'audit,
CSV corrigé, formules, champs vides, changements de documents et parcours de l'application.

L'OCR et l'inférence sont simulés dans les tests d'intégration ; le graphe,
les schémas, les validations, SQLite et les interactions Streamlit sont réels.
Il ne s'agit PAS d'une mesure de précision des modèles ni d'une recette OCR réelle.

## Recette locale à effectuer avec vos modèles

1. Lancer l'application depuis la racine du projet (`streamlit run app.py`),
   avec les dépendances initiales et le modèle Ollama déjà installés localement.
2. Utiliser exclusivement des justificatifs fictifs.
3. Déposer une attestation, vérifier employeur/revenu/date et les citations.
4. Déposer un relevé avec une charge mensuelle explicitement libellée, dont un cas zéro/non-zéro.
5. Corriger un montant, confirmer puis télécharger le CSV : vérifier la valeur finale.
6. Changer de document, revenir au premier, rouvrir un champ : il doit disparaître de l'export
   jusqu'à sa nouvelle confirmation.

## Limites conservées

- Le LLM ne calcule pas les charges : si le relevé ne contient que des transactions sans
  total mensuel explicite, le champ reste nul pour revue/saisie humaine. Une agrégation
  déterministe des crédits récurrents demande des règles métier validées, hors de ce lot.
- Une citation retrouvée dans l'OCR ne prouve ni la justesse de la valeur ni la qualité du scan.
  La vérification humaine du document original reste obligatoire ; pas de coordonnées de surlignage.
- Export partiel autorisé, clairement indiqué : les champs non confirmés sont exclus,
  les champs obligatoires manquants sont signalés. Aucune décision de crédit n'est produite.
- Les scores du modèle restent non calibrés. Le benchmark, l'API REST, Docker, l'authentification,
  la refonte des sessions pickle et les autres points de l'audit restent à traiter séparément.
