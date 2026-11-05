# Kolejka wyjątków magazynowych dla Odoo 19

Bezpłatny moduł pokazuje ujemną ilość wolną, ilość wolną poniżej minimum reguły uzupełniania oraz zero obserwowane przez wybraną liczbę dni. Wymaga tylko Magazynu (`stock`). Nie zmienia stanów magazynowych i nie tworzy zamówień.

## Konfiguracja

1. Zainstaluj moduł i otwórz **Magazyn → Wyjątki magazynowe → Zakresy skanowania**.
2. Administrator magazynu tworzy zakres dla firmy, magazynu i lokalizacji wewnętrznej pod główną lokalizacją magazynu. Skan obejmuje tę lokalizację i jej podlokalizacje wewnętrzne, najwyżej 50 lokalizacji łącznie. **Dni z zerem** oznaczają czas od pierwszej obserwacji zera przez moduł; `0` oznacza alarm przy drugim kolejnym skanie z zerem.
3. Klikaj **Skanuj kolejną partię**, aż stan będzie **Bezczynny** i data ostatniego skanu będzie aktualna. Jedno kliknięcie obejmuje maksymalnie 200 produktów w najwyżej 50 lokalizacjach. Zadanie automatyczne uruchamia się co pięć minut i skanuje jedną partię zakresu obsłużonego najdawniej; pole **Ostatnia partia** pokazuje rotację. Duży katalog lub wiele zakresów może wymagać ręcznych skanów, aby skończyć w ciągu dnia.
4. Otwórz **Magazyn → Wyjątki magazynowe → Kolejka wyjątków**. Użytkownicy magazynu mogą ją czytać; administratorzy zarządzają zakresami i skanują.

Kolejka domyślnie pokazuje wagę, produkt, lokalizację, zakres, ilość wolną, minimum, ostatni skan i nieaktualność. Pozostałe pola, w tym stan, rezerwacje i pierwsze zero, są dostępne w wyborze kolumn oraz formularzu wiersza. Lista zakresów również pokazuje nieaktualność.

## Znaczenie danych

**Stan** to suma ilości w kwantach danej lokalizacji. **Zarezerwowano** to suma rezerwacji. **Ilość wolna** to stan minus rezerwacje w podstawowej jednostce produktu. **Minimum reguły** pochodzi z aktywnej reguły uzupełniania dla dokładnie tego produktu i lokalizacji. Dane nie są prognozą: moduł nie uwzględnia przyszłych ruchów. Wyklucza kwanty należące do innego właściciela i sumuje partie oraz opakowania. Produkt bez kwantu i bez reguły nie jest kandydatem.

**Trwałe zero** liczy się od pierwszego skanu, w którym moduł zobaczył zero. Nie jest odtwarzane z historii ruchów. Flaga **Zero utrzymuje się** pozostaje widoczna także wtedy, gdy główną wagą jest **Poniżej minimum**. **Nieaktualne wyniki** oznaczają brak ukończonego skanu, skan w toku lub skan starszy niż 36 godzin. Błąd zadania dziennego jest widoczny na zakresie; po naprawieniu przyczyny uruchom skan ponownie.

Produkty firmy nadrzędnej są uwzględniane w magazynie firmy podrzędnej, gdy pozwalają na to reguły Odoo. Zakresy mogą się nakładać, więc ta sama para produkt/lokalizacja może pojawić się pod dwoma zakresami. Zadanie udostępnia do 288 partii dziennie dla wszystkich zakresów. Moduł nie koryguje stanów, nie rezerwuje, nie zamawia i nie analizuje terminów ważności. Wersja Enterprise nie została jeszcze sprawdzona.
