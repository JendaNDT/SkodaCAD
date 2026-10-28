# STEP v metrech

Autor zadal doplnění metrů a ověření na Macu i Windows. Import stále přijímá
pouze jeden platný uzavřený díl, nyní v milimetrech, metrech nebo palcích.
Jádro převede souřadnice do milimetrů a aplikace ukáže zdrojové jednotky česky.
Formát modelu zůstává verze 24; zdroj se ukládá v původní podobě. Neznámé nebo
nejednoznačné jednotky se neodhadují.

## Vzorky

* Syntetický kvádr `07-metry.step` má zdroj v metrech a ověřované rozměry
  10 × 13 × 17 mm a objem 2 210 mm³. Je přiložen do repozitáře spolu s generátorem.
* [Veřejný vzorek z Onshape](https://gist.github.com/MattFerraro/76adbd74042696895e7f9b0f87313a88)
  není součástí repozitáře; přenosový test jej stahuje z konkrétní verze a před
  použitím kontroluje SHA-256. Hlavička a souřadnice STEP používají metry.
  Autor jej nazývá krychlí 1 cm, ale souřadnice v souboru udávají rozměry
  0,02 × 0,02 × 0,02 m. Proto test ověřuje 20 × 20 × 20 mm a objem 8 000 mm³,
  nikoli rozměr z názvu. Není k dispozici nezávislý výkres.

Přenosový běh na obou systémech vytváří model, otevře jej na druhém systému,
porovná původní bajty, rozměry, objem a počet těles, a zkontroluje export a
opětovný import. Dostupnost veřejného vzorku je pro tento běh nutná; test
odmítne změněné bajty. Výsledky jednotlivých běhů sleduj v příslušném PR.
