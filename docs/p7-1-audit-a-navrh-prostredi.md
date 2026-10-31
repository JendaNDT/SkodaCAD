# P7.1 – audit rozložení a návrh prostředí strojního CADu

Datum: **31. 10. 2026**. Výchozí aplikace: `b834c81` (P6.10, PR #79).
Stav: **technický průzkum a návrh k připomínkám**, nikoli hotové nové rozhraní.

## Zadání autora

Autor po návrhu P6.4 odpověděl „to přeskočíme“ a požádal o další krok vývoje.
Zkouška P6 na jeho vlastním dílu tedy zůstává neprovedená. Navazuje P7.
K úpravě hlavního okna napsal „na tomhle si musíme dát extra záležet“ a upřesnil
vzhled: **„Něco ve stylu solid edge nebo Inventor.“**

Tento pokyn určuje směr návrhu. Nejde o výběr jednoho ze dvou níže uvedených
rozložení ani o provedení autorských pracovních scénářů P7.1/P7.4.

## Technické nálezy

Měření proběhlo ve skutečném Qt/Cocoa okně na místním Macu, se skutečným
OCCT prohlížečem a ukázkou `rizeny_prechod.json`. Rozměry jsou **logické body**,
nikoli fyzické pixely Retiny. Velikost okna zahrnuje rám.

| Okno | Současný 3D pohled | Výška editoru | Šířka pole X₁ |
|---|---|---|---|
| 1 470 × 866 | 728 × 783 | 377 | 45 |
| 1 280 × 800 | 538 × 717 | 317 | 41 |
| 1 024 × 720 | 282 × 637 | 237 | 41 |

- Pravá strana dělí výšku mezi editor a skupinu sedmi dalších panelů. Editor
  vodítek se nevejde celý; názvy spodních záložek se zkracují.
- Každý dock má v `_add_dock` nejméně 340 bodů šířky. Na malém okně zbývá
  pro model jen 282 bodů. Samotné volání `resizeDocks` tento problém neřeší.
- Čtyři sloupce výrazů v tabulce vodítek mají příliš malou šířku i pro běžný
  parametrický zápis s přidaným posunem.
- Popis ukázky zabírá velkou část levého panelu, i když autor právě upravuje prvek.
  Sedm parametrů nebo dlouhý popis navíc ubírají výšku stromu.
- Pevná pomocná barva `#555555` má na současném pozadí `#323232` kontrast
  přibližně **1,72 : 1**. To vysvětluje špatnou čitelnost v tmavém režimu.
- Chybí uživatelská obnova výchozího rozložení a uložení rozměrů/panelů mezi starty.
- Název prvku ve stromu předchází dlouhá informace o počtu těles; samotný název
  pak často není celý vidět. Důležitý stav se musí zachovat, ale čitelněji uspořádat.

Zdroj nálezů: `gui/main_window.py`, `gui/feature_editor.py` a nativní měření
v `out/p7-layout-study/native-study.json`. Nejde o pozorování práce autora.

## Vizuální směr

Použít běžnou stavbu strojního CADu: pás nástrojů seskupených podle činnosti,
strom modelu, velkou 3D plochu a kontextový editor. Ovládání bude česky,
se skutečnými funkcemi ŠkodaCADu a vlastními ikonami/popisky.

Podklady:

- [Inventor – rozhraní](https://help.autodesk.com/cloudhelp/2024/ENU/Inventor-Help/files/GUID-8E3158B6-56F5-4D74-9B6A-5D5B6049116A.htm):
  členění příkazů podle úlohy, prohlížeč modelu a kontextové parametry.
- [Inventor – property panels](https://help.autodesk.com/cloudhelp/2024/ENU/Inventor-Help/files/GUID-3E5505B9-9F60-43A0-BF32-97D183B91A70.htm):
  skupiny parametrů, sbalitelné části, dokování a zapamatování stavu.
- [Solid Edge 2026 – přizpůsobení](https://blogs.sw.siemens.com/solidedge/new-in-designcenter-solid-edge-2026-customization/):
  prostorově úsporné příkazové panely, čitelné škálovatelné ikony a tmavý vzhled.

### Strom a pravý editor

Vlevo zůstává stručný strom s parametry ve sbalitelné sekci. Vpravo je jediný
editor přes celou dostupnou výšku; měření nebo NDT jej podle zvoleného příkazu
nahradí. Editor lze zavřít a znovu otevřít. Strom a hodnoty jsou viditelné současně.

**Doporučená výchozí varianta:** umožňuje sledovat historii i souřadnice při úpravě.
Na malém okně bude potřebovat režim s jedním postranním panelem.

### Společný levý panel

Model a editor využívají stejné místo vlevo a přepínají se přímo v jeho záhlaví.
Pravá strana je volná pro 3D. Přínosem je větší souvislá plocha modelu; cenou je
přepínání mezi stromem a hodnotami. Tento rozdíl se má posoudit na náhledu.

Obě varianty mají stejný pás: **Soubor, 3D model, Skica, Výkres, Sestava, NDT,
Zobrazení**. Sbalený pás lze znovu rozbalit výběrem jeho karty.
Tyto karty nenahrazují návrh skicáře ani okna sestavy; existující samostatná okna
zatím zůstávají samostatnými pracovními postupy.

## Návrhová pravidla pro implementaci

1. **Příkazy přes existující akce.** Tlačítka pásu využijí stejné `QAction` jako
   menu a zkratky. Každá dnešní akce zůstane dohledatelná. Seskupení do pásu
   nepřidává geometrické schopnosti jádra.
2. **Strom je přehled historie.** Název bude hlavní údaj, stav bude mít ikonu
   i text. Údaje o změně počtu těles a chybě se zachovají v detailu/bublině;
   závažná chyba zůstane přímo viditelná. Sémantické identifikátory se nemění.
3. **Široká pole.** U vodítek vybrat roh A–D a jednu ze dvou rukojetí; pro X/Y
   použít samostatné řádky. Delší výraz se musí dát pohodlně upravit a celý přečíst.
   Celkový přehled čtyř vodítek je vhodný jako pozdější volitelný režim, ne jako
   jediný způsob zadání.
4. **Kontrast podle palety.** Základní písmo zůstane čitelné, vedlejší text bude
   odvozený od vzhledu systému. Jako návrhové minimum pro běžný text používáme
   [4,5 : 1 podle W3C](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html).
   Jde o dílčí cíl čitelnosti, nikoli prohlášení o splnění celého WCAG.
5. **Rozložení v profilu.** Uložit rozměry, poslední panel a sbalené sekce do
   samostatného souboru nastavení okna. Žádné přidávání do receptu dílu. Zápis má
   být atomický, poškozený či neznámý stav vede k výchozímu rozložení. Po odpojení
   monitoru musí zůstat okno a panely na dostupné obrazovce.
6. **Potvrzování úprav vyžaduje jasné chování.** Dnešní formulář potvrzuje pole
   přes `editingFinished` (Enter nebo opuštění pole). První úprava rozložení tento
   význam zachová a v nápovědě jej vysvětlí. Tlačítka „OK/Zrušit“ pro celý příkaz
   se smějí přidat až s návrhem skutečného rozpracovaného stavu a ověřením historie.
7. **Pohled se neplete s modelem.** Změna panelu nebo rozložení bez rozepsaných
   hodnot nesmí měnit dokument, špinavý stav, geometrii ani Zpět/Znovu.
   Změna rozložení nesmí sama volat „Celý díl“ ani měnit natočení kamery.
   Při rozepsaném poli je nutné otestovat stávající okamžik potvrzení; hodnotu
   nelze při přestavbě formuláře tiše zahodit.
8. **Obnova je vždy dostupná.** „Zobrazení → Obnovit rozložení“ musí fungovat
   i při zavřeném editoru nebo skrytém stromu. Obnovuje pohled, nikoli hodnoty modelu.
9. **NDT zůstává samostatný kontext.** Úprava rozložení nemění výpočty ani závazná
   upozornění UT/PT/MT/RT. Kliknutí na plochu nebo aktualizace výpočtu nesmí
   svévolně přepnout autora z právě používaného panelu.

## Co bylo ověřeno a co ještě ne

[Spustitelný průzkum](p7-1-pruzkum-rozlozeni.py):

```sh
.venv/bin/python docs/p7-1-pruzkum-rozlozeni.py
```

V samostatném nativním testovacím okně ověřil jednotlivé principy: celý pravý
panel, přeskupení polí, volbu vodítka a barvy z palety. Po změnách rozložení
i výběru A–D zůstal dokument i historie beze změny; přepínání editor/měření/NDT
fungovalo. Objem ukázky zůstal **77 760 mm³**.

V tomto pokusu se šířka pole X₁ zvýšila na **153–160 bodů**, výška editoru
na **578–724 bodů** a kontrast zvolené pomocné barvy na **8,82 : 1**.
Na okně 1 024 × 720 ale model stále dostal jen **352 bodů** šířky.
Proto tento pokus není hotovým řešením malého okna. Ověřuje dílčí principy,
neimplementuje pás nástrojů ani úplnou variantu z interaktivního návrhu.

Interaktivní návrh ukazuje obě rozložení, skutečné snímky referenčního dílu
z OCCT, přepínání vodítek/pohledů, široká pole, kontextové karty a obnovu panelu.
Je to návrh vzhledu a ovládání; nepočítá nový model ani neukládá soubory CADu.
Souhrn kontroly náhledu patří do `out/p7-layout-study/browser-qa.json`.

Před předáním prošly obě varianty při vnější šířce náhledu 1 024, 736 a 320 bodů
bez vodorovného přetékání. Všech 12 kombinací A–D a tří pohledů načetlo správný
snímek. Zavření/obnovení editoru zachovalo rozepsaný výraz, sbalený pás šel znovu
otevřít a upozornění všech čtyř metod NDT odpovídala zdrojovému textu aplikace.
Pomocný text v náhledu měl kontrast **6,41 : 1** ve světlém a **7,15 : 1**
v tmavém vzhledu; konzole prohlížeče nehlásila chybu ani varování.
Úzký náhled se skládá pod sebe pro zobrazení v rozhovoru, není to příslib mobilní aplikace.

Zatím není ověřené uložení rozložení do produkčního profilu, úplné pracovní
scénáře, Windows/DPI, dlouhodobý provoz ani přijetí autorem. Plné systémové
kontroly a oba stažené balíčky se provedou s implementací před sloučením.

## Rozdělení následující implementace

1. **Nativní prototyp vybraného rozložení a pásu**, porovnání na 1 470 × 866
   a 1 280 × 800, záměrný kompaktní režim pro 1 024 × 720. Měřit šířku i plochu
   3D pohledu, ne jen vzhled jednoho snímku.
2. **Přehled stromu a formulářů**, dlouhé názvy/výrazy, průchod klávesnicí,
   pomocné texty ve světlém i tmavém vzhledu.
3. **Uložení a obnova rozložení**, změna monitoru, poškozená nastavení,
   zavření všech panelů a návrat bez změny modelu.
4. **Scénáře a přejímka**, vytvoření/úprava/import/výkres/sestava/NDT,
   cílené regrese, nativní snímky a oba úplné systémové běhy s balíčky.

Geometrické jádro, formát 34 a závislosti tento návrh nemění.
