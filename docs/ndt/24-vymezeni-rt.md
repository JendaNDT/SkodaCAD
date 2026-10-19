# Závazné vymezení rozsahu RT modulu ŠkodaCAD

**Rozhodnutí autora: 19. 10. 2026** – schválením návrhu etapy 13 včetně doporučení 1–10
([23-navrh-etapa-13.md](23-navrh-etapa-13.md)). Dokument má stejnou platnost jako
[závazné vymezení UT](04-zavazne-vymezeni-ut.md), [PT](20-vymezeni-pt.md) a
[MT](22-vymezeni-mt.md) a přednost před staršími návrhy (`01-…`, `02-…`, `03-…`) všude, kde
by požadovaly fyzikální výpočet radiografické zkoušky. Jde o změnu zadání pro Claude Code,
nikoli o schválený NDT postup.

## Co RT modul SMÍ vyhodnocovat

Jen **geometrii projekce**:

1. **Umístění zdroje a detektoru:** kam lze umístit zjednodušený model zdroje (ohnisko, kužel
   svazku, tělo zdroje) a plochého detektoru – kolize s dílem, přiložení detektoru na plochu.
2. **Přímé paprsky:** kudy vedou přímé paprsky z ohniska dílem na detektor a jakou tloušťku
   materiálu prozařují.
3. **Promítnutí oblasti:** zda místo leží ve svazku, zda se promítne na aktivní plochu
   detektoru a zda se jeho obraz překrývá s jinou částí oblasti.
4. **Geometrické veličiny:** geometrické zvětšení a geometrická neostrost z rozměru ohniska.
5. **Geometrická pravidla normy:** poměr prozařovaných tlouštěk a nejmenší vzdálenost zdroje
   od předmětu (ISO 17636-1, ISO 5579; vzorec pro film).

**Doporučené názvy v GUI a protokolech:**

- „Geometrie projekce RT“,
- „Mapa geometrického promítnutí oblasti RT“,
- „Náhled prozařované tloušťky – není radiografický snímek“.

Nepoužívat označení, která slibují víc než geometrii (například „simulovaný radiogram“,
„simulovaný snímek“, „mapa dávky“, „mapa zčernání“).

## Co RT modul NESMÍ tvrdit, že vyhodnocuje

- **Záření a bezpečnost:** dávku, dávkový příkon, radiační ochranu, kontrolované pásmo, stínění
  ani bezpečné vzdálenosti. **Geometrie projekce nenahrazuje posouzení radiační ochrany.**
- **Expozici:** napětí, proud, dobu expozice, aktivitu zdroje, energii záření ani to, zda zdroj
  danou tloušťku vůbec prozáří.
- **Obraz:** rozptýlené záření, zesilující fólie, kontrast, optickou hustotu (zčernání), šum,
  vlastní neostrost a rozlišení detektoru (ISO 17636-2) ani třídu kvality obrazu nad rámec
  geometrických pravidel.
- **Detekovatelnost vad:** viditelnost indikátorů kvality obrazu (IQI, ISO 19232), citlivost
  zkoušky, velikost nebo druh zjistitelné vady ani způsobilost kontroly podle normy.

„Promítne se“ **není** důkaz, že by vada byla na snímku vidět. Náhled prozařované tloušťky je
geometrický obraz délek v materiálu, **ne radiografický snímek**.

## Výsledky a jejich význam

- **Promítne se – geometrická pravidla platí:** místo leží ve svazku, promítne se na aktivní
  plochu detektoru, poměr prozařované tloušťky k tloušťce na středu svazku je v mezi třídy
  (1,1 pro B, 1,2 pro A), zdroj je aspoň v nejmenší vzdálenosti podle normy a obraz se
  nepřekrývá s jinou částí oblasti.
- **Promítne se jen omezeně:** místo se promítne, ale poměr tloušťky nebo vzdálenost zdroje
  nevyhoví, nebo se obraz překrývá. Výstup uvede proč.
- **Nepromítne se:** místo je mimo svazek nebo mimo detektor, nebo zdroj či detektor naráží
  do dílu. Nejde o důkaz, že jiná projekce není možná.
- **Nelze spolehlivě vyhodnotit:** paprsek vede přes hranu nebo tečně, poměr tloušťky nejde
  určit (střední paprsek nemíří do plného materiálu a jmenovitá tloušťka není zadaná) nebo
  vstupy nestačí. Nevyplňovat fiktivním výsledkem.

Uvádět rozměr ohniska, kužel svazku, tělo zdroje, rozměry detektoru, třídu, vzdálenosti
$f$ a $b$, nejmenší vzdálenost, neostrost, zvětšení, tloušťku na středu svazku, materiál,
krok sítě, verzi algoritmu a které hodnoty jsou zvolené pro výpočet (ne z normy). Procento
promítnuté plochy nebo objemu je jen geometrický podíl, ne pravděpodobnost nalezení vady.

## Povinné upozornění v GUI i v každém exportovaném protokolu

> ŠkodaCAD provádí pouze geometrické posouzení radiografické zkoušky: kam lze umístit zjednodušený model zdroje a detektoru, kudy vedou přímé paprsky z ohniska dílem, jakou tloušťku materiálu prozařují, kam se oblast promítne na detektor a jaké je geometrické zvětšení a geometrická neostrost z rozměru ohniska. Nevyhodnocuje dávku ani radiační ochranu, expoziční parametry, rozptýlené záření, kontrast, zčernání ani kvalitu obrazu, viditelnost indikátorů kvality obrazu, citlivost zkoušky ani detekovatelnost vad. Výsledky nenahrazují kvalifikovaný NDT postup, odborné posouzení ani posouzení radiační ochrany.

## Požadavky na implementaci

1. Výpočet geometrie je oddělený od okna (`ndt/rt.py`), opakovatelný (pevná síť, žádná
   náhoda) a testovaný na ručně spočítaných dílech.
2. Prozařovaná tloušťka sčítá všechny úseky v materiálu na spojnici zdroj–detektor;
   nejistý paprsek (přes hranu, tečně) se nikdy nepočítá jako promítnutý.
3. O kolizi zdroje a detektoru rozhoduje přesná kontrola průniku s tělesem.
4. Upozornění výše je doslova v konstantě `skodacad.ndt.RT_DISCLAIMER`;
   `tests/test_ndt_scope.py` ho porovnává s tímto dokumentem.
5. RT nikdy nemění geometrii dílu a AI není zdrojem čísel ani výsledků RT; neradí
   k radiační ochraně ani expozici.
