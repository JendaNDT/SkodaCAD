# Závazné vymezení rozsahu MT modulu ŠkodaCAD

**Rozhodnutí autora: 19. 10. 2026** – schválením návrhu etapy 12 včetně doporučení 1–10
([21-navrh-etapa-12.md](21-navrh-etapa-12.md)). Dokument má stejnou platnost jako
[závazné vymezení UT](04-zavazne-vymezeni-ut.md) a [PT](20-vymezeni-pt.md) a přednost před
staršími návrhy (`01-…`, `02-…`, `03-…`) všude, kde by požadovaly fyzikální výpočet
magnetické práškové zkoušky. Jde o změnu zadání pro Claude Code, nikoli o schválený NDT
postup.

## Co MT modul SMÍ vyhodnocovat

Jen **geometrii magnetické práškové zkoušky jhem**:

1. **Přiložení jha:** kam lze přiložit zjednodušený model jha – dosednutí pólů (mezera,
   přesah přes okraj), kolize nohou a těla s dílem, rozteč pólů, stěna mezi místem a pólem.
2. **Účinná oblast a orientační směr pole:** kterou část povrchu zasáhne oblast mezi póly
   a jakým orientačním směrem tam vede pole (přímka mezi póly sklopená do plochy).
3. **Směrové pokrytí:** zda místo pokryjí dva dostatečně odlišné směry magnetizace (všechny
   orientace vad) nebo jen jeden.
4. **Nanesení a prohlídka:** geometrická přístupnost pro nanesení detekčního prostředku
   a prohlídku (stejné kontroly jako PT).
5. **Materiál:** zda je materiál dílu podle tabulky feromagnetický.

**Doporučené názvy v GUI a protokolech:** „Přiložení jha a směry magnetizace pro MT“,
„Mapa geometrické proveditelnosti a směrového pokrytí MT“. Nepoužívat označení, která slibují
víc než geometrii (například „mapa magnetického pole“, „mapa intenzity pole“).

## Co MT modul NESMÍ tvrdit, že vyhodnocuje

- **Magnetické pole:** intenzitu ani skutečné rozložení pole v dílu, sycení, rozptylová pole,
  vliv mezery pod póly, tvaru dílu, tloušťky a materiálu na pole, střídavé ani stejnosměrné
  buzení, demagnetizaci.
- **Zařízení a postup:** zvedací sílu jha, dobu magnetizace, detekční prostředek (barevný,
  fluorescenční), osvětlení a UV-A (ISO 3059).
- **Detekovatelnost vad:** citlivost zkoušky, velikost nebo druh zjistitelné vady, způsobilost
  kontroly podle normy.

„Pokryto ve všech orientacích“ **není** důkaz, že je pole dost silné ani že by se na místě
vada našla. Směr pole je jen orientační – skutečné siločáry kolem otvorů, hran a v rozích se
nepočítají.

## Výsledky a jejich význam

- **Pokryto ve všech orientacích vad:** místo zasáhnou aspoň dva platné směry pole, které
  jsou od sebe aspoň dvojnásobek nejmenšího úhlu vady k poli (výchozí 2 × 30° = 60°),
  a nanesení i prohlídka geometricky jdou.
- **Jen část orientací nebo omezeně:** platné směry pole pokryjí jen část orientací vad, nebo
  nanesení či prohlídka jdou jen omezeně. Výstup uvede nepokryté orientace.
- **Nepokryto:** jho se v žádném směru nevejde tak, aby místo zasáhla účinná oblast, nebo
  nanesení či prohlídka geometricky nejdou. Nejde o důkaz, že jiné zařízení nebo postup není
  možný.
- **Nelze spolehlivě vyhodnotit:** rozhodující poloha je nejistá (pól přes hranu, tečně,
  nespočítaný průnik), směr pole v místě je nejasný nebo vstupy nestačí. Nevyplňovat
  fiktivním výsledkem.

Uvádět rozměry jha, rozteče, meze, materiál a jeho potvrzení, počet směrů, krok sítě, verzi
algoritmu a které hodnoty jsou zvolené pro výpočet (ne z normy). Procento pokryté plochy je jen
geometrický podíl plochy, ne pravděpodobnost nalezení vady.

## Povinné upozornění v GUI i v každém exportovaném protokolu

> ŠkodaCAD provádí pouze geometrické posouzení magnetické práškové zkoušky jhem: kam lze přiložit zjednodušený model jha, kterým orientačním směrem by mezi póly vedlo magnetické pole, zda lze místo pokrýt dvěma směry magnetizace a zda je místo přístupné pro nanesení detekčního prostředku a prohlídku. Nevyhodnocuje intenzitu ani skutečné rozložení magnetického pole, vliv materiálu, mezery pod póly a tvaru dílu na pole, citlivost zkoušky ani detekovatelnost vad. Výsledky nenahrazují kvalifikovaný NDT postup ani odborné posouzení.

## Požadavky na implementaci

1. Výpočet geometrie je oddělený od okna (`ndt/mt.py`), opakovatelný (pevná mřížka a směry,
   žádná náhoda) a testovaný na ručně spočítaných dílech.
2. O tom, že se jho vejde, rozhoduje přesná kontrola průniku s tělesem; paprsky jsou jen
   rychlé síto. Nejisté se nikdy nepočítá jako pokryté.
3. Upozornění výše je doslova v konstantě `skodacad.ndt.MT_DISCLAIMER`;
   `tests/test_ndt_scope.py` ho porovnává s tímto dokumentem.
4. U neferomagnetického materiálu se mapa nepočítá; nerez a neuvedený materiál jen po
   výslovném potvrzení uživatelem, které je vidět ve výstupu.
5. MT nikdy nemění geometrii dílu a AI není zdrojem čísel ani výsledků MT.
