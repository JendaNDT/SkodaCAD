# P4.2 — geometrie pohledů a řezu

Autor schválil doporučení V1–V9 v [návrhu P4.1](p4-1-navrh-vykresu.md).
Tato etapa připravuje výpočetní základ pro ortogonální pohledy a jeden řez;
nejde zatím o uživatelský výkres, ukládání, kótování ani export PDF/DXF listu.

## Souřadnice a měřítko

Všechny vrácené hrany jsou na rovině listu v milimetrech. Měřítko 1:2 je 0,5;
výsledné souřadnice jsou poloviční, fyzický díl se nemění. Směry odpovídají
3D prohlížeči: zepředu se dívá od −Y, shora od +Z a zprava od +X. Vodorovný
směr v prvních dvou pohledech je +X; v pravém +Y. Svisle je v čelním a pravém
pohledu +Z, v horním +Y. Při rozmístění na listu má být horní pohled pod čelním
a pravý vlevo, podle schváleného návrhu.

Řez může být kolmý na X, Y nebo Z, s polohou v mm a možností otočit stranu.
Po odříznutí části dílu se promítnou viditelné a skryté hrany zbývající části,
tedy i hrany za rovinou řezu. Šrafy se oříznou skutečnými plochami průřezu;
jejich rozteč je zadána v mm na listu a je stejná bez ohledu na měřítko.
Jejich počet a počet průsečíků má mez; výpočetně příliš složitý řez se odmítne.
Skrytá čára se ořízne v místech, kde splývá s viditelnou, aby nepřekreslila
plný obrys. Omezen je také počet porovnání hran; při překročení se výpočet zastaví.

## Ověřování a omezení

Testy kontrolují čelní, horní a pravý pohled nesouměrného kvádru a měřítko 1:2;
umístění excentrické kruhové díry, skryté hrany a jejich částečné překrytí,
řez přes otvor a šrafy mimo
dutinu; změnu strany řezu, neplatný vstup a geometrický díl z importu STEP.
Výsledky kontrol konkrétní revize jsou uvedeny v příslušném PR.

Jádro vrací geometrické hrany, nenavrhuje umístění kót ani výkresový list.
Správnost veškerých STEP modelů nebo shodu s normou nelze z několika testů
zaručit. P4.3 musí samostatně vyřešit ukládání a identitu kót; P4.4 list,
formát souboru a uživatelské ovládání. P4.5 vyžaduje ruční ověření exportu,
měřítka tisku a změn na obou operačních systémech.
