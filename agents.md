# LOCKON - Notes pour agents

Ce fichier capitalise les infos apprises pendant le developpement pour eviter de
repeter les memes erreurs.

## Materiel detecte

- La carte utilisee est un Arduino Nano sur `COM4`.
- Le televersement fonctionne avec le profil :

```powershell
arduino-cli upload -p COM4 --fqbn arduino:avr:nano:cpu=atmega328old esp32_prog
```

- Le profil Nano standard `arduino:avr:nano` peut echouer avec une erreur de
  synchronisation du type `not in sync`.
- Le laser est un module 5V / 5 mW avec deux fils :
  - rouge : alimentation positive
  - noir : GND
- En l'absence de transistor, le branchement de test utilise :
  - rouge laser -> `D7`
  - noir laser -> `GND`

## Reflexes avant diagnostic

- Quand une modification touche le sketch Arduino, compiler puis televerser le
  sketch. Ne pas demander a l'utilisateur de le faire si l'outil est disponible.
- Apres un televersement, la GUI doit reconnecter le port serie, car l'upload
  reprend `COM4`.
- Si une broche ne change pas au voltmetre, verifier d'abord :
  - que le sketch modifie a bien ete televerse
  - que la GUI affiche une reponse serie Arduino, pas `Simulation: ...`
  - que la commande de test force l'etat sans dependre de la camera
- Pour debugger le laser, utiliser la case `Laser force`, qui envoie `LASER 1`
  meme sans detection de cible.
- Le sketch fait aussi suivre l'etat laser sur la LED integree Arduino :
  - `LASER 1` -> LED ON
  - `LASER 0` -> LED OFF

## Securite laser

- Meme a 5 mW, ne jamais orienter le laser vers les yeux ou un visage.
- Tester contre une surface mate non reflechissante.
- Le branchement direct sur `D7` est acceptable pour debug court si le courant
  du module reste faible, mais un transistor ou MOSFET reste preferable pour un
  montage durable.
