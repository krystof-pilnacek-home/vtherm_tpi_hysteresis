# Hysteresis

## Objectif

Cette integration expose un controleur de chauffage et refroidissement a hysteresis simple a Versatile Thermostat via l'API d'algorithmes externes.

Elle est volontairement simple et sert de reference pour les developpeurs qui veulent brancher un autre algorithme dans VT.

## Parametres

### Ecart d'activation

En mode heat, le controleur demande une regulation active quand la temperature de la piece descend sous `target - hysteresis_on`.

En mode cool, le controleur demande une regulation active quand la temperature de la piece depasse `target + hysteresis_on`.

### Ecart de desactivation

En mode heat, le controleur demande une regulation inactive quand la temperature de la piece depasse `target + hysteresis_off`.

En mode cool, le controleur demande une regulation inactive quand la temperature de la piece descend sous `target - hysteresis_off`.

### Puissance active (`max_on_percent`)

La fraction de cycle envoyee au scheduler quand la regulation est active. La valeur `1.0` correspond a 100 % (defaut). Reduire cette valeur permet de plafonner la commande active envoyee au sous-jacent.

Plage : `0.0` – `1.0`. Defaut : `1.0`.

### Puissance inactive (`min_on_percent`)

La fraction de cycle envoyee au scheduler quand la regulation est inactive. La valeur `0.0` correspond a completement ferme (defaut). Definir une valeur non nulle permet de maintenir une vanne partiellement ouverte quand le relais est inactif.

Plage : `0.0` – `1.0`. Defaut : `0.0`.

## Attributs de suivi

Le controleur expose sa derniere decision dans `specific_states.hysteresis` :

- `is_active`
- `hvac_mode`
- `on_percent`
- `last_reason`
- `activation_threshold`
- `deactivation_threshold`
- `hysteresis_on`
- `hysteresis_off`
- `max_on_percent`
- `min_on_percent`

## Modes de configuration

Le config flow supporte deux portees :

- des valeurs globales appliquees quand aucune entree specifique au thermostat n'existe
- des reglages specifiques a une entite VT

## Persistance

L'etat du relais est conserve dans le stockage Home Assistant pour reprendre avec un etat coherent apres redemarrage.
