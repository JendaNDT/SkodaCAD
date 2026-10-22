# P1.2B — ruční přijetí na macOS a sloučení, 22. 10. 2026

**Výsledek: všech 17 vedených kontrolních bodů autor potvrdil.** Modelové zkoušky
proběhly 22. 10. 2026; spuštění nové aplikace a její označení sestavení autor
potvrdil v předchozím průchodu. Tato potvrzení jsou oddělená od automatických testů.

[Implementační PR #35](https://github.com/JendaNDT/SkodaCAD/pull/35) bylo po samostatném
pokynu autora **„ok, sluč to“** sloučené 22. 10. 2026 jako
`3a8deffca360da6ba412cd808837bff8f3ad1d10`. Sloučení bylo ověřené načtením `main`;
jeho strom je přesně shodný s otestovanou hlavou i ručně přijatým balíčkem.

## Sestavení a prostředí

- Autor potvrdil nové spuštění a údaj **f5caf402fac4 (2026-10-21)** v **Nápověda → O aplikaci**.
- Plný testovací commit balíčku: `f5caf402fac42c5c4f217ac75205b50372b85871`.
- Hlava PR: `c30dd09b505868595154e74354535ad6c21af289`; základ `cbf19b11a51955de7d409530dc59fea119e96897`.
- Testovací spojení i hlava mají stejný Git strom `c197eb0bdc7c10a1d2913d7a21f2fe807220fcad`.
- Sdílený Mac: **macOS 27.0.1, arm64, Apple M4, Mac16,12**. Údaje prostředí byly zjištěné bez sériového čísla a UUID.
- [Použitý macOS balíček](https://github.com/JendaNDT/SkodaCAD/actions/runs/39659723680/artifacts/12375566351).

## Potvrzené výsledky

| Zkouška | Výsledek potvrzený autorem |
|---|---|
| Pole — chyba, oprava a historie | Původní 2 otvory, 1 těleso, přibližně 79 874 mm³; chyba pole a přeskočená kontrolní skica, bez částečné třetí díry. Rozteč 20 → −20: 4 otvory, 79 749 mm³, úspěch. Zpět/Znovu vrací chybu/opravu. |
| Pole — soubory | Kopie `p1-2b-pole-opravene.json` po otevření zachová 4 otvory, 79 749 mm³ a úspěch. Originál po otevření stále 2 otvory, 79 874 mm³ a chyba; oba 1 těleso. |
| Zrcadlení — chyba, oprava a historie | Původní 2 otvory, 1 těleso, 79 874 mm³, chyba a přeskočená skica; bez částečné třetí díry. Posun roviny 20 → 0: 4 otvory, 79 749 mm³ a úspěch. Zpět/Znovu funguje. |
| Zrcadlení — soubory | Opravená kopie `p1-2b-zrcadleni-opravene.json` se úspěšně otevře se 4 otvory. Originál zachová původní 2 otvory a chybu. Ověřené odpovídající objemy a 1 těleso. |
| Příruba — rozměr a historie | Změna t=18 → 20 zesílí přírubu, 1 těleso, všechny prvky úspěšné. Zpět vrátí t=18, Znovu t=20. |
| Příruba — soubory | Otevřená kopie `p1-2b-priruba-upravena.json` má t=20, originál t=18. Oba 1 těleso a úspěšné prvky. |
| Tři trubky | Viditelné všechny 3 trubky, 3 tělesa, přibližně 96 496 mm³, všechny prvky úspěšné. Zprávy počtu těles 0 → 1 a 1 → 3 odpovídají očekávání ze souhrnu. |
| Zaoblení tří trubek | Poloměr 50 selže, kontrolní skica přeskočená, všechny 3 trubky zachované, 96 496 mm³. Poloměr 0.5 projde, zůstanou 3 tělesa, zpráva 3 → 3. Zpět/Znovu vrací chybu/opravu; opravená kopie `p1-2b-trubky-opravene.json` se uloží. |
| Zastavení výpočtu | Výchozí M5 bez vymodelovaného závitu, 1 těleso, přibližně 11 861 mm³. Po zaškrtnutí modelování závitu autor přerušil skutečně běžící přepočet. Zpráva „Přepočet zastaven“, volba se vrátí na vypnuto, původní deska zůstane. Ani po několika sekundách se neobjeví opuštěný výsledek. |
| Další práce po zastavení | Změna M5 → M6 s vypnutým modelováním závitu proběhne: 1 těleso, přibližně 11 804 mm³, všechny prvky úspěšné. Kopie `p1-2b-po-zastaveni.json` po otevření zachová M6, vypnutou volbu a stejný výsledek. |

Každý bod je podložený navazující odpovědí autora „to také sedí“, „ok“ nebo
„ok, to také funguje“ na konkrétní popsaný postup. Podrobný strojově čitelný záznam
17 bodů je `evidence/manual-acceptance-final.json` v příloze evidence.
Zprávy počtu těles byly potvrzené podle hodnot předložených ve vedených pokynech;
nejde o samostatné ruční potvrzení doslovného čtení celého CLI/offline textu.

## Automatické důkazy a meze

- Místní Ruff a celý pytest po každém ze tří kroků: B.1 1 279 / 415,02 s;
  B.2 1 300 / 414,59 s; B.3 **1 311 / 416,95 s**, bez přeskočení.
- [macOS 144](https://github.com/JendaNDT/SkodaCAD/actions/runs/39659723680): **1 311 testů / 989,912 s (JUnit)**, baseline, sestavení/podpis a self-test staženého balíčku OK.
- [Windows 185](https://github.com/JendaNDT/SkodaCAD/actions/runs/39659723383): **1 311 testů / 1 476,097 s (JUnit)**, baseline, sestavení, kontrola DLL a self-test staženého balíčku OK.
- Obě úlohy obou workflow jsou úspěšné. Otisky zdrojů/vstupů i sledované geometrické/NDT podpisy jsou ověřené. Automatické sloučení není zapnuté a Releases se z PR nezveřejnily.
- Ruční průchod potvrzuje výsledky v aplikaci. Skryté mapy operací a staré aliasy prokazují testy T01–T12; porovnání bajtů původních souborů nebylo po autorovi požadováno. U kopie zaoblení trubek bylo potvrzené uložení, nikoli samostatné nové otevření.
- Ruční Windows průchod ani odborná NDT-17 validace se neprohlašují za provedené. První snímky zamčené obrazovky byly vyřazené; platné nativní snímky vznikly po odemčení a byly vizuálně ověřené.

P1.2B je ověřené v rozsahu schválených B1–B7 a podporovaných cest. R05 lze v tomto
vymezení označit za vyřešené; nejde o záruku obnovy po libovolné nativní havárii nebo
chybě neznámého budoucího builderu. R01, R03, R04, R12 a odborná NDT-17 zůstávají
samostatně otevřené. P1.3–P1.5, P2, nový formát a NDT-16 nejsou tímto schválené.

**P1.2B je dokončené v popsaném rozsahu.** Následující
[návrh P1.3](p1-3-navrh-bezpecnych-referenci.md) čeká na schválení; nevzniká tím
povolení další implementace. Evidence CI výše patří kontrolám PR #35, nikoli
novému tvrzení o zveřejnění balíčku po sloučení.
