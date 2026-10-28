# P3.2 — návrh uložení importu STEP

**Stav: doporučení I1–I9 předaná autorovi; následoval jeho pokyn „ok, pokračuj“ a zadání P3.3–P3.5. Implementace zatím není dokončena.** Navazuje na plán P3 a na
[sadu P3.1 v PR #46](https://github.com/JendaNDT/SkodaCAD/pull/46), která k datu
přípravy návrhu ještě není sloučena. P3.1 obsahuje syntetické soubory, ne důkaz
kompatibility se všemi CAD programy. Dnešní formát je JSON verze 23; samotný
uživatelský STEP import zatím v aplikaci neexistuje.

## Co se navrhuje

Doporučuji vložit originální STEP do jediného souboru modelu. Při přenosu tak
stačí zkopírovat model ŠkodaCAD; původní soubor STEP už nemusí zůstat na svém
místě. Nevýhodou je větší a méně přehledný JSON. Obsah STEP bude převeden na
text pomocí base64, což jej zvětší přibližně o třetinu. Parametrická historie
původního CADu se tím neobnoví.

| Rozhodnutí | Doporučení | Důvod a dopad |
|---|---|---|
| **I1 Kopie zdroje** | Přesné původní bajty STEP vložit do JSON jako base64 v novém prvku `step_import`. Žádná závislost na původní cestě ani na vedlejším souboru. | Jeden přenositelný soubor; proti externímu odkazu spotřebuje více místa a paměti. |
| **I2 Identita** | Povinné `sha256` a `size_bytes` původních bajtů; ověřit po dekódování před čtením geometrie. `source_name` je jen informativní název bez cesty. | Chyba nebo změna bajtů se zjistí; hash není důkaz autorství, původu ani bezpečnosti souboru. |
| **I3 Rozsah prvku** | Nejvýše jeden `step_import`, jako první prvek vytvářející těleso; obsahuje celý originální STEP. Po něm mohou následovat dosud podporované operace, pokud jejich vlastní předpoklady platí. | Základ pro jeden importovaný díl; sestavy, víc těles a výběr dílu vyžadují rozhodnutí P3.3/P3.4, nepovažují se zde za podporované. |
| **I4 Jednotky** | Zdroj uchovat beze změny; při importu jednotku přečíst a převést geometrii do mm. Chybějící, nejednoznačnou či nepodporovanou jednotku nepřevádět odhadem; nabídnout řešení až podle návrhu P3.3. | Zachová se zdroj i dnešní pravidlo modelu v mm; zápis jednotky v metadatech nesmí nahradit skutečnou diagnostiku. |
| **I5 Limity** | Pro první verzi navrhuji max. **16 MiB** původních STEP bajtů na model; před dekódováním ověřit délku base64 a po něm přesnou délku, kontrolovat také omezení paměti a času při čtení. Soubor větší než limit odmítnout s českou zprávou, ne oříznout. | Předvídatelnější spotřeba paměti; větší reálné díly mohou vyžadovat pozdější samostatný návrh ukládání. Limit je návrh, nikoli změřená bezpečná hodnota. |
| **I6 Poškození a obnova** | Chybějící obsah, chybný base64, nesouhlas délky či hash: zastavit import a navazující výpočty, vysvětlit problém, zachovat recept a nabídnout výběr originálního souboru. Obnova je možná pouze při shodě velikosti a SHA-256; náhrada jiným zdrojem je samostatná výslovně potvrzená změna modelu. | Žádné tiché použití jiného souboru. Poškozený uložený model se nesmí přepsat jen pokusem o opravu. |
| **I7 Odkazy a změna zdroje** | Import má stabilní `id` jako jiné prvky. Stejný obsah s jiným názvem je stejný zdroj; výměna obsahu znamená nový původ geometrie. Navazující odkazy a měření při výměně nelze automaticky považovat za platné; NDT studie označit za zastaralé. | Hash určuje bajty zdroje, nikoli trvalou identitu jednotlivých ploch. Automatické přiřazení ploch po výměně není bezpečně zaručeno. |
| **I8 Verze a uložení** | Navrhuji formát **24**, otevření stávajících verzí 1–23 a zachování dnešního pravidla, že uložení zapíše aktuální verzi. Starší aplikace verzi 24 odmítne. Změna souboru musí být bezpečná při selhání zápisu a existující soubor se nesmí ztratit. | Jednoznačná kompatibilita, ale i model bez importu se po uložení novou verzí stane nečitelný pro staré sestavení, stejně jako u předchozích verzí. Bezpečné ukládání je nutné ověřit, dnešní `Document.save` zapisuje přímo do cíle. |
| **I9 Výběr a potvrzení** | Soubor před přijetím načíst a prověřit mimo hlavní vlákno; zobrazit rozměry, jednotky, počet těles, případná omezení a velikost uložené kopie. Teprve potvrzení vloží prvek jako jeden vratný krok; zrušení nezmění dokument. | Zachová kontrolu uživatele a běžnou funkci Zpět/Znovu. Podrobnosti služby a rozhraní patří do P3.3–P3.4. |

Příklad navrhovaného zápisu (zkrácený obsah a otisk jsou **ilustrativní**,
nejde o platný soubor):

```json
{
  "id": "import_1",
  "type": "step_import",
  "name": "Importovaný díl",
  "source_name": "priruba.step",
  "size_bytes": 12345,
  "sha256": "<64 malých hexadecimálních znaků>",
  "encoding": "base64",
  "data": "<úplný base64 obsah původního STEP>"
}
```

Při ukládání se `source_name` používá jen k zobrazení, nikdy jako cesta pro
čtení nebo zápis. Při poškození lze z původního souboru obnovit identické bajty;
když originál neexistuje a vložená kopie je poškozená, data nelze slíbit obnovit.
Záměrná výměna zdroje vyžaduje samostatné potvrzení a řešení neplatných vazeb;
není totožná s obnovou. Návrh nevytváří cache geometrie, která by se mohla
zaměnit za ověřený zdroj.

## Kritéria ověření pro implementaci

Následují požadavky na budoucí testy, nikoliv tvrzení, že už prošly:

1. Modely verzí 1–23 a stávající ukázky se nadále správně načtou. Starší
   aplikace verzi 24 odmítne; ověřit chování modelu bez importu po uložení.
2. Každý podporovaný vzorek P3.1 uložit, otevřít a přenést mezi Windows a macOS
   bez původního souboru. Porovnat SHA-256, počet těles, rozměry a objem ve
   schválených tolerancích; nepodporované vzorky odmítnout s důvodem.
3. Ověřit přesný limit, překročení limitu, chybný base64, nesouhlas délky a
   otisku, chybějící pole i neplatný STEP. Nepokračovat s neověřenými daty.
4. Obnovit chybějící obsah ze shodného souboru, odmítnout odlišný; cílenou
   výměnu testovat zvlášť, včetně vazeb, měření, NDT, Zpět/Znovu a opětovného
   otevření. Rizikové a nejednoznačné odkazy zastavit, ne hádat.
5. Přerušení výpočtu a zrušení náhledu nezmění model; simulovat selhání zápisu
   a ověřit, že původní soubor zůstane čitelný. Změření paměti a odezvy pro
   vstupy poblíž limitu provést na obou systémech před jeho konečným přijetím.
6. Jednotky INCH přepočítat na mm podle známých rozměrů; chybějící či sporné
   jednotky neodhadovat. Vzorky různých CAD systémů doplnit před přijetím P3.

## Rozhodnutí autora a hranice etapy

Ke schválení jsou doporučení **I1–I9**, zejména volba jednoho souboru, limit
16 MiB a verze formátu 24. Schválení návrhu není samo o sobě důkazem, že import
funguje; P3.3 musí před implementací rozpracovat diagnostiku, podporované typy,
bezpečný běh a zrušení. P3.4 řeší ovládání. P3.5 ověří celou cestu na obou
systémech. Odborná validace NDT zůstává samostatná.

## Pokračování po předání návrhu

Autor po předání odpověděl „ok, pokračuj“. Na tuto odpověď navazuje průzkum
P3.3 podle doporučení I1–I9. Nepovažuje se za souhlas se sloučením P3.1 ani
za přijetí implementace. Před implementací služby je nutné vyřešit její skutečné
chování při opravách geometrie a omezení výpočetních prostředků.
