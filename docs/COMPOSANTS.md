# Composants tiers et licences

Déclaration exigée par FLX-CDC-001 §9 : composants libres utilisés et leurs licences. Toutes autorisent une exploitation commerciale ; aucune n'impose de publier le code de FLUXAA Port.

| Composant | Rôle | Licence |
|---|---|---|
| Django 5.2 | cadriciel web | BSD-3-Clause |
| Django REST framework | API publique | BSD-3-Clause |
| drf-spectacular (+ sidecar) | schéma OpenAPI, documentation de l'API | BSD-3-Clause |
| psycopg 3 | pilote PostgreSQL | LGPL-3.0 (bibliothèque utilisée sans modification, liée dynamiquement) |
| cryptography | chiffrement du domaine N4 et des secrets TOTP | Apache-2.0 ou BSD-3-Clause |
| pyotp | double authentification (TOTP) | MIT |
| qrcode | QR codes (2FA, liens d'accès, code de vérification des actes d'autorisation) | BSD |
| gunicorn | serveur d'application | MIT |
| whitenoise | service des fichiers statiques | MIT |
| anthropic | client de l'assistance IA optionnelle | Apache-2.0 |
| pyais | décodage des trames AIS (NMEA) d'un récepteur local, commande `ais_listen` | MIT |
| websockets | abonnement au flux aisstream.io, commande `ais_listen` | BSD-3-Clause |
| HTMX 2.0.11 (`static/vendor`) | rafraîchissement partiel des écrans | Zero-Clause BSD (0BSD, fichier de licence joint) |
| Poppins, IBM Plex Mono (`static/fonts`) | polices de l'interface, auto-hébergées | SIL Open Font License 1.1 (fichiers de licence joints) |
| PostgreSQL 16 | base de données (image Docker) | PostgreSQL License |
| Caddy | frontal HTTPS (image Docker) | Apache-2.0 |
| pytest, pytest-django | tests (développement uniquement) | MIT, BSD-3-Clause |

Aucune police, bibliothèque ni ressource n'est chargée depuis un service tiers à l'exécution : l'interface fonctionne sans accès à Internet côté poste client, ce qui est aussi la condition du mode hors ligne.
