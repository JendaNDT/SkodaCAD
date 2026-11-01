# P7.13 – izolace vybraného dílu v sestavě

Datum: **1. 11. 2026**. Navazuje na rychlé pohledy P7.12.

## Ovládání

Vybrat díl ve stromu nebo ve 3D a použít **Izolovat** (I). Vybraná podsestava
zobrazí všechny své potomky. **Zobrazit vše** (Ctrl+Shift+I; na Macu Cmd+Shift+I)
vrátí celek. Oba příkazy jsou na liště a v nabídce Zobrazení.
Bez zobrazitelného dílu je izolace vypnutá; návrat je dostupný po dobu izolace.

Strom zůstává celý. Výběr jiného řádku sám nezmění izolaci; opakované Izolovat
ji přesměruje na novou komponentu. Rozhoduje cesta id od kořene, takže dvě kopie
stejného souboru lze izolovat nezávisle. Titulek ukazuje režim a počet viditelných
dílů. Souhrn navíc jmenuje komponentu a výslovně odděluje viditelnost od součtů
za celou sestavu.

Izolace i návrat vměstnají zobrazené díly a zachovají směr kamery. F v izolaci
nese název **Vměstnat** a přizpůsobí jen viditelnou geometrii. Číslice i I
v textovém poli dál zapisují znaky. Přepnutí nezahodí rozepsanou polohu ani
vzdálenost vazby. Výběr komponenty zůstává zachovaný, výběr ploch pro přidání
vazby se vyčistí, aby skrytá plocha nezůstala vstupem příkazu.

Zvýraznění komponent a nálezů používá jen viditelné kopie. Značka středu kolize
se ukazuje jen tehdy, jsou-li viditelné obě strany. Plochy vazeb se během izolace
nezvýrazňují; editor nabídne návrat přes Zobrazit vše. Tím zvýraznění neodkryje
skryté těleso. Po návratu se plochy vazby znovu zvýrazní.

## Životnost a data

Jde pouze o pohled okna. Recept, historie, příznak změny, součty, kontroly,
kusovník i export STEP stále pracují s úplným `AssemblyResult`. Filtr vytváří
jen zobrazovanou složeninu a nemění sdílená tělesa ani seznam kopií.

Úprava, Zpět/Znovu, přepočet i Uložit jako zachovají izolaci podle id. Při chybě
zdroje zůstane izolovaný pohled prázdný a návrat je dostupný. Odstranění cílové
komponenty izolaci ukončí. Úspěšné otevření nebo založení jiného dokumentu ji
vynuluje; zrušení dialogu či neúspěšné otevření původní pohled zachová.
Stav se neukládá do souboru ani do profilu. Formát a závislosti se nemění.

## Ověření

Regrese měří objem, počet těles a světovou obálku konkrétních kopií i vnořených
podsestav. Ověřují přesměrování izolace, odmítnutí skrytého výběru, práci s vazbou,
rozepsané hodnoty, historii, chybějící zdroj a odstranění komponenty. Uložení
zachová všech šest komponent a následný import STEP všech šest těles a jejich
celkový objem; otevření uložené kopie obnoví celý pohled.

Nativní self-test kontroluje všech šest ovládacích tlačítek při šířkách 1024/960.
Skutečným kliknutím izoluje víčko a ověří tvar AIS: 1 z 6 těles, jeho objem
a světovou obálku. F musí vměstnat vrcholy izolovaného dílu. Druhým tlačítkem
obnoví 6 z 6 těles a původní objem. Kamera, výběr, recept, historie a rozepsané
pole se kontrolují před i po přepnutí.

Místní protokoly a snímky patří do `out/p7-assembly-isolation/`; úplné výsledky
macOS/Windows a stažených balíčků do implementačního PR. P7.4 (autorská přejímka)
zůstává otevřená.
