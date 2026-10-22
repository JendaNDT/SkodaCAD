# P1.3 — postup ručního přijetí

**Stav: připraveno, autor zatím nepotvrdil žádný z následujících bodů.**
Schválení návrhu z 22. 10. 2026 ani přijetí P1.2B nenahrazuje tuto zkoušku.
Použít nové sestavení z implementačního PR P1.3; před zkouškou zaznamenat jeho
commit, platformu a odkaz na artefakt. Verzi otevřít přes Nápověda → O aplikaci.
Potvrzené kroky zapisovat až podle skutečné odpovědi autora.

Podklady: `modely-P1-3.zip`, šest receptů vytvořených z `tests/reference_documents.py`
a příruby z `examples/priruba.json`. Nejsou to nové vestavěné ukázky ani nový formát.
Recepty 02–05 jsou záměrně vadné; jejich chyba je očekávaný výsledek.
Originály ponechat a výsledky ukládat přes **Uložit jako** do vlastních kopií.
Geometricky správný díl může mít neplatné uložené měření či NDT oblast; zelená
geometrie sama nepotvrzuje platnost těchto záznamů.

| Soubor | Výchozí očekávání |
|---|---|
| `01-priruba.json` | Platná příruba, 1 těleso, 311 092,547330 mm³. |
| `02-hrany.json` | Kvádr 20 × 30 × 40, 24 000 mm³; `bad` odmítne dvě stejně blízké svislé hrany, `tail` přeskočen. |
| `03-plochy.json` | Dva kvádry, celkem 8 000 mm³; měření bez čísla, PT studie s chybnou vazbou. |
| `04-polomer.json` | Válec Ø 12 × 10, 1 130,973355 mm³; starý odkaz R5 je neplatný, měření bez čísla, PT oblast chybná. |
| `05-projekce.json` | Kvádr 24 000 mm³; skica `bad` odmítne nejednoznačnou projekci `r1`, vysunutí `tail` přeskočené. |
| `06-rez.json` | Deska 40 × 30 × 10 s průchozí dírou Ø 8; 11 497,345175 mm³, řez Y = 0 má 320 mm². |

## Vedený průchod

1. Otevřít správný nový balíček a zjistit sestavení. Otevřít přírubu, změnit `t`
   z 18 na 20. Navázané prvky a skupiny hran musí zůstat platné. Zpět/Znovu,
   Uložit jako a nové otevření kopie zachovají odpovídající stav a tloušťku.
2. Otevřít `02-hrany.json`. Ověřit českou chybu `bad`, přeskočený `tail`, ostré rohy
   a objem 24 000 mm³. Vybrat `bad` ve stromu, ve 3D přední pravou svislou hranu
   a z místní nabídky **Nahradit hrany vybraného prvku výběrem**. Zaoblení R3 musí
   změnit jen tento roh: 23 922,743339 mm³, 1 těleso, všechny prvky platné.
   Zpět vrátí chybu i 24 000 mm³; Znovu opravu. Kopii uložit a znovu otevřít.
3. Otevřít `03-plochy.json`, přepnout na Měření a NDT. Uložené měření musí mít
   vysvětlení nejednoznačnosti bez hodnoty, studie `Kontrolní oblast PT` chybnou vazbu.
   **Potvrdit pro aktuální díl** ji nesmí náhodně opravit (pro chybnou vazbu je tlačítko
   zakázané). Vybrat horní plochu levého kvádru, střed přibližně X = −60, a dát
   **Oblast z výběru**. Studie má nejprve zůstat zastaralá; teprve výslovné potvrzení
   ji opraví. Odborné ověření zůstává „Neověřeno.“ Staré měření se samo nepřepíše:
   smazat jej v seznamu uložených měření, na vybrané ploše uložit nové měření
   obsahu 400 mm². Ověřit historii a kopii po otevření.
4. Otevřít `04-polomer.json`. Ve 3D je Ø 12, staré měření však nemá vydávat jiné
   číslo za úspěch. Výslovně vybrat válcovou boční plochu, uložit nové měření
   průměru 12 mm a smazat vadné staré. Oblast PT změnit přes **Oblast z výběru**,
   pak samostatně potvrdit pro aktuální díl. Ověřit Zpět/Znovu a uloženou kopii.
5. Otevřít `05-projekce.json`. Musí se zobrazit chyba projekce `r1` a neprovést
   navazující vysunutí. Ve skicáři skici `bad` odstranit vadnou fialovou projekci,
   nástrojem **Promítnout** převzít horní přední vodorovnou hranu. Zachovat kružnici
   R1. Po potvrzení vysunutí přidá váleček výšky 2: 24 006,283185 mm³.
   Zpět/Znovu a kopie musí zachovat příslušný stav, staré body nesmějí potichu
   nahradit neplatnou projekci. Když se vadný prvek nepodaří v okně vybrat,
   zaznamenat přesně tento problém; nepovažovat automatickou opravu za ruční přijetí.
6. Otevřít `06-rez.json`, zapnout řez Y = 0. Zkusit vybrat skutečný zbytek původní
   horní plochy pro oblast PT: má se přenést na původní plochu. Zkusit místo ní
   umělou rovinnou stěnu vytvořenou řezem: vytvoření oblasti se musí odmítnout
   českým důvodem bez přepsání receptu či historie. Vypnout řez a ověřit celý díl.
   Řez zůstává pouze pohledem a neukládá se do receptu.

Každý bod lze rozdělit do kratších samostatně potvrzovaných zkoušek. Windows
ruční průchod a odborná NDT-17 nejsou nahrazené průchodem na Macu ani CI.
Zbytková historická identita R04 zůstává přiznaná podle [evidence](p1-3-overeni.md).
Po dokončení se vyžádá **samostatný pokyn ke sloučení implementačního PR**.
