# Versatile Thermostat Hysteresis

[Read the English version](README.md)

<p align="center">
  <strong>Integration externe de reference pour un algorithme Versatile Thermostat</strong>
</p>

Ce depot fournit un algorithme de chauffage et refroidissement a hysteresis simple, empaquete comme integration externe pour Versatile Thermostat.

Les plugins d'algorithmes ont pour vocation de remplacer le TPI embarqué. Ils sont donc limités aux sous-jacents over_valve, over_valve, et over_climate avec controle de la valve.

## Ce que montre ce depot

- L'enregistrement d'un algorithme proportionnel externe via `vtherm_api`
- Un packaging Home Assistant complet avec `manifest.json`, `config_flow.py`, traductions et metadonnees HACS
- Des configurations globales et par thermostat
- Un handler minimal qui implemente tout le contrat `InterfacePropAlgorithmHandler`
- La persistance de l'etat de l'algorithme avec le stockage Home Assistant

## Loi de regulation

L'algorithme applique une hysteresis classique selon le mode HVAC actif :

- en mode heat, la regulation s'active quand `current_temperature <= target_temperature - hysteresis_on`
- en mode heat, la regulation se desactive quand `current_temperature >= target_temperature + hysteresis_off`
- en mode cool, la regulation s'active quand `current_temperature >= target_temperature + hysteresis_on`
- en mode cool, la regulation se desactive quand `current_temperature <= target_temperature - hysteresis_off`
- dans la bande, l'etat precedent est conserve

Le resultat est ensuite transmis au scheduler VT sous la forme `on_percent = max_on_percent` (regulation active) ou `on_percent = min_on_percent` (regulation inactive). Les deux valeurs sont configurables ; les valeurs par defaut sont respectivement `1.0` et `0.0`.

## Installation

### Via HACS

[![Ouvrir votre instance Home Assistant et ouvrir un depot dans le Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=KipK&repository=vtherm_hysteresis&category=Integration)

1. Ajouter le depot dans HACS comme integration.
2. Installer le depot.
3. Redemarrer Home Assistant.
4. Ajouter l'integration `Versatile Thermostat Hysteresis` depuis le menu Paramètres / Appareils et Services / Ajouter une intégration.
5. Selectionner l'algorithme Hysteresis dans les parametres du sous-jacent du VTherm dans la configuration Versatile Thermostat.
6. Choisir une configuration globale ou une configuration specifique a un thermostat dabs la page de l'integration vtherm-hysteresis

### Installation manuelle

1. Copier `custom_components/vtherm_hysteresis` dans le dossier `custom_components` de Home Assistant.
2. Redemarrer Home Assistant.
3. Ajouter l'integration depuis l'interface.

## Structure du depot

- `custom_components/vtherm_hysteresis/` : code de l'integration Home Assistant
- `documentation/en/` : documentation utilisateur et technique en anglais
- `documentation/fr/` : documentation utilisateur et technique en francais
- `.github/workflows/` : exemples de validation, tests et release

## Documentation

- [Documentation utilisateur](documentation/fr/vtherm_hysteresis.md)
- [Documentation technique](documentation/fr/technical_doc.md)

## Licence

Le proprietaire du depot doit definir les termes de licence appliques a ce scaffold.
