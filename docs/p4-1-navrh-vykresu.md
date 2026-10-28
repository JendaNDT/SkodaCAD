# P4.1 — návrh prvního technického výkresu

**Stav: autor schválil body V1–V9 slovy „schvaluji vše“; funkce výkresu dosud není hotová.** Autor
upřednostnil strojní díly pro výrobu. Následující rozsah je návrh pro P4.2–P4.5,
nikoli prohlášení o souladu s konkrétní normou nebo způsobilosti výkresu k výrobě.

## Co aplikace umí dnes

* Náhled dílu do SVG promítá izometrii a rozlišuje viditelné a skryté hrany;
  jeho velikost se přizpůsobuje obrázku. Není to měřítkový technický výkres.
* Řez umí rozříznout díl rovinou a samostatně vyvézt obrys plochy řezu do DXF
  nebo SVG. Neobsahuje celé zobrazení dílu za řezem, výkresový list ani kóty.
* Hotový systém více pohledů, kót a jejich vazeb na listu v projektu zatím není.

## Navrhovaná první verze

| Bod | Doporučení | Přínos a hranice |
|---|---|---|
| V1 List | Jeden list A4 nebo A3 na šířku; výchozí A4. Rámeček a jednoduché popisové pole s názvem dílu, materiálem, datem, měřítkem a označením listu. Text vyplní autor. | Výkres je čitelný a má základní informace; více listů odložit. |
| V2 Jednotky a měřítko | Rozměry v mm; nabídnout 1:1, 1:2, 1:5, 1:10, 2:1 a 5:1. Výchozí 1:1; při nevejití varovat a nabídnout změnu listu nebo měřítka. Nepřizpůsobovat obsah tiskárně automaticky. | Hodnoty kót jsou rozměry dílu, velikost kresby se řídí měřítkem. Vytištěná kontrolní úsečka dovolí ověřit nastavení tisku. |
| V3 Pohledy | Ortogonální pohled zepředu, shora a zprava; autor může jednotlivé pohledy skrýt. Navrhuji evropské rozložení: pohled shora pod předním, pohled zprava vlevo od předního. Před implementací doložit směry souřadnic na nesouměrném dílu. | Tři pohledy popíší běžný díl. Izometrii lze přidat jako nepovinný pomocný náhled bez kót. |
| V4 Hrany | Viditelné hrany plně, skryté čárkovaně; zobrazení skrytých hran lze vypnout. Promítání skutečné geometrie, ne snímku obrazovky; nepodporovanou geometrii označit a export neprohlásit za úplný. | Obrázek zůstane vektorový a čitelný. Přesnost a funkčnost skrytých hran je nutné teprve ověřit v P4.2. |
| V5 Řez | Jeden úplný rovinný řez v rovině kolmé na X, Y nebo Z; volba polohy a strany pohledu. Označení A–A, obrys řezaného materiálu a šrafování; současně zobrazit relevantní hrany dílu za rovinou. | Umožní popsat dutiny. Lomené, částečné a vícečetné řezy jsou mimo první verzi. Současný export obrysu řezu zůstává samostatnou funkcí. |
| V6 Kóty | Ručně vložit délku, vzdálenost, průměr a poloměr z podporovaných prvků; text, umístění a přehlednost zkontroluje autor. Hodnota se odvozuje z modelu, ne zadáním libovolného čísla. | Kóty umožní základní zadání výroby. Tolerance, drsnost, geometrické tolerance, svarové a závitové značky zatím nepřidávat; náročnější zadání vyžaduje doplnění jiným nástrojem. |
| V7 Změna dílu | Pohledy přepočítat po změně. Kótu se zaniklou nebo nejednoznačnou vazbou viditelně označit a při exportu vyžadovat nápravu; žádné tiché převedení na jinou plochu. | Výkres nesmí potichu ukazovat hodnotu jiného prvku. Zachování odkazů u importů STEP není zaručeno. |
| V8 Export | Vícestránkový export zatím ne; jeden vektorový PDF list a výměnný DXF list s měřítkem a popisky. Volba skutečné velikosti při tisku; PDF i DXF ověřit otevřením v nezávislé aplikaci. | PDF pro sdílení a tisk, DXF pro další zpracování. Prvky a rozsah DXF je potřeba ověřit, není slíbená plná kompatibilita všech CADů. |
| V9 Uložení | Před P4.3 samostatně navrhnout a schválit uložení výkresu, identitu odkazů a kompatibilitu souborů. P4.1 žádný formát ani nové knihovny nezavádí. | Model se nezmění bez odsouhlaseného řešení; zálohování a přenositelnost musí být řešeny před implementací. |

## Příklad k ověření

Deska 100 × 60 × 10 mm se středovým průchozím otvorem Ø20 mm. Na A4 v měřítku
1:1 navrhnout přední pohled, pohled shora a řez vedený středem díry. Zobrazit
celkové rozměry, tloušťku, průměr a polohu otvoru. Změnit průměr díry z 20 na
24 mm: příslušná kóta se po přepočtu změní na 24 mm. Při odstranění otvoru se
vazba označí jako neplatná a export vyžaduje opravu.

Přední a horní pohled testovat navíc na nesouměrném dílu se slepou dírou, aby
byla vidět záměna stran a skrytá hrana. Výkres z importovaného STEP dílu ověřit
samostatně; historie zdrojového CADu není k dispozici.

## Kritéria přijetí

1. P4.2: orientace a poloha viditelných i skrytých hran, řez a šrafy na kvádru,
   desce s otvorem a nesouměrném dílu; analýza hran i chyb geometrie.
2. P4.3: kóty zachovají správné hodnoty po změně dílu; zaniklé, nejednoznačné a
   poškozené odkazy se označí a nezpůsobí zavádějící výstup.
3. P4.4: PDF i DXF otevřít a zkontrolovat na Windows a macOS; rozměry listu,
   češtinu, měřítko, šrafy a typy čar ověřit i mimo ŠkodaCAD.
4. P4.5: vytisknout bez přizpůsobení stránky a fyzicky změřit kontrolní úsečku;
   porovnat hodnoty kót s modelem a ručně projít vytvoření, změnu a znovuotevření.
5. U každého omezení nebo chyby má aplikace jasně říct, co chybí; výkres bez
   technologických údajů se nesmí automaticky označit za připravený k výrobě.

## Rozhodnutí před pokračováním

Ke schválení jsou body **V1–V9**. Zejména je potřeba odsouhlasit A4/A3, směr
rozložení pohledů, jeden řez, rozsah kót a výstupy PDF/DXF. Schválení P4.1 samo
o sobě neschvaluje podobu ukládání z P4.3 ani sloučení budoucí implementace.
