# ŠkodaCAD

Osobní parametrický 3D CAD postavený na jádře **Open CASCADE** (přes knihovnu
[build123d](https://github.com/gumyr/build123d)). Vyvíjený vibecodingem v Claude Code.

**Stav:** jádro + první okno pro Windows. Díl se popíše v čitelném souboru JSON
(parametry + seznam prvků), jádro z něj postaví přesné těleso, spočítá objem a hmotnost
a uloží exporty pro jiné CAD programy i 3D tisk. Okno ukáže díl ve 3D a dovolí měnit
parametry.

## Aplikace pro Windows

1. Stáhni **[SkodaCAD-windows.zip](https://github.com/JendaNDT/SkodaCAD/releases/latest/download/SkodaCAD-windows.zip)**
   (stránka [Releases](https://github.com/JendaNDT/SkodaCAD/releases), vydání „nejnovejsi“).
2. Rozbal ho (pravé tlačítko → *Extrahovat vše*).
3. Ve složce `SkodaCAD` spusť **`SkodaCAD.exe`**.
4. Windows může napsat *„Systém Windows ochránil váš počítač“* – aplikace není digitálně
   podepsaná. Klikni na *Další informace* → *Přesto spustit*.

Aplikace sestavuje GitHub automaticky po každé změně ve větvi `main`
(postup [.github/workflows/windows.yml](.github/workflows/windows.yml)).

## Aplikace pro macOS (Apple Silicon) – zkušební

Pro Mac s čipem M1–M4 a macOS 13 nebo novějším. **Zatím neověřeno na skutečném Macu** –
sestavuje a testuje ji GitHub na svém Macu, ruční zkouška na MacBooku Air M4 teprve přijde
(postup a seznam zkoušek v [docs/ndt/08-navrh-macos.md](docs/ndt/08-navrh-macos.md)).

1. Stáhni **[SkodaCAD-macos.zip](https://github.com/JendaNDT/SkodaCAD/releases/download/nejnovejsi-mac/SkodaCAD-macos.zip)**
   (vydání „nejnovejsi-mac“, označené jako předběžné).
2. Rozbal ho (dvojklik ve Finderu) a **SkodaCAD** přetáhni do složky *Aplikace*.
3. Při prvním spuštění macOS napíše, že aplikaci nejde ověřit – není podepsaná certifikátem
   Apple ani notarizovaná. Otevři *Nastavení systému → Soukromí a zabezpečení*, sjeď dolů
   a u SkodaCAD klikni na **Přesto otevřít** (od macOS 15 už nefunguje pravý klik → Otevřít).
   Kdyby to nešlo, v Terminálu: `xattr -dr com.apple.quarantine /Applications/SkodaCAD.app`.
4. Ovládání je stejné jako ve Windows, jen místo `Ctrl` používej **`Cmd` (⌘)**: `Cmd`+klik
   přidá plochu do výběru, `Cmd`+`Z` je Zpět. Na trackpadu posouváš pohled **`Shift` + tažením**,
   zoom dvěma prsty.
5. Nastavení, log (`skodacad.log`) a výchozí místo pro modely je složka **`SkodaCAD`** ve tvé
   domovské složce – stejně jako ve Windows.
6. Kdyby 3D nešlo spustit s grafickou kartou (virtuál, vzdálená plocha), aplikace kreslí
   softwarově – pomaleji, ale funguje. Kontrolu celé aplikace spustíš v Terminálu:
   `/Applications/SkodaCAD.app/Contents/MacOS/SkodaCAD --self-test ~/SkodaCAD/self-test.txt`
   (výsledek je v souboru `self-test.txt`, na konci „VÝSLEDEK: OK“).

AI asistent posílá model společnosti Anthropic **jen** po tvém dotazu v panelu *AI asistent*
a jen s vloženým API klíčem. Bez klíče (např. při prezentaci) z aplikace nic neodchází.

Mac sestavuje samostatný postup [.github/workflows/macos.yml](.github/workflows/macos.yml);
sestavení pro Windows se tím nemění.

### Ovládání

| Akce | Jak |
|---|---|
| Otáčení | levé tlačítko + táhnout |
| Posun | prostřední nebo pravé tlačítko + táhnout, nebo `Shift` + levé tlačítko + táhnout |
| Zoom | kolečko (ke kurzoru) |
| Výběr plochy / hrany | klik – popis (typ, obsah, průměr…) se ukáže dole ve stavovém řádku a **změří se** (panel *Měření* vpravo) |
| Více hran / ploch | `Ctrl`+klik (nebo `Shift`+klik) přidá nebo ubere – u dvou věcí se změří vzdálenost a úhel |
| Co s výběrem | pravé tlačítko (bez tažení): Zaoblit, Srazit, Skica na ploše, Skořepina… |
| Zrušit výběr | `Esc` |
| Celý díl | dvojklik nebo `F` |
| Pohledy | `0` izometrie, `1` zepředu, `3` zprava, `7` shora (s `Ctrl` opačná strana) |
| Změna parametru | přepiš hodnotu vlevo a stiskni Enter (číslo, `12,5` i výraz `D/2 + 5`) |
| Přepočítat | `F5` (pomalý přepočet jde zastavit tlačítkem dole vpravo) |

Neplatná hodnota parametru se zbarví červeně a model zůstane beze změny. Když některý
prvek nejde spočítat, ve stromu prvků se ukáže ✕ a česky proč.

**Přepočet na pozadí:** model se přepočítává v samostatném pomocném procesu, takže okno
nikdy nezamrzne – ani u pomalých prvků, jako je vymodelovaný závit. Trvá-li přepočet déle,
strom prvků zešedne (⏳), vlastnosti ukazují hodnoty z minulého stavu a dole běží
„Přepočítávám… N s“ s tlačítkem **Zastavit přepočet**. Zastavení vrátí model do posledního
spočítaného stavu (*Znovu* změnu vrátí a zkusí to znovu). Když během výpočtu změníš další
hodnotu, rozpočítaný přepočet se zahodí a hned se počítá ten nejnovější. Export a prvky
z výběru ve 3D počkají, až bude model spočítaný.

### Vlastní díl od nuly

1. **Soubor → Nový**, vlevo nahoře vyplň název a materiál.
2. **Přidat prvek → Skica**: na rovině XY vznikne obdélník 40 × 30. Vpravo v panelu
   *Úprava prvku* změň rozměry, přidej další tvary (*Přidat tvar*) – otvor je tvar
   s režimem *odečíst*.
3. **Přidat prvek → Vysunutí**: ze skici vznikne těleso, vpravo nastav vzdálenost.
4. Díra nebo výstupek: další **Skica** se sama položí na horní plochu dílu (kružnice Ø10),
   pak **Vysunutí** s operací *odebrat materiál* a případně *Řez skrz celý díl*.
5. **Zaoblení / Sražení kliknutím**: klikni ve 3D na hranu (další s `Ctrl`), pravé tlačítko →
   *Zaoblit vybrané hrany*. Program si hranu nezapamatuje číslem, ale významem („hrana mezi
   přední a pravou plochou“, „kružnice R3 na horní ploše“) – výběr tak platí i po změně
   rozměrů. Hrany vybraného zaoblení svítí ve 3D růžově; další přidáš přes pravé tlačítko →
   *Přidat vybrané hrany do…*. Hrany jde vybrat i ručně ve formuláři (na ploše, rovnoběžné…).
6. **Skica na ploše kliknutím**: klikni na plochu (i dno kapsy, schod, **šikmou** plochu
   sražení nebo **válec**), pravé tlačítko → *Skica na vybrané ploše* – kružnice Ø10 vznikne
   v místě kliknutí. Na zakřivené ploše (válec, kužel, koule) leží skica na rovině, která se
   plochy v místě kliknutí dotýká (**tečná rovina**) – tak vznikne třeba drážka pro pero nebo
   plocha na hřídeli. U šikmé a zakřivené plochy je počátek skici v místě kliknutí a osa X
   míří podél osy válce (jinak vodorovně po ploše).
7. **Díra podle tabulek kliknutím**: klikni na plochu (i šikmou nebo válcovou – příčná díra do
   hřídele) tam, kde má díra být, pravé
   tlačítko → *Díra na vybrané ploše*. Vpravo vyber druh (závitová, průchozí, zahloubení,
   3D tisk) a velikost M2–M30. Další díru stejného prvku přidáš kliknutím na plochu a
   *Přidat díru v místě kliknutí*. Viz [Díry](#díry-podle-strojnických-tabulek).
8. **Skicář (obrys z čar s vazbami)**: *Přidat prvek → Skica – nakreslit obrys…* (nebo u tvaru
   „Obrys z čar“ tlačítko *Upravit ve skicáři…*). Viz [Skicář](#skicář) níže.
9. **+ Parametr** vytvoří pojmenovaný rozměr; jeho název pak můžeš napsat do kteréhokoli
   pole (např. `sirka` nebo `sirka/2 - 5`).

### Skicář

1. Nástroj **Úsečka** (`L`): klikej body obrysu. Klik na existující bod čáry napojí, klik do
   počátku (zelený kroužek) obrys k počátku připne. Skoro vodorovná/svislá čára dostane vazbu
   sama. Konec řetězu: `Esc` nebo pravé tlačítko. **Oblouk** (`A`): začátek, konec a bod,
   kudy má vést. **Kružnice** (`R`): střed a bod na obvodu – střed na existujícím bodě (třeba
   středu oblouku) ji udělá soustřednou, obvod na existujícím bodě ho na kružnici připne.
2. Nástroj **Výběr** (`S`): klikni na čáru nebo bod (`Ctrl` = přidat další) a přidej vazbu
   tlačítkem vlevo – *Vodorovně, Svisle, Rovnoběžně, Kolmo, Tečně, Stejně velké, Na bodě/čáře,
   Uprostřed, Soustředně, Souměrně, Pevný bod*. Tažením obvodu kružnice měníš její velikost.
3. **Kóta…** (`D`): úsečka = délka, oblouk = poloměr, kružnice = průměr (Ø), dva body nebo
   bod a čára = vzdálenost, dvě úsečky = úhel. Hodnota může být číslo i výraz s parametrem
   (`sirka`, `D/2`) – obrys se pak mění s parametrem.
4. Dole vpravo je vidět, kolik rozměrů **zbývá určit** (modrý obrys jde ještě táhnout myší),
   nebo **✓ plně určeno** (černý obrys). Vazby, které si odporují, jsou **červeně** – smaž je
   (*Smazat vazbu*) nebo dej *Zpět* (`Ctrl+Z`).
5. **Pomocná čára** (`G`) se účastní vazeb, ale není součástí obrysu (např. osa souměrnosti).
6. **Hotovo** uloží obrys do modelu (jako jeden krok pro Zpět v hlavním okně). Obrys pak vysuň
   nebo orotuj; s režimem *odečíst* je z něj otvor.

**Díry a vazby mezi tvary:** jeden obrys smí mít víc uzavřených smyček. Smyčka (nebo kružnice)
uvnitř jiné je **díra**, smyčka uvnitř díry je zase materiál. Díky tomu jde díru navázat na
obrys: *Soustředně* s obloukem, *Tečně* (kružnice se dotkne čáry, oblouku nebo jiné
kružnice), *Souměrně* podle osy, *Stejně velké* (i kružnice s obloukem), *Na bodě/čáře* (bod
na obvodu) nebo kótou vzdálenosti středu od hrany. Smyčky se nesmí křížit – skicář to hned
hlásí červeně.

Ukázky: *Soubor → Otevřít ukázku → paka* – změň `L` nebo `R` a obrys páky se přepočítá.
*prilozka* – příložka s pěti otvory navázanými na obrys; změň `L` nebo `B` a otvory jdou s ní.

**Promítnutí hran dílu:** když skica leží na dílu (třeba na horní ploše), skicář ukáže hrany
dílu pod ní šedě. Nástroj **Promítnout** (`U`) – klik na šedou hranu ji převezme jako pevnou
**fialovou** čáru (úsečku, kružnici díry, oblouk zaoblení). K ní jde dát vazby a kóty (bod na
hraně, vzdálenost od hrany, soustředně s dírou, tečně, napojení na roh – fialové body se
přichytávají). **Převzít do obrysu** (`W`) z vybraných fialových hran udělá skutečný obrys
navázaný na díl (třeba výstupek přesně podle plochy). Když se díl změní (parametr, posunutá
díra), skica jde s ním. Promítnout jde úsečka a kružnice či oblouk rovnoběžné se skicou.

Ukázka *sloupky* – deska se 4 dírami M3 a distančními sloupky pro plošný spoj: sloupky jsou
soustředné s promítnutými dírami; změň rozteč `rx` nebo `ry` a sloupky jdou s dírami.

### Díry podle strojnických tabulek

Ukázka: *Soubor → Otevřít ukázku → deska*. Závit je ve výchozím stavu jen **vyznačený**
(jako v běžných CAD): díra má průměr vrtáku pod závit a u prvku je zapsáno „M8 závit,
hl. 12“. Do STEP/STL jde jen díra, ne závit.

**Vymodelovaný závit pro 3D tisk:** u závitové díry zaškrtni *Vymodelovat závit (3D tisk)*.
Vznikne skutečná šroubovice se základním profilem ISO 68-1 (úhel 60°, malý průměr
D1 = D − 1,0825·P) zvětšená o *vůli pro tisk* (výchozí 0,2 mm na průměru – když šroub
nejde zašroubovat, zvětši ji). Díra má ploché dno, závit vede po celé hloubce. Závit je
složený z drobných plošek (nejvýš 0,05 mm od přesného tvaru – pod rozlišením tiskárny),
protože s hladkou šroubovicí jádro OCCT neumí spolehlivě řezat. Přepočet trvá pár sekund
(M3 nejdéle – nejvíc závitů); pro tisk doporučeno od M6.

| Druh (`kind`) | Co vznikne | Tabulka | Velikosti |
|---|---|---|---|
| `tapped` – závitová | vrták pod závit, slepá díra končí špičkou vrtáku 118° | ISO 2306 (vrták ≈ d − stoupání ISO 261) | M2–M30 |
| `clearance` – průchozí | díra pro šroub, řada jemná/střední/hrubá | ISO 273 | M2–M30 |
| `counterbore` – válcové zahloubení | pro imbus s válcovou hlavou ISO 4762 | DIN 974-1 | M3–M24 |
| `countersink` – kuželové 90° | pro zápustnou hlavu ISO 10642 | DIN 74 tvar F (Würth) | M3–M12 |
| `insert` – 3D tisk | díra pro zálisnou (zatavovací) matici, ploché dno | doporučení ruthex/Accu | M2–M6 |
| `plastic` – 3D tisk | šroub přímo do plastu, ploché dno | vrták pod závit (norma není) | M2–M30 |

Příklad: M6 → vrták Ø5,0; průchozí Ø6,4 / 6,6 / 7,0; zahloubení Ø11 × 6,4; kuželové Ø13,7.
U 3D tisku se zdroje liší o desetiny mm a záleží na tiskárně – vytiskni zkušební kousek
a případně zadej *Vlastní průměr*. Tabulky a zdroje jsou v
[src/skodacad/holes.py](src/skodacad/holes.py) (normy samotné jsou placené; hodnoty jsou
ověřené porovnáním více zdrojů – u průchozí díry M16 jeden zdroj uvádí 18 místo 17,5).

### Měření

Ukázka: *Soubor → Otevřít ukázku → trubka* (trubka s korozní jamkou a uloženými měřeními
tloušťky stěny). Měří se samo – stačí kliknout, výsledky jsou vpravo v panelu **Měření**.

| Vybráno | Co se změří |
|---|---|
| jedna plocha | **tloušťka stěny v místě kliknutí** (jako ultrazvukový tloušťkoměr: kolmo do materiálu až k protější ploše), u válce a koule průměr, obsah plochy |
| jedna hrana | délka, u kružnice průměr, u oblouku poloměr |
| dvě rovnoběžné plochy | jejich kolmá vzdálenost (tloušťka desky, šířka drážky) |
| dvě díry (válce nebo jejich hrany) | **rozteč os**, u hran i vzdálenost středů |
| díra a plocha | vzdálenost osy díry od plochy (je-li s ní rovnoběžná) |
| dvě plochy / hrany pod úhlem | úhel mezi nimi (sražení 45°, šikmá hrana a plocha …) |
| vždy u dvou věcí | nejkratší vzdálenost |

* Vybraný řádek se ve 3D ukáže jako **zelená čára** s hodnotou (odkud kam se měřilo).
  Hlavní hodnota dvou věcí je i dole ve stavovém řádku.
* **Uložit do modelu** (nebo pravé tlačítko → *Uložit měření do modelu*) uloží vybraný řádek
  do souboru. Uložené měření se **přepočítá při každé změně** modelu – změníš tloušťku
  stěny a hned vidíš novou zbytkovou tloušťku. Přejmenovat (i dvojklikem) a smazat jde pod
  seznamem *Uložená měření*, Zpět/Znovu funguje i tady.
* Uložené měření si plochy a hrany pamatuje **významem**, ne číslem: plochu bodem, směrem,
  druhem a poloměrem (díra se najde, i když se posune), hranu jako zaoblení. Když plocha
  zmizí, měření se zbarví červeně a napíše proč.
* Měří se vždy jedna nebo dvě věci; u víc vybraných se nic nezměří.

### Mapa tloušťky stěny (NDT)

Ukázka: *Soubor → Otevřít ukázku → trubka* a pak **Model → Mapa tloušťky stěny** (klávesa
`M` nebo tlačítko v horní liště). Celý povrch dílu se obarví podle tloušťky stěny:

| Barva | Význam |
|---|---|
| červená → žlutá → zelená → modrá | od nejtenčího místa po horní mez škály (výchozí = nejčastější tloušťka dílu, tedy jmenovitá stěna); tlustší místa jsou modrá |
| fialová | pod **minimální dovolenou tloušťkou** (zadáš ji v panelu) |
| šedá | tloušťku tu nejde jednoznačně změřit – okraj jamky, drážky nebo ostrá hrana |

* Tloušťka se měří jako ultrazvukovým tloušťkoměrem: v hustě rozmístěných bodech po celém
  povrchu kolmo do materiálu až k protější stěně. Platí jen stěna, která k paprsku stojí
  zhruba kolmo („koncové echo“) – jinak je místo šedé, ne s nesmyslně malým číslem.
* Nejtenčí místo má ve 3D fialovou značku s hodnotou. Klikem kamkoli na mapu změříš přesnou
  tloušťku v tom bodě (stavový řádek a panel *Měření*).
* Panel **Mapa tloušťky** (záložka vedle *Měření*): minimální tloušťka, krok bodů (prázdné
  = automaticky, asi 30 000 bodů) a horní mez škály. Nastavení se **ukládá do modelu**
  (Zpět/Znovu funguje). Pod nimi legenda a souhrn: nejtenčí místo se souřadnicemi,
  nejčastější tloušťka, kolik procent povrchu je pod minimem.
* Zapnutá mapa se **přepočítá s modelem** – změníš tloušťku stěny nebo hloubku jamky a mapa
  se na pozadí spočítá znovu (okno nezamrzne, výpočet trvá pár sekund).
* **Export CSV…** uloží body mapy (x, y, z, tloušťka, pod minimem) pro Excel – se
  středníkem a desetinnou čárkou, jak je zvyklý český Excel. Hodí se k porovnání
  s naměřenými hodnotami z ultrazvuku.
* Pod mapou je díl jen v obrysech hran, aby byly vidět barvy.

### Řez modelem

**Model → Řez modelem** (klávesa `R` nebo tlačítko v horní liště) díl přesně rozřízne rovinou
a ukáže jednu polovinu – vidíš dovnitř (stěny, díry, závity, jamky). Model se přitom
**nemění**, řez je jen pohled a do souboru se neukládá.

* Panel **Řez** (záložka vedle *Měření* a *Mapy tloušťky*):
  * **Rovina** – kolmo na osu X, Y nebo Z (výchozí podélně kolmo na Y, uprostřed dílu),
    nebo **rovnoběžně s vybranou plochou**: klikni na rovinnou plochu (i šikmou) a zvol tuto
    možnost (nebo pravé tlačítko → *Řez rovnoběžně s vybranou plochou*) – posuvník pak
    posouvá řez do hloubky pod plochu.
  * **Poloha** posuvníkem (řez se spočítá po puštění) nebo přesně číslem v mm.
  * **Otočit stranu** – zbude druhá polovina.
  * **Export DXF/SVG…** – obrys plochy řezu jako 2D výkres: DXF pro jiné CADy či laser,
    SVG (vyplněný řez) jako obrázek do protokolu.
* Plochy řezu jsou **cihlové** a pod panelem je jejich obsah (průřez dílu v té rovině).
* Na rozříznutý díl jde klikat jako jindy: měření (i na ploše řezu – vzdálenosti, tloušťka),
  zaoblení, sražení, skica a díra na ploše. Prvek se přidá na celý díl. Co vzniklo jen řezem
  (plocha řezu), na díl použít ani uložit nejde – okno to česky řekne.
* Se zapnutou **mapou tloušťky** zůstane barevná i rozříznutá – mapa se ořízne přesně
  rovinou řezu a uvidíš i vnitřek (třeba korozi uvnitř trubky).

### NDT studie (předběžné posouzení)

Začátek modulu NDT podle plánu v [docs/ndt/](docs/ndt/) (etapy 00 a 01). **NDT studie** je
záznam v modelu: metoda (**UT, PT, MT, RT**), **kontrolovaná oblast** (plochy dílu), poznámka
a ověření. Zatím se nic nepočítá (paprsek, sonda a pokrytí přijdou v dalších etapách) – studie
ale hlídá, jestli ještě platí pro aktuální díl. Díl samotný nikdy nemění.

> Předběžné posouzení proveditelnosti NDT. Nenahrazuje kvalifikovaný postup, normové
> vyhodnocení ani reálnou kontrolu.

**UT je závazně vymezené** ([docs/ndt/04-zavazne-vymezeni-ut.md](docs/ndt/04-zavazne-vymezeni-ut.md),
má přednost před starším plánem): program posuzuje jen **přístupnost UT sondy** (jde přiložit
a posouvat bez kolize?) a **geometrické pokrytí** kontrolované oblasti – nikdy prozvučitelnost
materiálu (útlum, struktura, akustická vazba) ani detekovatelnost vad. V okně (skupina
*Přístupnost UT sondy*) i ve výpisech příkazové řádky je povinné upozornění:

> ŠkodaCAD provádí pouze geometrické posouzení přístupnosti ultrazvukové sondy a pokrytí
> kontrolované oblasti na základě zjednodušeného modelu ultrazvukového svazku. Nevyhodnocuje
> fyzikální prozvučitelnost materiálu ani detekovatelnost vad. Výsledky nenahrazují
> kvalifikovaný NDT postup ani odborné posouzení.

* **Referenční díly:** *Soubor → Otevřít ukázku → NDT – referenční díly* – deska, blok
  s kapsou, deska se žebrem, otvor, trubka, tupý svar V, koutový svar a obtížný přístup.
  Každý má ukázkovou studii; ručně spočítané očekávané výsledky (půlkroky, mezní úhly, vůle
  sondy) jsou v [docs/ndt/05-referencni-dily.md](docs/ndt/05-referencni-dily.md).
* **Panel NDT** (záložka vedle *Měření*, nabídka *NDT*): vyber ve 3D plochy kontrolované
  oblasti (Ctrl+klik přidá další), zvol metodu a **Nová NDT studie z výběru** (i pravým
  tlačítkem → *Z výběru ve 3D*). Klik na studii v seznamu oblast ve 3D zvýrazní.
* Stav studie se počítá při každé změně modelu:

| Stav | Kdy |
|---|---|
| ✓ **platná** | díl je stejný jako při nastavení studie a všechny plochy oblasti se našly |
| ⚠ **zastaralá** | díl se od nastavení změnil (parametr, prvek, materiál) – u plochy, která se posunula, i o kolik; zkontroluj a dej **Potvrdit pro aktuální díl** |
| ⚠ **neúplná** | chybí kontrolovaná oblast – vyber plochy a dej **Oblast z výběru** |
| ✕ **neplatná vazba** | plocha oblasti na dílu už není (nebo díl nejde postavit) |

* Pozná se to podle **otisku dílu** – kontrolního součtu parametrů, prvků a materiálu.
  Přejmenování prvku se nepočítá, posunutá díra ano (i když objem zůstane stejný).
  Přejmenování studie zastaralou studii neopraví – jen *Potvrdit*.
* **Ověřit…** zapíše, kdo studii odborně ověřil a kdy. Ověření platí jen pro díl, pro který
  se dalo – po změně dílu se ukáže „ověření neplatí“. Změna metody nebo oblasti ho smaže.
* Každá úprava studie je jeden krok **Zpět**; změníš tloušťku → studie zastaralá → Ctrl+Z →
  zase platná.
* **Geometrické jádro NDT** (etapa 02, zatím bez okna): průchod přímky dílem (úseky
  v materiálu, úhly dopadu), směr a zakřivení plochy, bod uvnitř/vně, viditelnost a kolize
  tělesa (budoucí sonda) s dílem. Hraniční případy – přímka po povrchu, přes hranu nebo
  tečně – jsou **nejisté** s vysvětlením a nikdy se nezapočítají jako materiál. Vyzkoušet
  jde příkazem `skodacad paprsek` (viz *Příkazová řádka*).
* **Virtuální sonda, geometrický paprsek UT a ruční pohyb sondy** (etapy 03 až 05, milník M1): ve
  skupině *Přístupnost UT sondy* v panelu NDT nastavíš sondu
  (*Sonda…* – přímá Ø D × výška, nebo úhlová délka × šířka × výška s výstupním bodem od čela,
  úhlem paprsku v materiálu $\beta$ [°], počtem odrazů v dílu, dovolenou mezerou pod sondou
  a manipulační rezervou; uloží se do studie). Klikni ve 3D na plochu
  a dej **Přiložit sondu sem** (nebo zapni **Jezdit sondou myší**, případně kdykoli drž `Alt` +
  levé tlačítko myši a táhni po povrchu dílu): sonda i lomená dráha osy paprsku v dílu (včetně
  odrazu od stěn) se nakreslí **zeleně** (přiloženo), **oranžově** (málo místa, nedosedá,
  přesahuje přes okraj či otvor) nebo **červeně** (koliduje) a pod ní je vysvětlení s čísly
  (mezera, průnik v mm³, volno k překážkám, ramena paprsku v materiálu, půlkrok, celý krok a
  jistota).
  * **Natočení a krokování:** *Směr paprsku [°]* (nebo kolečko myši při zapnutém *Jezdit sondou
    myší* / s podrženým `Alt`) sondu natočí po 15° (0° = osa +X, 90° = +Y). Tlačítka **◀ / ▶**
    posouvají přiloženou sondu po ploše o zvolený *Krok [mm]* dopředu ve směru paprsku a dozadu.
  * **Projet čáru a posuvník:** tlačítko **Projet čáru** zkontroluje přímku zvolené délky
    (*Délka čáry [mm]*) po 1 mm ve směru paprsku, vypíše souhrn (*„Volně: 0–5 mm. První potíž
    po 6 mm: Koliduje.“*) a zpřístupní posuvník, kterým lze sondu po čáře plynule posouvat.
  * *Odebrat sondu* ji schová. Přiložení, posuv i dráha paprsku jsou jen pohled (vidět i
    v zapnutém *Řezu modelem*) – do souboru se neukládají a po změně dílu se přepočítají.
* Sonda vždy dosedá kontaktní plochou do tečné roviny. Mezera pod ní se měří přesně (na trubce
  Ø 114,3 dá přímá sonda Ø 20 mezeru 0,88 mm → nedosedá; výchozí mez 0,5 mm odpovídá
  EN ISO 17640). Vůle se počítá jen k překážkám **nad** rovinou přiložení. Lom podle Snellova
  zákona (`--snell ALFA,C1,C2`) se počítá jen s výslovně zadanými rychlostmi.
* **Mapa geometrického pokrytí UT (etapa 06):** vyber cílové plochy jako oblast platné UT
  studie, nastav sondu a přilož ji na pojezdovou plochu. V panelu NDT zvol *Po ploše přiložení*
  nebo *Z přímé dráhy*, krok v mm a **Spočítat pokrytí**. Přímá dráha používá *Délku čáry*.
  Výpočet běží na pozadí, tlačítkem *Zastavit přepočet* jej lze přerušit. Barvy plošek:
  zelená = geometricky pokryto, červená = geometricky nepokryto, žlutá = nelze spolehlivě
  vyhodnotit. Souhrn obsahuje podíly v % i mm², počet poloh, krok a toleranci. **Export CSV…**
  uloží vzorky, první zasahující rameno, délku dráhy a předpoklady. **Skrýt mapu** obnoví běžný
  pohled. Při zobrazení pokrytí má tato mapa přednost před mapou tloušťky; řez ji ořízne.
  Po změně dílu, studie, sondy či přiložení výsledek zanikne; do JSON se neukládá (verze 15).
  Numerická tolerance sama neospravedlňuje kolidující polohu sondy: na rovinném pojezdu se
  mezilehlé polohy znovu ověřují. Procento je geometrický podíl, nikoli pravděpodobnost nálezu
  vady. Krok zjemni a porovnej výsledky; u bodových dotazů jde o podíl bodů, nikoli plochu.

  Příklady příkazové řádky (bez změny modelu):

  ```powershell
  python -m skodacad pokryti examples/ndt/deska.json --plocha 0,0,20 --prima 10 --cil-plocha 0,0,0 --krok 5 --konvergence --csv pokryti.csv
  python -m skodacad pokryti examples/ndt/zebro.json --plocha 60,0,20 --cil 0,0,0 --sklon 45 --smer 180 --odrazy 0 --rezim line --delka 50 --krok 2
  ```

### Tažení a přechod

**Tažení** protáhne profil po trase – trubky, kolena, madla, rámy z jeklu. Ukázka:
*Soubor → Otevřít ukázku → koleno*.

* **Trasa** jsou body `x; y; z`, jeden na řádek (i s parametry, např. `L; 0; L`). Profil se
  táhne od prvního bodu k poslednímu.
* **Poloměr ohybu** zaoblí rohy trasy jako ohýbačka trubek. Prázdné nebo 0 = ostrý roh,
  kusy se potkají **na pokos** (svařený rám).
* **Profil**: *kruh / trubka* (průměr), *obdélník / jekl* (šířka × výška), nebo *tvar ze skici*
  (libovolná skica, i s dírami). S **tloušťkou stěny** je kruh trubka a obdélník jekl.
* Profil stojí kolmo na začátek trasy, jeho střed (počátek skici) je v prvním bodě. Šířka
  jde vodorovně; když trasa začíná svisle, šířka jde podél osy X (stejně jako skica na XY).
* **Ocelový profil podle tabulek** (*Profil → ocelový profil*): IPE, U, L, jekl nebo trubka –
  profil stojí na výšku, střed obalového obdélníku je v prvním bodě trasy.
* **Uzavřená trasa** (poslední bod = první) udělá rám: všechny rohy jsou stejné (na pokos
  nebo s ohybem). Ukázka: *ram* – rám z jeklu 40 × 20 × 2.
* Tažení jde i odebírat (*Operace → odebrat*: drážka podél hrany) a opakovat polem.

**Přechod** plynule spojí dvě a více skic – výsypka, redukce, násypka. Ukázka: *výsypka*.

1. Nakresli skicu dole (třeba kruh na XY) a další výš (*Posun roviny* např. 300 – čtverec).
2. *Přidat prvek → Přechod* – spojí dvě poslední skici. Pořadí je pořadí ve stromu, v panelu
   jde zaškrtnout i víc skic (dole kruh, uprostřed ovál, nahoře čtverec).
3. **Rovné stěny** – mezi skicami rovné plochy (jehlan, komolý kužel); bez nich se plocha
   mezi více skicami plynule prohne.
4. **Tloušťka stěny** – dutý přechod s otevřenými konci (plech). Mezi dvěma kruhy nebo
   podobnými tvary je stěna přesně kolmo k povrchu. U přechodu **kruh ↔ hranatý tvar** to
   jádro neumí – stěna se tam měří v rovinách skic (vodorovně) a kolmo k šikmé stěně je
   o něco tenčí (u ukázky výsypky asi 2,7 mm místo 3 mm). Skutečnou tloušťku ukáže
   *mapa tloušťky stěny*.

Skici přechodu musí mít každá jeden obrys bez děr (dutý přechod se dělá tloušťkou stěny).

### Normalizované díly

*Přidat prvek → Normalizovaný díl* vloží díl podle strojnických tabulek. Ukázka:
*drzak_loziska* (kapsa na ložisko 608 a kapsy na matice M3 pro 3D tisk).

| Druh | Velikosti | Délka |
|---|---|---|
| šroub s válcovou hlavou, imbus – ISO 4762 | M2–M30 | dřík pod hlavou |
| šroub se šestihrannou hlavou – ISO 4017 | M2–M30 | dřík pod hlavou |
| zápustný šroub, imbus – ISO 10642 | M3–M20 | celková i s hlavou |
| šestihranná matice – ISO 4032, podložka – ISO 7089 | M2–M30 | – |
| kuličkové ložisko | 623–626, 608, 688, řady 6000 a 6200 (do 6010/6210) | – |
| válcový kolík – ISO 2338 | Ø2–Ø20 | délka kolíku |
| těsné pero – DIN 6885 tvar A | 2 × 2 až 28 × 16 (u každého rozsah hřídele) | délka pera |
| ocelový profil – tyč | IPE 80–400, U 80–240, L 20 × 3 – 120 × 12, jekly, trubky | délka tyče |

* Díl stojí na zvolené **rovině** v **polohách** `x; y` (jako díra – víc kusů najednou):
  šroub má hlavu nad plochou a dřík v materiálu, zápustný šroub je zapuštěný, matice,
  podložka, ložisko, kolík a tyč leží na ploše. **Natočení** otočí šestihran, pero či profil.
* **Operace**: *nový díl* (samotný šroub k tisku nebo do STEP), *přidat*, nebo **odebrat =
  kapsa**. Kapsa je obrys dílu bez děr (matice bez díry, ložisko jako válec) zvětšený o
  **vůli kapsy** na každou stranu (pro 3D tisk 0,1–0,2 mm). Aby kapsa šla do materiálu,
  zvol *Směr → otočit do materiálu*.
* **Drážka pro pero**: na hřídeli klikni na plášť (*Skica na ploše* → tečná rovina) a pero
  odeber – vznikne drážka hloubky t1 podle DIN 6885 (pero leží podél osy hřídele).
* Závit je **vyznačený** – dřík má jmenovitý průměr (M6 = 6 mm), stejně jako u děr. Tvary jsou
  zjednodušené (bez sražení hlav, ložisko jako prstenec).
* Ocelový profil jde dát i **do skici** (*tvar Ocelový profil*) – pak ho jde vysunout,
  táhnout či otáčet jako každou skicu.

Rozměry jsou z tabulek ověřených porovnáním více zdrojů (normy jsou placené) – zdroje jsou
v `src/skodacad/standards.py`. Plochy průřezů IPE, U a L souhlasí s tabulkovými.

### AI asistent

**Model → AI asistent** (`Ctrl+I`, tlačítko v liště) otevře rozhovor s Claude (Anthropic).
Napiš česky, co s modelem udělat – AI ho upraví sama:

* „zvětši přírubu na průměr 200 a přidej jednu díru se závitem M8 na roztečnou kružnici“
* „udělej krabičku 100 × 60 × 40, stěna 2 mm, 4 sloupky se závitem M3“ (nový díl od nuly)
* „proč je vysunutí červeně?“, „kolik díl váží?“ (vysvětlí a navrhne opravu)

Jak to funguje:

* AI mění model **stejnými kroky jako formulář** (parametry, prvky, název a materiál) a po
  každém kroku vidí výsledek přepočtu – chyby, objem, rozměry. Úpravu si tak sama ověří,
  případně opraví, a může si díl i prohlédnout (snímek 3D pohledu).
* V panelu průběžně vidíš, co dělá („→ Nastavuji parametry: D = 200“), a na konci shrnutí.
  **Celou úpravu vrátíš jedním Zpět** (`Ctrl+Z`). Během práce AI jsou ruční úpravy
  zamčené; *Zastavit AI* ji přeruší (co stihla, zůstane – vrátíš jedním Zpět).
* *Nová konverzace* – AI zapomene předchozí dotazy (při otevření jiného modelu samo).

**Nastavení AI…** (tlačítko v panelu nebo menu Model):

* **API klíč** – vytvoř ho na [console.anthropic.com](https://console.anthropic.com/settings/keys)
  (účet s kreditem – předplatné Claude.ai API nezahrnuje). Uloží se jen do tvého profilu
  (`C:\Users\<jméno>\SkodaCAD\nastaveni.json`); funguje i proměnná `ANTHROPIC_API_KEY`.
* **Model** – *Claude Opus 5.5* (výchozí, nejschopnější) nebo *Claude Sonnet 5.5* (poloviční
  cena). **Důkladnost** – rychle a levně / vyváženě / důkladně (výchozí).
* **Cena**: jedna úprava stojí orientačně 2–7 Kč u Opus, u Sonnet zhruba polovinu; spotřebu
  konverzace ukazuje panel. Model (JSON) se posílá ke zpracování společnosti Anthropic.
  Kdyby bezpečnostní filtr dotaz odmítl, zkusí ho automaticky záložní model Claude.

### Pole a zrcadlení

Ukázka: *Soubor → Otevřít ukázku → kryt*. **Pole** zopakuje vybrané prvky (díru, výřez,
výstupek, žebro …), **zrcadlení** je převrátí podle roviny. Kopie nejsou samostatné – když
změníš původní prvek (průměr díry, rozměr výstupku), přepočítají se s ním.

1. Ve stromu vyber prvek, který chceš opakovat (třeba díru).
2. *Přidat prvek → Pole* (nebo *Zrcadlení*) – nový prvek se vloží za vybraný a rovnou ho
   opakuje. V panelu *Úprava prvku* jde zaškrtnout i víc prvků najednou.
3. Zvol druh pole a vyplň hodnoty:

| Druh | Hodnoty | Příklad |
|---|---|---|
| **kruhové** – dokola | počet kusů, osa (X/Y/Z), bod na ose, celkový úhel | 6 děr dokola na přírubě |
| **lineární** – v řadě | počet kusů, směr (X/Y/Z), rozteč (záporná = opačně) | 5 žeber v řadě |
| **mřížka** | k lineárnímu navíc druhý směr, počet a rozteč | 4 × 3 větrací otvory |

* Počet kusů je **včetně původního** (6 = původní + 5 kopií).
* Celkový úhel 360° (výchozí) rozloží kusy rovnoměrně dokola; menší úhel dá první a poslední
  kus na kraje úhlu (4 kusy na 90° = po 30°).
* **Zrcadlení celého dílu:** když u zrcadlení nic nezaškrtneš, zrcadlí se celý díl – stačí
  namodelovat polovinu souměrného dílu. Rovina může být i plocha dílu (např. *pravá
  plocha* díl zdvojí).
* Opakovat jde vysunutí, rotace, tažení, přechod, normalizované díly, díry, pole a
  zrcadlení. Zaoblení, sražení a skořepina se
  opakovat nedají – dej je do stromu až za pole.

Prvek vybraný ve stromu jde smazat (*Smazat*, klávesa Delete) nebo posunout (▲ ▼). Nový prvek
se vloží za vybraný. **Zpět / Znovu**: `Ctrl+Z` / `Ctrl+Y`.

Do složky **`SkodaCAD`** ve tvém uživatelském profilu (`C:\Users\<jméno>\SkodaCAD`) se
zapisuje soubor `skodacad.log` – při potížích ho pošli, je v něm popis chyby.

## Příkazová řádka

```bash
skodacad build examples/priruba.json            # postaví přírubu, exporty do out/
skodacad build examples/priruba.json --set n=8  # totéž s 8 dírami místo 4
skodacad build examples/krabicka.json --format 3mf,svg
skodacad ai examples/priruba.json "zvětši D na 200"   # AI asistent → priruba-ai.json
skodacad ai krabicka.json "krabička 100 × 60 × 40, stěna 2 mm"  # nový díl (soubor neexistuje)
skodacad paprsek examples/ndt/trubka.json --z 0,0,100 --smer 0,0,-1   # NDT: přímka dílem
skodacad sonda examples/ndt/zebro.json --bod 22,0,20 --smer -1,0,0 --posun -1,0,0 --delka 10
```

`skodacad paprsek` vypíše, kudy přímka z bodu `--z` směrem `--smer` prochází materiálem
(úseky, délky, úhly dopadu od normály) a jestli je výsledek jistý. Souřadnice v mm jako
`0,0,100`, s desetinnou čárkou `"0;0;12,5"`; `--delka` omezí délku přímky, `--set` dočasně
změní parametr. Jde jen o geometrii přímky – ne o fyzikální model UT:

```
Paprsek z [0; 0; 100] směrem [0; 0; -1] (algoritmus ndt-geometrie 1):
  úsek 1: 42.85 → 48.85 mm, v materiálu 6.00 mm (vstup 0.0°, výstup 0.0°)
  úsek 2: 151.15 → 157.15 mm, v materiálu 6.00 mm (vstup 0.0°, výstup 0.0°)
  celkem v materiálu: 12.00 mm (jen jisté úseky), jistota: ok
```

`skodacad sonda` přiloží virtuální sondu do bodu `--bod` (na povrchu) se směrem paprsku
`--smer` a spočítá geometrickou dráhu osy UT paprsku v dílu: výchozí úhlová 40 × 20 × 25 mm
($\beta = 45^\circ$, 1 odraz), jiná přes `--prima 10`, `--uhlova 40x20x25`, `--celo 12`,
`--uhel 60` (nebo `--snell 36.44,2730,3250` a `--vlna shear`), `--odrazy 1`, `--dosah 100`,
sonda ze studie `--studie s1`; meze `--mezera 0.5` a `--rezerva 5`. S `--posun`
(a `--delka`, `--krok`) sondu posouvá a vypíše, odkud kam volně jede:

```
Úhlová sonda 40 × 20 × 25 mm, výstupní bod 12 mm od čela (mezera nejvýš 0.50 mm, rezerva 0.00 mm)
Přiložení v [22; 0; 20], paprsek [-1; 0; 0]:
  Přiloženo. Mezera pod sondou 0.00 mm, volno k překážkám 5.00 mm.
Dráha paprsku (úhel lomu 45.0°, nejvýš 1 odraz, algoritmus ndt-ut-paprsek 1):
  rameno 1: [22; 0; 20] → [2; 0; 0], délka 28.28 mm, vodorovně 20.00 mm, hloubka 20.00 mm (dopad 45.0°)
  ...
Posun směrem [-1; 0; 0] o 10 mm po 1 mm: volně 0–5 mm
  první potíž po 6 mm: Koliduje. Průnik těla sondy s dílem 500 mm³.
  (ŠkodaCAD provádí pouze geometrické posouzení přístupnosti ultrazvukové sondy a pokrytí …)
```

`skodacad ai` průběžně vypíše kroky AI, výsledek uloží vedle původního modelu jako
`<model>-ai.json` (`-o` jinam, `--prepsat` do původního) a ukáže spotřebu. Klíč a model bere
z nastavení okna (nebo `ANTHROPIC_API_KEY`), `--claude claude-sonnet-5-5` a
`--dukladnost low|medium|high` je přepíšou.

Výstup:

```
Strom prvků:
  ✓ Skica „Obrys příruby“
  ✓ Vysunutí „Deska“
  ...
Vlastnosti dílu:
  Objem:     311 093 mm³ (311.09 cm³)
  Hmotnost:  2.442 kg (ocel, 7.85 g/cm³)
  Rozměry:   165.00 × 165.00 × 18.00 mm
Uloženo: out/priruba.step, out/priruba.stl, out/priruba.3mf, out/priruba.svg
```

Model s NDT studiemi vypíše i jejich stav (`skodacad build examples/ndt/deska.json
--set t=30`):

```
NDT studie:
  ⚠ UT desky shora (UT) – zastaralá
      Díl se od nastavení studie změnil – zkontroluj ji a potvrď pro aktuální díl.
      Kontrolovaná plocha se posunula o 10.00 mm – zkontroluj, že je to pořád ta správná.
      Neověřeno.
```

Model s uloženými měřeními je vypíše taky a s nastavenou mapou tloušťky (nebo s volbou
`--mapa`) i její souhrn – body mapy uloží do `out/<model>-tloustka.csv`
(`skodacad build examples/trubka.json --set h=4`):

```
Měření:
  Jmenovitá tloušťka stěny: 6.00 mm
  Zbytková tloušťka pod jamkou: 2.00 mm
  Vnější průměr: 114.30 mm
Mapa tloušťky stěny:
  Nejtenčí místo: 2.00 mm (X 49.24  Y 0.00  Z 53.15)
  Nejčastější tloušťka: 6.00 mm, největší: 300.00 mm
  Pod minimem 4.00 mm: 0.30 % povrchu (619 mm²)
  27940 bodů po 12.4 mm, výpočet 3.9 s
```

| Formát | K čemu |
|---|---|
| `step` | přesná geometrie pro jiné CAD programy (Inventor, Solid Edge, Fusion …) |
| `stl`, `3mf` | 3D tisk (3MF je modernější a nese jednotky) |
| `glb` | prohlížeče, Blender |
| `svg` | izometrický náhled se skrytými hranami |

## Formát modelu

```json
{
  "format": "skodacad",
  "version": 15,
  "name": "Plochá příruba",
  "material": "ocel",
  "parameters": {"D": 165, "t": 18, "k": "D - 40"},
  "features": [ ... ],
  "measurements": [ ... ],
  "thickness_map": {"limit": 4},
  "ndt": {"studies": [ ... ]}
}
```

Každá číselná hodnota může být číslo nebo **výraz** s parametry, např. `"D/2 - 5"`.
Výrazy umí `+ - * / **`, závorky, `sqrt`, `sin`, `cos`, `tan` (ve stupních), `min`, `max`, `pi`.
Rozměry jsou v milimetrech, úhly ve stupních.

### Prvky (`features`)

Každý prvek má jedinečné `id`, `type` a volitelně český `name` pro výpis stromu.

| `type` | Co dělá | Hodnoty |
|---|---|---|
| `sketch` | 2D skica | `plane`, `offset`, `elements` (seznam tvarů) |
| `extrude` | vysunutí skici | `sketch`, `distance`, `operation`, `direction`, `through_all` |
| `revolve` | rotace skici kolem osy | `sketch`, `axis` (`X`/`Y`/`Z`), `angle` (výchozí 360) |
| `sweep` | tažení profilu po trase | `path` (`[[x, y, z], …]`, aspoň 2 body; poslední = první → uzavřený rám), `bend_radius` (0 = ostré rohy na pokos), `profile` (`circle`/`rectangle`/`steel`/`sketch`), `diameter`; `width`, `height`; `section` (`"IPE 100"`, `"L 50x5"`, `"RHS 40x20x2"`, `"CHS 48.3x2.6"`); `sketch`; `wall` (trubka/jekl), `operation` |
| `standard` | normalizovaný díl | `kind` (`socket_screw`, `hex_screw`, `countersunk_screw`, `nut`, `washer`, `bearing`, `pin`, `key`, `profile`), `size` (`"M6"`, `"608"`, `"6"`, `"8x7"`, `"IPE 100"`), `length`, `plane`, `offset`, `positions` (`[[x, y], …]`), `angle`, `direction` (`normal`/`reverse` = do materiálu), `operation`, `clearance` (vůle kapsy) |
| `loft` | přechod mezi skicami | `sketches` (`["dole", "nahore"]`, v pořadí), `ruled` (`true` = rovné stěny), `wall` (dutý s otevřenými konci), `operation` |
| `fillet` | zaoblení hran | `edges`, `radius` |
| `chamfer` | sražení hran | `edges`, `distance` |
| `shell` | skořepina (vydlabání) | `thickness`, `open_faces` (např. `["top"]`) |
| `hole` | díra podle tabulek | `kind`, `size` (`"M6"`), `fit`, `plane`, `offset`, `positions` (`[[x, y], …]`), `depth` nebo `through_all`, `thread_depth`, `diameter` (vlastní průměr), `modeled_thread` (`true` = vymodelovaný závit), `print_clearance` |
| `pattern` | pole – opakuje prvky | `features` (`["dira1"]`), `kind` (`circular`/`linear`), `count` (včetně původního); kruhové: `axis`, `center` (`[x, y, z]`), `angle` (výchozí 360); lineární: `direction` (`X`/`Y`/`Z`), `spacing`, pro mřížku `direction2`, `count2`, `spacing2` |
| `mirror` | zrcadlení | `plane`, `offset`, `features` (bez nich se zrcadlí celý díl) |

* **`plane`** – základní rovina `XY`, `XZ`, `YZ`, nebo plocha dílu `top`, `bottom`, `front`,
  `back`, `left`, `right`. Souřadnice skici na ploše dílu jsou globální (na `top` platí X a Y dílu).
  Šikmá či zakřivená plocha: `{"at": [x, y, z], "normal": [nx, ny, nz]}` – plocha nejbližší
  bodu `at` (směr `normal` rozhodne na hraně); rovinná plocha nese skicu přímo, zakřivená
  tečnou rovinou v tom bodě. Počátek skici je v bodě `at`, osa X podél osy válce/kužele,
  jinak vodorovně po ploše. Ukázka: *cep* (příčná díra a drážka pro pero na čepu).
* **`operation`** – `new` (první těleso), `add` (přidat materiál), `cut` (odebrat).
* **`direction`** – `normal` (ven z roviny), `reverse` (opačně), `both` (symetricky, `distance` je
  celková tloušťka). Řez (`cut`) jde ve výchozím stavu do materiálu.
* **`through_all": true`** – řez skrz celý díl.

### Tvary ve skice (`elements`)

| `shape` | Hodnoty |
|---|---|
| `rectangle` | `width`, `height`, `corner_radius` |
| `circle` | `diameter` |
| `circle_pattern` | `count`, `pitch_diameter`, `diameter`, `start_angle` – díry na roztečné kružnici |
| `regular_polygon` | `sides`, `diameter` (opsaný) – např. šestihran |
| `slot` | `length` (rozteč středů), `width` – drážka |
| `polygon` | `points` – seznam bodů `[[x, y], …]` |
| `profile` | obrys z úseček a oblouků s vazbami – kreslí se ve skicáři, viz níže |
| `steel` | `section` – průřez ocelového profilu podle tabulek (`"IPE 100"`, `"UPN 100"`, `"L 50x5"`, `"RHS 40x20x2"`, `"CHS 48.3x2.6"`), střed obalového obdélníku v `center` |

Všechny tvary mají navíc `center` (`[x, y]`), `angle` a `mode` (`add` = přidat, `subtract` = odečíst,
tak vzniká např. otvor v kruhu).

### Obrys s vazbami (`profile`)

```json
{"shape": "profile",
 "points": {"A": [0, 0], "B": [40, 0], "C": [40, 20], "M": [40, 10], "D": [0, 20]},
 "segments": {"s1": {"type": "line", "start": "A", "end": "B"},
              "s2": {"type": "arc", "start": "B", "end": "C", "center": "M"},
              "s3": {"type": "line", "start": "C", "end": "D"},
              "s4": {"type": "line", "start": "D", "end": "A"}},
 "constraints": [{"type": "coincident", "point": "A", "on": "origin"},
                 {"type": "horizontal", "segment": "s1"},
                 {"type": "length", "segment": "s1", "value": "sirka"},
                 {"type": "radius", "segment": "s2", "value": 10},
                 {"type": "tangent", "segments": ["s1", "s2"]}]}
```

* `points` jsou přibližné polohy – přesné spočítá řešič vazeb (SolveSpace) při každém přepočtu.
* Oblouk vede **proti směru hodinových ručiček** od `start` do `end`; `"construction": true`
  = pomocná čára. Bod `origin` je počátek skici.
* Kružnice: `{"type": "circle", "center": "K", "radius": 5}` – `radius` je přibližný, přesný
  určí vazby (po vyřešení se uloží). Víc smyček v jednom obrysu = vnořené jsou díry.
* Vazby: `fix` (point), `coincident` (point + on: bod/čára/oblouk/kružnice/origin),
  `horizontal`/`vertical` (segment, nebo points), `parallel`, `perpendicular`, `tangent`,
  `equal`, `concentric` (segments), `midpoint` (point + segment), `symmetric` (points +
  segment = osa); kóty s `value` (číslo nebo výraz): `length` (segment), `distance` (points,
  nebo point + segment), `radius`, `diameter` (segment – oblouk či kružnice), `angle`
  (segments, °).
* `tangent` u čar se společným koncovým bodem řeší přímo SolveSpace, jinak (kružnice, oblouk
  bez společného bodu) přes skrytý bod dotyku.
* Promítnuté hrany dílu: `"references": {"r1": {"edge": {"face": "top", "type": "circle",
  "near": [40, 25, 3]}, "kind": "circle", "center": [40, 25], "radius": 1.7}}` – `edge` je
  hrana popsaná významem (jako u zaoblení), `kind` a souřadnice se při každém přepočtu
  spočítají znovu z dílu před skicou. Jsou pevné; vazby na ně odkazují jménem (`r1`) a body
  `r1.start`, `r1.end`, `r1.center`.

### Výběr hran (`edges`)

Hrany se vybírají **významem, ne číslem** – výběr tak platí i po změně rozměrů.

```json
"edges": "all"
"edges": {"face": "top"}                                  // hrany horní plochy
"edges": {"face": "top", "type": "circle", "radius": "D/2"} // jen vnější kružnice nahoře
"edges": {"parallel": "Z"}                                // svislé hrany
"edges": {"between": ["front", "right"]}                  // hrana mezi přední a pravou plochou
"edges": {"face": "top", "radius": 3, "near": [20, 0, 10]} // z děr R3 nahoře ta nejbližší k bodu
"edges": [{"face": "top"}, {"parallel": "Z"}]             // seznam = všechny dohromady
```

Výběr kliknutím ve 3D vytváří tyto popisy sám: zkusí nejjednodušší, který vybere přesně
kliknuté hrany. `near` (nejbližší k bodu) použije jen tam, kde nic jiného nestačí – třeba jedna
ze čtyř stejných děr. Soubory verze 1 (bez `between`, `near` a seznamu) se načtou dál.

### Uložená měření (`measurements`)

```json
{"id": "m1", "name": "Tloušťka desky", "kind": "thickness",
 "a": {"face": {"at": [60, 0, 18], "normal": [0, 0, 1], "type": "plane"}}}
{"id": "m2", "name": "Rozteč os", "kind": "parallel",
 "a": {"edge": {"face": "top", "radius": 9, "near": [37.83, 37.83, 18]}},
 "b": {"edge": {"face": "top", "radius": 9, "near": [-37.83, 37.83, 18]}}}
```

* **`kind`** – co se měří: `thickness` (tloušťka stěny v bodě `at`), `parallel` (kolmá
  vzdálenost rovnoběžných ploch/hran, rozteč os), `distance` (nejkratší vzdálenost),
  `angle` (úhel), `centers` (vzdálenost středů), `diameter`, `radius`, `length`, `area`.
* **`a`**, **`b`** – plocha `{"face": {"at", "normal", "type", "radius"}}` (nejbližší
  plocha toho druhu k bodu `at`, rovina přednostně se stejným směrem, válec se stejným
  poloměrem) nebo hrana `{"edge": …}` popsaná jako u zaoblení. Druhou věc má jen měření
  dvou věcí.
* Hodnota se do souboru neukládá – spočítá se při každém přepočtu (okno, příkazová řádka).
  Soubory verze 1–8 (bez měření) se načtou dál.

### Mapa tloušťky stěny (`thickness_map`)

```json
"thickness_map": {"limit": 4, "step": 2.5, "scale_max": 8}
```

Vše je nepovinné: `limit` = minimální dovolená tloušťka [mm] (pod ní fialově), `step` =
vzdálenost bodů [mm] (bez ní automaticky, asi 30 000 bodů), `scale_max` = horní mez barevné
škály [mm] (bez ní nejčastější tloušťka dílu). Samotná mapa se do souboru neukládá – spočítá
se znovu. Soubory verze 1–9 se načtou dál. Verze 11 přidala prvky `sweep` a `loft`,
verze 12 normalizované díly (`standard`) a ocelový profil (`steel`), verze 13 NDT studie
(`ndt`), verze 14 sonda ve studii (`device`), verze 15 úhel paprsku a počet odrazů sondy
(`beam_angle`, `bounces`), verze 16 cílové objemy a svary NDT (krok 07A).
Starší soubory verze 1–15 se načtou beze změny. Uložení novou aplikací zapisuje verzi 16;
starší aplikace takový soubor neumí otevřít. Pouhé otevření původní soubor nepřepisuje.

### NDT studie (`ndt`)

```json
"ndt": {"studies": [
  {"id": "s1", "name": "UT desky shora", "method": "UT",
   "target": {"kind": "faces",
              "faces": [{"face": {"at": [0, 0, 20], "normal": [0, 0, 1], "type": "plane"}}]},
   "note": "Přímá sonda z horní plochy.", "created": "2026-10-16", "part": "3f9a1c0b7d2e4a65",
   "verified": {"by": "J. N.", "date": "2026-10-16", "part": "3f9a1c0b7d2e4a65"}}
]}
```

* **`method`** – `UT`, `PT`, `MT` nebo `RT`. **`target`** – kontrolovaná oblast:
  `"kind": "faces"` se seznamem ploch zapsaných jako u měření (bod `at`, směr `normal`, druh,
  poloměr), nebo objem/svar podle popisu níže. Bez oblasti (nebo s prázdným seznamem ploch)
  je studie neúplná.
* **`part`** – otisk dílu (16 znaků), ke kterému byla studie založena nebo naposledy
  potvrzena; jiný otisk = studie zastaralá. **`verified`** (nepovinné) – kdo a kdy ověřil,
  pro jaký otisk dílu. `name`, `note`, `created` jsou texty.
* Stav studie se do souboru neukládá – spočítá se při každém přepočtu. Neznámé položky
  ve studii jsou chyba (překlep se tak nepřehlédne). Sekce bez studií se nezapisuje.
* **`device`** (verze 14–15, nepovinné) – sonda studie, bez ní výchozí úhlová:
  `{"kind": "angle", "length": 40, "width": 20, "height": 25, "front": 12, "beam_angle": 45,
  "bounces": 1, "max_gap": 0.5, "reserve": 0}` nebo `{"kind": "straight", "diameter": 10,
  "height": 25, "bounces": 0, "max_gap": 0.5, "reserve": 0}` (mm; `front` = výstupní bod od čela,
  `beam_angle` = úhel lomu v materiálu $\beta$ [°] 1–85, `bounces` = počet odrazů 0–10,
  `max_gap` = dovolená mezera pod sondou, `reserve` = manipulační rezerva). Přiložení sondy ani
  dráha paprsku se do souboru neukládají.

### Cílové objemy a svary (07A, verze 16)

Krok 07A ukládá a geometricky ověřuje pomocné objemy. **07B přidává výpočet objemového
pokrytí přes CLI a ModelSession; editor a náhled objemové mapy v okně patří až do 07C**.
Podrobnosti a meze výpočtu: [Etapa 07B](docs/ndt/13-navrh-etapa-07b.md).
Plošné mapy Etapy 06 fungují dál. Objemový cíl
se do výrobního dílu nepřidává a nemění jeho hmotnost, objem ani exporty.

Objemový výsledek se váží v **mm³**, plochový dál v mm² a bodový počtem bodů.
Buňky se oříznou skutečným cílem a každý jejich oddělený kus má vlastní ověřený
vnitřní bod. Jeho stav zastupuje celý kus: jde o aproximaci podle kroku cíle.
Známý objem bez spolehlivého vnitřního bodu zůstává nejistý. Součet vah se kontroluje
bez přenormování. Výsledky zůstávají pouze v paměti a zanikají se změnou zadání.

`skodacad pokryti MODEL --studie s1 --plocha X,Y,Z --rezim face --krok 5 --krok-cile 2
--konvergence --csv out/pokryti.csv` vyhodnotí cíl uložený ve studii. Adresář `out`
musí existovat. Porovnání zdvojnásobí oba kroky při stejné toleranci; nízký rozdíl
není zárukou přesnosti. Výstup i CSV vždy obsahují úplné upozornění UT.
Objemový pojezd po čáře (`line`) s nulovým rozevřením se odmítá, protože ideální
osy nevymezují kladný objem. Nenulové rozevření vyžaduje výslovné zadání.
Počty buněk/kusů/poloh a porovnání jsou omezené; příliš jemný výpočet doporučí
zhrubnout, nepřepne se na hrubší krok automaticky.

Ukázky k otevření přes **Soubor → Otevřít**:

- [Tupý V svar](examples/ndt/cilove_objemy/tupy_svar_objem.json): 14 613,843876 mm³.
- [Dva koutové svary](examples/ndt/cilove_objemy/koutovy_svar_objem.json): dva nezávislé cíle
  po 2 450 mm³. Díl je geometricky stejný jako původní referenční příklad.

Pomocný objem je polygonální hranol:

```json
"target": {
  "kind": "volume",
  "frame": {"origin": [0, 0, 0], "axis": [0, 1, 0], "across": [1, 0, 0]},
  "length_mm": 20,
  "profile_mm": [[0, 0], [10, 0], [10, 10], [0, 10]]
}
```

`axis` je směr délky od počátku, `across` první souřadnice průřezu; druhá souřadnice
má směr `across × axis` (zde +Z). Směry musí být nenulové a kolmé; při načtení se
normalizují. Rozměry jsou konečná čísla v mm, bez výrazů. Cíl je průnik hranolu
s materiálem dílu; souhrn odděluje zadaný a účinný objem. Prázdný průnik je neplatný.

U `kind: "weld"` se místo `profile_mm` zadává `weld_type` a `dimensions`:

- `fillet`: kladná ramena `leg_across_mm`, `leg_height_mm`.
- `butt_v` bez otupení kořene: `thickness_mm`, `angle_deg` (0–180° bez krajních hodnot)
  a nezáporná `root_gap_mm`; volitelně skupina `cap_width_mm`, `cap_top_width_mm`,
  `cap_height_mm` pro převýšení a `root_width_mm`, `root_tip_width_mm`, `root_height_mm`
  pro podkořen. Chybějící skupina má rozměry 0. Při nenulové výšce je nutná kladná
  šířka u plechu, koncová šířka 0 vytvoří trojúhelník.

Jde o nominální geometrii zadanou člověkem. Svar musí tvořit souvislé těleso a musí
se celý vejít do materiálu (objemová tolerance `max(0,000001 mm³; objem × 10⁻⁸)`);
chybějící materiál se nesmí tiše odříznout. Skutečnou hranici natavení ani tepelně
ovlivněnou oblast program neurčuje.

`ModelSession.set_ndt_volume_target(id, target)` nastaví validovaný cíl s historií
Zpět/Znovu; `ndt_target_volume(id)` vrací jeho pomocné těleso a objemy v mm³.
Po změně receptu dílu je studie zastaralá; pokud svar už nemá materiál, vazba je neplatná.
Potvrzení ponechá zadané souřadnice, nepřesune cíl na jiné místo. Změna cíle odstraní
starou mapu i ověření. Ověření objemu má navíc `verified.target`, otisk zadání cíle;
při ruční změně cíle v JSON přestane platit i při stejném dílu.

### Materiály

`ocel`, `nerez`, `litina`, `hlinik`, `mosaz`, `med`, `titan`, `pla`, `petg`, `abs`
(diakritika a velká písmena nevadí).

## Pro vývoj

Pravidla projektu, architektura a plán jsou v [CLAUDE.md](CLAUDE.md). Podkladové výzkumy
jsou ve složce [docs/](docs/).

```bash
pip install -e ".[dev,gui]"   # jádro, okno a nástroje pro vývoj
pytest -q                     # testy (ověřují geometrii výpočtem objemu)
ruff check src tests          # kontrola kódu
skodacad-gui                  # spustí okno (bez argumentu otevře ukázku příruby)
skodacad-gui --self-test zprava.txt   # kontrola aplikace bez obsluhy
```
